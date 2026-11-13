import requests
import logging

logger = logging.getLogger('authentication')


class KeycloakAdminService:
    """
    Service class for managing users in Keycloak via the Admin REST API.

    This class handles all communication between Django and Keycloak
    for user management operations — create, update, delete users.

    Why a separate service class:
    Keeping all Keycloak API calls in one place means:
    - Easy to test
    - Easy to update if Keycloak API changes
    - Views stay clean — they just call service methods
    - If Keycloak is down, the error is handled here

    How admin authentication works:
    The Keycloak Admin API requires an access token to prove
    the caller has permission to manage users.
    We get this token by logging in as the Keycloak admin user
    using the 'master' realm's token endpoint.
    This token expires in 60 seconds so we get a fresh one
    for every operation.
    """

    def __init__(self):
        from django.conf import settings
        self.server_url   = settings.KEYCLOAK_SERVER_URL
        self.realm        = settings.KEYCLOAK_REALM
        self.client_id    = settings.KEYCLOAK_CLIENT_ID
        self.client_secret = settings.KEYCLOAK_CLIENT_SECRET

        # Admin credentials — we add these to .env in a moment
        self.admin_username = getattr(settings, 'KEYCLOAK_ADMIN_USERNAME', 'admin')
        self.admin_password = getattr(settings, 'KEYCLOAK_ADMIN_PASSWORD', 'admin123')

    def _get_admin_token(self):
        """
        Gets a short-lived admin access token from Keycloak.

        We authenticate as the Keycloak admin user against the
        'master' realm (not our govasset realm).
        The master realm is Keycloak's own admin realm.

        Returns the access token string or raises an exception.
        """
        token_url = f"{self.server_url}/realms/master/protocol/openid-connect/token"

        response = requests.post(
            token_url,
            data={
                'grant_type': 'password',
                'client_id':  'admin-cli',
                'username':   self.admin_username,
                'password':   self.admin_password,
            },
            timeout=10
        )

        if response.status_code != 200:
            logger.error(
                f"Keycloak admin token failed: {response.status_code} "
                f"{response.text}"
            )
            raise Exception(
                f"Cannot connect to Keycloak admin. "
                f"Status: {response.status_code}"
            )

        return response.json()['access_token']

    def _get_headers(self):
        """
        Returns HTTP headers with the admin token.
        Used on every Admin API call.
        """
        token = self._get_admin_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type':  'application/json',
        }

    def create_user(self, username, email, first_name, last_name,
                    password, role, ministry_schema):
        """
        Creates a new user in Keycloak.

        Returns the Keycloak user UUID (keycloak_id) on success.
        Raises an exception on failure.

        Steps:
        1. Create the user record (without password)
        2. Set the password separately
        3. Set the custom attributes (role, ministry_schema)

        Why password is set separately:
        Keycloak's user creation endpoint does not accept a
        plain text password directly. Passwords are set via
        a separate credentials endpoint for security reasons.
        """
        headers  = self._get_headers()
        base_url = f"{self.server_url}/admin/realms/{self.realm}"

        # ── Step 1: Create the user ───────────────────────────────────────────
        user_data = {
            'username':   username,
            'email':      email,
            'firstName':  first_name,
            'lastName':   last_name,
            'enabled':    True,
            'attributes': {
                'role':            [role],
                'ministry_schema': [ministry_schema or ''],
            }
        }

        create_response = requests.post(
            f"{base_url}/users",
            json=user_data,
            headers=headers,
            timeout=10
        )

        if create_response.status_code == 409:
            raise Exception(
                f"Username '{username}' already exists in Keycloak."
            )

        if create_response.status_code not in [201, 200]:
            raise Exception(
                f"Failed to create user in Keycloak. "
                f"Status: {create_response.status_code}. "
                f"Response: {create_response.text}"
            )

        # ── Step 2: Get the new user's ID ─────────────────────────────────────
        # Keycloak returns the new user's URL in the Location header
        # The UUID is the last part of that URL
        location = create_response.headers.get('Location', '')
        keycloak_id = location.split('/')[-1]

        if not keycloak_id:
            # If Location header missing, search by username
            keycloak_id = self.get_user_id(username)

        if not keycloak_id:
            raise Exception(
                f"User created in Keycloak but could not retrieve UUID "
                f"for username '{username}'"
            )

        # ── Step 3: Set the password ──────────────────────────────────────────
        password_response = requests.put(
            f"{base_url}/users/{keycloak_id}/reset-password",
            json={
                'type':      'password',
                'value':     password,
                'temporary': False,
                # temporary=False means user does NOT need to change
                # password on first login
            },
            headers=headers,
            timeout=10
        )

        if password_response.status_code not in [204, 200]:
            # Password failed — delete the user we just created
            # so we don't have a user without a password
            self.delete_user(keycloak_id)
            raise Exception(
                f"Failed to set password for '{username}' in Keycloak. "
                f"Status: {password_response.status_code}"
            )

        logger.info(
            f"Keycloak: Created user '{username}' with ID {keycloak_id}"
        )

        return keycloak_id

    def get_user_id(self, username):
        """
        Searches Keycloak for a user by username and returns their UUID.
        Used as fallback when Location header is missing.
        """
        headers = self._get_headers()
        base_url = f"{self.server_url}/admin/realms/{self.realm}"

        response = requests.get(
            f"{base_url}/users",
            params={'username': username, 'exact': 'true'},
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            users = response.json()
            if users:
                return users[0]['id']

        return None

    def delete_user(self, keycloak_id):
        """
        Deletes a user from Keycloak by their UUID.
        Called for rollback when Django user creation fails
        after Keycloak user was already created.
        """
        try:
            headers  = self._get_headers()
            base_url = f"{self.server_url}/admin/realms/{self.realm}"

            requests.delete(
                f"{base_url}/users/{keycloak_id}",
                headers=headers,
                timeout=10
            )
            logger.info(f"Keycloak: Deleted user {keycloak_id} (rollback)")
        except Exception as e:
            logger.error(f"Keycloak: Rollback delete failed: {e}")

    def update_user(self, keycloak_id, email=None, first_name=None,
                    last_name=None, role=None, ministry_schema=None,
                    is_active=None):
        """
        Updates an existing Keycloak user's information.
        Called when admin edits a user in Django.
        Only updates fields that are provided (not None).
        """
        headers  = self._get_headers()
        base_url = f"{self.server_url}/admin/realms/{self.realm}"

        update_data = {}
        if email        is not None: update_data['email']     = email
        if first_name   is not None: update_data['firstName'] = first_name
        if last_name    is not None: update_data['lastName']  = last_name
        if is_active    is not None: update_data['enabled']   = is_active

        if role is not None or ministry_schema is not None:
            update_data['attributes'] = {}
            if role             is not None:
                update_data['attributes']['role'] = [role]
            if ministry_schema  is not None:
                update_data['attributes']['ministry_schema'] = [
                    ministry_schema or ''
                ]

        if not update_data:
            return

        response = requests.put(
            f"{base_url}/users/{keycloak_id}",
            json=update_data,
            headers=headers,
            timeout=10
        )

        if response.status_code not in [204, 200]:
            raise Exception(
                f"Failed to update user in Keycloak. "
                f"Status: {response.status_code}"
            )

        logger.info(f"Keycloak: Updated user {keycloak_id}")

    def reset_password(self, keycloak_id, new_password):
        """
        Resets a user's password in Keycloak.
        Called when admin resets password in Django.
        """
        headers  = self._get_headers()
        base_url = f"{self.server_url}/admin/realms/{self.realm}"

        response = requests.put(
            f"{base_url}/users/{keycloak_id}/reset-password",
            json={
                'type':      'password',
                'value':     new_password,
                'temporary': False,
            },
            headers=headers,
            timeout=10
        )

        if response.status_code not in [204, 200]:
            raise Exception(
                f"Failed to reset password in Keycloak. "
                f"Status: {response.status_code}"
            )

        logger.info(f"Keycloak: Reset password for user {keycloak_id}")