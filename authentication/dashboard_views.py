from django.shortcuts import render
from django_tenants.utils import schema_context
from django.utils import timezone

from .decorators import login_required_custom, ministry_isolation_check


@login_required_custom
@ministry_isolation_check
def dashboard_view(request):
    """
    Main dashboard shown after login.
    Content changes depending on the user's role.

    Super Admin sees platform-wide statistics (all ministries).
    Everyone else sees statistics for their own ministry only.
    """
    user = request.user
    context = {
        "user": user,
        "role": user.role,
        "ministry_schema": user.ministry_schema,
    }

    if user.role == "SUPER_ADMIN":
        context.update(_get_super_admin_stats())
    else:
        context.update(_get_ministry_stats(user.ministry_schema))

    return render(request, "dashboard/dashboard.html", context)


def _get_super_admin_stats():
    """
    Platform-wide statistics for Super Admin.
    Reads from the public schema only.
    """
    from tenants.models import Ministry
    from authentication.models import CustomUser

    try:
        total_ministries = Ministry.objects.exclude(schema_name="public").count()
        total_users = CustomUser.objects.count()

        # Count assets across ALL ministry schemas
        total_assets = 0
        active_assets = 0
        ministries = Ministry.objects.exclude(schema_name="public")
        from assets.models import Asset

        for ministry in ministries:
            try:
                with schema_context(ministry.schema_name):
                    total_assets += Asset.objects.count()
                    active_assets += Asset.objects.filter(status="ACTIVE").count()
            except Exception:
                pass

    except Exception:
        total_ministries = 0
        total_users = 0
        total_assets = 0
        active_assets = 0

    return {
        "total_ministries": total_ministries,
        "total_users": total_users,
        "total_assets": total_assets,
        "active_assets": active_assets,
        "page_title": "Platform Overview",
        "expired_assets": [],
        "expiring_soon": [],
        "expiring_later": [],
        "recent_audit": [],
    }


def _get_ministry_stats(schema_name):
    """
    Ministry-level dashboard statistics.
    Includes expiry warnings grouped by urgency.
    """
    from assets.models import Asset
    from organizations.models import AuditLog

    today = timezone.now().date()

    try:
        with schema_context(schema_name):
            total_assets = Asset.objects.count()
            active_assets = Asset.objects.filter(status="ACTIVE").count()
            total_audit = AuditLog.objects.count()

            # ── Expiry warnings ───────────────────────────────────────────────
            # Only check assets that are ACTIVE and have an expiry date set
            expirable = (
                Asset.objects.filter(asset_expiry_date__isnull=False, status="ACTIVE")
                .select_related("category")
                .order_by("asset_expiry_date")
            )

            expired_assets = []  # Already past expiry date
            expiring_soon = []  # Expires within 30 days
            expiring_later = []  # Expires within 31–90 days

            for asset in expirable:
                days_left = (asset.asset_expiry_date - today).days
                if days_left < 0:
                    expired_assets.append(asset)
                elif days_left <= 30:
                    expiring_soon.append(asset)
                elif days_left <= 90:
                    expiring_later.append(asset)

            # ── Recent audit activity ─────────────────────────────────────────
            recent_audit = list(
                AuditLog.objects.order_by("-timestamp")[:5].values(
                    "action",
                    "model_name",
                    "performed_by_name",
                    "timestamp",
                    "object_repr",
                )
            )

    except Exception:
        total_assets = 0
        active_assets = 0
        total_audit = 0
        expired_assets = []
        expiring_soon = []
        expiring_later = []
        recent_audit = []

    return {
        "total_assets": total_assets,
        "active_assets": active_assets,
        "total_audit_records": total_audit,
        "expired_assets": expired_assets,
        "expiring_soon": expiring_soon,
        "expiring_later": expiring_later,
        "total_warnings": len(expired_assets) + len(expiring_soon),
        "recent_audit": recent_audit,
        "page_title": "Ministry Dashboard",
    }
