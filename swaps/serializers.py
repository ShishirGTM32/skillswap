from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from users.models import Skill

from .models import SwapRequest
from .services import eligible_swap_users

User = get_user_model()


class SwapRequestCreateSerializer(serializers.Serializer):
    recipient_id = serializers.IntegerField()
    offered_skill_id = serializers.IntegerField()
    requested_skill_id = serializers.IntegerField()
    message = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        request = self.context["request"]
        requester = request.user

        try:
            recipient = eligible_swap_users().get(pk=attrs["recipient_id"])
        except User.DoesNotExist:
            raise serializers.ValidationError({"recipient_id": "User not found."})

        if recipient.pk == requester.pk:
            raise serializers.ValidationError({"recipient_id": "You cannot swap with yourself."})

        try:
            offered_skill = Skill.objects.get(pk=attrs["offered_skill_id"], user=requester)
        except Skill.DoesNotExist:
            raise serializers.ValidationError({"offered_skill_id": "Offered skill not found."})

        try:
            requested_skill = Skill.objects.get(
                pk=attrs["requested_skill_id"],
                user=recipient,
            )
        except Skill.DoesNotExist:
            raise serializers.ValidationError({"requested_skill_id": "Requested skill not found."})

        requester_wants = requester.desired_skills.filter(
            name__iexact=requested_skill.name
        ).exists()
        recipient_wants = recipient.desired_skills.filter(
            name__iexact=offered_skill.name
        ).exists()

        if not requester_wants:
            raise serializers.ValidationError(
                "You are not looking to learn this skill."
            )
        if not recipient_wants:
            raise serializers.ValidationError(
                "They are not looking to learn your offered skill."
            )

        attrs["recipient"] = recipient
        attrs["offered_skill"] = offered_skill
        attrs["requested_skill"] = requested_skill
        return attrs

    def create(self, validated_data):
        requester = self.context["request"].user
        if SwapRequest.objects.filter(
            requester=requester,
            recipient=validated_data["recipient"],
            offered_skill=validated_data["offered_skill"],
            requested_skill=validated_data["requested_skill"],
            status=SwapRequest.Status.PENDING,
        ).exists():
            raise serializers.ValidationError(
                "A pending swap request already exists for this pairing."
            )

        return SwapRequest.objects.create(
            requester=requester,
            recipient=validated_data["recipient"],
            offered_skill=validated_data["offered_skill"],
            requested_skill=validated_data["requested_skill"],
            message=validated_data.get("message", ""),
        )


class SwapRequestUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SwapRequest.Status.choices)

    def validate_status(self, value):
        if value not in (
            SwapRequest.Status.ACCEPTED,
            SwapRequest.Status.DECLINED,
            SwapRequest.Status.CANCELLED,
        ):
            raise serializers.ValidationError("Invalid status for this action.")
        return value

    def validate(self, attrs):
        swap: SwapRequest = self.context["swap"]
        user = self.context["request"].user
        new_status = attrs["status"]

        if swap.status != SwapRequest.Status.PENDING:
            raise serializers.ValidationError("Only pending swap requests can be updated.")

        if new_status == SwapRequest.Status.CANCELLED:
            if user.pk not in (swap.requester_id, swap.recipient_id):
                raise serializers.ValidationError("You cannot cancel this swap request.")
            return attrs

        if user.pk != swap.recipient_id:
            raise serializers.ValidationError("Only the recipient can accept or decline.")

        return attrs

    def save(self, **kwargs):
        swap: SwapRequest = self.context["swap"]
        swap.status = self.validated_data["status"]
        swap.save(update_fields=["status", "updated_at"])
        return swap


class SwapRequestSerializer(serializers.ModelSerializer):
    requester = serializers.SerializerMethodField()
    recipient = serializers.SerializerMethodField()
    offered_skill = serializers.SerializerMethodField()
    requested_skill = serializers.SerializerMethodField()

    class Meta:
        model = SwapRequest
        fields = (
            "id",
            "status",
            "message",
            "requester",
            "recipient",
            "offered_skill",
            "requested_skill",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def _user_brief(self, user):
        request = self.context.get("request")
        avatar = None
        if user.avatar and request:
            avatar = request.build_absolute_uri(user.avatar.url)
        return {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "avatar": avatar,
        }

    def get_requester(self, obj):
        return self._user_brief(obj.requester)

    def get_recipient(self, obj):
        return self._user_brief(obj.recipient)

    def get_offered_skill(self, obj):
        skill = obj.offered_skill
        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "proficiency_percent": skill.proficiency_percent,
        }

    def get_requested_skill(self, obj):
        skill = obj.requested_skill
        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "proficiency_percent": skill.proficiency_percent,
        }
