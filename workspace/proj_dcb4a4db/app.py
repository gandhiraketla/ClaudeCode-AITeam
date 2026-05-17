import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()

from src.agent import TravelAgent
from src.state import init_session_state

st.set_page_config(page_title="Travel Itinerary Agent", page_icon="✈️", layout="centered")
st.title("✈️ Travel Itinerary Agent")
st.caption("Plan flights, hotels, and day-by-day itineraries through conversation.")

init_session_state()

if "agent" not in st.session_state:
    st.session_state.agent = TravelAgent(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        serpapi_api_key=os.environ["SERPAPI_API_KEY"]
    )

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Where would you like to travel?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Planning your trip..."):
            response = st.session_state.agent.process_message(
                user_message=prompt,
                messages=st.session_state.messages[:-1],
                slots=st.session_state.slots,
                last_search_results=st.session_state.last_search_results
            )
            st.markdown(response["reply"])
            if response.get("slots"):
                st.session_state.slots.update(response["slots"])
            if response.get("search_results"):
                st.session_state.last_search_results.update(response["search_results"])

    st.session_state.messages.append({"role": "assistant", "content": response["reply"]})
