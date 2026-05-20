from rest_framework.response import Response
from rest_framework.views import exception_handler

from .utils import get_error_message


def envelope_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    return Response({"success": False, "error": get_error_message(exc)}, status=response.status_code)
