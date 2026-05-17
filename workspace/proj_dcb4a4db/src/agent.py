import os
import json
from anthropic import Anthropic
from src.tools import search_flights, search_hotels, resolve_iata

client = Anthropic()

SYSTEM_PROMPT = """You are a travel planning assistant that produces structured itineraries. You are NOT a booking engine.

Behavioral rules:
- Ask one clarifying question at a time, never multiple
- Never fabricate flight or hotel data — use tool results verbatim for prices and times
- If data is unavailable, say so explicitly rather than omitting sections silently
- Do not offer to book, pay, or confirm reservations — V1 is plan-only
- If user asks to book or pay, say booking is out of scope and offer to refine the itinerary

Output format for itineraries:
- Use day headers: Day 1: [date]
- Sub-sections: Flights / Accommodation / Activities
- Include price and time for every flight and hotel entry
- Use markdown for readability

Scope guardrails:
- Only use hotel/flight entries present in the provided data arrays
- If fewer than 2 options exist, say so rather than padding with invented options
- Never log or display API keys"""

INTENT_EXTRACTION_PROMPT = """Analyze the conversation and extract travel intent and slots.

Return a JSON object with exactly this structure:
{
  "intent": "full_itinerary" | "flights_only" | "hotels_only" | "unclear",
  "slots": {
    "origin": "city or IATA or null",
    "destination": "city or IATA or null",
    "departure_date": "YYYY-MM-DD or null",
    "return_date": "YYYY-MM-DD or null",
    "check_in_date": "YYYY-MM-DD or null",
    "check_out_date": "YYYY-MM-DD or null",
    "num_travelers": integer_or_null,
    "budget_usd": number_or_null,
    "interests": []
  },
  "missing_required": ["list of missing required slot names"]
}

Required slots for full_itinerary: origin, destination, departure_date, check_in_date, check_out_date, num_travelers
Required slots for flights_only: origin, destination, departure_date, num_travelers
Required slots for hotels_only: destination, check_in_date, check_out_date, num_travelers

Return ONLY valid JSON, no explanation."""


def extract_intent_and_slots(messages: list, current_slots: dict) -> dict:
    recent = messages[-10:] if len(messages) > 10 else messages
    conversation = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
    prompt = f"{INTENT_EXTRACTION_PROMPT}\n\nConversation:\n{conversation}\n\nAlready confirmed slots: {json.dumps(current_slots)}"
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {"intent": "unclear", "slots": {}, "missing_required": ["destination"]}


def generate_clarification_question(intent: str, confirmed_slots: dict, missing_required: list) -> str:
    first_missing = missing_required[0] if missing_required else "destination"
    slot_questions = {
        "origin": "Where will you be departing from?",
        "destination": "Where would you like to travel to?",
        "departure_date": "What date would you like to depart? (e.g. March 15, 2025)",
        "return_date": "When would you like to return?",
        "check_in_date": "What date would you like to check in to the hotel?",
        "check_out_date": "What date would you like to check out of the hotel?",
        "num_travelers": "How many travelers will be on this trip?",
        "budget_usd": "Do you have a budget in mind (in USD)?",
    }
    return slot_questions.get(first_missing, f"Could you provide more details about your {first_missing.replace('_', ' ')}?")


def merge_slots(existing: dict, new_slots: dict) -> dict:
    merged = dict(existing)
    for k, v in new_slots.items():
        if v is not None and v != [] and v != "null":
            merged[k] = v
    return merged


def compose_itinerary(slots: dict, flights: list, hotels: list, intent: str) -> str:
    data_block = json.dumps({
        "confirmed_slots": slots,
        "intent": intent,
        "flight_results": flights,
        "hotel_results": hotels
    }, indent=2)
    prompt = f"""Using ONLY the data provided below (do not invent any prices, times, or hotel names), compose a structured day-by-day travel itinerary in markdown format.

Travel Data:
{data_block}

Compose the itinerary now:"""
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def run_agent_turn(user_message: str, session_state: dict) -> str:
    messages = session_state.get("messages", [])
    slots = session_state.get("slots", {})
    last_search_results = session_state.get("last_search_results", {})
    clarification_turns = session_state.get("clarification_turns", 0)

    # Scope check for booking requests
    booking_keywords = ["book", "reserve", "purchase", "pay", "confirm", "buy ticket"]
    if any(kw in user_message.lower() for kw in booking_keywords):
        return "Booking and reservations are out of scope for V1 — I can help you plan and explore itinerary options. Would you like me to refine or adjust your current itinerary?"

    messages.append({"role": "user", "content": user_message})

    # Extract intent and slots
    extraction = extract_intent_and_slots(messages, slots)
    new_slots = extraction.get("slots", {})
    slots = merge_slots(slots, new_slots)
    intent = extraction.get("intent", "unclear")
    missing = extraction.get("missing_required", [])

    session_state["slots"] = slots

    # Cap clarification turns
    if missing and clarification_turns >= 4:
        return f"I still need the following details to proceed: {', '.join(missing)}. Please provide all of them in one message."

    if missing:
        session_state["clarification_turns"] = clarification_turns + 1
        question = generate_clarification_question(intent, slots, missing)
        messages.append({"role": "assistant", "content": question})
        return question

    # Reset clarification counter
    session_state["clarification_turns"] = 0

    # Resolve IATA codes
    origin_iata = resolve_iata(slots.get("origin", ""))
    dest_iata = resolve_iata(slots.get("destination", ""))
    num_travelers = slots.get("num_travelers", 1) or 1

    flights_data = None
    hotels_data = None
    warnings = []

    # Search flights
    if intent in ("full_itinerary", "flights_only"):
        if origin_iata and dest_iata and slots.get("departure_date"):
            result = search_flights(
                origin_iata=origin_iata,
                destination_iata=dest_iata,
                departure_date=slots["departure_date"],
                return_date=slots.get("return_date"),
                num_travelers=num_travelers
            )
            if result.get("error"):
                warnings.append(f"Flight search issue: {result['error']}")
            else:
                flights_data = result.get("flights", [])
            last_search_results["flights"] = result
        else:
            warnings.append("Missing origin, destination, or departure date for flight search.")

    # Search hotels
    if intent in ("full_itinerary", "hotels_only"):
        dep = slots.get("departure_date")
        ret = slots.get("return_date")
        check_in = slots.get("check_in_date") or dep
        check_out = slots.get("check_out_date") or ret
        if check_in == check_out:
            check_out = None  # Skip hotel if same-day
        dest = slots.get("destination", "")
        if dest and check_in and check_out:
            result = search_hotels(
                destination=dest,
                check_in_date=check_in,
                check_out_date=check_out,
                num_guests=num_travelers,
                budget_usd_per_night=slots.get("budget_usd")
            )
            if result.get("error"):
                warnings.append(f"Hotel search issue: {result['error']}")
            else:
                hotels_data = result.get("hotels", [])
            last_search_results["hotels"] = result
        elif check_in == check_out:
            warnings.append("Check-in and check-out are the same date — skipping hotel search.")
        else:
            warnings.append("Missing destination or dates for hotel search.")

    session_state["last_search_results"] = last_search_results

    if flights_data is None and hotels_data is None and not warnings:
        response_text = "I wasn't able to retrieve live flight or hotel data. Please check your connection and try again."
    else:
        response_text = compose_itinerary(slots, flights_data, hotels_data, intent)
        if warnings:
            response_text += "\n\n> **Notes:**\n" + "\n".join(f"- {w}" for w in warnings)

    messages.append({"role": "assistant", "content": response_text})
    session_state["messages"] = messages
    return response_text
