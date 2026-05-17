"""Travel search tools: flights via SerpApi google_flights, hotels via SerpApi google_hotels."""
from __future__ import annotations
import os
import logging
from datetime import datetime
from typing import Any
from serpapi import GoogleSearch

logger = logging.getLogger(__name__)

# IATA code map for common ambiguous cities
CITY_TO_IATA: dict[str, str] = {
    "new york": "JFK", "ny": "JFK", "nyc": "JFK",
    "los angeles": "LAX", "la": "LAX",
    "chicago": "ORD",
    "london": "LHR",
    "paris": "CDG",
    "tokyo": "NRT",
    "dallas": "DFW", "dfw": "DFW",
    "san francisco": "SFO", "sf": "SFO",
    "miami": "MIA",
    "boston": "BOS",
    "seattle": "SEA",
    "atlanta": "ATL",
    "denver": "DEN",
    "dubai": "DXB",
    "singapore": "SIN",
    "sydney": "SYD",
    "toronto": "YYZ",
    "amsterdam": "AMS",
    "frankfurt": "FRA",
    "madrid": "MAD",
    "rome": "FCO",
    "barcelona": "BCN",
    "bangkok": "BKK",
}


def _get_api_key() -> str:
    key = os.environ.get("SERPAPI_API_KEY", "")
    if not key:
        raise EnvironmentError("SERPAPI_API_KEY is not set")
    return key


def _normalize_iata(value: str) -> str | None:
    """Return a 3-letter IATA code from user input, or None if unresolvable."""
    if not value:
        return None
    v = value.strip()
    if len(v) == 3 and v.isalpha():
        return v.upper()
    lower = v.lower()
    return CITY_TO_IATA.get(lower)


def _normalize_date(value: str) -> str | None:
    """Return an ISO8601 date string (YYYY-MM-DD), or None if unparseable."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _scrub_key(text: str) -> str:
    """Remove API key substrings from error strings before returning to caller."""
    key = os.environ.get("SERPAPI_API_KEY", "")
    if key and key in text:
        text = text.replace(key, "[REDACTED]")
    return text


def _validate_flight_result(raw: dict) -> dict:
    """Parse and validate a single raw flight result from SerpApi."""
    required = {"airline", "departure_time", "arrival_time", "price"}
    if not isinstance(raw, dict):
        return {}
    if not required.issubset(raw.keys()):
        return {}
    try:
        price = float(str(raw.get("price", "0")).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        price = 0.0
    return {
        "airline": str(raw.get("airline", ""))[:100],
        "flight_number": str(raw.get("flight_number", ""))[:20],
        "departure_time": str(raw.get("departure_time", ""))[:50],
        "arrival_time": str(raw.get("arrival_time", ""))[:50],
        "duration_minutes": int(raw.get("duration", 0) or 0),
        "price_usd": price,
        "stops": int(raw.get("stops", 0) or 0),
        "booking_url": str(raw.get("booking_url", ""))[:500] if raw.get("booking_url") else None,
    }


def _validate_hotel_result(raw: dict) -> dict:
    """Parse and validate a single raw hotel result from SerpApi."""
    if not isinstance(raw, dict):
        return {}
    if not raw.get("name"):
        return {}
    try:
        ppn = float(str(raw.get("rate_per_night", {}).get("extracted_lowest", 0) or 0))
    except (ValueError, TypeError, AttributeError):
        ppn = 0.0
    try:
        total = float(str(raw.get("total_rate", {}).get("extracted_lowest", 0) or 0))
    except (ValueError, TypeError, AttributeError):
        total = ppn
    amenities = raw.get("amenities", [])
    if not isinstance(amenities, list):
        amenities = []
    return {
        "name": str(raw.get("name", ""))[:200],
        "star_rating": float(raw.get("overall_rating", 0) or 0),
        "price_per_night_usd": ppn,
        "total_price_usd": total,
        "address": str(raw.get("address", ""))[:300],
        "amenities": [str(a)[:100] for a in amenities[:10]],
        "booking_url": str(raw.get("link", ""))[:500] if raw.get("link") else None,
    }


def search_flights(
    origin_iata: str,
    destination_iata: str,
    departure_date: str,
    return_date: str | None = None,
    num_travelers: int = 1,
    currency: str = "USD",
) -> dict[str, Any]:
    """Search Google Flights via SerpApi. Validates and normalizes all inputs."""
    norm_origin = _normalize_iata(origin_iata)
    norm_dest = _normalize_iata(destination_iata)
    norm_dep = _normalize_date(departure_date)
    norm_ret = _normalize_date(return_date) if return_date else None

    if not norm_origin:
        return {"flights": [], "error": f"Could not resolve origin '{origin_iata}' to an IATA code. Please specify a 3-letter airport code.", "search_timestamp": datetime.utcnow().isoformat()}
    if not norm_dest:
        return {"flights": [], "error": f"Could not resolve destination '{destination_iata}' to an IATA code.", "search_timestamp": datetime.utcnow().isoformat()}
    if not norm_dep:
        return {"flights": [], "error": f"Could not parse departure date '{departure_date}'. Use YYYY-MM-DD format.", "search_timestamp": datetime.utcnow().isoformat()}

    try:
        num_travelers = max(1, int(num_travelers))
    except (ValueError, TypeError):
        num_travelers = 1

    params: dict[str, Any] = {
        "engine": "google_flights",
        "departure_id": norm_origin,
        "arrival_id": norm_dest,
        "outbound_date": norm_dep,
        "adults": num_travelers,
        "currency": currency,
        "hl": "en",
        "api_key": _get_api_key(),
    }
    if norm_ret:
        params["return_date"] = norm_ret
        params["type"] = "1"  # round trip
    else:
        params["type"] = "2"  # one way

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
    except Exception as exc:
        safe_msg = _scrub_key(str(exc))
        logger.error("SerpApi flights error: %s", safe_msg)
        return {"flights": [], "error": "Flight search is temporarily unavailable. Please try again.", "search_timestamp": datetime.utcnow().isoformat()}

    raw_flights: list[dict] = []
    for key in ("best_flights", "other_flights"):
        section = results.get(key, [])
        if isinstance(section, list):
            raw_flights.extend(section)

    parsed: list[dict] = []
    for item in raw_flights[:10]:
        # SerpApi nests flight details under "flights" key inside each result
        legs = item.get("flights", [item])
        if not isinstance(legs, list):
            legs = [item]
        for leg in legs:
            entry = {
                "airline": leg.get("airline", item.get("airline", "")),
                "flight_number": leg.get("flight_number", ""),
                "departure_time": leg.get("departure_airport", {}).get("time", "") if isinstance(leg.get("departure_airport"), dict) else "",
                "arrival_time": leg.get("arrival_airport", {}).get("time", "") if isinstance(leg.get("arrival_airport"), dict) else "",
                "duration": leg.get("duration", 0),
                "price": item.get("price", 0),
                "stops": len(item.get("layovers", [])),
            }
            validated = _validate_flight_result(entry)
            if validated:
                parsed.append(validated)
        if parsed:
            break  # take first valid multi-leg result

    return {
        "flights": parsed,
        "search_timestamp": datetime.utcnow().isoformat(),
        "error": None if parsed else "No flights found for this route and date.",
    }


def search_hotels(
    destination: str,
    check_in_date: str,
    check_out_date: str,
    num_guests: int = 1,
    budget_usd_per_night: float | None = None,
) -> dict[str, Any]:
    """Search Google Hotels via SerpApi. Validates and normalizes all inputs."""
    if not destination or not destination.strip():
        return {"hotels": [], "error": "Destination is required for hotel search.", "search_timestamp": datetime.utcnow().isoformat()}

    norm_in = _normalize_date(check_in_date)
    norm_out = _normalize_date(check_out_date)

    if not norm_in:
        return {"hotels": [], "error": f"Could not parse check-in date '{check_in_date}'. Use YYYY-MM-DD.", "search_timestamp": datetime.utcnow().isoformat()}
    if not norm_out:
        return {"hotels": [], "error": f"Could not parse check-out date '{check_out_date}'. Use YYYY-MM-DD.", "search_timestamp": datetime.utcnow().isoformat()}
    if norm_out <= norm_in:
        return {"hotels": [], "error": "Check-out date must be after check-in date.", "search_timestamp": datetime.utcnow().isoformat()}

    try:
        num_guests = max(1, int(num_guests))
    except (ValueError, TypeError):
        num_guests = 1

    params: dict[str, Any] = {
        "engine": "google_hotels",
        "q": destination.strip(),
        "check_in_date": norm_in,
        "check_out_date": norm_out,
        "adults": num_guests,
        "currency": "USD",
        "hl": "en",
        "api_key": _get_api_key(),
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
    except Exception as exc:
        safe_msg = _scrub_key(str(exc))
        logger.error("SerpApi hotels error: %s", safe_msg)
        return {"hotels": [], "error": "Hotel search is temporarily unavailable. Please try again.", "search_timestamp": datetime.utcnow().isoformat()}

    raw_hotels = results.get("properties", [])
    if not isinstance(raw_hotels, list):
        raw_hotels = []

    parsed: list[dict] = []
    for raw in raw_hotels[:10]:
        validated = _validate_hotel_result(raw)
        if not validated:
            continue
        if budget_usd_per_night and validated["price_per_night_usd"] > budget_usd_per_night:
            continue
        parsed.append(validated)

    return {
        "hotels": parsed,
        "search_timestamp": datetime.utcnow().isoformat(),
        "error": None if parsed else "No hotels found for this destination and dates.",
    }
