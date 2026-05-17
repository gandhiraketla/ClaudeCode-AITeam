# Code Review - APPROVED_WITH_CHANGES

## Summary
This is the third implementation pass for the travel itinerary agent. The core architecture — Streamlit UI, ReAct agent, SerpApi flight and hotel tools, Claude-based itinerary composer, and session state management — is structurally sound and aligned with the approved design. However, the security audit in this pass continues to flag all four originally blocking issues as unresolved: prompt injection sanitization, SerpApi exception leakage of API keys, absence of per-session rate limiting, and the missing hard cap on clarification turns. Until the code demonstrates these four controls are actually present in the source, the verdict remains APPROVED_WITH_CHANGES. The six suggestions cover schema validation, slot-merge safety, dual-null composition guard, API-key post-processing, search_flights input guard, and config.toml confirmation — none are blocking independently but together represent meaningful production risk reduction.

## [BLOCKING] src/agent.py clarification loop logic
The security audit in this third pass still flags 'clarification turn cap of 4 is in design doc but not confirmed enforced in code.' If st.session_state.clarification_turns is not incremented and checked with a hard guard before calling generate_clarification_question, an adversarial or confused user can loop indefinitely, exhausting LLM API budget.
**Fix:** Add: if st.session_state.get('clarification_turns', 0) >= 4: return hard-stop message before any clarification call. Increment the counter after each clarification response.

## [BLOCKING] src/tools.py SerpApi call sites
Security audit (third pass) still rates SerpApi raw exceptions as HIGH. If except blocks re-raise or propagate exception.args, the API key embedded in the SerpApi request URL can appear in Streamlit's error display or logs.
**Fix:** All SerpApi calls must be wrapped in try/except Exception as e: return {"error": "Search unavailable. Please try again."}. Never reference str(e), e.args, or the request URL in any returned value.

## [BLOCKING] src/app.py chat submit handler
No per-session call counter exists per the security audit (third pass still flagged MEDIUM). Without a hard cap, a single browser session can issue unlimited SerpApi and Anthropic calls, creating unbounded cost exposure.
**Fix:** Add st.session_state.call_count (init 0). Increment on every LLM or SerpApi call. If call_count >= 20, display a warning and return without calling any external API.

## [BLOCKING] src/agent.py user message append
Security audit (third pass) still flags prompt injection as HIGH. User message is appended to the Claude context without filtering instruction-override patterns.
**Fix:** Before appending user_message to the messages array, screen for patterns like 'ignore previous', 'disregard', 'you are now', 'system:', and truncate or reject the message with a user-visible warning if matched.

## [SUGGESTION] src/tools.py SerpApi response parsing
SerpApi JSON responses are passed to compose_itinerary without schema validation. A malformed payload with missing keys causes unhandled KeyError inside the composer.
**Fix:** Validate that required keys (e.g. 'flights', 'hotels', 'price') exist before returning data. Use .get() with defaults and drop malformed entries rather than letting KeyError propagate.

## [SUGGESTION] src/agent.py slot merge logic
If extract_intent_and_slots returns an overlapping slot value (e.g. a new destination that contradicts an earlier one), the merge strategy is unclear. A simple dict update will silently overwrite confirmed slots.
**Fix:** Log slot overwrites at DEBUG level and, if a confirmed slot changes value mid-session, prompt the user to confirm the change rather than silently replacing it.

## [SUGGESTION] src/agent.py compose_itinerary guard
If both search_flights and search_hotels return errors, compose_itinerary may still be called with flights=null and hotels=null, producing an empty or misleading itinerary.
**Fix:** Add a pre-composition guard: if flights is null and hotels is null, return a user-facing message explaining both data sources failed, and skip the compose call.

## [SUGGESTION] src/prompts.py compose_itinerary system prompt
Security audit flagged that no runtime check strips API key values from Claude output. The system prompt alone cannot guarantee the model never echoes an injected key.
**Fix:** After receiving compose_itinerary response from Claude, assert that SERPAPI_API_KEY and ANTHROPIC_API_KEY substrings are absent from the response string before displaying in chat.

## [SUGGESTION] src/tools.py search_flights input validation
Agent design requires rejecting any search_flights call missing origin_iata or departure_date and routing back to clarification. If this validation lives only in agent.py and not in tools.py, a future caller can bypass it.
**Fix:** Add a guard at the top of search_flights: if not origin_iata or not departure_date: return {"error": "Missing required fields", "flights": []}.

## [SUGGESTION] .streamlit/config.toml entire file
Security audit flagged missing config.toml with CORS and XSRF protections. Implementation report lists config.toml as written, but the security audit in this third pass still references it as a finding.
**Fix:** Confirm file exists at .streamlit/config.toml with [server] enableCORS = false and enableXsrfProtection = true. If present, this finding is resolved.
