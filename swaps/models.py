from django.conf import settings
from django.db import models


class SwapRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="swap_requests_sent",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="swap_requests_received",
    )
    offered_skill = models.ForeignKey(
        "users.Skill",
        on_delete=models.CASCADE,
        related_name="swap_offers",
    )
    requested_skill = models.ForeignKey(
        "users.Skill",
        on_delete=models.CASCADE,
        related_name="incoming_swap_requests",
    )
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["requester", "recipient", "offered_skill", "requested_skill"],
                condition=models.Q(status="pending"),
                name="unique_pending_swap_request",
            ),
        ]

    def __str__(self):
        return f"{self.requester_id} → {self.recipient_id} ({self.status})"
