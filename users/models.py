from enum import unique
import secrets
from turtle import Turtle

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def user_avatar_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    return f"avatars/{instance.pk}/{secrets.token_hex(8)}.{ext}"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, password, **extra_fields):
        if not username:
            raise ValueError("Username must be set")
        email = extra_fields.pop("email", None)
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("email_verified", False)
        extra_fields.setdefault("deactivated_by_admin", False)
        return self._create_user(username, password, **extra_fields)

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("email_verified", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("deactivated_by_admin", False)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(username, password, **extra_fields)


class User(AbstractUser):
    username = models.CharField(unique=True, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    email_verified = models.BooleanField(default=False, db_index=True)
    deactivated_by_admin = models.BooleanField(
        default=False,
        db_index=True,
        help_text="When True, staff deactivated this account; login and most actions are blocked.",
    )
    admin_deactivated_at = models.DateTimeField(null=True, blank=True)
    avatar = models.ImageField(upload_to=user_avatar_upload_to, blank=True, null=True)
    bio = models.TextField(blank=True)
    profile_updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.username

    def clean(self):
        super().clean()
        if self.avatar and hasattr(self.avatar, "file") and self.avatar.size > 5 * 1024 * 1024:
            raise ValidationError({"avatar": "Image must be 5 MB or smaller."})

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar and self.avatar.name)

    @property
    def has_skills(self) -> bool:
        return self.skills.exists()

    @property
    def completion_percent(self) -> int:
        score = 0
        if self.has_avatar:
            score += 30
        if self.has_skills:
            score += 70
        return score

    @property
    def is_profile_complete(self) -> bool:
        return self.completion_percent == 100


class Skill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    proficiency_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="How good you are at this skill, from 0 to 100 percent.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class DesiredSkill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="desired_skills")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Priority order; lower values appear first.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_desired_skill_name_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"
