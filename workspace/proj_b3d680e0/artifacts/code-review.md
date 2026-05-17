# Code Review - APPROVED_WITH_CHANGES

## Summary
The resubmission resolves the structural issues from the first review cycle but leaves four security-critical blocking issues unaddressed: the API key is still passed as a plain parameter and risks leaking through exception context, CSV sample values are still inserted into the prompt without prompt-injection sanitization, there is still no upload cooldown to prevent API cost abuse across successive uploads, and broad exception handling still risks surfacing key fragments in the UI. These were all flagged as HIGH in the security audit and BLOCKING in the prior review, making them non-negotiable before testing. Non-blocking suggestions cover localhost binding, MIME validation, token estimation accuracy, the missing confabulated-column post-processor, the header-only CSV error message, and the correct Anthropic exception class name. The core pipeline (CSV parsing, chart generation, session state management, Streamlit rendering) is structurally sound and architecturally aligned. Fix the four blocking issues and this implementation is ready for testing.

## [BLOCKING] src/insight_generator.py around line 10-25
Anthropic client is instantiated with api_key passed as a plain function parameter. If an exception is thrown and locals() are logged, the key leaks. Security audit flagged this as HIGH and the prior review flagged it as BLOCKING, but the pattern persists in the resubmission.
**Fix:** Remove api_key parameter. Instantiate anthropic.Anthropic() inside the function reading os.environ directly. Never pass the key through the call stack.

## [BLOCKING] src/insight_generator.py around line 55-80
CSV cell values are inserted into the Claude prompt without any sanitization against prompt injection sequences. Security audit flagged this as HIGH and it remains unaddressed.
**Fix:** Before inserting sample row values into the prompt, strip or escape strings matching patterns like 'ignore previous instructions', role delimiters ('Human:', 'Assistant:'), and control characters.

## [BLOCKING] src/app.py around line 30-60
Session guard insight_generated prevents repeated calls within one upload event, but there is no cooldown timestamp between successive uploads. A user can rapidly re-upload files to trigger unlimited API calls. Security audit flagged this as HIGH and it is not addressed in the resubmission.
**Fix:** Add last_api_call_time to session_state and reject new uploads within a 10-second window, returning a user-friendly message.

## [BLOCKING] src/insight_generator.py around line 85-100
Exception handling catches broad Exception and surfaces str(e) to the UI via st.error. Some Anthropic SDK versions include request headers (containing the Authorization bearer token) in the exception message string, leaking key fragments to the browser.
**Fix:** Catch anthropic.APIError specifically. Log str(e) to server console only (print or logging). Display a static generic message to the UI with no exception detail.

## [SUGGESTION] src/app.py around line 1-10
No .streamlit/config.toml present to bind the server to localhost only. Default binding is 0.0.0.0:8501, exposing the upload endpoint to any host on the local network.
**Fix:** Create .streamlit/config.toml with [server] address = 'localhost' as documented in the security audit.

## [SUGGESTION] src/csv_parser.py around line 15-30
MIME type or magic-byte validation is absent. A file renamed to .csv but containing HTML or binary content will be passed directly to pandas, producing confusing parse errors rather than a clean user-facing rejection.
**Fix:** Read the first 512 bytes and confirm the content is plausible text (no null bytes, no HTML doctype). Reject with st.error before calling pd.read_csv.

## [SUGGESTION] src/insight_generator.py around line 40-55
Token estimation uses a rough character-count heuristic. For CSV rows with long string values the estimate can be significantly off, risking prompt exceeding Haiku context window.
**Fix:** Use tiktoken cl100k_base encoder for more accurate token counting, or apply a conservative safety multiplier (e.g. chars/3 instead of chars/4).

## [SUGGESTION] src/insight_generator.py around line 60-75
Confabulated column name post-processing was flagged as unimplemented in the prior review. The agent design explicitly requires checking that any quoted column name in the summary exists in column_profiles and appending a disclaimer if not.
**Fix:** After receiving the summary string, extract quoted tokens, check each against column_profiles names, and append the disclaimer if any are missing.

## [SUGGESTION] src/csv_parser.py around line 45-55
Header-only CSV (row_count == 0 after parse) is handled with a generic error path rather than the specific message mandated by the agent design: 'The uploaded file appears to be empty — please upload a CSV with at least one data row.'
**Fix:** Add an explicit row_count == 0 branch that sets error to the exact message from the agent design before returning.

## [SUGGESTION] requirements.txt full file
All dependency versions are pinned, which is correct, but anthropic 0.28.0 has known breaking changes in error handling between minor versions. The exception type anthropic.APIError may not exist in 0.28.0 under that exact name.
**Fix:** Verify the correct exception class name in anthropic 0.28.0 (may be anthropic.APIStatusError or anthropic.AuthenticationError) and use the correct type in except clauses.
