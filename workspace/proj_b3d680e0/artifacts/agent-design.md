# Agent Design Document

## Reasoning Strategy
Plan-then-execute: The agent receives a complete CSV schema and sample at invocation time and has all the information it needs to form a full plan before acting. There is no iterative discovery — the column types are known, the data is in memory, and the AI call is a single structured request. ReAct would add unnecessary looping overhead for what is essentially a one-shot analysis task. The agent plans its output structure (which charts to recommend, which insights to surface) from the schema, then executes the Claude API call once with a well-formed prompt. This produces deterministic, auditable behavior and avoids the hallucination risk of iterative self-directed tool calls.

## Tools

### parse_csv
- Purpose: Read and validate the uploaded CSV file. Infer column types (numeric, categorical, date) and compute per-column statistics. Agent calls this first, before any AI interaction. If this fails, the pipeline stops and an error is surfaced to the user.
- Input: csv_bytes: raw bytes of the uploaded file; max_size_bytes: integer (10485760)
- Output: column_profiles: list of objects each with {name: string, inferred_type: 'numeric'|'categorical'|'date', nunique: int, null_count: int, min: any, max: any, top_values: list}; row_count: int; error: string or null

### select_chart_specs
- Purpose: Apply deterministic heuristics to column profiles to produce a list of chart specifications. Called after parse_csv succeeds. No AI involved — pure rule-based selection. Rules: date+numeric->line, categorical+numeric->bar, categorical with nunique<=6->pie. Returns at least 2 specs or raises a fallback.
- Input: column_profiles: output from parse_csv
- Output: chart_specs: list of objects each with {chart_type: 'bar'|'line'|'pie', x_column: string, y_column: string or null, title: string}; count: int

### build_insight_prompt
- Purpose: Construct the structured prompt payload for the Claude API call. Truncates sample rows to stay within token budget. Agent calls this to assemble the prompt before calling generate_insights. Centralizes all token-limit logic.
- Input: column_profiles: list from parse_csv; raw_dataframe_sample: first N rows as list of dicts; max_tokens_budget: int (default 3000 for prompt body)
- Output: prompt_payload: {system_prompt_sections: list of strings, user_prompt_body: string, estimated_token_count: int, rows_included: int}

### generate_insights
- Purpose: Send the structured prompt to Claude claude-3-haiku-20240307 via Anthropic SDK and return the plain-English insight summary. Agent calls this exactly once per CSV upload. Must not be called if parse_csv returned an error.
- Input: prompt_payload: output from build_insight_prompt; api_key: string from environment; max_response_tokens: int (default 1024)
- Output: summary: string containing plain-English insights (minimum 3 observations); raw_response: full API response object; error: string or null

### render_charts
- Purpose: Build Plotly figure objects from chart_specs and column data. Agent calls this in parallel with generate_insights (both depend only on parse_csv output). Returns renderable figures, not HTML.
- Input: chart_specs: list from select_chart_specs; dataframe: parsed pandas DataFrame
- Output: figures: list of Plotly Figure objects each tagged with {title: string, chart_type: string}; errors: list of {spec: object, reason: string} for any spec that failed to render

## Memory Strategy
No persistent memory. This is a single-session, single-upload workflow. All state (parsed DataFrame, column profiles, chart specs, insight summary) is held in Streamlit session_state for the duration of one browser session. State is reset on each new CSV upload. No database, no file writes, no cross-session memory. session_state keys: last_filename, column_profiles, chart_specs, figures, insight_summary, error_message. Memory scope: one Streamlit session, cleared on page refresh or new upload.

## Prompt Architecture
System prompt sections in order: (1) Role definition — one sentence establishing the agent as a data analyst producing insights for non-technical business analysts. (2) Output format contract — explicitly specifies that the response must contain exactly N labeled observations, each a single plain-English sentence, no bullet markdown, no technical jargon. (3) Constraints — do not invent data not present in the sample; do not reference column names the user would not understand; flag if sample is too small to draw conclusions. User prompt sections in order: (1) Dataset metadata block — column names, inferred types, row count, null counts. (2) Statistical summary block — min, max, nunique per numeric column. (3) Sample rows block — up to 20 rows in CSV-like format, prefixed with row count included vs total. (4) Task instruction — ask for 3-5 key insights covering trends, outliers, and top/bottom performers. Ordering rationale: system prompt sets immutable rules; user prompt leads with structure before asking for output, which reduces hallucination of non-existent columns.

## Failure Modes
- CSV with no detectable numeric columns: select_chart_specs returns zero specs. Handler: surface st.warning 'No numeric columns found — charts cannot be generated' and still proceed with insight generation if column profiles exist.
- Claude API returns insight summary mentioning column names not present in the CSV: occurs when model confabulates. Handler: post-process the summary string to check that any quoted column name exists in column_profiles; if mismatch found, append a disclaimer 'Some references may not match your data exactly.'
- CSV sample rows push prompt over token budget: build_insight_prompt reduces rows_included until estimated_token_count is under max_tokens_budget. If even 0 sample rows exceeds budget (schema alone too large), return error 'CSV has too many columns to analyze — reduce to under 50 columns.'
- Claude API call times out or returns 5xx: generate_insights catches the exception and sets error field. Handler: display st.error 'Insight generation failed — please retry. Charts are still available.' Charts render independently.
- Uploaded file is valid UTF-8 CSV but contains only one row (header only): parse_csv detects row_count==0. Handler: st.error 'The uploaded file appears to be empty — please upload a CSV with at least one data row.'
- Plotly render fails for a specific chart spec (e.g. y_column contains all nulls): render_charts adds the spec to its errors list. Handler: skip that chart silently and log to console; remaining charts still render.

## Guardrails
- Token budget enforcement: build_insight_prompt must hard-cap the prompt body at 3000 tokens estimated. If truncation reduces sample to 0 rows and schema still exceeds budget, the tool returns an error and generate_insights is not called. Enforced inside build_insight_prompt before any API call.
- No file writes outside session: agent and all tools operate only on in-memory objects and Streamlit session_state. No tool may write to disk. Enforced by not providing any file-write tool and by code review gate in the implementer stage.
- Single API call per upload: generate_insights may be invoked at most once per CSV upload event. Enforced via session_state flag insight_generated: bool, checked before calling the tool. Prevents runaway API spend on Streamlit re-renders.
- CSV size limit enforced before parsing: parse_csv rejects input where len(csv_bytes) > max_size_bytes and returns an error immediately. Streamlit file_uploader also sets its own size limit as a secondary defense.
- Insight summary is read-only to the user: the summary string returned by generate_insights is rendered as st.markdown with no editable widget. No user input is fed back into any subsequent AI call in v1.
- API key never logged or displayed: ANTHROPIC_API_KEY is read once from environment via python-dotenv and passed to generate_insights as a parameter. It must not appear in any st.write, st.code, log output, or error message. Enforced by ensuring error handlers only surface the exception message, not the request headers.
