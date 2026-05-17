# Security Audit

## Files Audited
- src/app.py
- src/csv_parser.py
- src/chart_engine.py
- src/insight_generator.py
- src/demo.py
- requirements.txt
- .env.example

## [HIGH] src/insight_generator.py: Prompt Injection
CSV cell values inserted into Claude prompt without sanitization; attacker-controlled CSV can hijack instructions.
**Fix:** Strip or escape sequences like 'Ignore previous instructions' and role-delimiter strings before inserting sample rows into prompt.

## [HIGH] src/insight_generator.py: Sensitive Data Exposure
Full API key passed as function parameter; if exception is logged with locals(), key leaks to console/log.
**Fix:** Never pass api_key as a plain parameter. Instantiate Anthropic client inside the function reading from env directly; never include key in exception context.

## [HIGH] src/app.py: Missing Rate Limiting
No per-session or time-based guard on API calls beyond insight_generated flag; flag reset on each re-upload allows rapid repeated calls.
**Fix:** Add a cooldown timestamp in session_state (e.g., last_api_call_time) and enforce minimum 10s between uploads to prevent cost DoS.

## [MEDIUM] src/csv_parser.py: Input Validation
CSV MIME type not verified; attacker can upload HTML/JS/executable renamed as .csv and trigger pandas parse errors or path confusion.
**Fix:** Check first bytes for CSV-compatible content (text/plain magic) and reject files where pandas raises ParserError before processing.

## [MEDIUM] src/insight_generator.py: Sensitive Data Exposure to Third Party
Up to 20 rows of raw CSV data (potentially PII: names, emails, salaries) sent to Anthropic API with no scrubbing.
**Fix:** Add a pre-send PII detector (regex for email, phone, SSN patterns) and mask matched values before inserting into prompt payload.

## [MEDIUM] src/app.py: Security Misconfiguration
Streamlit runs on 0.0.0.0:8501 by default; any host on the local network can access the app and upload files.
**Fix:** Add server.address=localhost to .streamlit/config.toml to restrict binding to loopback only for local deployment.

## [MEDIUM] src/insight_generator.py: Insecure Error Handling
If API exception message contains request headers (some SDK versions do), key fragments may surface in st.error output.
**Fix:** Catch anthropic.APIError specifically, log str(e) to server console only, and display a generic message to the UI.

## [LOW] .env.example: Sensitive Data Exposure
If .env (not .env.example) is accidentally committed, ANTHROPIC_API_KEY is exposed in version control.
**Fix:** Confirm .env is in .gitignore; add a pre-commit hook or CI check that scans for ANTHROPIC_API_KEY= patterns.

## Deployment Warnings
- THREE HIGH findings present — review prompt injection and API key exposure before any non-local deployment.
- CSV data including potential PII is transmitted to Anthropic API — confirm this is acceptable under your data policy before use with real sales data.
- Streamlit default binding is 0.0.0.0 — restrict to localhost before deploying on any shared or networked machine.
- Ensure .env is in .gitignore and never committed to version control.
- Do not enable Streamlit debug mode or set STREAMLIT_LOGGER_LEVEL=debug in production as it may expose session state.
