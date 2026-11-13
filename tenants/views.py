from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django_tenants.utils import schema_context

from authentication.decorators import login_required_custom, role_required
from .models import Ministry, Domain


@login_required_custom
@role_required('SUPER_ADMIN')
def ministry_list_view(request):
    """
    Lists all ministries on the platform.
    Only Super Admin can access this page.
    Shows ministry name, schema, domain, status, and asset count.
    """
    ministries = Ministry.objects.exclude(
        schema_name='public'
    ).prefetch_related('domains').order_by('name')

    # For each ministry get their asset and user counts
    from assets.models import Asset
    from authentication.models import CustomUser

    ministry_data = []
    for ministry in ministries:
        asset_count = 0
        try:
            with schema_context(ministry.schema_name):
                asset_count = Asset.objects.count()
        except Exception:
            pass

        user_count = CustomUser.objects.filter(
            ministry_schema=ministry.schema_name
        ).count()

        primary_domain = ministry.domains.filter(is_primary=True).first()

        ministry_data.append({
            'ministry':       ministry,
            'asset_count':    asset_count,
            'user_count':     user_count,
            'primary_domain': primary_domain,
        })

    return render(request, 'tenants/ministry_list.html', {
        'ministry_data': ministry_data,
        'page_title':    'Ministry Management',
        'total':         len(ministry_data),
    })


@login_required_custom
@role_required('SUPER_ADMIN')
def ministry_create_view(request):
    """
    Onboard a new ministry onto the platform.

    What happens when this form is submitted:
    1. We validate that the schema name is unique and safe
    2. We create a Ministry record — django-tenants automatically
       executes CREATE SCHEMA schema_name in PostgreSQL
    3. django-tenants runs all TENANT_APPS migrations inside the new schema
       (creates organizations_orgunit, assets_asset etc. tables)
    4. We create a Domain record mapping domain to the ministry
    5. We create the root OrgUnit (MINISTRY level) inside the new schema
    6. We write a success message and redirect

    This entire process that used to require the Django shell now
    happens through a single web form.
    """
    if request.method == 'POST':
        name       = request.POST.get('name', '').strip()
        short_name = request.POST.get('short_name', '').strip().upper()
        schema_name = request.POST.get('schema_name', '').strip().lower()
        domain     = request.POST.get('domain', '').strip().lower()

        # ── Validation ────────────────────────────────────────────────────────
        errors = []

        if not name:
            errors.append("Ministry name is required.")
        if not short_name:
            errors.append("Short name / abbreviation is required.")
        if not schema_name:
            errors.append("Schema name is required.")
        if not domain:
            errors.append("Domain is required.")

        # Schema name must contain only letters, digits, and underscores
        # Spaces and hyphens are NOT allowed — PostgreSQL will reject them
        import re
        if schema_name and not re.match(r'^[a-z][a-z0-9_]*$', schema_name):
            errors.append(
                "Schema name must start with a letter and contain only "
                "lowercase letters, numbers, and underscores. "
                "No spaces or hyphens. Example: mol_schema"
            )

        # Schema name must end with _schema for consistency
        if schema_name and not schema_name.endswith('_schema'):
            errors.append(
                "Schema name must end with '_schema'. "
                f"Did you mean '{schema_name}_schema'?"
            )

        # Check uniqueness
        if Ministry.objects.filter(schema_name=schema_name).exists():
            errors.append(f"Schema name '{schema_name}' is already in use.")
        if Ministry.objects.filter(name=name).exists():
            errors.append(f"A ministry named '{name}' already exists.")
        if Domain.objects.filter(domain=domain).exists():
            errors.append(f"Domain '{domain}' is already registered.")

        existing = Ministry.objects.exclude(
            schema_name='public'
        ).values('name', 'schema_name').order_by('name')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'tenants/ministry_form.html', {
                'page_title': 'Onboard New Ministry',
                'form_data':  request.POST,
                'existing':   existing,
            })

        # ── Create the ministry ───────────────────────────────────────────────
        try:
            # Step 1: Create Ministry record
            # auto_create_schema=True means django-tenants will automatically
            # run CREATE SCHEMA and all tenant migrations right now
            ministry = Ministry(
                schema_name=schema_name,
                name=name,
                short_name=short_name,
                is_active=True,
            )
            ministry.save()  # ← This triggers schema creation

            # Step 2: Create domain mapping
            Domain.objects.create(
                domain=domain,
                tenant=ministry,
                is_primary=True,
            )

            # Step 3: Create the root OrgUnit inside the new schema
            # Every ministry needs at least one OrgUnit at MINISTRY level
            # so that users and assets can be assigned to it
            from organizations.models import OrgUnit
            with schema_context(schema_name):
                OrgUnit.objects.create(
                    name=name,
                    code=short_name,
                    unit_type='MINISTRY',
                    parent=None,
                    is_active=True,
                )

            messages.success(
                request,
                f"Ministry '{name}' onboarded successfully. "
                f"Schema '{schema_name}' created and all tables migrated. "
                f"Domain '{domain}' registered."
            )
            return redirect('ministry_list')

        except Exception as e:
            # If anything goes wrong during schema creation, report it clearly
            messages.error(request, f"Error creating ministry: {str(e)}")
            # Try to clean up if partial creation happened
            try:
                Ministry.objects.filter(schema_name=schema_name).delete()
            except Exception:
                pass

    existing = Ministry.objects.exclude(
        schema_name='public'
    ).values('name', 'schema_name').order_by('name')

    return render(request, 'tenants/ministry_form.html', {
        'page_title': 'Onboard New Ministry',
        'form_data':  {},
        'existing':   existing,
    })


@login_required_custom
@role_required('SUPER_ADMIN')
def ministry_detail_view(request, ministry_id):
    """
    Shows full details of one ministry.
    Includes user list, asset count, and schema information.
    """
    ministry = get_object_or_404(Ministry, id=ministry_id)

    if ministry.schema_name == 'public':
        messages.error(request, "Cannot view the public schema as a ministry.")
        return redirect('ministry_list')

    from authentication.models import CustomUser
    from assets.models import Asset
    from organizations.models import OrgUnit

    users = CustomUser.objects.filter(
        ministry_schema=ministry.schema_name
    ).order_by('role', 'username')

    asset_count  = 0
    org_units    = []
    recent_assets = []

    try:
        with schema_context(ministry.schema_name):
            asset_count   = Asset.objects.count()
            org_units     = list(OrgUnit.objects.all().order_by('unit_type', 'name'))
            recent_assets = list(
                Asset.objects.select_related('category')
                .order_by('-created_at')[:5]
            )
    except Exception:
        pass

    primary_domain = ministry.domains.filter(is_primary=True).first()

    return render(request, 'tenants/ministry_detail.html', {
        'ministry':       ministry,
        'users':          users,
        'asset_count':    asset_count,
        'org_units':      org_units,
        'recent_assets':  recent_assets,
        'primary_domain': primary_domain,
        'page_title':     ministry.name,
    })


@login_required_custom
@role_required('SUPER_ADMIN')
def ministry_toggle_active_view(request, ministry_id):
    """
    Activate or deactivate a ministry.
    Deactivating prevents all users in that ministry from logging in.
    The schema and data are preserved — nothing is deleted.
    """
    if request.method != 'POST':
        return redirect('ministry_list')

    ministry = get_object_or_404(Ministry, id=ministry_id)

    if ministry.schema_name == 'public':
        messages.error(request, "Cannot deactivate the public schema.")
        return redirect('ministry_list')

    ministry.is_active = not ministry.is_active
    ministry.save()

    action = "activated" if ministry.is_active else "deactivated"
    messages.success(request, f"Ministry '{ministry.name}' {action} successfully.")
    return redirect('ministry_list')