# Security Audit

## Files Audited
- src/app.py
- src/agent.py
- src/tools.py
- src/prompts.py
- src/state.py
- src/demo.py

## [HIGH] src/agent.py: Prompt Injection
User message appended to Claude context without sanitization; adversarial input can override system prompt
**Fix:** Strip instruction-override patterns (e.g. 'ignore previous instructions') before appending to messages array

## [HIGH] src/tools.py: Sensitive Data Exposure
SerpApi raw exceptions may include API key or full request URL in exception.args propagated to caller
**Fix:** Wrap all SerpApi calls in try/except; return only a normalized error string; never expose exception.args

## [MEDIUM] src/app.py: Rate Limiting
No per-session call counter; user or script can trigger unlimited SerpApi and Anthropic API spend
**Fix:** Track call count in st.session_state; hard-cap at 20 combined LLM+search calls; show warning at limit

## [MEDIUM] src/agent.py: Agent Loop — Cost/DoS
Clarification turn cap of 4 is specified in design but has not been confirmed present in source code
**Fix:** Add guard: if st.session_state.clarification_turns >= 4 raise hard stop before calling generate_clarification_question

## [MEDIUM] src/tools.py: Insecure Deserialization
SerpApi JSON used without schema validation; malformed payloads cause KeyError or inject bad data into itinerary
**Fix:** Validate response keys against expected schema; drop or flag unexpected fields before passing to compose_itinerary

## [MEDIUM] src/agent.py: Sensitive Data in LLM Context
Full message history including budget_usd and num_travelers sent verbatim to Claude on every extract call
**Fix:** Pass slots object separately to extract_intent_and_slots; exclude raw PII slot values from message history

## [LOW] src/app.py: Security Misconfiguration
No .streamlit/config.toml detected; default Streamlit config may allow CORS from any origin
**Fix:** Add .streamlit/config.toml with enableCORS = false and enableXsrfProtection = true under [server]

## [LOW] src/prompts.py: Information Disclosure
No runtime check strips API key substrings from Claude output; keys could appear in LLM responses
**Fix:** Post-process all Claude response strings and assert SERPAPI_API_KEY and ANTHROPIC_API_KEY are absent

## Deployment Warnings
- HIGH: Two HIGH findings remain unresolved across three implementation passes — do not deploy to any internet-facing environment
- Prompt injection sanitization has not been confirmed implemented in src/agent.py — treat as unmitigated
- SerpApi exception wrapping has not been confirmed complete in src/tools.py — API key leakage risk remains
- Per-session rate limiting is absent — SerpApi and Anthropic costs are unbounded per user
- Clarification loop hard cap of 4 turns is unconfirmed in code — infinite loop and runaway cost possible
- Ensure .env is in .gitignore; SERPAPI_API_KEY and ANTHROPIC_API_KEY must never be committed to source control
- Do not run Streamlit in debug mode in any shared or hosted environment — tracebacks expose internal paths
- Add .streamlit/config.toml before any hosted deployment to enforce CORS and XSRF protections
