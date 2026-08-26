from django.db import models


class SourceType(models.TextChoices):
    CUSTOMER_AGREEMENT = "CUSTOMER_AGREEMENT", "Customer Agreement"
    POLICY_SOP = "POLICY_SOP", "Policy / SOP"
    PRODUCT_DOC = "PRODUCT_DOC", "Product Documentation"
    HISTORICAL_CONTEXT = "HISTORICAL_CONTEXT", "Historical Tickets / Notes"
    DEPRECATED = "DEPRECATED", "Deprecated"


class DocumentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    CURRENT = "CURRENT", "Current"
    DEPRECATED = "DEPRECATED", "Deprecated"
    CONTEXT_ONLY = "CONTEXT_ONLY", "Context Only"


class ScopeType(models.TextChoices):
    CUSTOMER_SPECIFIC = "CUSTOMER_SPECIFIC", "Customer Specific"
    GENERAL = "GENERAL", "General"
    PRODUCT = "PRODUCT", "Product / Domain"


class ChunkStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    RESOLVED = "RESOLVED", "Resolved"
    MONITORING = "MONITORING", "Monitoring"
    INVESTIGATING = "INVESTIGATING", "Investigating"
    HISTORICAL = "HISTORICAL", "Historical"


class SourceDocument(models.Model):
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=64, choices=SourceType.choices)
    status = models.CharField(max_length=32, choices=DocumentStatus.choices)
    authority_level = models.IntegerField(default=0)
    scope_type = models.CharField(max_length=32, choices=ScopeType.choices, default=ScopeType.GENERAL)
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    effective_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    supersedes_document = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_by",
    )
    explicit_override_domains = models.JSONField(default=list, blank=True)
    file_path = models.CharField(max_length=512, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-authority_level", "name"]

    def __str__(self):
        return f"{self.name} [{self.status}/{self.authority_level}]"


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        SourceDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    content = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    section_title = models.CharField(max_length=255, blank=True)
    page_reference = models.CharField(max_length=64, blank=True)
    chunk_status = models.CharField(
        max_length=32, choices=ChunkStatus.choices, default=ChunkStatus.ACTIVE
    )
    known_issue_status = models.CharField(max_length=32, blank=True)
    known_issue_id = models.CharField(max_length=64, blank=True)
    domain = models.CharField(max_length=128, blank=True)
    chunk_effective_date = models.DateField(null=True, blank=True)
    chunk_expiry_date = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Chunk {self.id} of {self.document_id}"
