from mozilla_django_oidc.auth import OIDCAuthenticationBackend
import logging

logger = logging.getLogger('authentication')


class GovAssetOIDCBackend(OIDCAuthenticationBackend):
    """
    Custom OIDC authentication backend for the Government Asset Platform.
    Connects Keycloak authentication to Django user accounts.
    """

    def filter_users_by_claims(self, claims):
        """
        Finds an existing Django user matching the Keycloak token.
        Called first on every SSO login.
        """
        from authentication.models import CustomUser

        # Log ALL claims so we can see exactly what Keycloak is sending
        logger.info(f"OIDC claims received: {claims}")

        keycloak_id = claims.get('sub', '')
        username    = claims.get('preferred_username', '')

        logger.info(
            f"OIDC: Looking for "
            f"keycloak_id={keycloak_id} username={username}"
        )

        # First try by keycloak_id
        if keycloak_id:
            users = CustomUser.objects.filter(keycloak_id=keycloak_id)
            if users.exists():
                logger.info(
                    f"OIDC: Found by keycloak_id: {username}"
                )
                return users

        # Second try by username
        if username:
            users = CustomUser.objects.filter(username=username)
            if users.exists():
                user = users.first()
                logger.info(
                    f"OIDC: Found by username: {username}"
                )
                if not user.keycloak_id and keycloak_id:
                    user.keycloak_id = keycloak_id
                    user.save(update_fields=['keycloak_id'])
                    logger.info(
                        f"OIDC: Linked {username} to {keycloak_id}"
                    )
                return users

        logger.warning(
            f"OIDC: No user found for "
            f"username={username} keycloak_id={keycloak_id}"
        )
        return CustomUser.objects.none()

    def create_user(self, claims):
        """
        Called when no existing Django user matches the token.
        We BLOCK auto-creation and record in PendingAccess instead.
        """
        username    = claims.get('preferred_username', '')
        email       = claims.get('email', '')
        full_name   = claims.get('name', '')
        keycloak_id = claims.get('sub', '')

        logger.warning(
            f"OIDC: No Django user found for Keycloak user: {username} "
            f"(keycloak_id: {keycloak_id}). Access blocked."
        )

        try:
            from authentication.models import PendingAccess
            PendingAccess.objects.create(
                username=username,
                email=email or '',
                full_name=full_name or '',
                keycloak_id=keycloak_id,
                status='PENDING',
            )
        except Exception as e:
            logger.error(
                f"OIDC: Failed to create PendingAccess: {e}"
            )

        # Flag this specific failure reason in the session so the
        # login page can show a clear "awaiting approval" message
        # instead of a generic error. Named WITHOUT an 'oidc_' prefix
        # so it survives the OIDC session cleanup in login_view.
        if self.request is not None:
            self.request.session['pending_access_notice'] = True

        return None

    def update_user(self, user, claims):
        """
        Called after a known user is found.
        Updates their info from the token.
        """

        
        keycloak_id     = claims.get('sub', '')
        ministry_schema = claims.get('ministry_schema', '')
        role            = claims.get('role', '')

        update_fields = []

        if keycloak_id and not user.keycloak_id:
            user.keycloak_id = keycloak_id
            update_fields.append('keycloak_id')

        valid_roles = [
            'SUPER_ADMIN', 'MINISTRY_ADMIN',
            'AGENCY_MANAGER', 'FACILITY_CLERK', 'AUDITOR'
        ]

        if role and role in valid_roles and user.role != role:
            user.role = role
            update_fields.append('role')

        if ministry_schema and user.ministry_schema != ministry_schema:
            user.ministry_schema = ministry_schema
            update_fields.append('ministry_schema')

        if update_fields:
            user.save(update_fields=update_fields)
            logger.info(
                f"OIDC: Updated user {user.username} "
                f"fields: {update_fields}"
            )

        return user

    def get_userinfo(self, access_token, id_token, payload):
        """
        Gets user information from the token payload.
        """
        userinfo = super().get_userinfo(
            access_token, id_token, payload
        )
        return userinfo