from rest_framework import serializers

from apps.accounts.models import Account
from apps.documents.models import SourceDocument


class SourceDocumentSerializer(serializers.ModelSerializer):
    account_code = serializers.SerializerMethodField()
    chunk_count = serializers.IntegerField(source="chunks.count", read_only=True)

    class Meta:
        model = SourceDocument
        fields = [
            "id",
            "name",
            "source_type",
            "status",
            "authority_level",
            "scope_type",
            "account_code",
            "effective_date",
            "expiry_date",
            "explicit_override_domains",
            "original_filename",
            "chunk_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "original_filename",
            "chunk_count",
            "created_at",
            "updated_at",
        ]

    def get_account_code(self, obj) -> str | None:
        if not obj.account_id:
            return None
        return obj.account.account_code


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    name = serializers.CharField(max_length=255)
    source_type = serializers.CharField(max_length=64)
    status = serializers.CharField(max_length=32)
    authority_level = serializers.IntegerField()
    scope_type = serializers.CharField(max_length=32)
    account_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    effective_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    explicit_override_domains = serializers.CharField(
        required=False, allow_blank=True, help_text="Comma-separated domains"
    )

    def create_document(self):
        from pathlib import Path
        from django.conf import settings
        from apps.documents.ingestion import ingest_file

        data = self.validated_data
        upload = data["file"]
        media_dir = Path(settings.MEDIA_ROOT) / "uploads"
        media_dir.mkdir(parents=True, exist_ok=True)
        dest = media_dir / upload.name
        with dest.open("wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)

        account = None
        code = data.get("account_code")
        if code:
            account = Account.objects.filter(account_code=code).first()

        domains = []
        raw = data.get("explicit_override_domains") or ""
        if raw:
            domains = [d.strip().upper() for d in raw.split(",") if d.strip()]

        return ingest_file(
            dest,
            name=data["name"],
            source_type=data["source_type"],
            status=data["status"],
            authority_level=data["authority_level"],
            scope_type=data["scope_type"],
            account=account,
            effective_date=data.get("effective_date"),
            expiry_date=data.get("expiry_date"),
            explicit_override_domains=domains,
            domains=domains or None,
        )


DocumentUploadSerializer = DocumentUploadSerializer
