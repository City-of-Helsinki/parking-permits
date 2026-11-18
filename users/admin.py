from django.conf import settings
from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

from users.models import User

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    def user_change_password(self, request, id, form_url=""):
        if not request.user.is_superuser:
            user = self.get_object(request, unquote(id))
            if user is not None and user.is_superuser:
                raise PermissionDenied
        return super().user_change_password(request, id, form_url)

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
