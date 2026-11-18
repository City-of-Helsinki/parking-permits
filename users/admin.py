from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from users.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if settings.LOCAL_ADMIN_ROLES_ENABLED and not request.user.is_superuser:
            return (
                *readonly_fields,
                "groups",
                "user_permissions",
                "is_staff",
                "is_superuser",
            )
        return readonly_fields
