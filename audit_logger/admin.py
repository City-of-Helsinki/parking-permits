import json
import logging

from django.contrib import admin
from django.utils.html import format_html

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("colored_msg", "operation", "status", "create_datetime_format")
    list_display_links = ("colored_msg",)
    list_filter = ("level",)
    list_per_page = 10
    readonly_fields = (
        "created_at",
        "level",
        "is_sent",
        "message_format",
        "traceback_format",
    )

    @admin.display(description="Message")
    def colored_msg(self, instance):
        if instance.level in [logging.NOTSET, logging.INFO]:
            color = "green"
        elif instance.level in [logging.WARNING, logging.DEBUG]:
            color = "orange"
        else:
            color = "red"
        return format_html(
            '<span style="color: {color};">{msg}</span>',
            color=color,
            msg=instance.message["message"],
        )

    @admin.display(description="Created at")
    def create_datetime_format(self, instance):
        return instance.created_at.strftime("%Y-%m-%d %X")

    @admin.display(description="Message")
    def message_format(self, instance):
        return format_html(
            "<pre>{msg}</pre>",
            msg=json.dumps(instance.message, indent=4, sort_keys=True),
        )

    @admin.display(description="Traceback")
    def traceback_format(self, instance):
        return format_html(
            "<pre>{traceback}</pre>",
            traceback=instance.trace or "",
        )

    @admin.display(description="Status")
    def status(self, instance):
        status = instance.message.get("status", None)
        return status or "-"

    @admin.display(description="Operation")
    def operation(self, instance):
        operation = instance.message.get("operation", None)
        return operation or "-"

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
