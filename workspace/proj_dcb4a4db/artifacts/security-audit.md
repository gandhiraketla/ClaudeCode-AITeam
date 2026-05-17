# Security Audit

## Files Audited
- src/app.py
- src/agent.py
- src/tools.py
- src/prompts.py
- src/state.py
- src/demo.py

## [HIGH] src/agent.py: Prompt Injection
User message appended to Claude context without sanitization; adversarial input can hijack system instructions
**Fix:** Detect and strip instruction-override patterns (e.g. 'ignore previous') before appending to messages array

## [HIGH] src/tools.py: Sensitive Data Exposure
SerpApi raw exceptions may include API key or request URL in exception.args propagated to caller
**Fix:** Wrap all SerpApi calls in try/except; return only normalized error string; never expose exception.args or URLs

## [MEDIUM] src/app.py: Rate Limiting
No per-session call counter; script or user can trigger unlimited SerpApi and Anthropic spend
**Fix:** Track call count in st.session_state; hard-cap at 20 LLM+search calls; show user-visible warning at limit

## [MEDIUM] src/agent.py: Agent Loop — Cost/DoS
Clarification turn cap of 4 is in design doc but not confirmed enforced in code; infinite loop risk
**Fix:** Add guard: if st.session_state.clarification_turns >= 4 raise hard stop before calling generate_clarification_question

## [MEDIUM] src/tools.py: Insecure Deserialization
SerpApi JSON used without schema validation; malformed payloads cause KeyError or inject bad data into itinerary
**Fix:** Validate response keys against expected schema; drop or flag unexpected fields before passing to compose_itinerary

## [MEDIUM] src/agent.py: Sensitive Data in LLM Context
Full message history including budget_usd and num_travelers sent verbatim to Claude on every extract call
**Fix:** Pass slots object separately; exclude raw PII slot values from message history sent to extract_intent_and_slots

## [LOW] src/app.py: Security Misconfiguration
No .streamlit/config.toml found; default Streamlit config may allow CORS from any origin
**Fix:** Add .streamlit/config.toml with enableCORS = false and enableXsrfProtection = true under [server]

## [LOW] src/prompts.py: Information Disclosure
System prompt instructs agent not to reveal keys but no runtime check strips key values from Claude output
**Fix:** Post-process all Claude response strings: assert SERPAPI_API_KEY and ANTHROPIC_API_KEY substrings are absent

## Deployment Warnings
- HIGH findings present: do not deploy to internet-facing environment without resolving prompt injection and API key exposure risks
- Per-session rate limiting is absent; SerpApi and Anthropic costs are unbounded per user before deployment
- Ensure .env is in .gitignore; SERPAPI_API_KEY and ANTHROPIC_API_KEY must never be committed to source control
- Do not run Streamlit in debug mode in any internet-accessible environment; tracebacks expose internal paths
- Add .streamlit/config.toml with CORS and XSRF protections before any shared or hosted deployment
