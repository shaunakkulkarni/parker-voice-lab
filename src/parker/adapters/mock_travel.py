"""Deterministic calendar/flight/weather mock for travel prep."""

from __future__ import annotations

from typing import Any

from parker.contracts.domains import FlightInfo, TravelPlan


class MockTravel:
    """Travel preparation and gated check-in."""

    def __init__(self) -> None:
        self.trips: dict[str, dict[str, Any]] = {
            "new_york": {
                "destination": "New York",
                "departure_time": "2026-08-12T08:15:00",
                "flight_number": "UA412",
                "weather": "Clear, 24C",
                "packing": ["charger", "badge", "jacket", "toiletries"],
                "check_in_open": True,
            },
            "tomorrow": {
                "destination": "Chicago",
                "departure_time": "2026-08-08T07:00:00",
                "flight_number": "AA190",
                "weather": "Rain, 16C",
                "packing": ["umbrella", "charger", "notes"],
                "check_in_open": True,
            },
        }
        self.checked_in: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.stale_flight = False

    def reset(self) -> None:
        self.checked_in.clear()
        self.calls.clear()
        self.stale_flight = False

    def prepare(self, destination_key: str) -> TravelPlan | None:
        key = destination_key.strip().lower().replace(" ", "_")
        if key in {"new york", "ny", "nyc"}:
            key = "new_york"
        trip = self.trips.get(key)
        self.calls.append({"command": "prepare", "destination": key})
        if trip is None:
            return None
        flight = FlightInfo(
            flight_number=str(trip["flight_number"]),
            destination=str(trip["destination"]),
            departure_time=str(trip["departure_time"]),
            check_in_open=bool(trip["check_in_open"]),
            stale=self.stale_flight,
        )
        packing = list(trip["packing"])
        spoken = (
            f"Trip plan for {trip['destination']}: depart "
            f"{trip['departure_time']}, flight {trip['flight_number']}. "
            f"Weather: {trip['weather']}. Pack {', '.join(packing)}. "
            "Home readiness: lights off checklist ready. "
            "Check-in is available when you confirm."
        )
        if self.stale_flight:
            spoken += " Flight data may be stale."
        return TravelPlan(
            destination=str(trip["destination"]),
            packing_list=packing,
            departure_time=str(trip["departure_time"]),
            weather_summary=str(trip["weather"]),
            flight=flight,
            home_readiness=["lights_off_checklist", "lock_review"],
            spoken=spoken,
            check_in_pending=True,
        )

    def check_in(self, flight_number: str) -> dict[str, Any]:
        self.calls.append({"command": "check_in", "flight": flight_number})
        self.checked_in.append(flight_number)
        return {
            "success": True,
            "flight_number": flight_number,
            "confirmation": f"CHECKED-IN-{flight_number}",
        }
