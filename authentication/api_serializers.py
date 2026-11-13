from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import serializers
from django.contrib.auth import authenticate


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer that adds extra fields to the token.

    By default SimpleJWT only puts user_id in the token payload.
    We override get_token() to add:
    - role          → so Flutter knows what the user can do
    - ministry_schema → so Flutter knows which ministry data to show
    - keycloak_id   → the Keycloak UUID for reference
    - full_name     → so Flutter can display the user's name
    - email         → for display purposes

    Why these fields in the token:
    The Flutter app needs all this information to function.
    Without role it cannot show/hide features.
    Without ministry_schema it cannot filter data by ministry.
    Putting them in the token means one request to /api/auth/login/
    gives Flutter everything it needs — no extra API calls required.

    We also override validate() to add these fields to the
    response body so Flutter gets them on login without
    needing to decode the token manually.
    """

    @classmethod
    def get_token(cls, user):
        """
        Called when creating a new token pair.
        We call the parent to get the base token then add our fields.
        """
        token = super().get_token(user)

        # Add custom claims to the token payload
        # These are readable by anyone with the token
        token['role']            = user.role
        token['ministry_schema'] = user.ministry_schema or ''
        token['keycloak_id']     = user.keycloak_id or ''
        token['full_name']       = user.get_full_name() or user.username
        token['email']           = user.email or ''

        return token

    def validate(self, attrs):
        """
        Called when the login form is submitted.
        We call the parent to verify credentials and get tokens,
        then add extra user information to the response.

        The response sent to Flutter will be:
        {
          "access": "eyJ...",         ← access token (30 min)
          "refresh": "eyJ...",        ← refresh token (1 day)
          "user": {                   ← user info for immediate use
            "id": 1,
            "username": "moh_admin",
            "full_name": "Amina Hassan",
            "email": "admin@moh.go.tz",
            "role": "MINISTRY_ADMIN",
            "ministry_schema": "moh_schema"
          }
        }
        """
        data = super().validate(attrs)

        # Add user profile to the response
        user = self.user
        data['user'] = {
            'id':              user.id,
            'username':        user.username,
            'full_name':       user.get_full_name() or user.username,
            'email':           user.email or '',
            'role':            user.role,
            'ministry_schema': user.ministry_schema or '',
        }

        return data


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializes a CustomUser for the /api/auth/me/ endpoint.
    Returns user profile information without sensitive fields.
    """

    full_name = serializers.SerializerMethodField()

    class Meta:
        from authentication.models import CustomUser
        model  = CustomUser
        fields = [
            'id',
            'username',
            'full_name',
            'first_name',
            'last_name',
            'email',
            'role',
            'ministry_schema',
            'phone',
            'is_active',
            'date_joined',
        ]
        # Never include password in API responses
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class AssetCategorySerializer(serializers.Serializer):
    """
    Serializes AssetCategory for API responses.
    We use Serializer not ModelSerializer because AssetCategory
    is in a tenant schema — we load it manually with schema_context.
    """
    id          = serializers.IntegerField(read_only=True)
    name        = serializers.CharField()
    code        = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_active   = serializers.BooleanField()


class AssetSerializer(serializers.Serializer):
    """
    Serializes Asset for API responses.
    Covers all fields needed by the Flutter mobile app.
    """
    id                   = serializers.IntegerField(read_only=True)
    asset_number         = serializers.CharField()
    name                 = serializers.CharField()
    serial_number        = serializers.CharField(allow_blank=True, allow_null=True)
    category_id          = serializers.IntegerField()
    category_name        = serializers.SerializerMethodField()
    category_code        = serializers.SerializerMethodField()
    org_unit_id          = serializers.IntegerField(allow_null=True)
    org_unit_name        = serializers.CharField(allow_blank=True)
    location_type        = serializers.CharField(allow_blank=True)
    location_description = serializers.CharField(allow_blank=True)
    status               = serializers.CharField()
    condition            = serializers.CharField()
    manufacturer         = serializers.CharField(allow_blank=True)
    model_number         = serializers.CharField(allow_blank=True)
    supplier_name        = serializers.CharField(allow_blank=True)
    purchase_order_number = serializers.CharField(allow_blank=True)
    acquisition_date     = serializers.DateField(allow_null=True)
    warranty_expiry_date = serializers.DateField(allow_null=True)
    asset_expiry_date    = serializers.DateField(allow_null=True)
    useful_life_years    = serializers.IntegerField(allow_null=True)
    acquisition_cost     = serializers.DecimalField(
        max_digits=15, decimal_places=2, allow_null=True
    )
    current_value        = serializers.DecimalField(
        max_digits=15, decimal_places=2, allow_null=True
    )
    funding_source       = serializers.CharField(allow_blank=True)
    acquisition_method   = serializers.CharField(allow_blank=True)
    cost_centre          = serializers.CharField(allow_blank=True)
    disposal_method      = serializers.CharField(allow_blank=True)
    disposal_date        = serializers.DateField(allow_null=True)
    registered_by_name   = serializers.CharField(allow_blank=True)
    created_at           = serializers.DateTimeField(read_only=True)
    updated_at           = serializers.DateTimeField(read_only=True)
    is_expired           = serializers.SerializerMethodField()
    expires_soon         = serializers.SerializerMethodField()
    days_until_expiry    = serializers.SerializerMethodField()

    def get_category_name(self, obj):
        try:
            return obj.category.name
        except Exception:
            return ''

    def get_category_code(self, obj):
        try:
            return obj.category.code
        except Exception:
            return ''

    def get_is_expired(self, obj):
        return obj.is_expired

    def get_expires_soon(self, obj):
        return obj.expires_soon

    def get_days_until_expiry(self, obj):
        return obj.days_until_expiry


class OrgUnitSerializer(serializers.Serializer):
    """
    Serializes OrgUnit for API responses.
    Includes children for tree structure.
    """
    id        = serializers.IntegerField(read_only=True)
    name      = serializers.CharField()
    code      = serializers.CharField(allow_blank=True)
    unit_type = serializers.CharField()
    parent_id = serializers.IntegerField(allow_null=True)
    is_active = serializers.BooleanField()


class AuditLogSerializer(serializers.Serializer):
    """
    Serializes AuditLog for API responses.
    """
    id                 = serializers.IntegerField(read_only=True)
    performed_by_id    = serializers.IntegerField(allow_null=True)
    performed_by_name  = serializers.CharField()
    action             = serializers.CharField()
    model_name         = serializers.CharField()
    object_id          = serializers.CharField(allow_blank=True, allow_null=True)
    object_repr        = serializers.CharField(allow_blank=True)
    old_value          = serializers.JSONField(allow_null=True)
    new_value          = serializers.JSONField(allow_null=True)
    timestamp          = serializers.DateTimeField()
    ip_address         = serializers.CharField(allow_null=True)