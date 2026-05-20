from django.contrib import admin

from .models import SwapRequest


@admin.register(SwapRequest)
class SwapRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "requester",
        "recipient",
        "offered_skill",
        "requested_skill",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "requester__email",
        "requester__username",
        "recipient__email",
        "recipient__username",
    )
    readonly_fields = ("created_at", "updated_at")
