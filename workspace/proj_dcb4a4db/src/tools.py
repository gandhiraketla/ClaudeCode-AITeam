import os
import json
from datetime import datetime
from serpapi import GoogleSearch
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

AIRPORT_MAP = {
    "new york": "JFK", "ny": "JFK", "nyc": "JFK",
    "los angeles": "LAX", "la": "LAX",
    "london": "LHR", "paris": "CDG",
    "chicago": "ORD", "dallas": "DFW", "dfw": "DFW",
    "miami": "MIA", "san francisco": "SFO",
    "tokyo": "NRT", "dubai": "DXB",
    "rome": "FCO", "barcelona": "BCN",
    "amsterdam": "AMS", "frankfurt": "FRA",
    "sydney": "SYD", "toronto": "YYZ",
}


def resolve_iata(city: str) -> str:
    if not city:
        return ""
    if len(city) == 3 and city.isupper():
        return city
    return AIRPORT_MAP.get(city.lower().strip(), city.upper()[:3])


def extract_intent_and_slots(messages: list, current_user_message: str) -> dict:
    recent = messages[-10:] if len(messages) > 10 else messages
    conversation = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
    prompt = f"""Analyze this travel conversation and extract intent and slots.

Conversation:\n{conversation}\nCurrent message: {current_user_message}

Return ONLY valid JSON:
{{
  "intent": "full_itinerary|flights_only|hotels_only|unclear",
  "slots": {{
    "origin": null,
    "destination": null,
    "departure_date": null,
    "return_date": null,
    "check_in_date": null,
    "check_out_date": null,
    "num_travelers": null,
    "budget_usd": null,
    "interests": null
  }},
  "missing_required": []
}}

For full_itinerary: required = origin, destination, departure_date, check_in_date, check_out_date.
For flights_only: required = origin, destination, departure_date.
For hotels_only: required = destination, check_in_date, check_out_date.
Dates must be ISO8601 (YYYY-MM-DD). If year not specified assume 2025.
Only include fields in missing_required if truly absent."""
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception as e:
        return {"intent": "unclear", "slots": {}, "missing_required": [], "error": str(e)}


def generate_clarification_question(intent: str, confirmed_slots: dict, missing_required: list) -> dict:
    if not missing_required:
        return {"question": "", "slot_being_asked": ""}
    slot = missing_required[0]
    slot_prompts = {
        "origin": "Where will you be departing from?",
        "destination": "Where would you like to travel to?",
        "departure_date": "What date are you planning to depart? (e.g., 2025-06-15)",
        "return_date": "What date will you be returning?",
        "check_in_date": "What date would you like to check in to your hotel?",
        "check_out_date": "What date will you be checking out of your hotel?",
        "num_travelers": "How many travelers will be going?",
        "budget_usd": "Do you have a budget in mind (USD)?",
        "interests": "What are your interests or preferences for activities?",
    }
    question = slot_prompts.get(slot, f"Could you please provide your {slot.replace('_', ' ')}?")
    return {"question": question, "slot_being_asked": slot}


def search_flights(origin_iata: str, destination_iata: str, departure_date: str,
                  return_date: str = None, num_travelers: int = 1, currency: str = "USD") -> dict:
    if not origin_iata or not destination_iata or not departure_date:
        return {"flights": [], "error": "Missing required fields: origin, destination, or departure_date",
                "search_timestamp": datetime.utcnow().isoformat()}
    origin_iata = resolve_iata(origin_iata)
    destination_iata = resolve_iata(destination_iata)
    try:
        params = {
            "engine": "google_flights",
            "departure_id": origin_iata,
            "arrival_id": destination_iata,
            "outbound_date": departure_date,
            "currency": currency,
            "hl": "en",
            "api_key": os.getenv("SERPAPI_API_KEY"),
        }
        if return_date:
            params["return_date"] = return_date
            params["type"] = "1"
        else:
            params["type"] = "2"
        search = GoogleSearch(params)
        results = search.get_dict()
        flights = []
        for section in ["best_flights", "other_flights"]:
            for item in results.get(section, []):
                legs = item.get("flights", [])
                if not legs:
                    continue
                first = legs[0]
                flights.append({
                    "airline": first.get("airline", "Unknown"),
                    "flight_number": first.get("flight_number", "N/A"),
                    "departure_time": first.get("departure_airport", {}).get("time", ""),
                    "arrival_time": legs[-1].get("arrival_airport", {}).get("time", ""),
                    "duration_minutes": item.get("total_duration", 0),
                    "price_usd": item.get("price", 0),
                    "stops": len(legs) - 1,
                    "booking_url": ""
                })
            if len(flights) >= 5:
                break
        return {"flights": flights[:5], "search_timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"flights": [], "error": "Flight search unavailable. Please try again later.",
                "search_timestamp": datetime.utcnow().isoformat()}


def search_hotels(destination: str, check_in_date: str, check_out_date: str,
                 num_guests: int = 1, budget_usd_per_night: float = None) -> dict:
    if not destination or not check_in_date or not check_out_date:
        return {"hotels": [], "error": "Missing required fields: destination, check_in_date, or check_out_date",
                "search_timestamp": datetime.utcnow().isoformat()}
    try:
        params = {
            "engine": "google_hotels",
            "q": f"hotels in {destination}",
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "adults": str(num_guests),
            "currency": "USD",
            "hl": "en",
            "api_key": os.getenv("SERPAPI_API_KEY"),
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        hotels = []
        for prop in results.get("properties", [])[:5]:
            rate = prop.get("rate_per_night", {})
            price_per_night = 0
            if isinstance(rate, dict):
                extracted = rate.get("extracted_lowest", rate.get("lowest", 0))
                try:
                    price_per_night = float(str(extracted).replace(",", "").replace("$", ""))
                except (ValueError, TypeError):
                    price_per_night = 0
            try:
                from datetime import date
                ci = date.fromisoformat(check_in_date)
                co = date.fromisoformat(check_out_date)
                nights = max((co - ci).days, 1)
            except Exception:
                nights = 1
            hotels.append({
                "name": prop.get("name", "Unknown Hotel"),
                "star_rating": prop.get("overall_rating", 0),
                "price_per_night_usd": price_per_night,
                "total_price_usd": round(price_per_night * nights, 2),
                "address": prop.get("description", destination),
                "amenities": prop.get("amenities", [])[:5],
                "booking_url": prop.get("link", "")
            })
        return {"hotels": hotels, "search_timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"hotels": [], "error": "Hotel search unavailable. Please try again later.",
                "search_timestamp": datetime.utcnow().isoformat()}


def compose_itinerary(slots: dict, flights: list, hotels: list, intent: str) -> dict:
    if not flights and not hotels:
        return {"itinerary_markdown": "", "days": 0,
                "warnings": ["No live flight or hotel data was available to compose an itinerary."]}
    warnings = []
    flights_text = json.dumps(flights, indent=2) if flights else "No flight data available."
    hotels_text = json.dumps(hotels, indent=2) if hotels else "No hotel data available."
    if not flights:
        warnings.append("No live flight data was found for this route and date.")
    if not hotels:
        warnings.append("No live hotel data was found for this destination and dates.")
    prompt = f"""You are a travel planning assistant. Compose a structured day-by-day itinerary.

IMPORTANT RULES:
- Use ONLY the flight and hotel data provided below. Do NOT invent prices, times, or hotel names.
- If fewer than 2 hotels are available, state that clearly instead of padding with invented options.
- Format: Day headers (Day 1: YYYY-MM-DD), sub-sections for Flights, Accommodation, Activities.
- Include price and time for every flight and hotel entry.
- Do not offer to book anything.

Trip details: {json.dumps(slots, indent=2)}
Intent: {intent}

Flight options:\n{flights_text}

Hotel options:\n{hotels_text}

Compose the itinerary now in markdown:"""
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        itinerary = response.content[0].text.strip()
        try:
            check_in = slots.get("check_in_date") or slots.get("departure_date", "")
            check_out = slots.get("check_out_date") or slots.get("return_date", "")
            if check_in and check_out:
                from datetime import date
                days = max((date.fromisoformat(check_out) - date.fromisoformat(check_in)).days, 1)
            else:
                days = 1
        except Exception:
            days = 1
        return {"itinerary_markdown": itinerary, "days": days, "warnings": warnings}
    except Exception as e:
        return {"itinerary_markdown": "", "days": 0, "warnings": ["Failed to compose itinerary. Please try again."]}
