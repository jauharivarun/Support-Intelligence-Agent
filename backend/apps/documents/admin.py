from django.contrib import admin

from .models import DocumentChunk, SourceDocument


class ChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    fields = ("section_title", "chunk_status", "known_issue_id", "domain")
    readonly_fields = fields


@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "status", "authority_level", "account")
    list_filter = ("source_type", "status", "scope_type")
    inlines = [ChunkInline]
