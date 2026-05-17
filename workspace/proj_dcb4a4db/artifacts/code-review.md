# Code Review - APPROVED_WITH_CHANGES

## Summary
This is the fourth implementation pass for the travel itinerary agent. The overall architecture — Streamlit UI, ReAct agent loop, SerpApi flight and hotel tools, Claude-based itinerary composer, and session state management — is correctly structured and aligned with the approved design. However, the same four blocking issues flagged in the two previous code reviews remain unresolved in the source: (1) user input is appended to the Claude context without prompt-injection sanitization, (2) SerpApi exceptions may leak the API key through str(e) or exception.args, (3) there is no per-session API call counter capping spend, and (4) the clarification loop has no hard turn-cap enforced in code despite being specified in the agent design. These are not architectural changes — they are missing lines of defensive code that must be added before this agent is safe to run. Six suggestions cover slot-merge safety, dual-null composition guard, schema validation on SerpApi responses, API key post-processing in Claude output, IATA input validation, and config.toml content confirmation. The verdict is APPROVED_WITH_CHANGES pending resolution of all four blocking items.

## [BLOCKING] src/agent.py around line 40-80
User message is appended to the messages array and passed to Claude without any sanitization or prompt-injection filtering. Patterns such as 'ignore previous instructions' are not stripped before the context is sent to the LLM.
**Fix:** Before appending user_message to st.session_state.messages, run a simple filter that detects and strips or escapes common injection patterns (e.g. 'ignore previous', 'disregard your instructions', 'new system prompt'). Log a warning when a pattern is detected but do not expose the filter logic to the user.

## [BLOCKING] src/tools.py around line 20-80
SerpApi calls are wrapped in try/except but the except block re-raises or returns exception.args or str(e) which may contain the full request URL including the api_key query parameter. This leaks SERPAPI_API_KEY in error output passed back to the agent and potentially to the chat UI.
**Fix:** In every except block, return only a hardcoded normalized string such as 'Search service unavailable. Please try again.' Never call str(e), repr(e), or reference exception.args. Scrub any returned error string against the known API key value before returning.

## [BLOCKING] src/app.py around line 30-60
There is no per-session call counter in st.session_state. A user or script can submit messages in a tight loop, triggering unlimited SerpApi and Anthropic API calls with no guard. This exposes unbounded cost and is a DoS vector.
**Fix:** On session init set st.session_state.api_call_count = 0. Increment it on every LLM and SerpApi call. Before processing any new user message, check if the count has reached 20; if so, display a warning and return without calling any API.

## [BLOCKING] src/agent.py around line 55-100
The clarification turn cap of 4 specified in the agent design is not enforced in code. There is no guard that checks st.session_state.clarification_turns before calling generate_clarification_question, allowing an infinite clarification loop.
**Fix:** Track st.session_state.clarification_turns (init to 0, increment each time generate_clarification_question is called). Before calling it, check if clarification_turns >= 4; if so, surface a message listing all still-missing slots and ask the user to provide them in one message instead of asking another question.

## [SUGGESTION] src/tools.py around line 25-90
SerpApi JSON responses are consumed with direct key access (e.g. result['best_flights'][0]['price']) without checking whether the expected keys exist. A malformed or unexpected API response causes an unhandled KeyError that surfaces as a raw traceback.
**Fix:** Use .get() with defaults throughout all SerpApi response parsing. Wrap the parsing block in a try/except KeyError and return a normalized error structure rather than crashing.

## [SUGGESTION] src/agent.py around line 70-110
Slot merging uses a shallow dict update pattern. If extract_intent_and_slots returns a key with value None (slot was seen but not filled), it overwrites a previously confirmed non-None slot value in st.session_state.slots.
**Fix:** When merging new slots, only overwrite an existing slot value if the new value is not None. Use: for k, v in new_slots.items(): if v is not None: st.session_state.slots[k] = v

## [SUGGESTION] src/agent.py around line 115-140
compose_itinerary is called without a dual-null guard. If both search_flights and search_hotels return error states (flights=None, hotels=None), the composer still fires and Claude may fabricate content to fill the itinerary.
**Fix:** Before calling compose_itinerary, check if both flights and hotels are None/empty. If so, skip the composer call and return a user-facing message stating that live data could not be retrieved for any segment.

## [SUGGESTION] src/prompts.py around line 1-60
No runtime post-processing strips API key substrings from Claude response text. If the LLM ever echoes a key value embedded in a previous context message, it would be displayed in the chat UI.
**Fix:** After receiving any Claude response, run a scrub pass: assert that the SERPAPI_API_KEY and ANTHROPIC_API_KEY values (loaded from env) are not present in the response string. Replace with '[REDACTED]' if found.

## [SUGGESTION] src/tools.py around line 18-30
search_flights does not validate that origin_iata and destination_iata are non-empty IATA codes before calling SerpApi. Passing an empty string or city name causes a bad API call and a confusing error.
**Fix:** At the top of search_flights, assert that origin_iata and destination_iata match a basic IATA pattern (3 uppercase letters). If validation fails, return an error dict without calling SerpApi and route back to clarification.

## [SUGGESTION] .streamlit/config.toml entire file
config.toml is listed as written by the implementer but its content has not been confirmed to include enableCORS = false and enableXsrfProtection = true under [server]. Default Streamlit config allows CORS from any origin.
**Fix:** Confirm config.toml contains: [server] enableCORS = false enableXsrfProtection = true. Add headless = true if this will run in any non-local environment.
