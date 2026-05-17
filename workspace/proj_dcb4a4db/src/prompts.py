"""Prompt templates for the travel itinerary agent."""
from __future__ import annotations
import os
import re

SYSTEM_PROMPT = """You are a travel planning assistant. You help users create structured day-by-day travel itineraries.

Roles and responsibilities:
- Extract travel intent and slots (origin, destination, dates, travelers, budget, interests) from user messages
- Ask ONE clarifying question at a time when required information is missing
- Use ONLY real data from tool results — never fabricate flight numbers, hotel names, or prices
- When composing itineraries, follow the exact output format below
- If live data is unavailable for a segment, say so explicitly — never silently omit it
- Booking, payment, and reservation confirmation are OUT OF SCOPE — politely decline and offer to refine the plan

Output format for itineraries:
- Use day headers: "Day 1: [date]"
- Sub-sections per day: ### Flights, ### Accommodation, ### Activities
- Every flight entry must include: airline, flight number, departure/arrival times, price
- Every hotel entry must include: name, star rating, price per night, total price
- If fewer than 2 options exist for a section, state that clearly — do not invent additional options

Scope guardrails:
- Never offer to book, pay, or confirm reservations
- Never invent prices, flight numbers, or hotel names
- If asked to export to PDF/email/calendar, explain this is not available in V1
"""

INTENT_EXTRACTION_PROMPT = """Analyze the conversation and extract travel intent and slots.

Return ONLY a JSON object with this exact shape:
{{
  "intent": "full_itinerary|flights_only|hotels_only|unclear",
  "slots": {{
    "origin": "string or null",
    "destination": "string or null",
    "departure_date": "YYYY-MM-DD or null",
    "return_date": "YYYY-MM-DD or null",
    "check_in_date": "YYYY-MM-DD or null",
    "check_out_date": "YYYY-MM-DD or null",
    "num_travelers": "integer or null",
    "budget_usd": "number or null",
    "interests": "array of strings or null"
  }},
  "missing_required": ["list of missing required slot names"]
}}

Rules:
- intent=full_itinerary when user wants a complete trip plan
- intent=flights_only when user asks only about flights
- intent=hotels_only when user asks only about hotels
- For full_itinerary, required slots are: destination, departure_date
- For flights_only, required slots are: origin, destination, departure_date
- For hotels_only, required slots are: destination, check_in_date, check_out_date
- missing_required lists only truly missing slots, not optional ones
- Return ONLY the JSON object, no explanation

Conversation:
{conversation}

Current known slots:
{slots}
"""

CLARIFICATION_PROMPT = """The user is planning a trip and we need more information.

Intent detected: {intent}
Already known: {confirmed_slots}
First missing required slot: {first_missing}

Generate a single, friendly clarifying question to ask for the missing slot.
Return ONLY a JSON object:
{{"question": "your question here", "slot_being_asked": "{first_missing}"}}

Make the question conversational and specific to the travel context.
"""

COMPOSE_ITINERARY_PROMPT = """Compose a structured day-by-day travel itinerary.

Trip details:
{slots_json}

Flight results:
{flights_json}

Hotel results:
{hotels_json}

Intent: {intent}

Instructions:
- Use ONLY the flight and hotel data provided above — never invent data
- Format with day headers (Day 1: [date]), and sub-sections for Flights, Accommodation, Activities
- Include all prices, times, and flight numbers exactly as provided
- If flights data is null or empty, state that no flight data was available for this segment
- If hotels data is null or empty, state that no hotel data was available
- Suggest generic activities based on destination and interests (activities are not from live data — label them as suggestions)
- Keep the itinerary scannable: use bullet points, bold key info
"""


INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(previous|prior|all|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|prior|all|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(previous|prior|all|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"act\s+as\s+(?!a\s+travel)", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
]


def sanitize_user_input(text: str) -> str:
    """Strip prompt injection patterns from user input before adding to context."""
    if not isinstance(text, str):
        return ""
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub("[removed]", sanitized)
    return sanitized[:4000]


def scrub_api_keys(text: str) -> str:
    """Remove API key substrings from any LLM response before displaying."""
    serpapi_key = os.environ.get("SERPAPI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if serpapi_key and serpapi_key in text:
        text = text.replace(serpapi_key, "[REDACTED]")
    if anthropic_key and anthropic_key in text:
        text = text.replace(anthropic_key, "[REDACTED]")
    return text


def build_intent_prompt(conversation: list[dict], slots: dict) -> str:
    """Build the intent extraction prompt."""
    import json
    convo_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in conversation[-10:]
    )
    slots_text = json.dumps(slots, indent=2)
    return INTENT_EXTRACTION_PROMPT.format(conversation=convo_text, slots=slots_text)


def build_clarification_prompt(intent: str, confirmed_slots: dict, missing_required: list) -> str:
    """Build the clarification question prompt."""
    import json
    first_missing = missing_required[0] if missing_required else "unknown"
    return CLARIFICATION_PROMPT.format(
        intent=intent,
        confirmed_slots=json.dumps(confirmed_slots, indent=2),
        first_missing=first_missing,
    )


def build_compose_prompt(slots: dict, flights: list | None, hotels: list | None, intent: str) -> str:
    """Build the itinerary composition prompt."""
    import json
    return COMPOSE_ITINERARY_PROMPT.format(
        slots_json=json.dumps(slots, indent=2),
        flights_json=json.dumps(flights, indent=2) if flights is not None else "null",
        hotels_json=json.dumps(hotels, indent=2) if hotels is not None else "null",
        intent=intent,
    )
