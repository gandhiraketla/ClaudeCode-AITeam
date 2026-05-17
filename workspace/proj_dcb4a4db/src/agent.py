"""Agent orchestrator: ReAct loop for travel itinerary planning."""
from __future__ import annotations
import json
import logging
import os
from typing import Any

import anthropic

from src.state import (
    MAX_CLARIFICATION_TURNS,
    append_message,
    clarification_limit_reached,
    get_intent,
    get_recent_messages,
    get_search_results,
    get_slots,
    increment_call_count,
    increment_clarification_turns,
    is_rate_limited,
    merge_slots,
    set_intent,
    set_search_results,
)
from src.prompts import (
    build_clarification_prompt,
    build_compose_prompt,
    build_intent_prompt,
    sanitize_user_input,
    scrub_api_keys,
    SYSTEM_PROMPT,
)
from src.tools import search_flights, search_hotels

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-5"
MAX_TOKENS = 2048

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _claude_call(prompt: str) -> str:
    """Single-turn Claude call returning text. Increments call counter."""
    if not increment_call_count():
        return "{\"error\": \"rate_limit_reached\"}"
    try:
        client = _get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        return scrub_api_keys(raw)
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        raise


def _extract_json(text: str) -> dict:
    """Extract JSON object from LLM response text."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        logger.warning("No JSON found in LLM response: %.200s", text)
        return {}
    try:
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            logger.warning("LLM JSON was not a dict")
            return {}
        return parsed
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse error: %s — text: %.200s", exc, text)
        return {}


def _validate_intent_result(data: dict) -> bool:
    """Return True if the intent extraction result has the expected shape."""
    if "intent" not in data:
        return False
    if "slots" not in data or not isinstance(data["slots"], dict):
        return False
    if "missing_required" not in data or not isinstance(data["missing_required"], list):
        return False
    return True


def _extract_intent_and_slots(messages: list[dict], slots: dict) -> dict:
    """Call Claude to extract intent and slots from conversation."""
    prompt = build_intent_prompt(messages, slots)
    raw = _claude_call(prompt)
    data = _extract_json(raw)
    if not _validate_intent_result(data):
        logger.warning("Intent extraction returned invalid shape: %s", data)
        return {
            "intent": "unclear",
            "slots": {},
            "missing_required": ["destination"],
        }
    return data


def _generate_clarification(intent: str, slots: dict, missing: list) -> str:
    """Call Claude to produce a clarification question."""
    prompt = build_clarification_prompt(intent, slots, missing)
    raw = _claude_call(prompt)
    data = _extract_json(raw)
    question = data.get("question", "")
    if not question or not isinstance(question, str):
        first = missing[0] if missing else "details"
        question = f"Could you please provide the {first.replace('_', ' ')} for your trip?"
    return scrub_api_keys(question)


def _compose_itinerary(slots: dict, flights: list | None, hotels: list | None, intent: str) -> str:
    """Call Claude to compose the final day-by-day itinerary."""
    if not increment_call_count():
        return "Rate limit reached. Please start a new session."
    prompt = build_compose_prompt(slots, flights, hotels, intent)
    try:
        client = _get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        return scrub_api_keys(raw)
    except anthropic.APIError as exc:
        logger.error("Anthropic compose error: %s", exc)
        return "I encountered an error while composing your itinerary. Please try again."


def _is_booking_request(text: str) -> bool:
    """Return True if the user is asking to book/pay/confirm."""
    lower = text.lower()
    return any(kw in lower for kw in ("book", "reserve", "purchase", "pay", "confirm reservation", "buy ticket"))


def _resolve_search_inputs(slots: dict, intent: str) -> dict[str, Any]:
    """Map slot keys to tool input keys; return dict of resolved fields."""
    from src.tools import _normalize_iata, _normalize_date  # internal helpers
    resolved: dict[str, Any] = {}

    origin_raw = slots.get("origin", "")
    dest_raw = slots.get("destination", "")
    dep_raw = slots.get("departure_date", "")
    ret_raw = slots.get("return_date", "")
    ci_raw = slots.get("check_in_date", dep_raw or "")
    co_raw = slots.get("check_out_date", slots.get("return_date", ""))

    resolved["origin_iata"] = _normalize_iata(origin_raw or "")
    resolved["destination_iata"] = _normalize_iata(dest_raw or "")
    resolved["destination_str"] = (dest_raw or "").strip()
    resolved["departure_date"] = _normalize_date(dep_raw or "")
    resolved["return_date"] = _normalize_date(ret_raw or "") if ret_raw else None
    resolved["check_in_date"] = _normalize_date(ci_raw or "")
    resolved["check_out_date"] = _normalize_date(co_raw or "") if co_raw else None
    resolved["num_travelers"] = slots.get("num_travelers") or 1
    resolved["budget_usd"] = slots.get("budget_usd")
    return resolved


def process_message(user_message: str) -> str:
    """
    Main ReAct loop entry point.
    Takes raw user input, runs the agent, returns assistant reply.
    """
    if is_rate_limited():
        return "You have reached the maximum number of requests for this session. Please refresh to start a new session."

    if _is_booking_request(user_message):
        return (
            "Booking and reservation confirmation are not available in this version. "
            "I can help you plan and refine your itinerary — would you like me to do that?"
        )

    sanitized = sanitize_user_input(user_message)
    append_message("user", sanitized)

    recent = get_recent_messages(10)
    current_slots = get_slots()

    # Step 1: Extract intent and slots
    extraction = _extract_intent_and_slots(recent, current_slots)
    intent = extraction.get("intent", "unclear")
    new_slots = extraction.get("slots", {})
    missing = extraction.get("missing_required", [])

    if isinstance(new_slots, dict):
        merge_slots(new_slots)
    set_intent(intent)
    current_slots = get_slots()

    if intent == "unclear" and not current_slots.get("destination"):
        question = "Where would you like to travel? Please share your destination and any trip details you have in mind."
        append_message("assistant", question)
        return question

    # Step 2: Clarification loop
    if missing:
        if clarification_limit_reached():
            still_missing = ", ".join(missing)
            reply = (
                f"To complete your itinerary I still need: {still_missing}. "
                "Please provide all of these in one message so I can proceed."
            )
            append_message("assistant", reply)
            return reply

        increment_clarification_turns()
        question = _generate_clarification(intent, current_slots, missing)
        append_message("assistant", question)
        return question

    # Step 3: Search tools
    resolved = _resolve_search_inputs(current_slots, intent)
    search_results = get_search_results()
    flights_data = search_results.get("flights")
    hotels_data = search_results.get("hotels")

    do_flights = intent in ("full_itinerary", "flights_only")
    do_hotels = intent in ("full_itinerary", "hotels_only")

    # Skip hotel search if same-day round trip
    dep = resolved.get("departure_date")
    ret = resolved.get("return_date")
    if dep and ret and dep == ret:
        do_hotels = False

    if do_flights:
        origin = resolved.get("origin_iata")
        dest_iata = resolved.get("destination_iata")
        dep_date = resolved.get("departure_date")
        if not origin or not dest_iata or not dep_date:
            missing_fields = [f for f, v in [("origin", origin), ("destination IATA", dest_iata), ("departure date", dep_date)] if not v]
            question = _generate_clarification(intent, current_slots, missing_fields)
            append_message("assistant", question)
            return question
        flight_result = search_flights(
            origin_iata=origin,
            destination_iata=dest_iata,
            departure_date=dep_date,
            return_date=resolved.get("return_date"),
            num_travelers=resolved["num_travelers"],
        )
        flights_data = flight_result.get("flights") or None

    if do_hotels:
        dest_str = resolved.get("destination_str") or current_slots.get("destination", "")
        ci = resolved.get("check_in_date")
        co = resolved.get("check_out_date")
        if not dest_str or not ci or not co:
            missing_fields = [f for f, v in [("destination", dest_str), ("check_in_date", ci), ("check_out_date", co)] if not v]
            question = _generate_clarification(intent, current_slots, missing_fields)
            append_message("assistant", question)
            return question
        hotel_result = search_hotels(
            destination=dest_str,
            check_in_date=ci,
            check_out_date=co,
            num_guests=resolved["num_travelers"],
            budget_usd_per_night=resolved.get("budget_usd"),
        )
        hotels_data = hotel_result.get("hotels") or None

    set_search_results(flights_data, hotels_data)

    # Guardrail: if both searches failed, do not compose a fabricated itinerary
    if do_flights and do_hotels and flights_data is None and hotels_data is None:
        reply = (
            "I was unable to retrieve live flight and hotel data for your trip at this time. "
            "Please check your dates and try again, or try a different route."
        )
        append_message("assistant", reply)
        return reply

    # Step 4: Compose itinerary
    itinerary = _compose_itinerary(current_slots, flights_data, hotels_data, intent)
    append_message("assistant", itinerary)
    return itinerary
