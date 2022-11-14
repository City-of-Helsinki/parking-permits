import json
import logging

from django.contrib import admin
from django.utils.html import format_html

from .models import AuditLog


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

    colored_msg.short_description = "Message"

    def create_datetime_format(self, instance):
        return instance.created_at.strftime("%Y-%m-%d %X")

    create_datetime_format.short_description = "Created at"

    def message_format(self, instance):
        return format_html(
            "<pre>{msg}</pre>",
            msg=json.dumps(instance.message, indent=4, sort_keys=True),
        )

    message_format.short_description = "Message"

    def traceback_format(self, instance):
        return format_html(
            "<pre>{traceback}</pre>",
            traceback=instance.trace or "",
        )

    traceback_format.short_description = "Traceback"

    def status(self, instance):
        status = instance.message.get("status", None)
        return status or "-"

    status.short_description = "Status"

    def operation(self, instance):
        operation = instance.message.get("operation", None)
        return operation or "-"

    operation.short_description = "Operation"

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(AuditLog, AuditLogAdmin)
