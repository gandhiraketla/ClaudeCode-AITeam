#!/usr/bin/env python3
"""
demo.py — Standalone demo for the Travel Itinerary Agent.
Runs a simulated multi-turn conversation and prints the final itinerary.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("TRAVEL ITINERARY AGENT — DEMO")
print("=" * 60)
print("Agent: AI-powered travel planner that searches real-time")
print("       flights and hotels and composes a day-by-day itinerary.")
print("=" * 60)

SAMPLE_INPUT = "Plan my trip to Paris from New York for 5 days starting June 15 for 2 people, budget around $3000"
print(f"\nSample Input: {SAMPLE_INPUT}")
print("-" * 60)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from src.agent import TravelAgent
except ImportError as e:
    print(f"[ERROR] Could not import TravelAgent: {e}")
    print("Make sure you have run: pip install -r requirements.txt")
    sys.exit(1)

# Check required env vars
for var in ["ANTHROPIC_API_KEY", "SERPAPI_API_KEY"]:
    if not os.getenv(var):
        print(f"[WARNING] {var} not set in environment — API calls may fail.")

agent = TravelAgent()

print("\n[AGENT RESPONSE]\n")
try:
    response = agent.chat(SAMPLE_INPUT)
    print(response)
except Exception as e:
    print(f"[ERROR] Agent raised an exception: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("Demo complete.")
print("Run 'streamlit run app.py' to use the full chat interface.")
print("=" * 60)
