"""Travel search tools: flights and hotels via SerpApi."""
import os
import json
from datetime import datetime
from serpapi import GoogleSearch


FLIGHT_SCHEMA_KEYS = {"departure_airport", "arrival_airport", "airlines", "price", "total_duration"}
HOTEL_SCHEMA_KEYS = {"name", "rate_per_night", "overall_rating"}


def _get_serpapi_key() -> str:
    key = os.environ.get("SERPAPI_API_KEY", "")
    if not key:
        raise ValueError("SERPAPI_API_KEY not set in environment")
    return key


def _normalize_flight(raw: dict) -> dict:
    """Extract only expected fields from a raw SerpApi flight result."""
    try:
        legs = raw.get("flights", [{}])
        first_leg = legs[0] if legs else {}
        last_leg = legs[-1] if legs else {}
        dep_airport = first_leg.get("departure_airport", {})
        arr_airport = last_leg.get("arrival_airport", {})
        airline = first_leg.get("airline", "Unknown")
        flight_number = first_leg.get("flight_number", "")
        departure_time = dep_airport.get("time", "")
        arrival_time = arr_airport.get("time", "")
        duration = raw.get("total_duration", 0)
        price = raw.get("price", 0)
        stops = len(legs) - 1
        return {
            "airline": str(airline)[:100],
            "flight_number": str(flight_number)[:20],
            "departure_time": str(departure_time)[:50],
            "arrival_time": str(arrival_time)[:50],
            "duration_minutes": int(duration) if isinstance(duration, (int, float)) else 0,
            "price_usd": float(price) if isinstance(price, (int, float)) else 0.0,
            "stops": max(0, int(stops)),
            "booking_url": None,
        }
    except Exception:
        return None


def _normalize_hotel(raw: dict) -> dict:
    """Extract only expected fields from a raw SerpApi hotel result."""
    try:
        name = raw.get("name", "Unknown")
        rate_info = raw.get("rate_per_night", {})
        if isinstance(rate_info, dict):
            price_str = rate_info.get("lowest", "0").replace("$", "").replace(",", "")
        else:
            price_str = str(rate_info).replace("$", "").replace(",", "")
        try:
            price = float(price_str)
        except ValueError:
            price = 0.0
        rating = raw.get("overall_rating", 0)
        address = raw.get("link", "")[:200]
        amenities_raw = raw.get("amenities", [])
        amenities = [str(a)[:50] for a in amenities_raw[:10]] if isinstance(amenities_raw, list) else []
        return {
            "name": str(name)[:200],
            "star_rating": float(rating) if isinstance(rating, (int, float)) else 0.0,
            "price_per_night_usd": price,
            "total_price_usd": price,
            "address": address,
            "amenities": amenities,
            "booking_url": raw.get("link", None),
        }
    except Exception:
        return None


def search_flights(
    origin_iata: str,
    destination_iata: str,
    departure_date: str,
    return_date: str = None,
    num_travelers: int = 1,
    currency: str = "USD",
) -> dict:
    """Search Google Flights via SerpApi. Returns normalized results or error."""
    if not origin_iata or not destination_iata or not departure_date:
        return {"flights": [], "search_timestamp": datetime.utcnow().isoformat(), "error": "Missing required parameters: origin_iata, destination_iata, departure_date"}
    try:
        params = {
            "engine": "google_flights",
            "departure_id": origin_iata.upper()[:4],
            "arrival_id": destination_iata.upper()[:4],
            "outbound_date": departure_date,
            "adults": min(max(1, int(num_travelers)), 9),
            "currency": currency,
            "api_key": _get_serpapi_key(),
        }
        if return_date:
            params["return_date"] = return_date
            params["type"] = "1"
        else:
            params["type"] = "2"
        search = GoogleSearch(params)
        results = search.get_dict()
        raw_flights = results.get("best_flights", []) + results.get("other_flights", [])
        normalized = [_normalize_flight(f) for f in raw_flights[:10]]
        normalized = [f for f in normalized if f is not None]
        return {
            "flights": normalized,
            "search_timestamp": datetime.utcnow().isoformat(),
            "error": None if normalized else "No flights found for this route and date",
        }
    except Exception as exc:
        safe_msg = "Flight search failed. Please try different dates or airports."
        error_str = str(exc)
        if "api_key" in error_str.lower() or "apikey" in error_str.lower():
            safe_msg = "Flight search failed: invalid or missing API key."
        return {"flights": [], "search_timestamp": datetime.utcnow().isoformat(), "error": safe_msg}


def search_hotels(
    destination: str,
    check_in_date: str,
    check_out_date: str,
    num_guests: int = 1,
    budget_usd_per_night: float = None,
) -> dict:
    """Search Google Hotels via SerpApi. Returns normalized results or error."""
    if not destination or not check_in_date or not check_out_date:
        return {"hotels": [], "search_timestamp": datetime.utcnow().isoformat(), "error": "Missing required parameters: destination, check_in_date, check_out_date"}
    try:
        params = {
            "engine": "google_hotels",
            "q": str(destination)[:100] + " hotels",
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "adults": min(max(1, int(num_guests)), 9),
            "currency": "USD",
            "api_key": _get_serpapi_key(),
        }
        if budget_usd_per_night:
            params["max_price"] = int(budget_usd_per_night)
        search = GoogleSearch(params)
        results = search.get_dict()
        raw_hotels = results.get("properties", [])[:10]
        normalized = [_normalize_hotel(h) for h in raw_hotels]
        normalized = [h for h in normalized if h is not None]
        return {
            "hotels": normalized,
            "search_timestamp": datetime.utcnow().isoformat(),
            "error": None if normalized else "No hotels found for this destination and dates",
        }
    except Exception as exc:
        safe_msg = "Hotel search failed. Please try a different destination or dates."
        error_str = str(exc)
        if "api_key" in error_str.lower() or "apikey" in error_str.lower():
            safe_msg = "Hotel search failed: invalid or missing API key."
        return {"hotels": [], "search_timestamp": datetime.utcnow().isoformat(), "error": safe_msg}
