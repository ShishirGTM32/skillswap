from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError

from users.api_views import HandledAPIView

from .models import SwapRequest
from .serializers import (
    SwapRequestCreateSerializer,
    SwapRequestSerializer,
    SwapRequestUpdateSerializer,
)
from .services import build_match_payload, get_mutual_swap_matches


class SwapMatchListView(HandledAPIView):
    def get(self, request):
        return self.run_action(
            lambda: [
                build_match_payload(user, request.user, request=request)
                for user in get_mutual_swap_matches(request.user)
            ],
            message="Swap matches fetched successfully.",
            with_data=True,
        )


class SwapRequestListCreateView(HandledAPIView):
    def get(self, request):
        direction = request.query_params.get("direction", "all").lower()
        qs = SwapRequest.objects.select_related(
            "requester",
            "recipient",
            "offered_skill",
            "requested_skill",
        )

        if direction == "sent":
            qs = qs.filter(requester=request.user)
        elif direction == "received":
            qs = qs.filter(recipient=request.user)
        elif direction == "all":
            qs = qs.filter(Q(requester=request.user) | Q(recipient=request.user))
        else:
            raise DRFValidationError(
                {"direction": "Must be one of: sent, received, all."}
            )

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        return self.run_action(
            lambda: SwapRequestSerializer(
                qs,
                many=True,
                context={"request": request},
            ).data,
            message="Swap requests fetched successfully.",
            with_data=True,
        )

    @transaction.atomic
    def post(self, request):
        def action():
            ser = SwapRequestCreateSerializer(
                data=request.data,
                context={"request": request},
            )
            ser.is_valid(raise_exception=True)
            swap = ser.save()
            return SwapRequestSerializer(swap, context={"request": request}).data

        return self.run_action(
            action,
            message="Swap request created successfully.",
            status_code=status.HTTP_201_CREATED,
            with_data=True,
        )


class SwapRequestDetailView(HandledAPIView):
    def _get_swap(self, request, pk: int) -> SwapRequest:
        try:
            return SwapRequest.objects.select_related(
                "requester",
                "recipient",
                "offered_skill",
                "requested_skill",
            ).get(
                Q(requester=request.user) | Q(recipient=request.user),
                pk=pk,
            )
        except SwapRequest.DoesNotExist:
            raise Http404("Swap request not found.")

    def get(self, request, pk):
        swap = self._get_swap(request, pk)
        return self.run_action(
            lambda: SwapRequestSerializer(swap, context={"request": request}).data,
            message="Swap request fetched successfully.",
            with_data=True,
        )

    @transaction.atomic
    def patch(self, request, pk):
        swap = self._get_swap(request, pk)

        def action():
            ser = SwapRequestUpdateSerializer(
                data=request.data,
                context={"request": request, "swap": swap},
            )
            ser.is_valid(raise_exception=True)
            swap = ser.save()
            return SwapRequestSerializer(swap, context={"request": request}).data

        return self.run_action(
            action,
            message="Swap request updated successfully.",
            with_data=True,
        )
