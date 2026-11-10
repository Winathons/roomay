"""Fail-closed backend configuration; secrets are never logged or returned."""
from dataclasses import dataclass
import os
from uuid import UUID


def normalize_peg_uuid(value):
    """Return Workpeg's Peg identifier in canonical UUID text form."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("peg_uuid_invalid")
    try:
        return str(UUID(value.strip()))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("peg_uuid_invalid") from None


@dataclass(frozen=True)
class Settings:
    database_url: str
    workpeg_pk: str
    workpeg_api: str
    peg_id: str
    business_id: str
    hotel_id: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_uri: str
    public_base_url: str
    cookie_secure: bool
    bootstrap_owner_enabled: bool

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.environ.get("ROOMAY_DATABASE_URL", ""),
            workpeg_pk=os.environ.get("WORKPEG_PK", ""),
            workpeg_api=os.environ.get("WORKPEG_API", "https://api.workpeg.com").rstrip("/"),
            peg_id=os.environ.get("ROOMAY_WORKPEG_PEG_ID", ""),
            business_id=os.environ.get("ROOMAY_WORKPEG_BUSINESS_ID", ""),
            hotel_id=os.environ.get("ROOMAY_HOTEL_ID", ""),
            oidc_client_id=os.environ.get("WORKPEG_OIDC_CLIENT_ID", ""),
            oidc_client_secret=os.environ.get("WORKPEG_OIDC_CLIENT_SECRET", ""),
            oidc_redirect_uri=os.environ.get("ROOMAY_OIDC_REDIRECT_URI", ""),
            public_base_url=os.environ.get("ROOMAY_PUBLIC_BASE_URL", ""),
            cookie_secure=os.environ.get("ROOMAY_COOKIE_SECURE", "true").lower() == "true",
            bootstrap_owner_enabled=os.environ.get("ROOMAY_BOOTSTRAP_OWNER_ENABLED", "false").lower() == "true",
        )

    def validate(self):
        required = (self.database_url, self.workpeg_pk, self.peg_id, self.business_id, self.hotel_id,
                    self.oidc_client_id, self.oidc_redirect_uri,
                    self.public_base_url)
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise RuntimeError("backend_configuration_incomplete")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise RuntimeError("production_database_must_be_postgresql")
        if (not self.oidc_redirect_uri.startswith("https://")
                or not self.public_base_url.startswith("https://")):
            raise RuntimeError("production_urls_must_use_https")
        if self.workpeg_api != "https://api.workpeg.com":
            raise RuntimeError("workpeg_api_endpoint_not_supported")
        if not self.cookie_secure:
            raise RuntimeError("secure_cookies_required")
        try:
            normalized_peg_id = normalize_peg_uuid(self.peg_id)
            if (str(UUID(self.business_id)) != self.business_id
                    or str(UUID(self.hotel_id)) != self.hotel_id
                    or not normalized_peg_id):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise RuntimeError("workpeg_business_and_peg_binding_invalid") from None
        object.__setattr__(self, "peg_id", normalized_peg_id)
        return self
