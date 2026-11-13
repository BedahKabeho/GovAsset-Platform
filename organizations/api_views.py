from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django_tenants.utils import schema_context
import logging

from authentication.api_permissions import (
    HasMinistrySchema,
    CanViewAuditLogs,
)
from authentication.api_serializers import (
    OrgUnitSerializer,
    AuditLogSerializer,
)

logger = logging.getLogger('authentication')


class OrgUnitListAPIView(APIView):
    """
    GET /api/org-units/

    Returns the full organisational hierarchy for the user's ministry.

    Why Flutter needs this:
    When a Facility Clerk registers an asset on mobile, they need
    to select which facility the asset belongs to. This endpoint
    provides all org units so Flutter can show a dropdown.

    Also used by Flutter to display the org hierarchy in a
    tree view on the mobile dashboard.

    Response format:
    {
        "ministry": {
            "id": 1,
            "name": "Ministry of Health",
            "code": "MOH",
            "unit_type": "MINISTRY",
            "agencies": [
                {
                    "id": 2,
                    "name": "Muhimbili National Hospital",
                    "unit_type": "AGENCY",
                    "facilities": [
                        {
                            "id": 3,
                            "name": "Radiology Department",
                            "unit_type": "FACILITY"
                        }
                    ]
                }
            ]
        }
    }
    """
    permission_classes = [IsAuthenticated, HasMinistrySchema]

    def get(self, request):
        user = request.user

        if user.role == 'SUPER_ADMIN':
            return Response({
                'message': (
                    'Super Admin operates at platform level. '
                    'Log in as a ministry user to view org units.'
                ),
                'ministry': None,
            })

        try:
            with schema_context(user.ministry_schema):
                from organizations.models import OrgUnit

                # Load all units in one query
                all_units = list(
                    OrgUnit.objects.filter(
                        is_active=True
                    ).order_by('unit_type', 'name')
                )

                # Build tree structure
                # Step 1: Find root ministry unit
                ministry_unit = next(
                    (u for u in all_units if u.unit_type == 'MINISTRY'),
                    None
                )

                if not ministry_unit:
                    return Response({
                        'ministry': None,
                        'message':  'No organisation units found.',
                    })

                # Step 2: Find agencies under ministry
                agencies = [
                    u for u in all_units
                    if u.unit_type == 'AGENCY' and
                    u.parent_id == ministry_unit.id
                ]

                # Step 3: Find facilities under each agency
                agency_nodes = []
                for agency in agencies:
                    facilities = [
                        u for u in all_units
                        if u.unit_type == 'FACILITY' and
                        u.parent_id == agency.id
                    ]

                    agency_nodes.append({
                        'id':         agency.id,
                        'name':       agency.name,
                        'code':       agency.code or '',
                        'unit_type':  agency.unit_type,
                        'parent_id':  agency.parent_id,
                        'is_active':  agency.is_active,
                        'facilities': [
                            {
                                'id':        f.id,
                                'name':      f.name,
                                'code':      f.code or '',
                                'unit_type': f.unit_type,
                                'parent_id': f.parent_id,
                                'is_active': f.is_active,
                            }
                            for f in facilities
                        ],
                    })

                # Step 4: Also return a flat list of facilities only
                # Flutter uses this for the asset registration dropdown
                all_facilities = [
                    {
                        'id':        u.id,
                        'name':      u.name,
                        'code':      u.code or '',
                        'unit_type': u.unit_type,
                        'parent_id': u.parent_id,
                    }
                    for u in all_units
                    if u.unit_type == 'FACILITY'
                ]

            return Response({
                'ministry': {
                    'id':       ministry_unit.id,
                    'name':     ministry_unit.name,
                    'code':     ministry_unit.code or '',
                    'unit_type': ministry_unit.unit_type,
                    'agencies': agency_nodes,
                },
                'facilities_flat': all_facilities,
                'total_units': len(all_units),
            })

        except Exception as e:
            logger.error(f"OrgUnit API error: {e}")
            return Response({
                'error':   True,
                'message': f'Error loading org units: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AuditLogListAPIView(APIView):
    """
    GET /api/audit-logs/

    Returns paginated audit logs for the user's ministry.
    Only Auditor, Ministry Admin, and Super Admin can access.

    Supports filtering:
    ?action=CREATE     → filter by action type
    ?model=Asset       → filter by which model was affected
    ?page=2            → pagination

    Why Flutter needs this:
    Auditors use the mobile app to review audit logs
    in the field. They need to see recent changes to
    assets without being at a computer.

    Response:
    {
        "count": 150,
        "current_page": 1,
        "total_pages": 8,
        "results": [
            {
                "id": 1,
                "action": "CREATE",
                "model_name": "Asset",
                "performed_by_name": "Amina Hassan",
                "timestamp": "2024-01-15T09:23:45Z",
                "object_repr": "MOH-ICT-2024-0001 — Dell Laptop"
            }
        ]
    }
    """
    permission_classes = [
        IsAuthenticated,
        HasMinistrySchema,
        CanViewAuditLogs,
    ]

    def get(self, request):
        user = request.user

        if user.role == 'SUPER_ADMIN':
            return Response({
                'message': (
                    'Audit logs are per ministry. '
                    'Log in as a ministry user to view logs.'
                ),
                'count':   0,
                'results': [],
            })

        try:
            with schema_context(user.ministry_schema):
                from organizations.models import AuditLog

                qs = AuditLog.objects.all()

                # Apply filters
                action_filter = request.GET.get('action', '').strip()
                if action_filter:
                    qs = qs.filter(action=action_filter)

                model_filter = request.GET.get('model', '').strip()
                if model_filter:
                    qs = qs.filter(model_name__icontains=model_filter)

                total = qs.count()

                # Pagination
                page_size = 25
                try:
                    page = int(request.GET.get('page', 1))
                    if page < 1:
                        page = 1
                except ValueError:
                    page = 1

                start = (page - 1) * page_size
                end   = start + page_size
                logs  = list(qs[start:end])

            serializer  = AuditLogSerializer(logs, many=True)
            total_pages = (total + page_size - 1) // page_size

            return Response({
                'count':        total,
                'current_page': page,
                'total_pages':  total_pages,
                'page_size':    page_size,
                'results':      serializer.data,
            })

        except Exception as e:
            logger.error(f"AuditLog API error: {e}")
            return Response({
                'error':   True,
                'message': f'Error loading audit logs: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardStatsAPIView(APIView):
    """
    GET /api/dashboard/stats/

    Returns dashboard statistics for the Flutter mobile app.

    Why Flutter needs this:
    The mobile dashboard shows key numbers — total assets,
    active assets, expiry warnings. Without this endpoint
    Flutter would need to make multiple separate calls.
    This gives everything in one request.

    Response:
    {
        "total_assets": 45,
        "active_assets": 38,
        "total_audit_records": 230,
        "total_warnings": 3,
        "expired_assets": [...],
        "expiring_soon": [...],
        "ministry_schema": "moh_schema"
    }
    """
    permission_classes = [IsAuthenticated, HasMinistrySchema]

    def get(self, request):
        user = request.user

        # Super Admin stats
        if user.role == 'SUPER_ADMIN':
            try:
                from tenants.models import Ministry
                from authentication.models import CustomUser
                from assets.models import Asset

                total_ministries = Ministry.objects.exclude(
                    schema_name='public'
                ).count()
                total_users = CustomUser.objects.count()

                total_assets  = 0
                active_assets = 0
                for ministry in Ministry.objects.exclude(
                    schema_name='public'
                ):
                    try:
                        with schema_context(ministry.schema_name):
                            total_assets  += Asset.objects.count()
                            active_assets += Asset.objects.filter(
                                status='ACTIVE'
                            ).count()
                    except Exception:
                        pass

                return Response({
                    'role':               'SUPER_ADMIN',
                    'total_ministries':   total_ministries,
                    'total_users':        total_users,
                    'total_assets':       total_assets,
                    'active_assets':      active_assets,
                    'total_warnings':     0,
                    'expired_assets':     [],
                    'expiring_soon':      [],
                })
            except Exception as e:
                return Response({
                    'error':   True,
                    'message': str(e),
                    'code':    'server_error',
                    'status':  500,
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Ministry-level stats
        from django.utils import timezone
        today = timezone.now().date()

        try:
            with schema_context(user.ministry_schema):
                from assets.models import Asset
                from organizations.models import AuditLog

                total_assets  = Asset.objects.count()
                active_assets = Asset.objects.filter(
                    status='ACTIVE'
                ).count()
                total_audit   = AuditLog.objects.count()

                # Expiry warnings
                expirable = Asset.objects.filter(
                    asset_expiry_date__isnull=False,
                    status='ACTIVE'
                ).select_related('category').order_by(
                    'asset_expiry_date'
                )

                expired_list    = []
                expiring_soon   = []
                expiring_later  = []

                from authentication.api_serializers import AssetSerializer
                for asset in expirable:
                    days_left = (
                        asset.asset_expiry_date - today
                    ).days
                    asset_data = {
                        'id':               asset.id,
                        'asset_number':     asset.asset_number,
                        'name':             asset.name,
                        'asset_expiry_date': str(
                            asset.asset_expiry_date
                        ),
                        'days_until_expiry': days_left,
                        'category_name': (
                            asset.category.name
                            if asset.category else ''
                        ),
                    }
                    if days_left < 0:
                        expired_list.append(asset_data)
                    elif days_left <= 30:
                        expiring_soon.append(asset_data)
                    elif days_left <= 90:
                        expiring_later.append(asset_data)

                # Recent audit activity (last 5)
                recent_audit = list(
                    AuditLog.objects.order_by('-timestamp')[:5].values(
                        'action', 'model_name',
                        'performed_by_name', 'timestamp', 'object_repr'
                    )
                )

            return Response({
                'role':             user.role,
                'ministry_schema':  user.ministry_schema,
                'total_assets':     total_assets,
                'active_assets':    active_assets,
                'total_audit_records': total_audit,
                'total_warnings':   len(expired_list) + len(expiring_soon),
                'expired_assets':   expired_list,
                'expiring_soon':    expiring_soon,
                'expiring_later':   expiring_later,
                'recent_audit':     recent_audit,
            })

        except Exception as e:
            logger.error(f"Dashboard stats API error: {e}")
            return Response({
                'error':   True,
                'message': f'Error loading stats: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)