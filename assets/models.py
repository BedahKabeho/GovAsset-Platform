from django.db import models
from django.utils import timezone
from datetime import timedelta


class AssetCategory(models.Model):
    """
    Classifies assets into types.
    Each ministry configures their own categories.
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'assets'
        verbose_name = 'Asset Category'
        verbose_name_plural = 'Asset Categories'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} — {self.name}"


class Asset(models.Model):

    STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('ACTIVE', 'Active'),
        ('UNDER_MAINTENANCE', 'Under Maintenance'),
        ('DECOMMISSIONED', 'Decommissioned'),
        ('DISPOSED', 'Disposed'),
    ]

    CONDITION_CHOICES = [
        ('EXCELLENT', 'Excellent'),
        ('GOOD', 'Good'),
        ('FAIR', 'Fair'),
        ('POOR', 'Poor'),
        ('CRITICAL', 'Critical'),
    ]

    # ── Identification ────────────────────────────────────────────────────────
    asset_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique asset ID — auto-generated if left blank"
    )
    name = models.CharField(max_length=300)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT
    )

    # ── Manufacturer and supplier info ────────────────────────────────────────
    # These were missing before — important for warranty claims and procurement
    manufacturer = models.CharField(
        max_length=200,
        blank=True,
        help_text="Company that manufactured this asset. Example: Dell, Toyota"
    )
    model_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Manufacturer model or product number"
    )
    supplier_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Company or person who supplied this asset to the ministry"
    )
    purchase_order_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Government procurement PO number for this purchase"
    )

    # ── Location and ownership ────────────────────────────────────────────────
    org_unit_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of the OrgUnit (Facility) where this asset is located"
    )
    org_unit_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name snapshot — preserved if org unit is renamed"
    )
    location_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Type of location from master data. Example: Office Building"
    )
    location_description = models.CharField(
        max_length=300,
        blank=True,
        help_text="Physical location detail. Example: Block A, Room 204"
    )

    # ── Status and condition ──────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ACTIVE'
    )
    condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default='GOOD'
    )

    # ── Important dates ───────────────────────────────────────────────────────
    acquisition_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the asset was acquired by the ministry"
    )
    warranty_expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the manufacturer warranty expires"
    )
    asset_expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date this asset expires or must be replaced. "
                  "Used for fire extinguishers, medical equipment, licenses etc."
    )
    useful_life_years = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Expected useful life in years — used for depreciation calculations"
    )

    # ── Financial information ─────────────────────────────────────────────────
    acquisition_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original purchase price in Tanzanian Shillings"
    )
    current_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current estimated value after depreciation"
    )
    funding_source = models.CharField(
        max_length=100,
        blank=True,
        help_text="Where the money came from. Example: Government Budget"
    )
    acquisition_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="How the asset was obtained. Example: Direct Purchase"
    )
    cost_centre = models.CharField(
        max_length=100,
        blank=True,
        help_text="Department responsible. Example: ICT Department"
    )
    disposal_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="How the asset was disposed. Only filled when status is Disposed."
    )
    disposal_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the asset was disposed"
    )
    disposal_notes = models.TextField(
        blank=True,
        help_text="Notes about the disposal"
    )

    # ── Additional information ────────────────────────────────────────────────
    description = models.TextField(blank=True)
    photo = models.ImageField(
        upload_to='assets/photos/',
        null=True,
        blank=True
    )

    # ── Record keeping ────────────────────────────────────────────────────────
    registered_by_id = models.IntegerField(null=True, blank=True)
    registered_by_name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'assets'
        ordering = ['-created_at']
        verbose_name = 'Asset'
        verbose_name_plural = 'Assets'

    def __str__(self):
        return f"{self.asset_number} — {self.name}"

    # ── Helper properties used in templates and dashboard ────────────────────

    @property
    def is_expired(self):
        """
        Returns True if the asset expiry date has already passed.
        Used to show a red warning badge on the asset.
        """
        if self.asset_expiry_date:
            return self.asset_expiry_date < timezone.now().date()
        return False

    @property
    def expires_soon(self):
        """
        Returns True if the asset expires within the next 90 days.
        Used to show an amber warning badge on the asset.
        """
        if self.asset_expiry_date:
            days_left = (self.asset_expiry_date - timezone.now().date()).days
            return 0 <= days_left <= 90
        return False

    @property
    def days_until_expiry(self):
        """
        Returns the number of days until expiry.
        Returns None if no expiry date is set.
        Returns a negative number if already expired.
        """
        if self.asset_expiry_date:
            return (self.asset_expiry_date - timezone.now().date()).days
        return None

    @property
    def warranty_is_active(self):
        """Returns True if the warranty has not yet expired."""
        if self.warranty_expiry_date:
            return self.warranty_expiry_date >= timezone.now().date()
        return False