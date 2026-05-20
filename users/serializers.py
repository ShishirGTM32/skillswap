from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .email_service import send_otp_email
from .models import DesiredSkill, Skill
from .redis_otp import OtpPurpose, generate_numeric_otp, store_otp

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=255)
    last_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value.strip()).exists():
            raise ValidationError("An account with this email already exists.")
        return value.strip().lower()
    
    def validate_username(self, value):
        if User.objects.filter(username__iexact=value.strip()).exists():
            raise ValidationError("An account with this username already exists.")
        return value.strip().lower()

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise ValidationError("Password and confirm password do not match.")
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password", None)
        return User.objects.create_user(
            username = validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"].strip(),
            last_name=validated_data["last_name"].strip(),
            is_active=False,
            email_verified=False,
            deactivated_by_admin=False,
        )


class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise ValidationError("New password and confirm password do not match.")
        return attrs


class OtpPurposeField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(choices=["activate", "password_reset"], **kwargs)


class ResendOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = OtpPurposeField()


class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=4, max_length=12)
    purpose = serializers.CharField()

    def validate(self, values):
        if not values["purpose"]:
            raise ValidationError("Purpose is required.")
        return values
    def validate_otp(self, value):
        if not value:
            raise ValidationError("OTP is required.")
        return value
    def validate_email(self, value):
        if not value:
            raise ValidationError("Email is required.")
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ("id", "name", "description", "proficiency_percent")
        read_only_fields = ("id",)

    def validate_name(self, value):
        user = self.context["request"].user

        if Skill.objects.filter(
            user=user,
            name__iexact=value
        ).exists():
            raise serializers.ValidationError(
                "Skill with this name already exists."
            )

        return value


class SkillListSerializer(serializers.Serializer):
    skills = SkillSerializer(many=True)

    def validate_skills(self, value):
        if len(value) > 10:
            raise serializers.ValidationError(
                "You can add a maximum of 10 skills."
            )

        names = [item["name"].strip().lower() for item in value]

        if len(names) != len(set(names)):
            raise serializers.ValidationError(
                "Skill names must be unique."
            )

        return value

    def create(self, validated_data):
        user = self.context["request"].user
        skills_data = validated_data["skills"]

        skills = [
            Skill(
                user=user,
                name=item["name"],
                description=item.get("description", ""),
                proficiency_percent=item.get("proficiency_percent", 0),
            )
            for item in skills_data
        ]

        return Skill.objects.bulk_create(skills)


class SkillPatchItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = Skill
        fields = ("id", "name", "description", "proficiency_percent")
        extra_kwargs = {
            "description": {"required": False, "allow_blank": True},
            "proficiency_percent": {"required": False},
        }

    def validate(self, attrs):
        user = self.context["request"].user
        pk = attrs.get("id")
        if pk is not None and not Skill.objects.filter(pk=pk, user=user).exists():
            raise serializers.ValidationError({"id": "Skill not found."})
        return attrs


class SkillListPatchSerializer(serializers.Serializer):
    skills = SkillPatchItemSerializer(many=True)

    def validate_skills(self, value):
        user = self.context["request"].user
        if len(value) > 10:
            raise serializers.ValidationError(
                "You can add a maximum of 10 skills."
            )

        names = [item["name"].strip().lower() for item in value]
        if len(names) != len(set(names)):
            raise serializers.ValidationError(
                "Skill names must be unique."
            )

        payload_ids = {item["id"] for item in value if item.get("id") is not None}
        existing = set(user.skills.values_list("pk", flat=True))
        unknown = payload_ids - existing
        if unknown:
            raise serializers.ValidationError("Invalid skill id.")

        del_ids = existing - payload_ids
        for item in value:
            iid = item.get("id")
            name = item["name"].strip()
            qs = Skill.objects.filter(user=user, name__iexact=name)
            if iid is not None:
                qs = qs.exclude(pk=iid)
            qs = qs.exclude(pk__in=del_ids)
            if qs.exists():
                raise serializers.ValidationError(
                    "Skill with this name already exists."
                )

        return value

    @transaction.atomic
    def sync(self, user):
        skills_data = self.validated_data["skills"]
        payload_ids = {item["id"] for item in skills_data if item.get("id") is not None}
        user.skills.exclude(pk__in=payload_ids).delete()
        for item in skills_data:
            pk = item.get("id")
            defaults = {
                "name": item["name"].strip(),
                "description": item.get("description") or "",
                "proficiency_percent": item.get("proficiency_percent", 0),
            }
            if pk is not None:
                Skill.objects.filter(pk=pk, user=user).update(**defaults)
            else:
                Skill.objects.create(user=user, **defaults)


class DesiredSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = DesiredSkill
        fields = ("id", "name", "description", "order")
        read_only_fields = ("id", "order")

    def validate_name(self, value):
        user = self.context["request"].user
        if DesiredSkill.objects.filter(user=user, name__iexact=value).exists():
            raise serializers.ValidationError(
                "Skill with this name already exists."
            )
        return value


class DesiredSkillListSerializer(serializers.Serializer):
    skills = DesiredSkillSerializer(many=True)

    def validate_skills(self, value):
        if len(value) > 10:
            raise serializers.ValidationError(
                "You can add a maximum of 10 skills."
            )

        names = [item["name"].strip().lower() for item in value]
        if len(names) != len(set(names)):
            raise serializers.ValidationError(
                "Skill names must be unique."
            )

        return value

    def create(self, validated_data):
        user = self.context["request"].user
        skills_data = validated_data["skills"]

        skills = [
            DesiredSkill(
                user=user,
                name=item["name"],
                description=item.get("description", ""),
                order=index,
            )
            for index, item in enumerate(skills_data)
        ]

        return DesiredSkill.objects.bulk_create(skills)


class DesiredSkillPatchItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = DesiredSkill
        fields = ("id", "name", "description")
        extra_kwargs = {
            "description": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        user = self.context["request"].user
        pk = attrs.get("id")
        if pk is not None and not DesiredSkill.objects.filter(pk=pk, user=user).exists():
            raise serializers.ValidationError({"id": "Skill not found."})
        return attrs


class DesiredSkillListPatchSerializer(serializers.Serializer):
    skills = DesiredSkillPatchItemSerializer(many=True)

    def validate_skills(self, value):
        user = self.context["request"].user
        if len(value) > 10:
            raise serializers.ValidationError(
                "You can add a maximum of 10 skills."
            )

        names = [item["name"].strip().lower() for item in value]
        if len(names) != len(set(names)):
            raise serializers.ValidationError(
                "Skill names must be unique."
            )

        payload_ids = {item["id"] for item in value if item.get("id") is not None}
        existing = set(user.desired_skills.values_list("pk", flat=True))
        unknown = payload_ids - existing
        if unknown:
            raise serializers.ValidationError("Invalid skill id.")

        del_ids = existing - payload_ids
        for item in value:
            iid = item.get("id")
            name = item["name"].strip()
            qs = DesiredSkill.objects.filter(user=user, name__iexact=name)
            if iid is not None:
                qs = qs.exclude(pk=iid)
            qs = qs.exclude(pk__in=del_ids)
            if qs.exists():
                raise serializers.ValidationError(
                    "Skill with this name already exists."
                )

        return value

    @transaction.atomic
    def sync(self, user):
        skills_data = self.validated_data["skills"]
        payload_ids = {item["id"] for item in skills_data if item.get("id") is not None}
        user.desired_skills.exclude(pk__in=payload_ids).delete()
        for index, item in enumerate(skills_data):
            pk = item.get("id")
            defaults = {
                "name": item["name"].strip(),
                "description": item.get("description") or "",
                "order": index,
            }
            if pk is not None:
                DesiredSkill.objects.filter(pk=pk, user=user).update(**defaults)
            else:
                DesiredSkill.objects.create(user=user, **defaults)


class ProfileSerializer(serializers.ModelSerializer):
    completion_percent = serializers.ReadOnlyField()
    updated_at = serializers.DateTimeField(source="profile_updated_at", read_only=True)
    skills = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "avatar",
            "bio",
            "completion_percent",
            "updated_at",
            "skills",
        )
        read_only_fields = ("completion_percent", "updated_at")
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')

        if instance.avatar and request:
            data['avatar'] = request.build_absolute_uri(instance.avatar.url)
            # data['image'] = instance.image.url
        else:
            data['avatar'] = None

        return data

    def validate_avatar(self, value):
        if value and getattr(value, "size", 0) > 5 * 1024 * 1024:
            raise ValidationError("Image must be 5 MB or smaller.")
        return value

    def get_skills(self, obj):
        if not obj.skills.exists():
            return None
        return SkillSerializer(obj.skills, many=True).data


class UserMeSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "email_verified",
            "deactivated_by_admin",
            "admin_deactivated_at",
            "deactivated_by",
            "profile",
        )
        read_only_fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "email_verified",
            "deactivated_by_admin",
            "admin_deactivated_at",
            "deactivated_by",
        )

    def get_profile(self, obj):
        return ProfileSerializer(obj).data


class UserLoginSerializer(serializers.Serializer):

    email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def _issue_activation_otp(self, user: User) -> None:
        otp = generate_numeric_otp()
        store_otp(OtpPurpose.ACTIVATE, user.email, otp)
        send_otp_email(
            to_email=user.email,
            otp=otp,
            subject="Verify your SkillSwap account",
            intro="Welcome! Use this code to activate your account.",
            recipient_name=f"{user.first_name} {user.last_name}",
            heading="Email Verification",
            instruction="Please use the OTP below to verify your email address:",
        )

    def validate(self, data):
        identifier = (data.get("email") or "").strip()
        password = data.get("password") or ""

        if not identifier:
            raise ValidationError("Email/username is required.")
        if not password:
            raise ValidationError("Password is required.")

        user = User.objects.filter(
            Q(email__iexact=identifier) | Q(username__iexact=identifier)
        ).first()
        if not user:
            raise ValidationError("Account not found")

        if user.deactivated_by_admin:
            raise ValidationError("Account is disabled")

        if not user.is_active or not user.email_verified:
            if not user.check_password(password):
                raise ValidationError("Invalid password")
            self._issue_activation_otp(user)
            return {"needs_activation": True, "email": user.email}

        if not user.check_password(password):
            raise ValidationError("Invalid password")

        now = timezone.now()
        user.last_login = now
        user.save(update_fields=["last_login"])

        return user

