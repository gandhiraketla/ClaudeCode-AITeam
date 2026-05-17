"""Streamlit chat UI for the travel itinerary agent."""
from __future__ import annotations
import logging
import os
from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from src.state import (
    MAX_CALLS,
    init_state,
    is_rate_limited,
    get_slots,
)
from src.agent import process_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Travel Itinerary Agent",
    page_icon="✈️",
    layout="centered",
)


def render_header() -> None:
    st.title("✈️ Travel Itinerary Agent")
    st.caption(
        "Plan flights, hotels, and day-by-day itineraries. "
        "Try: *'Plan my trip to Paris for 5 days in June for 2 people'*"
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Session Info")
        call_count = st.session_state.get("call_count", 0)
        st.metric("API Calls Used", f"{call_count} / {MAX_CALLS}")
        if call_count >= MAX_CALLS * 0.8:
            st.warning(f"Approaching session limit ({MAX_CALLS} calls).")
        slots = get_slots()
        if slots:
            st.subheader("Collected Trip Details")
            for k, v in slots.items():
                if v:
                    st.write(f"**{k.replace('_', ' ').title()}:** {v}")
        if st.button("🔄 Start New Session"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def render_chat_history() -> None:
    messages = st.session_state.get("messages", [])
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        with st.chat_message(role):
            st.markdown(content)


def handle_user_input(user_input: str) -> None:
    """Process user input and display the assistant response."""
    with st.chat_message("user"):
        st.markdown(user_input)

    if is_rate_limited():
        reply = (
            f"You have reached the maximum of {MAX_CALLS} API calls for this session. "
            "Please click 'Start New Session' in the sidebar to continue."
        )
        with st.chat_message("assistant"):
            st.warning(reply)
        return

    with st.chat_message("assistant"):
        with st.spinner("Planning your trip..."):
            try:
                reply = process_message(user_input)
            except Exception as exc:
                logger.error("Unhandled error in process_message: %s", exc)
                reply = (
                    "An unexpected error occurred while processing your request. "
                    "Please try again or start a new session."
                )
        st.markdown(reply)


def main() -> None:
    init_state()
    render_header()
    render_sidebar()

    render_chat_history()

    user_input = st.chat_input("Where would you like to travel?")
    if user_input and user_input.strip():
        handle_user_input(user_input.strip())


if __name__ == "__main__":
    main()
