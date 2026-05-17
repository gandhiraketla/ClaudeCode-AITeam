"""Demo script: runs the travel itinerary agent with sample inputs and prints output.

This script bypasses Streamlit and calls the agent logic directly.
Run: python demo.py
"""
from __future__ import annotations
import os
import sys
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.WARNING)

# Minimal st.session_state stub so src/state.py works outside Streamlit
class _SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)
    def __setattr__(self, name, value):
        self[name] = value
    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name)

import streamlit as _st_module
_st_module.session_state = _SessionState()

# Also patch st.rerun to no-op for demo context
try:
    _st_module.rerun = lambda: None
except Exception:
    pass

from src.state import init_state
from src.agent import process_message


def run_demo_turn(label: str, message: str) -> str:
    print(f"\n{'='*60}")
    print(f"USER [{label}]: {message}")
    print("-" * 60)
    reply = process_message(message)
    print(f"AGENT:\n{reply}")
    return reply


def main() -> None:
    print("Travel Itinerary Agent — Demo")
    print("Checking environment variables...")

    missing_keys = []
    for key in ("ANTHROPIC_API_KEY", "SERPAPI_API_KEY"):
        if not os.environ.get(key):
            missing_keys.append(key)

    if missing_keys:
        print(f"ERROR: Missing required environment variables: {', '.join(missing_keys)}")
        print("Copy .env.example to .env and fill in your API keys.")
        sys.exit(1)

    print("Environment OK.\n")

    # Initialize session state
    init_state()

    # Demo scenario 1: open-ended Paris trip request
    print("\n--- Scenario 1: Full itinerary request ---")
    run_demo_turn(
        "open-ended trip",
        "Plan my trip to Paris for 5 days in June 2025 for 2 people. I love art and food."
    )

    # Reset state for scenario 2
    import streamlit as st
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()

    # Demo scenario 2: specific flight query
    print("\n--- Scenario 2: Flights-only request ---")
    run_demo_turn(
        "flights only",
        "Show me flights from New York to Dallas on 2025-07-15"
    )

    # Reset state for scenario 3
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()

    # Demo scenario 3: incomplete input triggers clarification
    print("\n--- Scenario 3: Incomplete input — clarification expected ---")
    run_demo_turn(
        "incomplete",
        "I want to visit Tokyo"
    )

    print("\n" + "="*60)
    print("Demo complete.")


if __name__ == "__main__":
    main()
