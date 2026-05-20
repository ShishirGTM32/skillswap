from __future__ import annotations

from typing import Any, Callable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import APIView

from .utils import error_message, get_error_message, success_message, success_with_data


class HandledAPIView(APIView):
    """APIView with consistent success/error envelopes via users.utils helpers."""

    def run_action(
        self,
        action: Callable[[], Any],
        *,
        message: str = "",
        status_code: int = 200,
        with_data: bool = False,
    ):
        try:
            result = action()
            if with_data:
                return success_with_data(data=result, message=message, status=status_code)
            return success_message(message=message, status=status_code)
        except Http404 as exc:
            detail = str(exc) or "Not found."
            return error_message(error=detail, status=404)
        except (DRFValidationError, DjangoValidationError) as exc:
            return error_message(error=get_error_message(exc), status=400)
        except Exception as exc:
            return error_message(error=get_error_message(exc), status=500)
