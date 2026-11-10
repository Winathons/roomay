from unittest import TestCase

from backend.config import Settings


class BackendConfigurationTests(TestCase):
    def valid(self, **changes):
        values = {
            "database_url": "postgresql+psycopg://roomay:ignored@localhost/roomay",
            "workpeg_pk": "test-only-value",
            "workpeg_api": "https://api.workpeg.com",
            "peg_id": "6fca06b2-9bcb-4b24-bba4-60591fcadd8e",
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

    def test_peg_id_requires_uuid_and_normalizes_to_canonical_lowercase(self):
        uppercase = "6FCA06B2-9BCB-4B24-BBA4-60591FCADD8E"
        settings = self.valid(peg_id=uppercase)
        self.assertIs(settings.validate(), settings)
        self.assertEqual(settings.peg_id, uppercase.lower())

    def test_peg_id_rejects_numeric_and_malformed_identifiers(self):
        with self.assertRaisesRegex(RuntimeError, "backend_configuration_incomplete"):
            self.valid(peg_id="").validate()
        for invalid in ("4812", "not-a-uuid", "00000000-0000-0000-0000-00000000000Z"):
            with self.subTest(peg_id=invalid):
                with self.assertRaisesRegex(RuntimeError, "workpeg_business_and_peg_binding_invalid"):
                    self.valid(peg_id=invalid).validate()


if __name__ == "__main__":
    import unittest
    unittest.main()
