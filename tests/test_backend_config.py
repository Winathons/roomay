import os
from unittest import TestCase
from unittest.mock import patch

from backend.config import Settings, require_experimental_backend_opt_in


class BackendConfigurationTests(TestCase):
    def valid(self, **changes):
        values = {
            "database_url": "postgresql+psycopg://roomay:ignored@localhost/roomay",
            "business_id": "6fca06b2-9bcb-4b24-bba4-60591fcadd8e",
            "hotel_id": "1ec2baa5-37ca-41a3-bf03-b433bf0384a5",
            "oidc_client_id": "test-client",
            "oidc_client_secret": "",
            "oidc_redirect_uri": "https://roomay.example/auth/workpeg/callback",
            "public_base_url": "https://roomay.example",
            "cookie_secure": True,
            "bootstrap_owner_enabled": False,
        }
        values.update(changes)
        return Settings(**values)

    def test_configuration_requires_postgresql_and_https(self):
        settings = self.valid()
        self.assertIs(settings.validate(), settings)
        with self.assertRaisesRegex(RuntimeError, "production_database_must_be_postgresql"):
            self.valid(database_url="sqlite:///local.db").validate()
        with self.assertRaisesRegex(RuntimeError, "production_urls_must_use_https"):
            self.valid(public_base_url="http://roomay.example").validate()
        with self.assertRaisesRegex(RuntimeError, "secure_cookies_required"):
            self.valid(cookie_secure=False).validate()

    def test_oidc_registration_is_required_but_standalone_tables_token_is_not(self):
        with self.assertRaisesRegex(RuntimeError, "backend_configuration_incomplete"):
            self.valid(oidc_client_id="").validate()

        values = {
            "ROOMAY_DATABASE_URL": self.valid().database_url,
            "ROOMAY_WORKPEG_BUSINESS_ID": self.valid().business_id,
            "ROOMAY_HOTEL_ID": self.valid().hotel_id,
            "WORKPEG_OIDC_CLIENT_ID": self.valid().oidc_client_id,
            "WORKPEG_OIDC_CLIENT_SECRET": "",
            "ROOMAY_OIDC_REDIRECT_URI": self.valid().oidc_redirect_uri,
            "ROOMAY_PUBLIC_BASE_URL": self.valid().public_base_url,
            "ROOMAY_COOKIE_SECURE": "true",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = Settings.from_env().validate()
        self.assertFalse(hasattr(settings, "workpeg_pk"))
        self.assertNotIn("WORKPEG_PK", values)

    def test_oidc_callback_is_pinned_to_exact_backend_https_origin(self):
        self.assertIs(self.valid().validate().__class__, Settings)
        self.assertIsNotNone(self.valid(
            public_base_url="https://roomay.example/",
        ).validate())
        for changes in (
            {"oidc_redirect_uri": "https://untrusted.example/auth/workpeg/callback"},
            {"oidc_redirect_uri": "https://roomay.example/incorrect/callback"},
            {"oidc_redirect_uri": "https://roomay.example/auth/workpeg/callback?code=unsafe"},
            {"oidc_redirect_uri": "https://user@roomay.example/auth/workpeg/callback"},
            {"public_base_url": "https://roomay.example/app"},
            {"public_base_url": "https://user@roomay.example"},
            {"public_base_url": "https://roomay.example?next=unsafe"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(
                    RuntimeError, "oidc_callback_must_match_public_origin|public_base_url_must_be_https_origin",
                ):
                    self.valid(**changes).validate()

    def test_standalone_backend_is_disabled_by_default(self):
        for values in ({}, {"ROOMAY_ENABLE_STANDALONE_PROTOTYPE": ""},
                       {"ROOMAY_ENABLE_STANDALONE_PROTOTYPE": "true"},
                       {"ROOMAY_ENABLE_STANDALONE_PROTOTYPE": "production"}):
            with self.subTest(values=values):
                with self.assertRaisesRegex(
                    RuntimeError, "standalone_guest_backend_disabled_pending_workpeg_integration"
                ):
                    require_experimental_backend_opt_in(values)
        # This acknowledges a test-only local prototype, NOT Workpeg authorization.
        require_experimental_backend_opt_in(
            {"ROOMAY_ENABLE_STANDALONE_PROTOTYPE": "local-only"}
        )

    def test_default_asgi_module_import_is_blocked_before_db_setup(self):
        # No environment values or DB credentials should be required to refuse
        # startup: the operational safety gate must run first.
        import subprocess
        import sys
        with patch.dict(os.environ, {}, clear=True):
            result = subprocess.run(
                [sys.executable, "-c", "import backend.main"],
                capture_output=True, text=True, timeout=10,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "standalone_guest_backend_disabled_pending_workpeg_integration",
            result.stderr,
        )

    def test_business_and_hotel_bindings_must_be_canonical_uuids(self):
        with self.assertRaisesRegex(RuntimeError, "workpeg_business_and_hotel_binding_invalid"):
            self.valid(business_id="browser-supplied").validate()
        with self.assertRaisesRegex(RuntimeError, "backend_configuration_incomplete"):
            self.valid(hotel_id="").validate()


if __name__ == "__main__":
    import unittest
    unittest.main()
