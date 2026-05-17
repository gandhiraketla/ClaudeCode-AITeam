"""Session state management for the Travel Itinerary Agent."""
from __future__ import annotations
import streamlit as st
from typing import Any

MAX_CLARIFICATION_TURNS = 4
MAX_SESSION_CALLS = 20

DEFAULT_STATE: dict[str, Any] = {
    "messages": [],
    "slots": {},
    "last_search_results": {"flights": None, "hotels": None},
    "clarification_turns": 0,
    "session_calls": 0,
    "intent": None,
}


def init_state() -> None:
    """Initialize st.session_state with default values if not already set."""
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            import copy
            st.session_state[key] = copy.deepcopy(value)


def get_messages() -> list[dict]:
    return st.session_state.messages


def append_message(role: str, content: str) -> None:
    st.session_state.messages.append({"role": role, "content": content})


def get_slots() -> dict:
    return st.session_state.slots


def merge_slots(new_slots: dict) -> None:
    """Merge new slot values into existing slots, never overwriting with None."""
    for k, v in new_slots.items():
        if v is not None and v != "":
            st.session_state.slots[k] = v


def get_search_results() -> dict:
    return st.session_state.last_search_results


def set_flight_results(flights: list | None) -> None:
    st.session_state.last_search_results["flights"] = flights


def set_hotel_results(hotels: list | None) -> None:
    st.session_state.last_search_results["hotels"] = hotels


def get_clarification_turns() -> int:
    return st.session_state.clarification_turns


def increment_clarification_turns() -> None:
    st.session_state.clarification_turns += 1


def clarification_limit_reached() -> bool:
    return st.session_state.clarification_turns >= MAX_CLARIFICATION_TURNS


def increment_session_calls() -> bool:
    """Increment call counter. Returns True if limit exceeded."""
    st.session_state.session_calls += 1
    return st.session_state.session_calls > MAX_SESSION_CALLS


def get_session_calls() -> int:
    return st.session_state.session_calls


def set_intent(intent: str | None) -> None:
    st.session_state.intent = intent


def get_intent() -> str | None:
    return st.session_state.intent


def get_recent_messages(n: int = 10) -> list[dict]:
    """Return the last n messages for intent extraction (context window management)."""
    return st.session_state.messages[-n:]
