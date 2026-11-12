"""Owner-run staff mapping CLI; only accepts OIDC subject IDs and reviewed roles."""
import argparse
from uuid import UUID, uuid4

from .config import Settings
from .db import make_database
from .models import HotelBinding, StaffBinding

DEPARTMENTS = {"reception", "housekeeping", "maintenance", "food_and_beverage"}
PRIVILEGES = {"hotel_manager", "incident_manager", "request_admin"}


def main():
    parser = argparse.ArgumentParser(description="Bind a verified Workpeg OIDC subject to Roomay hotel duties")
    parser.add_argument("--business-id", required=True)
    parser.add_argument("--hotel-id", required=True)
    parser.add_argument("--subject", required=True, help="Workpeg OIDC subject, never email")
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--department", choices=sorted(DEPARTMENTS), required=True)
    parser.add_argument("--roles", default="", help="Comma-separated least-privilege Roomay roles")
    args = parser.parse_args()
    roles = sorted(set(filter(None, args.roles.split(","))))
    if set(roles) - PRIVILEGES:
        parser.error("unsupported Roomay role")
    settings = Settings.from_env()
    if not settings.database_url.startswith("postgresql+psycopg://"):
        parser.error("staff mappings require the configured PostgreSQL operational database")
    if args.business_id != settings.business_id:
        parser.error("business id does not match the configured Roomay business")
    if args.hotel_id != settings.hotel_id:
        parser.error("hotel id does not match the configured Roomay hotel")
    try:
        if str(UUID(args.business_id)) != args.business_id or str(UUID(args.hotel_id)) != args.hotel_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        parser.error("business and hotel identifiers must be canonical UUIDs")
    _, sessions = make_database(settings.database_url)
    with sessions.begin() as db:
        binding = db.get(HotelBinding, args.business_id)
        if binding and binding.hotel_id != args.hotel_id:
            parser.error("business is already bound to a different hotel")
        if not binding:
            db.add(HotelBinding(business_id=args.business_id, hotel_id=args.hotel_id, active=True))
        staff = db.query(StaffBinding).filter_by(business_id=args.business_id,
                                                  workpeg_subject=args.subject).one_or_none()
        if staff:
            staff.actor_id, staff.hotel_id = args.actor_id, args.hotel_id
            staff.department, staff.roles, staff.active = args.department, roles, True
        else:
            db.add(StaffBinding(id=str(uuid4()), business_id=args.business_id,
                                hotel_id=args.hotel_id, workpeg_subject=args.subject,
                                actor_id=args.actor_id, department=args.department,
                                roles=roles, active=True))
    print("Staff mapping saved. No Workpeg data was changed.")


if __name__ == "__main__":
    main()
