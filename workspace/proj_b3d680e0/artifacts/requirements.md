# Requirements Document

## Problem Statement
Business analysts waste significant time manually creating charts and extracting insights from CSV sales reports; this app automates that process end-to-end.

## Users
- Business Analyst (non-technical, uploads sales CSVs, expects instant visual and textual insights)

## Functional Requirements
- User can upload a CSV file through a web interface
- App automatically parses the CSV and detects column types (numeric, categorical, date, etc.)
- App auto-selects the most meaningful columns and generates relevant charts (bar, line, pie, etc.) without user configuration
- App generates a plain-English summary of key insights derived from the data (trends, outliers, top/bottom performers)
- Charts and summary are rendered and viewable in-browser immediately after upload
- App sends CSV data to an external AI service to power insight generation

## Non-Functional Requirements
- Insight and chart generation should complete within a reasonable time (target: under 30 seconds for typical sales CSVs up to 10MB)
- App must be usable by non-technical business analysts with no training required
- UI must clearly communicate processing status while waiting for AI response
- App must handle malformed or empty CSVs gracefully with a user-friendly error message

## Acceptance Criteria
- Given a valid sales CSV is uploaded, when processing completes, then at least two relevant charts are displayed in-browser without any user configuration
- Given a valid sales CSV is uploaded, when processing completes, then a plain-English insight summary (minimum 3 key observations) is displayed alongside the charts
- Given a CSV with missing headers or corrupt data, when the user uploads it, then a clear error message is shown and no crash occurs
- Given a CSV up to 10MB, when uploaded, then charts and insights appear within 30 seconds

## Out of Scope
- Exporting charts or summaries to PDF, PowerPoint, or any file format
- Sharing reports via link or collaboration features
- Manual column selection or natural language querying by the analyst
- On-premise or air-gapped deployment; external AI service calls are permitted
- User authentication or multi-user access control
- Saving or persisting uploaded data or past reports
