"""Streamlit Chat UI for the Travel Itinerary Agent."""
import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

from src.state import init_state, is_call_limit_reached, MAX_CALLS_PER_SESSION
from src.agent import run_agent

st.set_page_config(
    page_title="Travel Itinerary Agent",
    page_icon="✈️",
    layout="centered",
)

st.title("✈️ Travel Itinerary Agent")
st.caption("Plan flights, hotels, and day-by-day itineraries using natural language.")

init_state()

# Show rate limit warning
call_count = st.session_state.get("call_count", 0)
if call_count >= MAX_CALLS_PER_SESSION - 5:
    remaining = MAX_CALLS_PER_SESSION - call_count
    st.warning(f"⚠️ {remaining} API call(s) remaining in this session.")

if is_call_limit_reached():
    st.error("Session API call limit reached. Please refresh the page to start a new session.")
    st.stop()

# Render conversation history
for msg in st.session_state.get("messages", []):
    role = msg.get("role", "user")
    content = msg.get("content", "")
    with st.chat_message(role):
        st.markdown(content)

# Chat input
if user_input := st.chat_input("Where would you like to go?"):
    # Display user message immediately
    with st.chat_message("user"):
        st.markdown(user_input)

    # Show spinner while agent processes
    with st.chat_message("assistant"):
        with st.spinner("Planning your trip..."):
            try:
                response = run_agent(user_input)
            except Exception as exc:
                safe = str(exc)
                # Never expose API keys in error messages
                serpapi_key = os.environ.get("SERPAPI_API_KEY", "")
                anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
                if serpapi_key and serpapi_key in safe:
                    safe = safe.replace(serpapi_key, "[REDACTED]")
                if anthropic_key and anthropic_key in safe:
                    safe = safe.replace(anthropic_key, "[REDACTED]")
                response = f"An error occurred while processing your request. Please try again."
        st.markdown(response)

# Sidebar with session info and reset button
with st.sidebar:
    st.header("Session Info")
    st.write(f"API calls used: {st.session_state.get('call_count', 0)} / {MAX_CALLS_PER_SESSION}")
    st.write(f"Clarification turns: {st.session_state.get('clarification_turns', 0)}")
    slots = st.session_state.get("slots", {})
    if slots:
        st.subheader("Collected Trip Details")
        for k, v in slots.items():
            if v is not None and v != "" and v != []:
                st.write(f"**{k}:** {v}")
    if st.button("🔄 Start New Trip"):
        from src.state import reset_session
        reset_session()
        st.rerun()
    st.markdown("---")
    st.caption("V1 — Plan only. Booking not supported.")
