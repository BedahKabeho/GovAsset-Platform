from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
# ALLOWED_HOSTS = ['*']
# In development we allow localhost and all tenant subdomains
# In production this should be locked to specific domains only
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.localhost',   # This covers moh.localhost, mof.localhost etc.
    '[::1]', # IPv6 localhost  
    '192.168.1.170',     
    '192.168.100.18',  # Your laptop WiFi IP for mobile access
    '172.16.20.232',
    '10.187.136.150'  # my phone's ip address 

]

# ─────────────────────────────────────────────────────────────────────────────
# DJANGO-TENANTS CONFIGURATION
# This is the core of our multi-tenancy system.
# SHARED_APPS = apps whose tables live in the PUBLIC schema (shared by everyone)
# TENANT_APPS = apps whose tables live in EACH MINISTRY'S private schema
# ─────────────────────────────────────────────────────────────────────────────

SHARED_APPS = [
    'django_tenants',        # MUST be first — it patches Django's database layer
    'tenants',               # Ministry and Domain models
    'authentication',        # CustomUser model — one user table for all ministries

    # Django's own apps — these go in the public schema
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'corsheaders',

    'mozilla_django_oidc',

    'drf_yasg',   
]

TENANT_APPS = [
    # Each ministry gets its own private copy of these tables
    'django.contrib.contenttypes',  # needed in tenant schema for FK resolution
    'organizations',  # OrgUnit (Ministry→Agency→Facility hierarchy), MasterData
    'assets',         # Asset, AssetCategory
]

# Django requires INSTALLED_APPS — django-tenants builds it from the two lists above
# We use a set to remove duplicates (contenttypes appears in both lists)
INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

# Tell django-tenants which models represent a Tenant and a Domain
TENANT_MODEL = "tenants.Ministry"
TENANT_DOMAIN_MODEL = "tenants.Domain"

# When no tenant domain matches the request host,
# fall back to the public schema instead of returning 404.
# This is needed for mobile API access via IP address.
SHOW_PUBLIC_IF_NO_TENANT_FOUND = True









# ─────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE
# TenantMainMiddleware must be FIRST — it reads the domain from the request
# and switches the database connection to the correct ministry schema
# before any other middleware or view runs
# ─────────────────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'authentication.middleware.SchemaMiddleware',
    'mozilla_django_oidc.middleware.SessionRefresh',
]

# ─────────────────────────────────────────────────────────────────────────────
# URL ROUTING
# django-tenants uses TWO url files:
#   ROOT_URLCONF = urls for tenant schemas (ministry-specific pages)
#   PUBLIC_SCHEMA_URLCONF = urls for the public schema (super admin, login)
# For now both point to the same file. We will split them later.
# ─────────────────────────────────────────────────────────────────────────────
ROOT_URLCONF = 'config.urls'
PUBLIC_SCHEMA_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# We use django_tenants.postgresql_backend instead of the standard PostgreSQL
# backend. This custom backend intercepts every database query and adds
# SET search_path = schema_name so PostgreSQL looks in the correct schema.
# This is why MySQL cannot be used — it has no schema feature.
# ─────────────────────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', cast=int),
    }
}

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# We use a custom User model (defined in authentication app).
# AUTH_USER_MODEL must be set BEFORE first migration. Cannot change it after.
# ─────────────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'authentication.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        'OPTIONS': {'user_attributes': ('username', 'email', 'first_name', 'last_name')}
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8}
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# STATIC FILES
# ─────────────────────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION AND SESSION SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
LOGIN_URL          = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

# Session expires when browser closes
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Session expires after 8 hours of inactivity even if browser stays open
# 8 hours = 28800 seconds — suitable for a government work day
SESSION_COOKIE_AGE = 28800

# Prevent JavaScript from reading the session cookie
# Protects against XSS attacks stealing the session
SESSION_COOKIE_HTTPONLY = True

# Only send session cookie over HTTPS in production
# Set to False in development because we use plain HTTP
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)

# Prevent CSRF cookie from being read by JavaScript
CSRF_COOKIE_HTTPONLY = True

# Only send CSRF cookie over HTTPS in production
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)

# Clickjacking protection — prevents our pages being
# loaded inside an iframe on another website
X_FRAME_OPTIONS = 'DENY'

# Tell browsers not to guess content types
SECURE_CONTENT_TYPE_NOSNIFF = True

# Tell browsers to always use HTTPS for this domain
# Only active in production when DEBUG=False
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)



# ─────────────────────────────────────────────────────────────────────────────
# REST FRAMEWORK — we configure this fully in Phase 6

# ─────────────────────────────────────────────────────────────────────────────
# DJANGO REST FRAMEWORK SETTINGS
#
# DEFAULT_AUTHENTICATION_CLASSES — how the API identifies who is calling it.
#   JWTAuthentication  → reads the Authorization: Bearer <token> header
#   SessionAuthentication → reads the session cookie (for browser-based calls)
#   We keep both so the web interface and mobile app both work.
#
# DEFAULT_PERMISSION_CLASSES — who is allowed to call API endpoints.
#   IsAuthenticated → must be logged in. Anonymous calls are rejected with 401.
#
# DEFAULT_RENDERER_CLASSES — how responses are formatted.
#   JSONRenderer → always return JSON, never HTML.
#   BrowsableAPIRenderer → shows a nice HTML page when you visit API in browser.
#   We keep both during development so you can test in browser easily.
#
# DEFAULT_PAGINATION_CLASS — automatically paginates list responses.
#   PageNumberPagination → adds page, page_size parameters to list endpoints.
#   PAGE_SIZE = 20 → return 20 items per page by default.
#
# EXCEPTION_HANDLER — handles errors consistently.
#   Our custom handler formats all errors as JSON with a clear message.
# ─────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': None,
'PAGE_SIZE': 20,
    'EXCEPTION_HANDLER': (
        'authentication.api_exception_handler.custom_exception_handler'
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# SILENCE EXPECTED WARNINGS
# rest_framework.W001 is expected — we use manual pagination in every
# view instead of DRF's automatic PageNumberPagination class.
# ─────────────────────────────────────────────────────────────────────────────
SILENCED_SYSTEM_CHECKS = ['rest_framework.W001']

# ─────────────────────────────────────────────────────────────────────────────
# SWAGGER / DRF-YASG SETTINGS
# Tells Swagger UI to use JWT Bearer token authentication
# instead of Basic username/password authentication.
#
# SECURITY_DEFINITIONS defines the auth methods shown in Swagger.
# We define one method called 'Bearer' of type 'apiKey'.
# apiKey type means "look for a key in a specific header".
# The header name is 'Authorization'.
# The value format is 'Bearer eyJ...'
# ─────────────────────────────────────────────────────────────────────────────
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type':        'apiKey',
            'name':        'Authorization',
            'in':          'header',
            'description': (
                'JWT Bearer token authentication. \n\n'
                'Format: **Bearer &lt;your_access_token&gt;**\n\n'
                'Example: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
            ),
        }
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR':      True,
    'SHOW_REQUEST_HEADERS': True,
    'DEFAULT_MODEL_RENDERING': 'example',
    'DOC_EXPANSION': 'list',
    'OPERATIONS_SORTER': 'method',
    'PERSIST_AUTH': True,
}



# ─────────────────────────────────────────────────────────────────────────────
# SIMPLEJWT SETTINGS
#
# This controls how JWT tokens are created and verified.
#
# ACCESS_TOKEN_LIFETIME — how long the access token is valid.
#   30 minutes is standard. After this the app must use the refresh token.
#   Short lifetime limits damage if a token is stolen.
#
# REFRESH_TOKEN_LIFETIME — how long the refresh token is valid.
#   1 day. The app uses this to get new access tokens without re-login.
#
# ROTATE_REFRESH_TOKENS — when a refresh token is used, issue a new one.
#   True = each refresh gives a brand new refresh token. More secure.
#
# BLACKLIST_AFTER_ROTATION — after rotating, old refresh token is blacklisted.
#   Prevents the old token from being used again if stolen.
#
# ALGORITHM — HS256 = HMAC with SHA-256.
#   Uses our Django SECRET_KEY to sign tokens.
#   Simpler than RS256 (which requires a separate key pair).
#
# AUTH_HEADER_TYPES — the prefix in the Authorization header.
#   'Bearer' = standard. Every request sends: Authorization: Bearer <token>
#
# TOKEN_OBTAIN_SERIALIZER — our custom serializer that adds extra fields
#   to the token response (role, ministry_schema, full_name etc.)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_OBTAIN_SERIALIZER': (
        'authentication.api_serializers.CustomTokenObtainPairSerializer'
    ),
}





















# ─────────────────────────────────────────────────────────────────────────────
# CORS SETTINGS
# Controls which domains can call our API endpoints.
# Important for Flutter mobile app and other groups.
# ─────────────────────────────────────────────────────────────────────────────

# In development allow all origins so Flutter and Postman work easily
# In production this should list only approved domains
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=True, cast=bool)

# When CORS_ALLOW_ALL_ORIGINS is False, list specific allowed origins here
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",    # React/Vue development server
    "http://localhost:8000",    # Django itself
    "http://127.0.0.1:8000",
]

# Allow these HTTP methods in cross-origin requests
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Allow these headers in cross-origin requests
# Authorization is required for JWT token passing
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Allow credentials (cookies) in cross-origin requests
CORS_ALLOW_CREDENTIALS = True




# ─────────────────────────────────────────────────────────────────────────────
# SECURITY CHECKS
# ─────────────────────────────────────────────────────────────────────────────
import sys

# Warn if using the default insecure secret key in production
if not DEBUG and 'django-insecure' in SECRET_KEY:
    print(
        "WARNING: You are running in production with an insecure "
        "SECRET_KEY. Generate a new one immediately.",
        file=sys.stderr
    )

# Warn if DEBUG is True when running tests
if 'test' in sys.argv and DEBUG:
    print(
        "WARNING: Running tests with DEBUG=True. "
        "Set DEBUG=False for accurate security testing.",
        file=sys.stderr
    )



# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# Records important system events to a file.
# Security events like failed logins are always logged.
# ─────────────────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
        'security_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'WARNING',
            'propagate': True,
        },
        'django.security': {
            'handlers': ['security_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'authentication': {
            'handlers': ['security_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}



# ─────────────────────────────────────────────────────────────────────────────
# KEYCLOAK / OIDC SETTINGS
#
# OIDC = OpenID Connect — the protocol used to talk to Keycloak
#
# How these URLs work:
# Keycloak organizes everything under a realm URL:
# http://localhost:8180/realms/govasset/
# Under that base URL there are specific endpoints:
#   /protocol/openid-connect/auth     → where users log in
#   /protocol/openid-connect/token    → where Django gets tokens
#   /protocol/openid-connect/userinfo → where Django gets user info
#   /protocol/openid-connect/logout   → where users log out
# ─────────────────────────────────────────────────────────────────────────────
KEYCLOAK_SERVER_URL   = config('KEYCLOAK_SERVER_URL', default='http://localhost:8180')
KEYCLOAK_REALM        = config('KEYCLOAK_REALM',      default='govasset')
KEYCLOAK_CLIENT_ID    = config('KEYCLOAK_CLIENT_ID',  default='govasset-django')
KEYCLOAK_CLIENT_SECRET = config('KEYCLOAK_CLIENT_SECRET', default='')

# Build the base realm URL once — used in all endpoint URLs below
_KEYCLOAK_BASE = f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect"

# These three URLs are the core of OIDC:
# OIDC_OP_AUTHORIZATION_ENDPOINT — where Django sends the user to log in
# When a user needs to log in, Django redirects their browser here.
# Keycloak shows its login form at this URL.
OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_KEYCLOAK_BASE}/auth"

# OIDC_OP_TOKEN_ENDPOINT — where Django exchanges the code for tokens
# After user logs in, Keycloak gives Django a code.
# Django calls this URL secretly (server to server) to exchange
# that code for the actual tokens.
OIDC_OP_TOKEN_ENDPOINT = f"{_KEYCLOAK_BASE}/token"

# OIDC_OP_USER_ENDPOINT — where Django gets user profile information
# Django can call this URL with the access token to get
# the latest user information from Keycloak.
OIDC_OP_USER_ENDPOINT = f"{_KEYCLOAK_BASE}/userinfo"

# OIDC_OP_JWKS_ENDPOINT — where Django gets Keycloak's public keys
# Keycloak signs tokens with a private key.
# Django uses Keycloak's public key to verify the signature.
# This ensures tokens cannot be forged.
OIDC_OP_JWKS_ENDPOINT = f"{_KEYCLOAK_BASE}/certs"

# OIDC_OP_LOGOUT_ENDPOINT — where Django sends user to log out of Keycloak
OIDC_OP_LOGOUT_ENDPOINT = f"{_KEYCLOAK_BASE}/logout"

# Our Django client credentials — Keycloak uses these to verify
# that the request is coming from our trusted Django application
# and not from an imposter
OIDC_RP_CLIENT_ID     = KEYCLOAK_CLIENT_ID
OIDC_RP_CLIENT_SECRET = KEYCLOAK_CLIENT_SECRET

# The signing algorithm Keycloak uses to sign tokens
# RS256 = RSA Signature with SHA-256 — the industry standard
OIDC_RP_SIGN_ALGO = 'RS256'

# Tell mozilla-django-oidc to use our custom authentication backend
# This is the class we will write in the next step that finds
# the correct Django user after Keycloak authentication
OIDC_AUTHENTICATE_CLASS = 'mozilla_django_oidc.views.OIDCAuthenticationRequestView'

OIDC_AUTHENTICATION_CALLBACK_CLASS = 'mozilla_django_oidc.views.OIDCAuthenticationCallbackView'

# Where to send user after successful login
LOGIN_REDIRECT_URL  = '/dashboard/'

# Where to send user after logout
LOGOUT_REDIRECT_URL = '/login/'

# Where to redirect if OIDC authentication fails
LOGIN_REDIRECT_URL_FAILURE = '/login/?error=auth_failed'

# Use the sub claim (Keycloak user ID) to identify users
OIDC_USE_PKCE = True

# Force Keycloak to always show the login form
# even if a session already exists.
# This prevents ghost sessions from blocking other users
# on the same browser during testing.
# In production with one user per browser this is not needed
# but it makes development much smoother.
OIDC_AUTH_REQUEST_EXTRA_PARAMS = {'prompt': 'login'}







# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION BACKENDS
#
# Django supports multiple authentication backends.
# We add our OIDC backend alongside Django's default backend.
# Django tries each backend in order until one succeeds.
#
# OIDCAuthenticationBackend — handles Keycloak SSO login
# ModelBackend — handles direct Django username/password login
#   (kept as fallback for admin and API access)
# ─────────────────────────────────────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    'authentication.oidc_backend.GovAssetOIDCBackend',
    'django.contrib.auth.backends.ModelBackend',
]