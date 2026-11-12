"""Offline server-side boundary for Workpeg-verified hotel staff identities.

This does NOT verify a Workpeg token or session. A production caller must first
complete Workpeg's OIDC flow on a trusted server, including PKCE, state, nonce,
issuer, audience, signature and expiry checks, and pass the resulting verified
identity through a server-owned session provider. The member checker, hotel
mapping and staff roster are also trusted SERVER ports, not browser payloads.

No Workpeg API requests, permissions, writes, or routes are provided here.
"""
from uuid import UUID


WORKPEG_STAFF_ROLES = frozenset({"owner", "admin", "member"})
DEPARTMENTS = frozenset({
    "reception", "housekeeping", "maintenance", "food_and_beverage",
})
ROOMAY_STAFF_PRIVILEGES = frozenset({
    "request_admin", "hotel_manager", "incident_manager",
})
ROSTER_FIELDS = frozenset({
    "workpeg_subject", "actor_id", "hotel_id", "department", "roles", "active",
})
DOMAIN_DIRECTORY_FIELDS = (
    "actor_id", "hotel_id", "department", "roles", "active",
)


class TrustedStaffIdentityError(ValueError):
    """Refusal code with no private provider or session information."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


class TrustedWorkpegStaffResolver:
    """Implement the identity_resolver port for StaffActionGateway.

    Required external, server-only ports:
      verified_sessions.resolve_verified(session_proof):
          return identity from a VERIFIED WorkpegAuth.complete() callback,
          stored and revalidated in a server-controlled session. Never accept
          client-submitted identity JSON or unverified JWT claims.
      business_membership.is_current_staff(subject, business_id):
          check fresh server-authoritative active business membership.
      hotel_mapping.resolve_hotel(business_id):
          return the authoritative hotel UUID for this business.
      staff_roster.list_staff(business_id, hotel_id):
          return current server-maintained roster rows with exact ROSTER_FIELDS.

    Workpeg's OIDC role (owner/admin/member) establishes only a Workpeg
    membership type. A Roomay department and request privileges come SOLELY
    from the trusted roster. Email and names never serve as identity keys.
    """

    def __init__(self, verified_sessions, business_membership,
                 hotel_mapping, staff_roster):
        methods = (
            (verified_sessions, "resolve_verified"),
            (business_membership, "is_current_staff"),
            (hotel_mapping, "resolve_hotel"),
            (staff_roster, "list_staff"),
        )
        if any(not callable(getattr(port, method, None))
               for port, method in methods):
            raise TrustedStaffIdentityError("trusted_staff_ports_required")
        self.verified_sessions = verified_sessions
        self.business_membership = business_membership
        self.hotel_mapping = hotel_mapping
        self.staff_roster = staff_roster

    def resolve(self, session_proof):
        """Resolve one verified OIDC subject to an active hotel staff record.

        Returns the exact keys required by StaffActionGateway. Returns no
        tokens, email, browser roles, table payloads or guest data.
        """
        try:
            principal = self.verified_sessions.resolve_verified(session_proof)
        except Exception:
            raise TrustedStaffIdentityError("staff_identity_unavailable") from None
        # A mapping of unverified browser-provided claims must never be
        # mistaken for the SDK's verified identity object.
        if principal is None or isinstance(principal, dict):
            raise TrustedStaffIdentityError("staff_identity_unverified")
        subject = getattr(principal, "subject", None)
        business_id = getattr(principal, "business_id", None)
        workpeg_role = getattr(principal, "role", None)
        if (not isinstance(subject, str) or not subject.strip()
                or not _uuid(business_id)
                or not isinstance(workpeg_role, str)
                or workpeg_role not in WORKPEG_STAFF_ROLES):
            raise TrustedStaffIdentityError("staff_identity_unverified")

        try:
            member = self.business_membership.is_current_staff(subject, business_id)
        except Exception:
            raise TrustedStaffIdentityError("staff_membership_unavailable") from None
        if member is not True:
            raise TrustedStaffIdentityError("staff_membership_unverified")

        try:
            hotel_id = self.hotel_mapping.resolve_hotel(business_id)
        except Exception:
            raise TrustedStaffIdentityError("staff_hotel_mapping_unavailable") from None
        if not _uuid(hotel_id):
            raise TrustedStaffIdentityError("staff_hotel_mapping_unverified")

        try:
            roster = self.staff_roster.list_staff(business_id, hotel_id)
        except Exception:
            raise TrustedStaffIdentityError("staff_directory_unavailable") from None
        if not isinstance(roster, list) or not roster:
            raise TrustedStaffIdentityError("staff_directory_unverified")
        seen_subjects = set()
        seen_actors = set()
        matched = None
        domain_directory = []
        for row in roster:
            if not isinstance(row, dict) or set(row) != ROSTER_FIELDS:
                raise TrustedStaffIdentityError("staff_directory_unverified")
            binding = row["workpeg_subject"]
            actor_id = row["actor_id"]
            department = row["department"]
            roles = row["roles"]
            if (not isinstance(binding, str) or not binding.strip()
                    or not isinstance(actor_id, str) or not actor_id.strip()
                    or binding in seen_subjects or actor_id in seen_actors
                    or row["hotel_id"] != hotel_id
                    or not isinstance(department, str)
                    or department not in DEPARTMENTS
                    or type(row["active"]) is not bool
                    or not isinstance(roles, list)
                    or not all(isinstance(role, str)
                               and role in ROOMAY_STAFF_PRIVILEGES
                               for role in roles)
                    or len(roles) != len(set(roles))):
                raise TrustedStaffIdentityError("staff_directory_unverified")
            seen_subjects.add(binding)
            seen_actors.add(actor_id)
            normalized = {field: row[field] for field in DOMAIN_DIRECTORY_FIELDS}
            normalized["roles"] = list(roles)
            domain_directory.append(normalized)
            if binding == subject:
                matched = normalized

        if matched is None or matched["active"] is not True:
            raise TrustedStaffIdentityError("staff_not_authorized")

        return {
            "authenticated": True,
            "membership_verified": True,
            "business_binding_verified": True,
            "active": True,
            "actor_id": matched["actor_id"],
            "business_id": business_id,
            "hotel_id": hotel_id,
            "department": matched["department"],
            "roles": list(matched["roles"]),
            "staff_directory": domain_directory,
        }
