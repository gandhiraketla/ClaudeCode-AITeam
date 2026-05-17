# Security Audit

## Files Audited
- src/app.py
- src/agent.py
- src/tools.py
- src/prompts.py
- src/state.py
- src/demo.py
- src/requirements.txt
- src/.env.example

## [HIGH] src/agent.py: Prompt Injection
User message appended to Claude context without sanitization; adversarial input can hijack agent instructions.
**Fix:** Strip or escape sequences like 'Ignore previous instructions' before appending user content to the messages array.

## [HIGH] src/tools.py: Sensitive Data Exposure
SerpApi raw HTTP errors may propagate upward and expose API key or internal URL in exception strings.
**Fix:** Catch all SerpApi exceptions; return only normalized error field; never include exception.args or request URLs in output.

## [MEDIUM] src/app.py: Rate Limiting
No rate limiting on chat submit; a user or script can trigger unlimited SerpApi and Anthropic calls per session.
**Fix:** Add per-session call counter in st.session_state; cap at ~20 LLM+search calls per session with a user-visible warning.

## [MEDIUM] src/agent.py: Agent Loop — Cost/DoS
Clarification loop cap of 4 turns is defined in design but must be enforced in code; unverified in implementation.
**Fix:** Assert st.session_state clarification_turns <= 4 before calling generate_clarification_question; raise hard stop if exceeded.

## [MEDIUM] src/tools.py: Insecure Deserialization
SerpApi JSON responses are used without schema validation; malformed or adversarial payloads could cause KeyError or inject data into itinerary.
**Fix:** Validate SerpApi response against expected keys before passing to compose_itinerary; drop or flag unexpected fields.

## [MEDIUM] src/agent.py: Sensitive Data in LLM Context
Full conversation history including budget_usd and num_travelers is sent to Claude; history is not scrubbed before LLM calls.
**Fix:** Exclude raw slot values from message history passed to extract_intent_and_slots; pass slots object separately instead.

## [LOW] src/app.py: Security Misconfiguration
Streamlit default config may enable CORS from any origin on localhost; no explicit server.enableCORS=false set.
**Fix:** Add .streamlit/config.toml with [server] enableCORS = false and enableXsrfProtection = true.

## [LOW] src/prompts.py: Information Disclosure
System prompt instructs agent not to reveal keys, but no runtime assertion prevents key values from appearing in composed strings.
**Fix:** Add a post-processing check on all strings returned from Claude: assert SERPAPI_API_KEY and ANTHROPIC_API_KEY substrings are absent.

## Deployment Warnings
- Do not deploy publicly without adding per-session rate limiting; SerpApi and Anthropic costs are unbounded per user.
- Ensure .env is in .gitignore and SERPAPI_API_KEY / ANTHROPIC_API_KEY are never committed to source control.
- Do not run in debug or development mode in any internet-facing environment; Streamlit debug exposes tracebacks.
- All API keys must be injected via environment variables only — never hardcoded or logged.
- Prompt injection risk is present: if deploying to untrusted users, add input filtering before LLM submission.
