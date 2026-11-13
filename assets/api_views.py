from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django_tenants.utils import schema_context
from django.utils import timezone
import logging
import traceback

from authentication.api_permissions import (
    CanManageAssets,
    CanDeleteAssets,
    HasMinistrySchema,
)
from authentication.api_serializers import (
    AssetSerializer,
    AssetCategorySerializer,
)

logger = logging.getLogger('authentication')


class AssetListCreateAPIView(APIView):
    """
    GET  /api/assets/ — List all assets for user's ministry
    POST /api/assets/ — Create a new asset

    Why one view handles both GET and POST:
    This is a REST convention. The URL /api/assets/ represents
    the COLLECTION of assets. GET retrieves the collection.
    POST adds to the collection. Same URL, different methods.

    GET supports these query parameters for filtering:
    ?search=laptop        → filter by name or asset number
    ?status=ACTIVE        → filter by status
    ?category=1           → filter by category ID
    ?page=2               → page number for pagination

    Example Flutter call:
    GET /api/assets/?status=ACTIVE&page=1
    Authorization: Bearer eyJ...
    """
    permission_classes = [
        IsAuthenticated,
        HasMinistrySchema,
        CanManageAssets,
    ]

    def get(self, request):
        """
        Returns paginated list of assets for the user's ministry.
        Super Admin gets an empty list with a message —
        they operate at platform level, not ministry level.
        """
        user = request.user

        # Super Admin does not belong to one ministry
        if user.role == 'SUPER_ADMIN':
            return Response({
                'count':    0,
                'next':     None,
                'previous': None,
                'results':  [],
                'message':  (
                    'Super Admin operates at platform level. '
                    'Log in as a ministry user to access assets.'
                ),
            })

        assets = []
        total  = 0

        try:
            with schema_context(user.ministry_schema):
                from assets.models import Asset, AssetCategory

                # Start with all assets
                qs = Asset.objects.select_related('category').all()

                # Apply filters from query parameters
                search = request.GET.get('search', '').strip()
                if search:
                    # Filter by name OR asset number
                    qs = qs.filter(name__icontains=search) | \
                         qs.filter(asset_number__icontains=search)

                status_filter = request.GET.get('status', '').strip()
                if status_filter:
                    qs = qs.filter(status=status_filter)

                category_filter = request.GET.get('category', '').strip()
                if category_filter:
                    qs = qs.filter(category_id=category_filter)

                condition_filter = request.GET.get('condition', '').strip()
                if condition_filter:
                    qs = qs.filter(condition=condition_filter)

                total = qs.count()

                # Manual pagination
                # We do this manually because automatic DRF pagination
                # does not work well with schema_context
                page_size = 20
                try:
                    page = int(request.GET.get('page', 1))
                    if page < 1:
                        page = 1
                except ValueError:
                    page = 1

                start = (page - 1) * page_size
                end   = start + page_size
                assets = list(qs[start:end])

        except Exception as e:
            logger.error(f"Asset list API error: {e}")
            return Response({
                'error':   True,
                'message': f'Error loading assets: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize the assets
        serializer  = AssetSerializer(assets, many=True)
        total_pages = (total + page_size - 1) // page_size

        base_url = request.build_absolute_uri(
            '/api/assets/'
        )

        return Response({
            'count':    total,
            'total_pages': total_pages,
            'current_page': page,
            'page_size': page_size,
            'next': (
                f"{base_url}?page={page + 1}"
                if page < total_pages else None
            ),
            'previous': (
                f"{base_url}?page={page - 1}"
                if page > 1 else None
            ),
            'results': serializer.data,
        })

    def post(self, request):
        """
        Creates a new asset in the user's ministry schema.

        Expected request body:
        {
            "name": "Dell Laptop Latitude 5520",
            "category_id": 1,
            "status": "ACTIVE",
            "condition": "GOOD",
            "location_description": "Block A Room 204",
            "acquisition_cost": "2500000.00",
            "manufacturer": "Dell",
            "asset_expiry_date": "2027-12-31"
        }

        asset_number is optional — auto-generated if not provided.
        """
        user = request.user

        if user.role == 'AUDITOR':
            return Response({
                'error':   True,
                'message': 'Auditors cannot create assets.',
                'code':    'permission_denied',
                'status':  403,
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data

        # Validate required fields
        errors = {}
        if not data.get('name', '').strip():
            errors['name'] = 'Asset name is required.'
        if not data.get('category_id'):
            errors['category_id'] = 'Category is required.'

        if errors:
            return Response({
                'error':   True,
                'message': 'Validation failed.',
                'errors':  errors,
                'code':    'bad_request',
                'status':  400,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with schema_context(user.ministry_schema):
                from assets.models import Asset, AssetCategory
                from assets.views import generate_asset_number

                # Verify category exists
                try:
                    category = AssetCategory.objects.get(
                        id=data.get('category_id')
                    )
                except AssetCategory.DoesNotExist:
                    return Response({
                        'error':   True,
                        'message': 'Category not found.',
                        'code':    'not_found',
                        'status':  404,
                    }, status=status.HTTP_404_NOT_FOUND)

                # Auto-generate asset number if not provided
                asset_number = data.get('asset_number', '').strip()
                if not asset_number:
                    asset_number = generate_asset_number(
                        user.ministry_schema,
                        category.code
                    )

                # Check uniqueness
                if Asset.objects.filter(
                    asset_number=asset_number
                ).exists():
                    return Response({
                        'error':   True,
                        'message': (
                            f"Asset number '{asset_number}' already exists."
                        ),
                        'code':    'bad_request',
                        'status':  400,
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Resolve org unit name snapshot
                org_unit_id   = data.get('org_unit_id')
                org_unit_name = ''
                if org_unit_id:
                    from organizations.models import OrgUnit
                    try:
                        org_unit = OrgUnit.objects.get(id=org_unit_id)
                        org_unit_name = org_unit.name
                    except OrgUnit.DoesNotExist:
                        org_unit_id = None

                # Create the asset
                asset = Asset.objects.create(
                    asset_number=asset_number,
                    name=data.get('name', '').strip(),
                    category=category,
                    serial_number=data.get('serial_number') or None,
                    manufacturer=data.get('manufacturer', ''),
                    model_number=data.get('model_number', ''),
                    supplier_name=data.get('supplier_name', ''),
                    purchase_order_number=data.get(
                        'purchase_order_number', ''
                    ),
                    status=data.get('status', 'ACTIVE'),
                    condition=data.get('condition', 'GOOD'),
                    location_type=data.get('location_type', ''),
                    location_description=data.get(
                        'location_description', ''
                    ),
                    org_unit_id=org_unit_id,
                    org_unit_name=org_unit_name,
                    useful_life_years=data.get('useful_life_years'),
                    acquisition_date=data.get('acquisition_date'),
                    warranty_expiry_date=data.get('warranty_expiry_date'),
                    asset_expiry_date=data.get('asset_expiry_date'),
                    acquisition_cost=data.get('acquisition_cost'),
                    current_value=data.get('current_value'),
                    funding_source=data.get('funding_source', ''),
                    acquisition_method=data.get('acquisition_method', ''),
                    cost_centre=data.get('cost_centre', ''),
                    description=data.get('description', ''),
                    registered_by_id=user.id,
                    registered_by_name=(
                        user.get_full_name() or user.username
                    ),
                )

                # Write audit log
                from organizations.models import AuditLog
                AuditLog.objects.create(
                    performed_by_id=user.id,
                    performed_by_name=(
                        user.get_full_name() or user.username
                    ),
                    action='CREATE',
                    model_name='Asset',
                    object_id=str(asset.id),
                    object_repr=str(asset),
                    old_value=None,
                    new_value={
                        'asset_number': asset.asset_number,
                        'name':         asset.name,
                        'status':       asset.status,
                        'source':       'API',
                    },
                )
                asset.refresh_from_db()
            
            serializer = AssetSerializer(asset)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Asset create API error: {e}")
            return Response({
                'error':   True,
                'message': f'Error creating asset: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AssetDetailAPIView(APIView):
    """
    GET    /api/assets/{id}/ — Get one asset
    PUT    /api/assets/{id}/ — Update one asset
    DELETE /api/assets/{id}/ — Delete one asset

    Why one view handles GET, PUT, DELETE:
    The URL /api/assets/1/ represents ONE specific asset.
    GET retrieves it. PUT updates it. DELETE removes it.
    Same URL, different HTTP methods — REST convention.
    """
    permission_classes = [
        IsAuthenticated,
        HasMinistrySchema,
        CanManageAssets,
        CanDeleteAssets,
    ]

    def _get_asset(self, asset_id, ministry_schema):
        """
        Helper to fetch one asset inside schema context.
        Returns (asset, error_response) tuple.
        If asset found: (asset_object, None)
        If not found:   (None, error_response)
        """
        from assets.models import Asset
        try:
            with schema_context(ministry_schema):
                asset = Asset.objects.select_related(
                    'category'
                ).get(id=asset_id)
                return asset, None
        except Asset.DoesNotExist:
            return None, Response({
                'error':   True,
                'message': f'Asset with ID {asset_id} not found.',
                'code':    'not_found',
                'status':  404,
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return None, Response({
                'error':   True,
                'message': f'Error loading asset: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, asset_id):
        """
        Returns full detail of one asset.
        All authenticated ministry users can view.
        """
        user = request.user

        if user.role == 'SUPER_ADMIN':
            return Response({
                'error':   True,
                'message': 'Log in as a ministry user to view assets.',
                'code':    'permission_denied',
                'status':  403,
            }, status=status.HTTP_403_FORBIDDEN)

        asset, error = self._get_asset(asset_id, user.ministry_schema)
        if error:
            return error

        serializer = AssetSerializer(asset)
        return Response(serializer.data)

    def put(self, request, asset_id):
        """
        Updates an existing asset.
        Records old and new values in audit log.
        """
        user = request.user

        if user.role in ['AUDITOR', 'SUPER_ADMIN']:
            return Response({
                'error':   True,
                'message': 'You do not have permission to edit assets.',
                'code':    'permission_denied',
                'status':  403,
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            with schema_context(user.ministry_schema):
                from assets.models import Asset, AssetCategory
                from organizations.models import AuditLog

                try:
                    asset = Asset.objects.select_related(
                        'category'
                    ).get(id=asset_id)
                except Asset.DoesNotExist:
                    return Response({
                        'error':   True,
                        'message': f'Asset {asset_id} not found.',
                        'code':    'not_found',
                        'status':  404,
                    }, status=status.HTTP_404_NOT_FOUND)

                # Capture old values for audit
                old_value = {
                    'name':      asset.name,
                    'status':    asset.status,
                    'condition': asset.condition,
                }

                data = request.data

                # Update only fields that are provided
                if 'name' in data:
                    asset.name = data['name'].strip()
                if 'status' in data:
                    asset.status = data['status']
                if 'condition' in data:
                    asset.condition = data['condition']
                if 'location_description' in data:
                    asset.location_description = data[
                        'location_description'
                    ]
                if 'location_type' in data:
                    asset.location_type = data['location_type']
                if 'manufacturer' in data:
                    asset.manufacturer = data['manufacturer']
                if 'model_number' in data:
                    asset.model_number = data['model_number']
                if 'acquisition_cost' in data:
                    asset.acquisition_cost = data['acquisition_cost']
                if 'current_value' in data:
                    asset.current_value = data['current_value']
                if 'funding_source' in data:
                    asset.funding_source = data['funding_source']
                if 'acquisition_method' in data:
                    asset.acquisition_method = data['acquisition_method']
                if 'cost_centre' in data:
                    asset.cost_centre = data['cost_centre']
                if 'asset_expiry_date' in data:
                    asset.asset_expiry_date = (
                        data['asset_expiry_date'] or None
                    )
                if 'warranty_expiry_date' in data:
                    asset.warranty_expiry_date = (
                        data['warranty_expiry_date'] or None
                    )
                if 'description' in data:
                    asset.description = data['description']
                if 'disposal_method' in data:
                    asset.disposal_method = data['disposal_method']
                if 'disposal_date' in data:
                    asset.disposal_date = data['disposal_date'] or None
                if 'disposal_notes' in data:
                    asset.disposal_notes = data['disposal_notes']

                # Update category if provided
                if 'category_id' in data:
                    try:
                        asset.category = AssetCategory.objects.get(
                            id=data['category_id']
                        )
                    except AssetCategory.DoesNotExist:
                        return Response({
                            'error':   True,
                            'message': 'Category not found.',
                            'code':    'not_found',
                            'status':  404,
                        }, status=status.HTTP_404_NOT_FOUND)

                asset.save()

                # Write audit log
                AuditLog.objects.create(
                    performed_by_id=user.id,
                    performed_by_name=(
                        user.get_full_name() or user.username
                    ),
                    action='UPDATE',
                    model_name='Asset',
                    object_id=str(asset.id),
                    object_repr=str(asset),
                    old_value=old_value,
                    new_value={
                        'name':      asset.name,
                        'status':    asset.status,
                        'condition': asset.condition,
                        'source':    'API',
                    },
                )

                asset.refresh_from_db()
            serializer = AssetSerializer(asset)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Asset update API error: {e}")
            return Response({
                'error':   True,
                'message': f'Error updating asset: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, asset_id):
        """
        Deletes an asset permanently.
        Only Ministry Admin and Super Admin can delete.
        Writes a DELETE audit log entry before removing.
        """
        user = request.user

        if user.role not in ['MINISTRY_ADMIN', 'SUPER_ADMIN']:
            return Response({
                'error':   True,
                'message': 'Only Ministry Admin can delete assets.',
                'code':    'permission_denied',
                'status':  403,
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            with schema_context(user.ministry_schema):
                from assets.models import Asset
                from organizations.models import AuditLog

                try:
                    asset = Asset.objects.select_related(
                        'category'
                    ).get(id=asset_id)
                except Asset.DoesNotExist:
                    return Response({
                        'error':   True,
                        'message': f'Asset {asset_id} not found.',
                        'code':    'not_found',
                        'status':  404,
                    }, status=status.HTTP_404_NOT_FOUND)

                # Write audit log BEFORE deleting
                AuditLog.objects.create(
                    performed_by_id=user.id,
                    performed_by_name=(
                        user.get_full_name() or user.username
                    ),
                    action='DELETE',
                    model_name='Asset',
                    object_id=str(asset.id),
                    object_repr=str(asset),
                    old_value={
                        'asset_number': asset.asset_number,
                        'name':         asset.name,
                        'status':       asset.status,
                        'source':       'API',
                    },
                    new_value=None,
                )
                

                asset_number = asset.asset_number
                asset.delete()

            return Response({
                'message': (
                    f"Asset '{asset_number}' deleted successfully."
                ),
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Asset delete API error: {e}")
            return Response({
                'error':   True,
                'message': f'Error deleting asset: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AssetCategoryListAPIView(APIView):
    """
    GET /api/assets/categories/

    Returns all active asset categories for the user's ministry.
    Flutter uses this to populate the category dropdown
    when registering a new asset.

    No POST here — categories are managed through the web
    interface by Ministry Admin, not through the mobile app.
    """
    permission_classes = [IsAuthenticated, HasMinistrySchema]

    def get(self, request):
        user = request.user

        if user.role == 'SUPER_ADMIN':
            return Response({'results': []})

        categories = []
        try:
            with schema_context(user.ministry_schema):
                from assets.models import AssetCategory
                categories = list(
                    AssetCategory.objects.filter(
                        is_active=True
                    ).order_by('name')
                )
        except Exception as e:
            return Response({
                'error':   True,
                'message': f'Error loading categories: {str(e)}',
                'code':    'server_error',
                'status':  500,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = AssetCategorySerializer(categories, many=True)
        return Response({
            'count':   len(categories),
            'results': serializer.data,
        })