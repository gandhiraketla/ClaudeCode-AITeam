"""Travel search tools: flights and hotels via SerpApi."""
from __future__ import annotations
import os
from datetime import datetime
from typing import Any

SERPAPI_AVAILABLE = False
try:
    from serpapi import GoogleSearch
    SERPAPI_AVAILABLE = True
except ImportError:
    pass

REQUIRED_FLIGHT_KEYS = {"airline", "departure_time", "arrival_time", "price"}
REQUIRED_HOTEL_KEYS = {"name", "price"}

# IATA city-to-code mapping for common ambiguous cities
CITY_TO_IATA: dict[str, str] = {
    "new york": "JFK", "ny": "JFK", "nyc": "JFK",
    "los angeles": "LAX", "la": "LAX",
    "chicago": "ORD",
    "london": "LHR",
    "paris": "CDG",
    "tokyo": "NRT",
    "dubai": "DXB",
    "sydney": "SYD",
    "dallas": "DFW", "dfw": "DFW",
    "miami": "MIA",
    "san francisco": "SFO", "sf": "SFO",
    "boston": "BOS",
    "seattle": "SEA",
    "denver": "DEN",
    "atlanta": "ATL",
    "frankfurt": "FRA",
    "amsterdam": "AMS",
    "singapore": "SIN",
    "toronto": "YYZ",
    "vancouver": "YVR",
    "rome": "FCO",
    "barcelona": "BCN",
    "madrid": "MAD",
}


def resolve_iata(city_or_code: str) -> str:
    """Resolve city name or IATA code to uppercase IATA code."""
    if not city_or_code:
        return ""
    normalized = city_or_code.strip().lower()
    if normalized in CITY_TO_IATA:
        return CITY_TO_IATA[normalized]
    # Assume it's already an IATA code
    return city_or_code.strip().upper()


def _get_api_key() -> str:
    key = os.environ.get("SERPAPI_API_KEY", "")
    return key


def _validate_flight_result(raw: dict) -> dict | None:
    """Validate and normalize a single flight result dict. Returns None if invalid."""
    try:
        airline = raw.get("airline") or raw.get("flights", [{}])[0].get("airline", "Unknown")
        departure = raw.get("departure_airport", {}).get("time") or raw.get("departure_time", "")
        arrival = raw.get("arrival_airport", {}).get("time") or raw.get("arrival_time", "")
        price = raw.get("price", 0)
        if not isinstance(price, (int, float)):
            try:
                price = float(str(price).replace("$", "").replace(",", ""))
            except (ValueError, TypeError):
                price = 0
        flight_number = ""
        if raw.get("flights"):
            first = raw["flights"][0]
            flight_number = first.get("flight_number", "")
            if not airline or airline == "Unknown":
                airline = first.get("airline", "Unknown")
            if not departure:
                departure = first.get("departure_airport", {}).get("time", "")
            if not arrival:
                arrival = first.get("arrival_airport", {}).get("time", "")
        return {
            "airline": str(airline)[:100],
            "flight_number": str(flight_number)[:20],
            "departure_time": str(departure)[:50],
            "arrival_time": str(arrival)[:50],
            "duration_minutes": int(raw.get("total_duration", 0)),
            "price_usd": float(price),
            "stops": int(raw.get("layovers", 0)) if isinstance(raw.get("layovers"), int)
                      else len(raw.get("layovers", [])),
            "booking_url": None,
        }
    except Exception:
        return None


def _validate_hotel_result(raw: dict) -> dict | None:
    """Validate and normalize a single hotel result dict. Returns None if invalid."""
    try:
        name = raw.get("name", "")
        if not name:
            return None
        price_per_night = raw.get("rate_per_night", {}).get("lowest") or raw.get("price", 0)
        if not isinstance(price_per_night, (int, float)):
            try:
                price_per_night = float(str(price_per_night).replace("$", "").replace(",", ""))
            except (ValueError, TypeError):
                price_per_night = 0
        total = raw.get("total_rate", {}).get("lowest") or raw.get("total_price", price_per_night)
        if not isinstance(total, (int, float)):
            try:
                total = float(str(total).replace("$", "").replace(",", ""))
            except (ValueError, TypeError):
                total = price_per_night
        amenities = raw.get("amenities", [])
        if not isinstance(amenities, list):
            amenities = []
        amenities = [str(a)[:80] for a in amenities[:10]]
        return {
            "name": str(name)[:150],
            "star_rating": float(raw.get("overall_rating", raw.get("star_rating", 0)) or 0),
            "price_per_night_usd": float(price_per_night),
            "total_price_usd": float(total),
            "address": str(raw.get("address", ""))[:200],
            "amenities": amenities,
            "booking_url": None,
        }
    except Exception:
        return None


def search_flights(
    origin_iata: str,
    destination_iata: str,
    departure_date: str,
    return_date: str | None = None,
    num_travelers: int = 1,
    currency: str = "USD",
) -> dict:
    """Search real-time flights via SerpApi google_flights engine."""
    if not origin_iata or not destination_iata or not departure_date:
        return {"flights": None, "search_timestamp": _now(), "error": "Missing required fields: origin, destination, or departure_date."}

    origin_iata = resolve_iata(origin_iata)
    destination_iata = resolve_iata(destination_iata)

    if not SERPAPI_AVAILABLE:
        return {"flights": None, "search_timestamp": _now(), "error": "SerpApi client not installed."}

    api_key = _get_api_key()
    if not api_key:
        return {"flights": None, "search_timestamp": _now(), "error": "Flight search service unavailable."}

    params: dict[str, Any] = {
        "engine": "google_flights",
        "departure_id": origin_iata,
        "arrival_id": destination_iata,
        "outbound_date": departure_date,
        "adults": num_travelers,
        "currency": currency,
        "hl": "en",
        "api_key": api_key,
    }
    if return_date:
        params["return_date"] = return_date
        params["type"] = "1"  # round trip
    else:
        params["type"] = "2"  # one way

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
    except Exception:
        return {"flights": None, "search_timestamp": _now(), "error": "Flight search service is temporarily unavailable."}

    if "error" in results:
        return {"flights": None, "search_timestamp": _now(), "error": "Flight search returned no results for this route and date."}

    raw_flights = results.get("best_flights", []) + results.get("other_flights", [])
    flights = []
    for rf in raw_flights[:10]:
        validated = _validate_flight_result(rf)
        if validated:
            flights.append(validated)

    return {
        "flights": flights if flights else None,
        "search_timestamp": _now(),
        "error": None if flights else "No flights found for this route and date.",
    }


def search_hotels(
    destination: str,
    check_in_date: str,
    check_out_date: str,
    num_guests: int = 1,
    budget_usd_per_night: float | None = None,
) -> dict:
    """Search real-time hotels via SerpApi google_hotels engine."""
    if not destination or not check_in_date or not check_out_date:
        return {"hotels": None, "search_timestamp": _now(), "error": "Missing required fields: destination, check_in_date, or check_out_date."}

    if not SERPAPI_AVAILABLE:
        return {"hotels": None, "search_timestamp": _now(), "error": "SerpApi client not installed."}

    api_key = _get_api_key()
    if not api_key:
        return {"hotels": None, "search_timestamp": _now(), "error": "Hotel search service unavailable."}

    params: dict[str, Any] = {
        "engine": "google_hotels",
        "q": f"hotels in {destination}",
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "adults": num_guests,
        "currency": "USD",
        "hl": "en",
        "api_key": api_key,
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
    except Exception:
        return {"hotels": None, "search_timestamp": _now(), "error": "Hotel search service is temporarily unavailable."}

    if "error" in results:
        return {"hotels": None, "search_timestamp": _now(), "error": "Hotel search returned no results for this destination and dates."}

    raw_hotels = results.get("properties", [])
    hotels = []
    for rh in raw_hotels[:10]:
        if budget_usd_per_night:
            price_raw = rh.get("rate_per_night", {}).get("lowest", 0)
            try:
                price_val = float(str(price_raw).replace("$", "").replace(",", ""))
                if price_val > budget_usd_per_night * 1.2:
                    continue
            except (ValueError, TypeError):
                pass
        validated = _validate_hotel_result(rh)
        if validated:
            hotels.append(validated)

    return {
        "hotels": hotels if hotels else None,
        "search_timestamp": _now(),
        "error": None if hotels else "No hotels found for this destination and dates.",
    }


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"
