"""Document ingestion: PDF load, chunk, embed, persist."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from django.conf import settings
from pypdf import PdfReader

from apps.accounts.models import Account
from apps.documents.embeddings import embed_texts
from apps.documents.models import (
    ChunkStatus,
    DocumentChunk,
    DocumentStatus,
    ScopeType,
    SourceDocument,
    SourceType,
)


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    # Normalize weird PDF spacing
    text = "\n".join(parts)
    # PDF often emits one word per line — rejoin into readable paragraphs
    lines = [ln.strip() for ln in text.splitlines()]
    merged: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if not ln:
            if buf:
                merged.append(" ".join(buf))
                buf = []
            continue
        if ln.startswith("●") or re.match(r"^\d+\.", ln):
            if buf:
                merged.append(" ".join(buf))
                buf = []
            merged.append(ln)
            continue
        buf.append(ln)
    if buf:
        merged.append(" ".join(buf))
    text = "\n\n".join(merged)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        # prefer break on paragraph/sentence
        if end < len(text):
            break_at = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
            if break_at > start + chunk_size // 3:
                end = break_at + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = max(end - overlap, end) if end > start else end + 1
    return chunks


def detect_known_issue_chunks(content: str) -> dict:
    meta: dict = {}
    ki = re.search(r"(KI-\d+)\s*[-–]\s*([^\n]+)", content)
    if ki:
        meta["known_issue_id"] = ki.group(1)
        meta["section_title"] = ki.group(0).strip()
    status_match = re.search(
        r"Status:\s*(Investigating|Monitoring|Resolved|Active)",
        content,
        re.IGNORECASE,
    )
    if status_match:
        meta["known_issue_status"] = status_match.group(1).upper()
        meta["chunk_status"] = status_match.group(1).upper()
    return meta


SEED_DOCUMENTS = [
    {
        "filename": "01_Support_Policy_v3_CURRENT.pdf",
        "name": "ParcelPilot Support Policy v3",
        "source_type": SourceType.POLICY_SOP,
        "status": DocumentStatus.CURRENT,
        "authority_level": 80,
        "scope_type": ScopeType.GENERAL,
        "account_code": None,
        "effective_date": date(2026, 5, 1),
        "expiry_date": None,
        "explicit_override_domains": [],
        "domains": ["SUPPORT", "SLA"],
    },
    {
        "filename": "02_Support_Policy_v2_DEPRECATED.pdf",
        "name": "ParcelPilot Support Policy v2",
        "source_type": SourceType.DEPRECATED,
        "status": DocumentStatus.DEPRECATED,
        "authority_level": 0,
        "scope_type": ScopeType.GENERAL,
        "account_code": None,
        "effective_date": date(2025, 1, 1),
        "expiry_date": date(2026, 4, 30),
        "explicit_override_domains": [],
        "domains": ["SUPPORT", "SLA"],
    },
    {
        "filename": "03_Cancellation_and_Service_Credit_SOP_v4.pdf",
        "name": "Cancellation & Service Credit SOP v4",
        "source_type": SourceType.POLICY_SOP,
        "status": DocumentStatus.CURRENT,
        "authority_level": 80,
        "scope_type": ScopeType.GENERAL,
        "account_code": None,
        "effective_date": date(2026, 6, 15),
        "expiry_date": None,
        "explicit_override_domains": [],
        "domains": ["CANCELLATION", "SERVICE_CREDIT"],
    },
    {
        "filename": "04_Product_Operations_Guide_and_Known_Issues.pdf",
        "name": "Product Operations Guide and Known Issues",
        "source_type": SourceType.PRODUCT_DOC,
        "status": DocumentStatus.CURRENT,
        "authority_level": 70,
        "scope_type": ScopeType.PRODUCT,
        "account_code": None,
        "effective_date": date(2026, 8, 14),
        "expiry_date": None,
        "explicit_override_domains": [],
        "domains": ["PRODUCT", "KNOWN_ISSUE", "BULK_UPLOAD", "STATUS"],
    },
    {
        "filename": "05_Northstar_Logistics_Enterprise_Agreement.pdf",
        "name": "Northstar Logistics Enterprise Agreement",
        "source_type": SourceType.CUSTOMER_AGREEMENT,
        "status": DocumentStatus.ACTIVE,
        "authority_level": 100,
        "scope_type": ScopeType.CUSTOMER_SPECIFIC,
        "account_code": "ACCT-001",
        "effective_date": date(2026, 1, 1),
        "expiry_date": date(2026, 12, 31),
        "explicit_override_domains": ["CANCELLATION", "SLA", "SUPPORT"],
        "domains": ["CANCELLATION", "SERVICE_CREDIT", "SLA", "SUPPORT"],
    },
    {
        "filename": "06_LumenWorks_Service_Agreement.pdf",
        "name": "LumenWorks Service Agreement",
        "source_type": SourceType.CUSTOMER_AGREEMENT,
        "status": DocumentStatus.ACTIVE,
        "authority_level": 100,
        "scope_type": ScopeType.CUSTOMER_SPECIFIC,
        "account_code": "ACCT-002",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "explicit_override_domains": ["SERVICE_CREDIT", "SLA", "SUPPORT"],
        "domains": ["CANCELLATION", "SERVICE_CREDIT", "SLA", "SUPPORT"],
    },
]


def ingest_file(
    path: Path,
    *,
    name: str,
    source_type: str,
    status: str,
    authority_level: int,
    scope_type: str,
    account: Account | None = None,
    effective_date: date | None = None,
    expiry_date: date | None = None,
    supersedes: SourceDocument | None = None,
    explicit_override_domains: list[str] | None = None,
    domains: list[str] | None = None,
) -> SourceDocument:
    text = extract_pdf_text(path) if path.suffix.lower() == ".pdf" else path.read_text(encoding="utf-8", errors="ignore")
    media_dir = Path(settings.MEDIA_ROOT) / "documents"
    media_dir.mkdir(parents=True, exist_ok=True)
    dest = media_dir / path.name
    if path.resolve() != dest.resolve():
        dest.write_bytes(path.read_bytes())

    doc = SourceDocument.objects.create(
        name=name,
        source_type=source_type,
        status=status,
        authority_level=authority_level,
        scope_type=scope_type,
        account=account,
        effective_date=effective_date,
        expiry_date=expiry_date,
        supersedes_document=supersedes,
        explicit_override_domains=explicit_override_domains or [],
        file_path=str(dest),
        original_filename=path.name,
    )

    pieces = chunk_text(text)
    embeddings = embed_texts(pieces)
    for i, (piece, emb) in enumerate(zip(pieces, embeddings)):
        ki_meta = detect_known_issue_chunks(piece)
        DocumentChunk.objects.create(
            document=doc,
            content=piece,
            embedding=emb,
            section_title=ki_meta.get("section_title", ""),
            page_reference=str(i + 1),
            chunk_status=ki_meta.get("chunk_status", ChunkStatus.ACTIVE),
            known_issue_status=ki_meta.get("known_issue_status", ""),
            known_issue_id=ki_meta.get("known_issue_id", ""),
            domain=(domains[0] if domains else ""),
            chunk_effective_date=effective_date,
            chunk_expiry_date=expiry_date,
            metadata={"domains": domains or [], **ki_meta},
        )
    return doc


def seed_documents(docs_dir: Path | None = None) -> list[SourceDocument]:
    docs_dir = docs_dir or Path(settings.DOCS_DIR)
    created: list[SourceDocument] = []
    by_name: dict[str, SourceDocument] = {}
    for spec in SEED_DOCUMENTS:
        path = docs_dir / spec["filename"]
        if not path.exists():
            continue
        account = None
        if spec["account_code"]:
            account = Account.objects.filter(account_code=spec["account_code"]).first()
        doc = ingest_file(
            path,
            name=spec["name"],
            source_type=spec["source_type"],
            status=spec["status"],
            authority_level=spec["authority_level"],
            scope_type=spec["scope_type"],
            account=account,
            effective_date=spec["effective_date"],
            expiry_date=spec["expiry_date"],
            explicit_override_domains=spec["explicit_override_domains"],
            domains=spec["domains"],
        )
        by_name[spec["filename"]] = doc
        created.append(doc)

    # Link supersedes: v3 supersedes v2
    v3 = by_name.get("01_Support_Policy_v3_CURRENT.pdf")
    v2 = by_name.get("02_Support_Policy_v2_DEPRECATED.pdf")
    if v3 and v2:
        v3.supersedes_document = v2
        v3.save(update_fields=["supersedes_document"])
    return created
