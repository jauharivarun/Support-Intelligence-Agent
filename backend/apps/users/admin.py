from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("email", "name", "role", "account", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("ParcelPilot", {"fields": ("role", "account", "name")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("ParcelPilot", {"fields": ("email", "role", "account", "name")}),
    )
    search_fields = ("email", "name", "username")
    ordering = ("email",)
