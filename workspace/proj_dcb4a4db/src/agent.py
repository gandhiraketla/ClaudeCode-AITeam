"""Agent Orchestrator for the Travel Itinerary Agent."""
from __future__ import annotations
import json
import os
import anthropic
from src.state import (
    get_messages, append_message, get_slots, merge_slots,
    get_search_results, set_flight_results, set_hotel_results,
    get_clarification_turns, increment_clarification_turns,
    clarification_limit_reached, increment_session_calls,
    set_intent, get_intent, get_recent_messages,
    MAX_CLARIFICATION_TURNS,
)
from src.prompts import (
    AGENT_SYSTEM_PROMPT, INTENT_EXTRACTION_PROMPT,
    CLARIFICATION_PROMPT, ITINERARY_COMPOSITION_PROMPT,
    sanitize_user_input, assert_no_key_leak, build_slots_summary,
)
from src.tools import search_flights, search_hotels, resolve_iata

MODEL = "claude-opus-4-5"
MAX_TOKENS = 2048

BOOKING_KEYWORDS = ["book", "reserve", "confirm", "purchase", "pay", "buy ticket"]


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def _call_claude(system: str, messages: list[dict], max_tokens: int = MAX_TOKENS) -> str:
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    raw = response.content[0].text
    return assert_no_key_leak(raw)


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _is_booking_request(message: str) -> bool:
    lowered = message.lower()
    return any(kw in lowered for kw in BOOKING_KEYWORDS)


def extract_intent_and_slots(user_message: str) -> dict:
    """Call Claude to extract intent and travel slots from conversation."""
    recent = get_recent_messages(10)
    messages_for_extraction = [
        {"role": "user", "content": INTENT_EXTRACTION_PROMPT +
         "\n\nConversation:\n" + json.dumps(recent) +
         "\n\nLatest user message: " + user_message}
    ]
    raw = _call_claude("You are a travel data extractor. Return only valid JSON.",
                       messages_for_extraction, max_tokens=512)
    result = _parse_json_response(raw)
    if not result:
        return {
            "intent": "unclear",
            "slots": {},
            "missing_required": ["destination"],
        }
    return result


def generate_clarification_question(intent: str, slots: dict, missing: list[str]) -> dict:
    """Ask Claude to produce a single clarifying question for the first missing slot."""
    prompt = CLARIFICATION_PROMPT.format(
        missing_required=missing,
        confirmed_slots={k: v for k, v in slots.items() if v is not None},
        intent=intent,
    )
    raw = _call_claude("You are a travel assistant. Return only valid JSON.",
                       [{"role": "user", "content": prompt}], max_tokens=256)
    result = _parse_json_response(raw)
    if not result or "question" not in result:
        return {"question": f"Could you please provide your {missing[0]}?",
                "slot_being_asked": missing[0]}
    return result


def compose_itinerary(slots: dict, flights: list | None, hotels: list | None, intent: str) -> str:
    """Call Claude to compose a structured day-by-day itinerary from tool results."""
    if flights is None and hotels is None:
        return ("I was unable to retrieve live flight or hotel data for your trip. "
                "Please try again or check travel sites directly.")
    slots_summary = build_slots_summary(slots)
    flights_json = json.dumps(flights, indent=2) if flights else "null"
    hotels_json = json.dumps(hotels, indent=2) if hotels else "null"
    prompt = ITINERARY_COMPOSITION_PROMPT.format(
        slots_summary=slots_summary,
        flights_json=flights_json,
        hotels_json=hotels_json,
    )
    all_messages = get_messages()
    messages_for_compose = list(all_messages) + [{"role": "user", "content": prompt}]
    return _call_claude(AGENT_SYSTEM_PROMPT, messages_for_compose, max_tokens=2048)


def process_message(user_message: str) -> str:
    """Main agent entry point. Returns assistant response string."""
    # Rate limit check
    if increment_session_calls():
        return ("You have reached the maximum number of requests for this session. "
                "Please refresh the page to start a new session.")

    # Sanitize input
    clean_message = sanitize_user_input(user_message)

    # Scope guardrail: booking requests
    if _is_booking_request(clean_message):
        return ("Booking is not available in this version. "
                "I can help you refine your itinerary instead.")

    # Append user message to history
    append_message("user", clean_message)

    # Extract intent and slots
    extraction = extract_intent_and_slots(clean_message)
    intent = extraction.get("intent", "unclear")
    new_slots = extraction.get("slots", {})
    missing = extraction.get("missing_required", [])

    # Merge newly extracted slots
    merge_slots(new_slots)
    slots = get_slots()
    set_intent(intent)

    # Unclear intent: ask for destination
    if intent == "unclear":
        question = "Where would you like to travel, and what dates are you thinking?"
        append_message("assistant", question)
        return question

    # Check for missing required slots
    if missing:
        # Clarification limit enforcement
        if clarification_limit_reached():
            still_missing = ", ".join(missing)
            response = (
                f"I still need the following information to proceed: {still_missing}. "
                "Could you please provide all of these in one message?"
            )
            append_message("assistant", response)
            return response

        increment_clarification_turns()
        clarification = generate_clarification_question(intent, slots, missing)
        question = clarification.get("question", f"Could you provide your {missing[0]}?")
        append_message("assistant", question)
        return question

    # All required slots present — execute searches
    flight_result = {"flights": None, "error": None}
    hotel_result = {"hotels": None, "error": None}
    warnings = []

    # Flight search
    if intent in ("full_itinerary", "flights_only"):
        origin = resolve_iata(slots.get("origin", ""))
        destination = resolve_iata(slots.get("destination", ""))
        departure_date = slots.get("departure_date", "")
        return_date = slots.get("return_date")
        num_travelers = slots.get("num_travelers", 1) or 1
        if origin and destination and departure_date:
            flight_result = search_flights(
                origin_iata=origin,
                destination_iata=destination,
                departure_date=departure_date,
                return_date=return_date,
                num_travelers=int(num_travelers),
            )
            set_flight_results(flight_result.get("flights"))
            if flight_result.get("error"):
                warnings.append(flight_result["error"])
        else:
            warnings.append("Flight search skipped — missing origin, destination, or date.")

    # Hotel search
    if intent in ("full_itinerary", "hotels_only"):
        destination = slots.get("destination", "")
        check_in = slots.get("check_in_date") or slots.get("departure_date")
        check_out = slots.get("check_out_date") or slots.get("return_date")
        num_guests = slots.get("num_travelers", 1) or 1
        budget = slots.get("budget_usd")
        # Skip hotel search if check-in == check-out (same-day trip)
        if destination and check_in and check_out and check_in != check_out:
            hotel_result = search_hotels(
                destination=destination,
                check_in_date=check_in,
                check_out_date=check_out,
                num_guests=int(num_guests),
                budget_usd_per_night=float(budget) if budget else None,
            )
            set_hotel_results(hotel_result.get("hotels"))
            if hotel_result.get("error"):
                warnings.append(hotel_result["error"])
        else:
            if check_in == check_out:
                warnings.append("Hotel search skipped — same-day trip detected.")
            else:
                warnings.append("Hotel search skipped — missing destination or dates.")

    # Compose itinerary
    itinerary = compose_itinerary(
        slots=slots,
        flights=flight_result.get("flights"),
        hotels=hotel_result.get("hotels"),
        intent=intent,
    )

    if warnings:
        warning_block = "\n\n> ⚠️ " + "\n> ⚠️ ".join(warnings)
        itinerary = itinerary + warning_block

    append_message("assistant", itinerary)
    return itinerary
