"""Session state management for the travel itinerary agent."""
import streamlit as st
from typing import Any, Optional


DEFAULT_SLOTS = {
    "origin": None,
    "destination": None,
    "check_in_date": None,
    "check_out_date": None,
    "departure_date": None,
    "return_date": None,
    "num_travelers": None,
    "budget_usd": None,
    "interests": None,
}


def init_state() -> None:
    """Initialize st.session_state keys if not already present."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "slots" not in st.session_state:
        st.session_state.slots = dict(DEFAULT_SLOTS)
    if "last_search_results" not in st.session_state:
        st.session_state.last_search_results = {"flights": None, "hotels": None}
    if "clarification_turns" not in st.session_state:
        st.session_state.clarification_turns = 0
    if "intent" not in st.session_state:
        st.session_state.intent = None


def add_message(role: str, content: str) -> None:
    """Append a message to the conversation history."""
    st.session_state.messages.append({"role": role, "content": content})


def merge_slots(new_slots: dict) -> None:
    """Merge newly extracted slot values into the persisted slots object.
    Only overwrites a slot if the new value is not None."""
    for key, value in new_slots.items():
        if value is not None:
            st.session_state.slots[key] = value


def get_slots() -> dict:
    """Return current accumulated slots."""
    return st.session_state.slots


def set_intent(intent: str) -> None:
    """Persist the latest detected intent."""
    st.session_state.intent = intent


def get_intent() -> Optional[str]:
    return st.session_state.intent


def set_search_results(flights: Any, hotels: Any) -> None:
    """Store the latest search results from tool calls."""
    st.session_state.last_search_results = {"flights": flights, "hotels": hotels}


def get_search_results() -> dict:
    return st.session_state.last_search_results


def get_recent_messages(limit: int = 10) -> list:
    """Return the last `limit` messages for context-constrained calls."""
    return st.session_state.messages[-limit:]


def get_all_messages() -> list:
    return st.session_state.messages


def increment_clarification_turns() -> int:
    st.session_state.clarification_turns += 1
    return st.session_state.clarification_turns


def get_clarification_turns() -> int:
    return st.session_state.clarification_turns


def reset_state() -> None:
    """Full reset — used for testing or explicit session clear."""
    st.session_state.messages = []
    st.session_state.slots = dict(DEFAULT_SLOTS)
    st.session_state.last_search_results = {"flights": None, "hotels": None}
    st.session_state.clarification_turns = 0
    st.session_state.intent = None
