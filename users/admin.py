from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import DesiredSkill, Skill, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "email_verified",
        "is_active",
        "date_joined",
    )
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("last_login", "date_joined", "profile_updated_at")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            "Profile",
            {"fields": ("avatar", "bio", "profile_updated_at")},
        ),
        (
            "Status",
            {
                "fields": (
                    "email_verified",
                    "is_active",
                    "deactivated_by_admin",
                    "admin_deactivated_at",
                    "deactivated_by",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "username" in form.base_fields:
            del form.base_fields["username"]
        return form


@admin.register(DesiredSkill)
class DesiredSkillAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "order")
    list_filter = ("user",)
    ordering = ("order", "name")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "proficiency_percent")
    list_filter = ()
