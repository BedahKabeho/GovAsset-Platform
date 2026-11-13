from django_tenants.utils import schema_context
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import logout
from django.shortcuts import redirect


class SchemaMiddleware(MiddlewareMixin):
    """
    Runs on every request. Switches the PostgreSQL search_path to the
    correct ministry schema based on the logged-in user's ministry_schema field.

    Why this is needed:
        When a user logs in, Django knows who they are but PostgreSQL still
        points at the 'public' schema. If we try to load an Asset record,
        PostgreSQL looks in public.assets_asset — which does not exist.
        This middleware says: "before any view runs, point PostgreSQL at
        moh_schema" so the query hits moh_schema.assets_asset instead.

    How it works:
        1. Request comes in
        2. We check if request.user is logged in
        3. If yes, we read their ministry_schema field
        4. We set request.schema_name so views can read it if needed
        5. django-tenants TenantMainMiddleware handles the actual
           schema switching based on the domain — we use schema_context
           inside views for any cross-schema operations
    """

    # These paths do not need schema switching — they work in the public schema
    PUBLIC_PATHS = [
        '/login/',
        '/logout/',
        '/static/',
        '/admin/',
    ]

    def process_request(self, request):
        # Skip schema logic for public paths
        for path in self.PUBLIC_PATHS:
            if request.path.startswith(path):
                return None

        # Attach schema info to request so every view can access it easily
        if hasattr(request, 'user') and request.user.is_authenticated:
            request.schema_name = request.user.ministry_schema or 'public'
            request.user_role = request.user.role
        else:
            request.schema_name = 'public'
            request.user_role = None

        return None