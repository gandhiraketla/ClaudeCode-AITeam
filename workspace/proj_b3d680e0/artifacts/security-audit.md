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
CSV cell values inserted into Claude prompt without sanitization; attacker CSV can hijack instructions.
**Fix:** Strip role-delimiter strings and 'ignore previous instructions' patterns from all cell values before prompt insertion.

## [HIGH] src/insight_generator.py: Sensitive Data Exposure
API key passed as plain function parameter; exception with locals() logs full key to console.
**Fix:** Instantiate Anthropic client inside function reading os.environ directly; never pass api_key as parameter.

## [HIGH] src/app.py: Missing Rate Limiting
insight_generated flag resets on each upload; rapid re-uploads allow unlimited API calls and cost abuse.
**Fix:** Store last_api_call_time in session_state; enforce minimum 10s cooldown between uploads before invoking API.

## [MEDIUM] src/csv_parser.py: Input Validation
CSV MIME type not verified; executable or HTML file renamed .csv can trigger unexpected pandas behavior.
**Fix:** Read first 512 bytes and reject if non-text content detected; catch pandas.ParserError before processing.

## [MEDIUM] src/insight_generator.py: Sensitive Data Exposure to Third Party
Up to 20 raw CSV rows including potential PII (emails, names, salaries) sent to Anthropic API unmasked.
**Fix:** Apply regex pre-scan for email, phone, SSN patterns and replace matches with [REDACTED] before prompt assembly.

## [MEDIUM] src/app.py: Security Misconfiguration
Streamlit binds to 0.0.0.0:8501 by default; any host on local network can access and upload files.
**Fix:** Add server.address=localhost to .streamlit/config.toml to restrict to loopback for local deployment.

## [MEDIUM] src/insight_generator.py: Insecure Error Handling
Raw SDK exception message may include request headers containing API key fragments surfaced via st.error.
**Fix:** Catch anthropic.APIError specifically; log str(e) server-side only; display generic message to UI.

## [LOW] .env.example: Sensitive Data Exposure
If .env is accidentally committed alongside .env.example, ANTHROPIC_API_KEY is exposed in version control.
**Fix:** Confirm .env is in .gitignore; add pre-commit hook scanning for ANTHROPIC_API_KEY= pattern in staged files.

## Deployment Warnings
- THREE HIGH findings unresolved — do not deploy beyond localhost until prompt injection and API key exposure are fixed.
- CSV data including potential PII is sent to Anthropic API — confirm compliance with your data policy before use with real sales data.
- Streamlit binds to 0.0.0.0 by default — restrict to localhost via .streamlit/config.toml before any networked deployment.
- Ensure .env is in .gitignore and has never been staged or committed to version control.
- Do not enable STREAMLIT_LOGGER_LEVEL=debug in any shared environment as it may expose session state and key fragments.
