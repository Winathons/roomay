from unittest import TestCase

from backend.config import Settings


class BackendConfigurationTests(TestCase):
    def valid(self, **changes):
        values = {
            "database_url": "postgresql+psycopg://roomay:ignored@localhost/roomay",
            "workpeg_pk": "test-only-value",
            "workpeg_api": "https://api.workpeg.com",
            "peg_id": "4812",
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
        with self.assertRaisesRegex(RuntimeError, "workpeg_api_endpoint_not_supported"):
            self.valid(workpeg_api="https://unexpected.example").validate()
        with self.assertRaisesRegex(RuntimeError, "secure_cookies_required"):
            self.valid(cookie_secure=False).validate()

    def test_configuration_requires_server_authentication_and_peg_binding(self):
        with self.assertRaisesRegex(RuntimeError, "backend_configuration_incomplete"):
            self.valid(workpeg_pk="").validate()
        with self.assertRaisesRegex(RuntimeError, "backend_configuration_incomplete"):
            self.valid(oidc_client_id="").validate()
        with self.assertRaisesRegex(RuntimeError, "workpeg_business_and_peg_binding_invalid"):
            self.valid(business_id="browser-supplied").validate()


if __name__ == "__main__":
    import unittest
    unittest.main()
