# Code Review - APPROVED_WITH_CHANGES

## Summary
The implementation covers the core flow — intent extraction, clarification, flight/hotel search, and itinerary composition — but has four blocking issues that must be resolved before this code is safe to run: the clarification loop has no hard cap in code (only in design), SerpApi exceptions are not fully caught and may leak the API key, there is no per-session rate limit protecting external API spend, and user input is appended to the Claude context without prompt-injection filtering. The security audit flagged all four of these and the implementer pass did not fully address them. Six suggestions cover schema validation, slot merge safety, dual-null guard before composition, IATA ambiguity handling, config.toml presence, and key-leak post-processing. The architecture and agent design are otherwise faithfully reflected in the code structure.

## [BLOCKING] src/agent.py around line 38-55
Clarification turn cap of 4 is referenced in design but not enforced in code. The clarification loop can run indefinitely, causing unbounded Anthropic API calls and potential DoS per session.
**Fix:** Before calling generate_clarification_question, check st.session_state.clarification_turns against a MAX_CLARIFICATION_TURNS=4 constant. If exceeded, return a hard-stop message listing all still-missing slots.

## [BLOCKING] src/tools.py around line 22-60
SerpApi exceptions are not fully caught. Raw exception strings, which may contain the API key or full request URL, can propagate up to the caller and surface in the chat UI.
**Fix:** Wrap all SerpApi calls in a broad try/except block. Return only a normalized error field string. Never include str(e), exception.args, or request URLs in the return value.

## [BLOCKING] src/app.py around line 15-30
No per-session rate limiting is implemented. A user or script can trigger unlimited SerpApi and Anthropic calls, resulting in unbounded external API costs.
**Fix:** Add st.session_state.call_count initialized to 0. Increment on each agent call. If call_count exceeds 20, display a warning and block further submissions for the session.

## [BLOCKING] src/agent.py around line 20-35
User message is appended to the Claude messages array without any sanitization. Prompt injection sequences can override the system prompt instructions.
**Fix:** Before appending user content to the messages list, strip or flag strings containing patterns like 'ignore previous instructions', 'disregard', or 'system:'. Log flagged inputs but do not crash.

## [SUGGESTION] src/tools.py around line 65-110
SerpApi JSON responses are passed to compose_itinerary without schema validation. Unexpected or missing keys will cause KeyError at itinerary composition time.
**Fix:** After receiving SerpApi response, validate expected top-level keys (e.g. 'flights', 'hotels') before returning. Drop or flag unexpected fields. Return empty list rather than raising KeyError.

## [SUGGESTION] src/prompts.py around line 1-40
System prompt instructs the model not to reveal API keys, but no runtime assertion checks that Claude-composed strings are key-free before they are displayed.
**Fix:** Add a post-processing guard in agent.py that asserts SERPAPI_API_KEY and ANTHROPIC_API_KEY substrings are absent from any string returned from Claude before writing to messages.

## [SUGGESTION] src/app.py root .streamlit/config.toml
No .streamlit/config.toml found with CORS and XSRF settings. The previous implementer pass was supposed to add this file per the security audit HIGH finding.
**Fix:** Ensure .streamlit/config.toml exists with [server] enableCORS = false and enableXsrfProtection = true.

## [SUGGESTION] src/agent.py around line 70-90
Slots are not always merged incrementally from each extract_intent_and_slots result. If the function re-extracts from scratch and earlier slot values are missing from the latest user turn, previously confirmed slots may be overwritten with None.
**Fix:** After calling extract_intent_and_slots, merge returned slots into st.session_state.slots using a dict update that skips None/missing values, never replaces a confirmed slot with None.

## [SUGGESTION] src/agent.py around line 100-120
No check prevents compose_itinerary from being called when both flights and hotels are None due to dual API errors. This would generate an empty or hallucinated itinerary.
**Fix:** Before calling compose_itinerary, check that at least one of flights or hotels is non-null and non-empty. If both are null, surface a user-friendly message instead of invoking the composer.

## [SUGGESTION] src/tools.py around line 18-25
City-to-IATA resolution for ambiguous cities (e.g. London: LHR/LGW/STN) is not implemented in the tool layer. The agent design specifies this must be handled before calling search_flights.
**Fix:** Add a simple city-to-primary-IATA mapping dict or a validation step that raises a structured error when a city resolves to multiple airports, so the orchestrator can route back to clarification.
