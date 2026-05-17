"""Demo script for the Travel Itinerary Agent — runs without user interaction."""
import os
import sys
import json
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

load_dotenv()

# Mock Streamlit session_state before importing agent modules
class MockSessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)
    def __setattr__(self, key, value):
        self[key] = value
    def get(self, key, default=None):
        return super().get(key, default)

mock_state = MockSessionState()

mock_st = MagicMock()
mock_st.session_state = mock_state

sys.modules["streamlit"] = mock_st

from src.state import init_state
from src.agent import run_agent


MOCK_FLIGHTS = [
    {
        "airline": "American Airlines",
        "flight_number": "AA100",
        "departure_time": "2025-06-10T08:00:00",
        "arrival_time": "2025-06-10T21:30:00",
        "duration_minutes": 450,
        "price_usd": 680.0,
        "stops": 0,
        "booking_url": None,
    }
]

MOCK_HOTELS = [
    {
        "name": "Hotel Le Marais",
        "star_rating": 4.2,
        "price_per_night_usd": 180.0,
        "total_price_usd": 900.0,
        "address": "Paris, France",
        "amenities": ["WiFi", "Breakfast", "Concierge"],
        "booking_url": None,
    }
]

MOCK_INTENT_RESULT = json.dumps({
    "intent": "full_itinerary",
    "slots": {
        "origin": "JFK",
        "destination": "Paris",
        "departure_date": "2025-06-10",
        "return_date": "2025-06-15",
        "check_in_date": "2025-06-10",
        "check_out_date": "2025-06-15",
        "num_travelers": 2,
        "budget_usd": None,
        "interests": ["museums", "food"]
    },
    "missing_required": []
})

MOCK_ITINERARY_RESULT = json.dumps({
    "itinerary_markdown": (
        "# Paris Trip Itinerary\n\n"
        "**Day 1: June 10, 2025**\n\n"
        "### Flights\n"
        "- American Airlines AA100 | JFK → CDG\n"
        "- Departs: 08:00 | Arrives: 21:30 | Duration: 7h 30m\n"
        "- Price: $680/person\n\n"
        "### Accommodation\n"
        "- Hotel Le Marais (4.2★) — $180/night\n"
        "- Amenities: WiFi, Breakfast, Concierge\n\n"
        "**Day 2: June 11, 2025**\n\n"
        "### Activities\n"
        "- Morning: Louvre Museum\n"
        "- Afternoon: Seine River Walk\n"
        "- Evening: Dinner in Le Marais district\n\n"
        "**Day 3-5: June 12-14, 2025**\n\n"
        "### Activities\n"
        "- Eiffel Tower, Musée d'Orsay, Montmartre\n\n"
        "**Day 6: June 15, 2025** — Departure"
    ),
    "days": 6,
    "warnings": []
})


def run_demo():
    print("=" * 60)
    print("Travel Itinerary Agent — Demo")
    print("=" * 60)

    sample_input = "Plan my trip to Paris for 5 days in June for 2 people, we love museums and food"
    print(f"\nUser: {sample_input}\n")

    call_responses = [MOCK_INTENT_RESULT, MOCK_ITINERARY_RESULT]
    call_index = {"i": 0}

    def mock_call_claude(system, user, max_tokens=1024):
        idx = call_index["i"]
        call_index["i"] += 1
        if idx < len(call_responses):
            return call_responses[idx]
        return json.dumps({"intent": "unclear", "slots": {}, "missing_required": []})

    mock_flights_return = {
        "flights": MOCK_FLIGHTS,
        "search_timestamp": "2025-06-01T12:00:00",
        "error": None
    }
    mock_hotels_return = {
        "hotels": MOCK_HOTELS,
        "search_timestamp": "2025-06-01T12:00:00",
        "error": None
    }

    with patch("src.agent._call_claude", side_effect=mock_call_claude), \
         patch("src.agent.search_flights", return_value=mock_flights_return), \
         patch("src.agent.search_hotels", return_value=mock_hotels_return):

        init_state()
        response = run_agent(sample_input)

    print("Agent Response:")
    print("-" * 60)
    print(response)
    print("-" * 60)
    print("\nDemo complete.")


if __name__ == "__main__":
    run_demo()
