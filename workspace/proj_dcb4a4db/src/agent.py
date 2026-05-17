"""Agent orchestrator for the Travel Itinerary Agent."""
import json
import os
import anthropic
from src.state import (
    init_state, append_message, merge_slots, get_recent_messages,
    get_all_messages, increment_call_count, is_call_limit_reached,
    increment_clarification_turns, is_clarification_cap_reached,
    set_search_results, get_search_results, set_intent, get_intent
)
from src.prompts import (
    SYSTEM_PROMPT, EXTRACT_INTENT_SYSTEM, EXTRACT_INTENT_TEMPLATE,
    CLARIFICATION_SYSTEM, CLARIFICATION_TEMPLATE,
    COMPOSE_ITINERARY_SYSTEM, COMPOSE_ITINERARY_TEMPLATE,
    sanitize_user_input, strip_api_keys
)
from src.tools import search_flights, search_hotels
import streamlit as st


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _call_claude(system: str, user: str, max_tokens: int = 1024) -> str:
    """Call Claude and return the text response. Increments call counter."""
    if increment_call_count():
        return json.dumps({"error": "Session API call limit reached. Please start a new session."})
    client = _get_client()
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return strip_api_keys(response.content[0].text)


def _extract_intent_and_slots(user_message: str) -> dict:
    history_text = json.dumps(get_recent_messages(10), ensure_ascii=False)
    prompt = EXTRACT_INTENT_TEMPLATE.format(
        history=history_text,
        user_message=user_message
    )
    raw = _call_claude(EXTRACT_INTENT_SYSTEM, prompt, max_tokens=512)
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Not a dict")
        return result
    except Exception:
        return {"intent": "unclear", "slots": {}, "missing_required": []}


def _generate_clarification(intent: str, missing_required: list) -> str:
    confirmed_slots = st.session_state.get("slots", {})
    prompt = CLARIFICATION_TEMPLATE.format(
        intent=intent,
        confirmed_slots=json.dumps(confirmed_slots),
        missing_required=json.dumps(missing_required)
    )
    raw = _call_claude(CLARIFICATION_SYSTEM, prompt, max_tokens=256)
    try:
        result = json.loads(raw)
        return result.get("question", "Could you provide more details about your trip?")
    except Exception:
        return "Could you provide more details about your trip?"


def _resolve_iata(location: str) -> str:
    """Return IATA code if already one, else use as-is (SerpApi handles city names)."""
    if location and len(location.strip()) == 3 and location.strip().isalpha():
        return location.strip().upper()
    return location.strip() if location else ""


def _compose_itinerary(slots: dict, flights: list, hotels: list, intent: str) -> str:
    prompt = COMPOSE_ITINERARY_TEMPLATE.format(
        slots=json.dumps(slots),
        flights=json.dumps(flights) if flights else "null",
        hotels=json.dumps(hotels) if hotels else "null",
        intent=intent
    )
    raw = _call_claude(COMPOSE_ITINERARY_SYSTEM, prompt, max_tokens=2048)
    try:
        result = json.loads(raw)
        md = result.get("itinerary_markdown", "")
        warnings = result.get("warnings", [])
        if warnings:
            md += "\n\n**Notices:**\n" + "\n".join(f"- {w}" for w in warnings)
        return strip_api_keys(md)
    except Exception:
        return strip_api_keys(raw)


def _check_booking_request(text: str) -> bool:
    lower = text.lower()
    booking_keywords = ["book ", "booking", "reserve", "reservation", "confirm", "pay ", "payment", "purchase"]
    return any(kw in lower for kw in booking_keywords)


def run_agent(user_message: str) -> str:
    """Main entry point. Process user message and return assistant response."""
    init_state()

    if is_call_limit_reached():
        return "You have reached the maximum number of API calls for this session. Please refresh to start a new session."

    sanitized = sanitize_user_input(user_message)
    append_message("user", sanitized)

    if _check_booking_request(sanitized):
        response = ("Booking, payment, and reservation confirmation are out of scope in V1. "
                    "I can help you build a detailed itinerary with real flight and hotel options. "
                    "Would you like me to refine your itinerary?")
        append_message("assistant", response)
        return response

    extraction = _extract_intent_and_slots(sanitized)
    intent = extraction.get("intent", "unclear")
    new_slots = extraction.get("slots", {})
    missing_required = extraction.get("missing_required", [])

    if isinstance(new_slots, dict):
        merge_slots(new_slots)
    if intent and intent != "unclear":
        set_intent(intent)
    else:
        intent = get_intent() or "unclear"

    slots = st.session_state.slots

    if missing_required:
        if is_clarification_cap_reached():
            still_missing = ", ".join(missing_required)
            response = (f"I still need the following information to proceed: {still_missing}. "
                        "Please provide all of them in your next message.")
            append_message("assistant", response)
            return response
        increment_clarification_turns()
        question = _generate_clarification(intent, missing_required)
        append_message("assistant", question)
        return question

    # Reset clarification counter once slots are complete
    st.session_state.clarification_turns = 0

    flights_result = None
    hotels_result = None

    if intent in ("full_itinerary", "flights_only"):
        origin = _resolve_iata(slots.get("origin", ""))
        destination = _resolve_iata(slots.get("destination", ""))
        departure_date = slots.get("departure_date", "")
        return_date = slots.get("return_date")
        num_travelers = int(slots.get("num_travelers") or 1)
        if origin and destination and departure_date:
            flights_result = search_flights(
                origin_iata=origin,
                destination_iata=destination,
                departure_date=departure_date,
                return_date=return_date,
                num_travelers=num_travelers
            )
            set_search_results(flights_result.get("flights"), None)
        else:
            flights_result = {"flights": [], "error": "Missing flight search parameters"}

    if intent in ("full_itinerary", "hotels_only"):
        destination = slots.get("destination", "")
        check_in = slots.get("check_in_date") or slots.get("departure_date", "")
        check_out = slots.get("check_out_date") or slots.get("return_date", "")
        num_guests = int(slots.get("num_travelers") or 1)
        budget = slots.get("budget_usd")
        # Skip hotel search if same-day trip
        if destination and check_in and check_out and check_in != check_out:
            hotels_result = search_hotels(
                destination=destination,
                check_in_date=check_in,
                check_out_date=check_out,
                num_guests=num_guests,
                budget_usd_per_night=float(budget) if budget else None
            )
            set_search_results(None, hotels_result.get("hotels"))
        elif intent == "hotels_only":
            hotels_result = {"hotels": [], "error": "Missing hotel search parameters or same-day trip"}

    search_cache = get_search_results()
    flights_data = (flights_result.get("flights") if flights_result else None) or search_cache.get("flights")
    hotels_data = (hotels_result.get("hotels") if hotels_result else None) or search_cache.get("hotels")

    if not flights_data and not hotels_data:
        flight_err = (flights_result or {}).get("error", "")
        hotel_err = (hotels_result or {}).get("error", "")
        errors = [e for e in [flight_err, hotel_err] if e]
        if errors:
            response = ("I was unable to retrieve live data: " + "; ".join(errors) +
                        ". Please check your inputs and try again.")
        else:
            response = "No results found. Please verify your destination, dates, and try again."
        append_message("assistant", response)
        return response

    response = _compose_itinerary(slots, flights_data, hotels_data, intent)
    append_message("assistant", response)
    return response
