"""Session state management for the Travel Itinerary Agent."""
import streamlit as st

MAX_CALLS_PER_SESSION = 20
MAX_CLARIFICATION_TURNS = 4


def init_state() -> None:
    """Initialize all session state keys if not already present."""
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
    """Append a message to conversation history."""
    st.session_state.messages.append({"role": role, "content": content})


def merge_slots(new_slots: dict) -> None:
    """Merge newly extracted slots into accumulated slots (never overwrite with None)."""
    for key, value in new_slots.items():
        if value is not None and value != "" and value != []:
            st.session_state.slots[key] = value


def get_recent_messages(n: int = 10) -> list:
    """Return the last n messages for token-limited calls."""
    return st.session_state.messages[-n:]


def get_all_messages() -> list:
    """Return full conversation history."""
    return list(st.session_state.messages)


def increment_call_count() -> bool:
    """Increment call counter. Returns True if limit exceeded."""
    st.session_state.call_count += 1
    return st.session_state.call_count > MAX_CALLS_PER_SESSION


def is_call_limit_reached() -> bool:
    """Check if per-session API call limit has been reached."""
    return st.session_state.call_count >= MAX_CALLS_PER_SESSION


def increment_clarification_turns() -> None:
    """Increment the clarification turn counter."""
    st.session_state.clarification_turns += 1


def is_clarification_cap_reached() -> bool:
    """Check if clarification turn cap has been reached."""
    return st.session_state.clarification_turns >= MAX_CLARIFICATION_TURNS


def set_search_results(flights: list | None, hotels: list | None) -> None:
    """Store the latest search results."""
    if flights is not None:
        st.session_state.last_search_results["flights"] = flights
    if hotels is not None:
        st.session_state.last_search_results["hotels"] = hotels


def get_search_results() -> dict:
    """Retrieve the latest cached search results."""
    return st.session_state.last_search_results


def set_intent(intent: str) -> None:
    """Store the current detected intent."""
    st.session_state.intent = intent


def get_intent() -> str | None:
    """Get the current detected intent."""
    return st.session_state.intent


def reset_session() -> None:
    """Clear all session state (for testing / manual reset)."""
    for key in ["messages", "slots", "last_search_results",
                "clarification_turns", "call_count", "intent"]:
        if key in st.session_state:
            del st.session_state[key]
    init_state()
