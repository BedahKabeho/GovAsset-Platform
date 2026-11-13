from django_tenants.models import TenantMixin, DomainMixin
from django.db import models


class Ministry(TenantMixin):
    """
    Represents one government ministry (one tenant).
    TenantMixin provides the schema_name field automatically.
    Each Ministry gets its own private PostgreSQL schema when created.

    Example:
        schema_name = 'moh_schema'   → Ministry of Health
        schema_name = 'mof_schema'   → Ministry of Finance
    """
    name = models.CharField(max_length=200, help_text="Full ministry name")
    short_name = models.CharField(max_length=50, help_text="Abbreviation e.g. MOH")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # This tells django-tenants to automatically create the PostgreSQL schema
    # when a new Ministry record is saved. Set to False if you want to create
    # the schema manually.
    auto_create_schema = True

    class Meta:
        app_label = 'tenants'
        verbose_name_plural = 'Ministries'

    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    """
    Maps a domain/hostname to a Ministry.
    DomainMixin provides 'domain', 'tenant', and 'is_primary' fields.

    Example:
        domain = 'moh.localhost'  → routes to Ministry of Health schema
        domain = 'mof.localhost'  → routes to Ministry of Finance schema
        domain = 'localhost'      → routes to public schema (Super Admin)
    """
    class Meta:
        app_label = 'tenants'

    def __str__(self):
        return self.domain