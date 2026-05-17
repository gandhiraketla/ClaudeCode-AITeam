# Test Plan & Evals - PASS_WITH_WARNINGS

## Eval Cases

- **happy_path: parse valid sales CSV**: valid 20-row sales CSV with date, product, region, sales, un -> parse_csv returns column_profiles list with >0 entries, row_

- **happy_path: at least 2 charts from valid CSV**: valid sales CSV with numeric and categorical columns -> select_chart_specs returns count>=2 chart specs without user

- **happy_path: insight prompt builds without error**: valid sales CSV column profiles and 20 sample rows -> build_insight_prompt returns payload with prompt body and es

- **failure_case: corrupt CSV returns error no crash**: binary garbage bytes uploaded as .csv -> parse_csv returns error string and does not raise an excepti

- **failure_case: header-only CSV detected**: CSV with only header row, no data rows -> parse_csv returns row_count=0 or non-null error string

- **edge_case: oversized CSV >10MB rejected**: CSV file of 11MB -> parse_csv returns non-null error before processing, does not

- **edge_case: no numeric columns handled gracefully**: CSV with only categorical text columns -> select_chart_specs returns zero specs or raises handled erro

- **adversarial: prompt injection CSV does not crash**: CSV with cell value containing 'Ignore previous instructions -> parse_csv completes without exception; pipeline does not cra

- **edge_case: token budget enforced <=3000**: valid sales CSV with 20 sample rows, budget=3000 -> build_insight_prompt returns estimated_token_count <= 3000

- **failure_case: empty bytes CSV returns error**: empty byte string as CSV upload -> parse_csv returns non-null error, no crash

## Gap Analysis
- Reviewer flagged missing insight_generated session guard — repeated API calls on re-render possible; eval cannot test Streamlit session_state directly but token budget test partially covers this
- Reviewer flagged confabulated column name post-processor unimplemented — no eval can fully validate this without a live Claude API call returning hallucinated column names
- Security audit flagged prompt injection sanitization absent in insight_generator.py — adversarial test only checks for no-crash, not sanitization effectiveness without live API key
- API key validation before client instantiation not tested in eval because it requires environment manipulation; noted as known gap from reviewer
- Rate limiting cooldown (security HIGH finding) cannot be tested in unit-style eval without mocking time; flagged as advisory gap
