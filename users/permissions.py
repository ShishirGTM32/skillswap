from rest_framework.permissions import BasePermission


class NotDeactivatedByAdmin(BasePermission):
    """
    Block API access for accounts marked deactivated_by_admin (JWT may still exist until expiry).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return True
        return not user.deactivated_by_admin
