from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def _first_validation_detail_message(detail):
    if detail is None:
        return None
    if isinstance(detail, dict):
        for value in detail.values():
            msg = _first_validation_detail_message(value)
            if msg:
                return msg
        return None
    if isinstance(detail, (list, tuple)):
        for item in detail:
            msg = _first_validation_detail_message(item)
            if msg:
                return msg
        return None
    s = str(detail).strip()
    return s if s else None


def get_error_message(e):
    detail = getattr(e, "detail", e)
    msg = _first_validation_detail_message(detail)
    return msg if msg else "Invalid request"

def _stringify_drfdetail(detail: Any) -> str:
    if detail is None:
        return "Invalid request."
    if isinstance(detail, (list, tuple)):
        if not detail:
            return "Invalid request."
        first = detail[0]
        return str(getattr(first, "string", first))
    if isinstance(detail, dict):
        for value in detail.values():
            if isinstance(value, (list, tuple)) and value:
                first = value[0]
                return str(getattr(first, "string", first))
            if isinstance(value, dict):
                nested = _stringify_drfdetail(value)
                if nested:
                    return nested
            if value is not None and value != "":
                return str(getattr(value, "string", value))
        return "Invalid request."
    return str(getattr(detail, "string", detail))


def envelope(*, success: bool, message: str = "", error: str = "", data: Any = None, status: int = 200) -> Response:
    if not success:
        return Response({"success": False, "error": error or "Request failed."}, status=status)
    return Response(
        {
            "success": True,
            "message": message or "",
            "error": "",
            "data": data,
        },
        status=status,
    )


def success_message(*, message: str = "", status: int = 200) -> Response:
    return Response(
        {
            "success": True,
            "message": message or "",
            "error": "",
            "data": None,
        },
        status=status,
    )


def error_message(*, error: str = "", status: int = 400) -> Response:
    return Response({"success": False, "error": error or "Request failed."}, status=status)


def success_with_data(*, data: Any = None, message: str = "", status: int = 200) -> Response:
    return Response(
        {
            "success": True,
            "message": message or "",
            "error": "",
            "data": data,
        },
        status=status,
    )