"""Streamlit Chat UI for the Travel Itinerary Agent."""
from __future__ import annotations
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.state import init_state, get_messages, get_session_calls, MAX_SESSION_CALLS
from src.agent import process_message

st.set_page_config(
    page_title="Travel Itinerary Agent",
    page_icon="✈️",
    layout="centered",
)

st.title("✈️ Travel Itinerary Agent")
st.caption("Plan flights, hotels, and day-by-day itineraries through conversation.")

init_state()

# Display conversation history
for msg in get_messages():
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Session call usage indicator
calls_used = get_session_calls()
if calls_used > 0:
    remaining = MAX_SESSION_CALLS - calls_used
    if remaining <= 5:
        st.warning(f"⚠️ {remaining} request(s) remaining in this session.")

# Chat input
user_input = st.chat_input("e.g. Plan my trip to Paris for 5 days in June for 2 people")

if user_input:
    # Show user message immediately
    with st.chat_message("user"):
        st.markdown(user_input)

    # Get agent response
    with st.chat_message("assistant"):
        with st.spinner("Planning your trip..."):
            response = process_message(user_input)
        st.markdown(response)
