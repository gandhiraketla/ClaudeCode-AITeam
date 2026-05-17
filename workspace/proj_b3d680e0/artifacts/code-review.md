# Code Review - APPROVED_WITH_CHANGES

## Summary
The implementation covers the core pipeline (CSV parsing, chart generation, AI insight generation, Streamlit rendering) and is structurally aligned with the architecture. Four blocking issues must be resolved before testing: the insight_generated session guard is missing causing repeated API calls on every Streamlit re-render, the confabulated column name post-processor is unimplemented, the API key validation before client instantiation is absent, and Streamlit's secondary file size enforcement is not configured. Non-blocking suggestions address the header-only CSV error path, token estimation precision, and API key redaction in error output. Once the four blocking issues are addressed the implementation should be functionally correct and safe to test.

## [BLOCKING] src/insight_generator.py around line 55-70
The generate_insights function constructs the Anthropic client using the api_key parameter but there is no validation that the key is non-empty before the API call. If ANTHROPIC_API_KEY is missing from .env, the client is instantiated with an empty string and the SDK will throw an AuthenticationError that is not caught by the existing except block, which only catches anthropic.APIError and generic Exception but may not surface a clear user-facing message for auth failures.
**Fix:** At the start of generate_insights, check if api_key is falsy and immediately return {error: 'ANTHROPIC_API_KEY is not set. Add it to your .env file.', summary: None} before instantiating the client.

## [BLOCKING] src/insight_generator.py around line 90-105
The session_state guard (insight_generated flag) described in the agent design as a guardrail against runaway API calls on Streamlit re-renders is not implemented inside insight_generator.py or enforced in app.py before calling generate_insights. Every Streamlit re-render triggered by any widget interaction will re-invoke the full pipeline including the Claude API call.
**Fix:** In app.py, before calling generate_insights, check st.session_state.get('insight_generated', False) and skip the call if True. Set st.session_state['insight_generated'] = True immediately after a successful call. Reset it to False only when a new file is uploaded.

## [BLOCKING] src/csv_parser.py around line 20-35
The CSV size check compares len(csv_bytes) against max_size_bytes, but the Streamlit file_uploader widget does not have its own size cap configured in app.py. The architecture specifies Streamlit's uploader should also enforce the 10MB limit as a secondary defense. Without the max_upload_size parameter set, users can upload files larger than 10MB that only get rejected after reading all bytes into memory.
**Fix:** In app.py, set st.file_uploader(..., type=['csv'], accept_multiple_files=False) and add Streamlit's config or use st.set_page_config with a note, or enforce via [server] maxUploadSize in .streamlit/config.toml. Also confirm parse_csv rejects before pandas reads the file.

## [BLOCKING] src/insight_generator.py around line 115-130
The post-processing guardrail for confabulated column names (checking that any quoted column name in the summary exists in column_profiles) specified in the agent design failure modes section is entirely absent. The raw Claude response is returned and rendered without any validation.
**Fix:** After receiving the summary string, extract any tokens that appear in backticks or quotes, check each against the set of column names in column_profiles, and if any mismatch is found append the disclaimer defined in the agent design: 'Some references may not match your data exactly.'

## [SUGGESTION] src/chart_engine.py around line 60-80
The render_charts fallback when zero chart specs are returned logs to console but app.py does not surface the st.warning 'No numeric columns found — charts cannot be generated' as specified in the agent design failure modes. The warning is silently swallowed.
**Fix:** In app.py, after calling select_chart_specs, check if chart_specs count is 0 and call st.warning with the exact message from the agent design before proceeding to insight generation.

## [SUGGESTION] src/csv_parser.py around line 45-55
parse_csv does not explicitly check for row_count == 0 (header-only CSV) as a distinct error case. It may silently return an empty DataFrame which causes downstream failures in chart_engine with an unhelpful error rather than the user-friendly message specified: 'The uploaded file appears to be empty — please upload a CSV with at least one data row.'
**Fix:** After reading the DataFrame, explicitly check if len(df) == 0 and return error='The uploaded file appears to be empty — please upload a CSV with at least one data row.' before proceeding with column profiling.

## [SUGGESTION] src/insight_generator.py around line 30-45
build_insight_prompt estimates token count using a rough character-division heuristic (chars / 4). For prompts near the 3000-token budget this approximation can be off by 20-30%, potentially allowing prompts that exceed the actual context limit to be sent to the API.
**Fix:** Consider using a tighter estimate (chars / 3) for safety margin, or add a hard cap on rows_included (e.g. max 20 rows) in addition to the token estimate, as the architecture specifies 20-row sample.

## [SUGGESTION] requirements.txt all lines
All five dependencies are pinned to exact versions (streamlit==1.35.0, pandas==2.2.2, plotly==5.22.0, anthropic==0.28.0, python-dotenv==1.0.1) which matches the architecture spec. No unused dependencies observed. This is correct.
**Fix:** No action needed — this is a positive finding noted for completeness.

## [SUGGESTION] src/app.py around line 25-40
The ANTHROPIC_API_KEY is loaded via python-dotenv and passed to generate_insights as a parameter, which matches the guardrail spec. However, there is no check that ensures the key does not appear in any st.error or st.write output when exception messages are surfaced. If the SDK embeds the key in an exception message (some SDKs do in auth errors), it would be displayed to the user.
**Fix:** Wrap all st.error calls that display exception messages with a sanitizer that checks if the api_key string appears in the message and replaces it with '[REDACTED]'.

## [SUGGESTION] src/insight_generator.py around line 70-85
The generate_insights function passes max_response_tokens defaulting to 1024 but the system prompt instructs the model to return 3-5 observations. At 1024 tokens this is adequate, but the max_tokens argument passed to the Anthropic SDK messages.create call should be verified to actually use this parameter rather than the SDK default.
**Fix:** Confirm that messages.create(..., max_tokens=max_response_tokens) uses the passed value. If the SDK default (4096) is used instead, costs will be higher than expected.
