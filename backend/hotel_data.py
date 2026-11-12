"""Fail-closed port for an approved Workpeg hotel-data integration."""


class HotelDataIntegrationUnavailable(RuntimeError):
    """No supported, authorized hotel-data bridge is configured."""


class UnavailableHotelSnapshotReader:
    """Production default until an owner-approved bridge is implemented."""

    def read_snapshot(self, business_id):
        # The business identifier is intentionally not included in the error.
        raise HotelDataIntegrationUnavailable(
            "authorized_hotel_data_integration_unavailable"
        )
