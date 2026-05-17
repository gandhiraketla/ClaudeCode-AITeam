"""Session state management for the travel itinerary agent."""
from __future__ import annotations
import streamlit as st
from typing import Any

MAX_CALLS = 20
MAX_CLARIFICATION_TURNS = 4


def init_state() -> None:
    """Initialize all session state keys if not already set."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "slots" not in st.session_state:
        st.session_state.slots = {}
    if "last_search_results" not in st.session_state:
        st.session_state.last_search_results = {"flights": None, "hotels": None}
    if "clarification_turns" not in st.session_state:
        st.session_state.clarification_turns = 0
    if "call_count" not in st.session_state:
        st.session_state.call_count = 0
    if "intent" not in st.session_state:
        st.session_state.intent = None


def append_message(role: str, content: str) -> None:
    """Append a message to the conversation history."""
    st.session_state.messages.append({"role": role, "content": content})


def merge_slots(new_slots: dict[str, Any]) -> None:
    """Merge newly extracted slots into accumulated session slots.
    Only updates keys that have a non-None, non-empty value.
    """
    for key, value in new_slots.items():
        if value is not None and value != "" and value != []:
            st.session_state.slots[key] = value


def increment_call_count() -> bool:
    """Increment the combined API call counter.
    Returns True if under limit, False if limit reached.
    """
    st.session_state.call_count += 1
    return st.session_state.call_count <= MAX_CALLS


def is_rate_limited() -> bool:
    """Return True if the session has hit the max combined API call limit."""
    return st.session_state.call_count >= MAX_CALLS


def increment_clarification_turns() -> None:
    """Increment the clarification turn counter."""
    st.session_state.clarification_turns += 1


def clarification_limit_reached() -> bool:
    """Return True if the agent has reached the max clarification turns."""
    return st.session_state.clarification_turns >= MAX_CLARIFICATION_TURNS


def set_search_results(flights: Any, hotels: Any) -> None:
    """Store the latest search results in session state."""
    st.session_state.last_search_results = {"flights": flights, "hotels": hotels}


def get_recent_messages(n: int = 10) -> list[dict]:
    """Return the last n messages from the conversation history."""
    return st.session_state.messages[-n:]


def get_slots() -> dict[str, Any]:
    """Return the current accumulated slots."""
    return dict(st.session_state.slots)


def get_search_results() -> dict[str, Any]:
    """Return the last stored search results."""
    return dict(st.session_state.last_search_results)


def set_intent(intent: str) -> None:
    """Store the most recently detected intent."""
    st.session_state.intent = intent


def get_intent() -> str | None:
    """Return the current intent."""
    return st.session_state.intent
