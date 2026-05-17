"""Demo script for the Travel Itinerary Agent — runs without user interaction."""
from __future__ import annotations
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Minimal stub for st.session_state so agent works outside Streamlit
class _SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)
    def __setattr__(self, name, value):
        self[name] = value

import streamlit as st
st.session_state = _SessionState()

from src.state import init_state
from src.agent import process_message

def run_demo():
    init_state()

    scenarios = [
        {
            "label": "Full itinerary request",
            "message": "Plan my trip to Paris for 5 days starting June 10 2025, 2 travelers, flying from New York. Budget around $200/night for hotels.",
        },
        {
            "label": "Flights-only query",
            "message": "Show me flights from New York to Dallas on March 15 2025 for 1 person.",
        },
        {
            "label": "Incomplete request (clarification expected)",
            "message": "I want to visit Tokyo.",
        },
    ]

    for scenario in scenarios:
        print("=" * 70)
        print(f"SCENARIO: {scenario['label']}")
        print(f"USER: {scenario['message']}")
        print("-" * 70)

        # Reset state for each scenario
        st.session_state.clear()
        init_state()

        response = process_message(scenario["message"])
        print(f"AGENT:\n{response}")
        print()

if __name__ == "__main__":
    missing_keys = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing_keys.append("ANTHROPIC_API_KEY")
    if not os.environ.get("SERPAPI_API_KEY"):
        missing_keys.append("SERPAPI_API_KEY")
    if missing_keys:
        print(f"WARNING: Missing environment variables: {', '.join(missing_keys)}")
        print("Add them to your .env file. Demo will run but API calls will fail gracefully.")
        print()
    run_demo()
