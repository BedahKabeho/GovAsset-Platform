from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """
    Allows access only to users with SUPER_ADMIN role.
    Used for platform-level API endpoints.
    """
    message = "Only Super Admin can access this endpoint."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == 'SUPER_ADMIN'
        )


class IsMinistryAdmin(BasePermission):
    """
    Allows access to Ministry Admin and above.
    """
    message = "Ministry Admin or above required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role in ['SUPER_ADMIN', 'MINISTRY_ADMIN']
        )


class IsAgencyManagerOrAbove(BasePermission):
    """
    Allows access to Agency Manager, Ministry Admin, and Super Admin.
    """
    message = "Agency Manager or above required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role in [
                'SUPER_ADMIN', 'MINISTRY_ADMIN', 'AGENCY_MANAGER'
            ]
        )


class CanManageAssets(BasePermission):
    """
    Allows asset creation and editing.
    Facility Clerk, Agency Manager, Ministry Admin, Super Admin.
    Auditors cannot manage assets — read only.
    """
    message = "You do not have permission to manage assets."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Safe methods (GET, HEAD, OPTIONS) allowed for all
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        # Write methods only for non-auditors
        return request.user.role in [
            'SUPER_ADMIN',
            'MINISTRY_ADMIN',
            'AGENCY_MANAGER',
            'FACILITY_CLERK',
        ]


class CanDeleteAssets(BasePermission):
    """
    Only Ministry Admin can delete assets.
    """
    message = "Only Ministry Admin can delete assets."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method == 'DELETE':
            return request.user.role in [
                'SUPER_ADMIN', 'MINISTRY_ADMIN'
            ]
        return True


class CanViewAuditLogs(BasePermission):
    """
    Only Auditor, Ministry Admin, and Super Admin
    can view audit logs.
    """
    message = "Auditor or above required to view audit logs."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role in [
                'SUPER_ADMIN', 'MINISTRY_ADMIN', 'AUDITOR'
            ]
        )


class HasMinistrySchema(BasePermission):
    """
    Ensures the user has a ministry_schema assigned.
    Super Admin is exempt — they operate at platform level.
    All other roles must belong to a ministry.
    """
    message = (
        "Your account is not assigned to any ministry. "
        "Contact your administrator."
    )

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == 'SUPER_ADMIN':
            return True
        return bool(request.user.ministry_schema)