# Agent Design Document

## Reasoning Strategy
ReAct (Reasoning + Acting) — because this agent must interleave natural language reasoning with dynamic tool calls whose results determine the next reasoning step. The agent cannot form a complete plan upfront: it does not know whether clarification is needed, which tools to invoke, or how many legs the trip has until it parses the user message. Plan-then-execute fails here because slot completeness is unknown at plan time. Chain-of-thought alone fails because real-time data is required. Reflection would add latency without meaningful quality gain for structured data retrieval. ReAct lets the agent reason about what it knows, decide whether to clarify or search, observe tool results, and reason again before composing — matching the actual conditional flow described in the architecture.

## Tools

### extract_intent_and_slots
- Purpose: Parse the user message plus conversation history to identify travel intent (full_itinerary, flights_only, hotels_only) and extract slots: origin, destination, check_in_date, check_out_date, departure_date, return_date, num_travelers, budget_usd, interests. Call this first on every new user message.
- Input: { messages: array of {role, content} representing full conversation, current_user_message: string }
- Output: { intent: enum(full_itinerary|flights_only|hotels_only|unclear), slots: { origin?: string, destination?: string, check_in_date?: ISO8601, check_out_date?: ISO8601, departure_date?: ISO8601, return_date?: ISO8601, num_travelers?: integer, budget_usd?: number, interests?: string[] }, missing_required: string[] }

### generate_clarification_question
- Purpose: Produce a single focused clarifying question for the first missing required slot. Call this when extract_intent_and_slots returns a non-empty missing_required list. Ask for only one missing slot per turn to avoid overwhelming the user.
- Input: { intent: string, confirmed_slots: object, missing_required: string[] }
- Output: { question: string, slot_being_asked: string }

### search_flights
- Purpose: Query SerpApi google_flights engine for real-time flight options. Call when intent is full_itinerary or flights_only and departure_date plus origin and destination are all present.
- Input: { origin_iata: string, destination_iata: string, departure_date: ISO8601, return_date?: ISO8601, num_travelers: integer, currency: string default USD }
- Output: { flights: array of { airline: string, flight_number: string, departure_time: string, arrival_time: string, duration_minutes: integer, price_usd: number, stops: integer, booking_url?: string }, search_timestamp: ISO8601, error?: string }

### search_hotels
- Purpose: Query SerpApi google_hotels engine for real-time hotel options. Call when intent is full_itinerary or hotels_only and destination, check_in_date, check_out_date are all present.
- Input: { destination: string, check_in_date: ISO8601, check_out_date: ISO8601, num_guests: integer, budget_usd_per_night?: number }
- Output: { hotels: array of { name: string, star_rating: number, price_per_night_usd: number, total_price_usd: number, address: string, amenities: string[], booking_url?: string }, search_timestamp: ISO8601, error?: string }

### compose_itinerary
- Purpose: Send confirmed slots, flight results, and hotel results to Claude to produce a structured day-by-day markdown itinerary. Call only after all required tool results are available. This is the final synthesis step.
- Input: { slots: object, flights: array or null, hotels: array or null, intent: string }
- Output: { itinerary_markdown: string, days: integer, warnings: string[] }

## Memory Strategy
All state lives in Streamlit st.session_state for the duration of the browser session — no persistence across sessions. Three objects are maintained: (1) messages: full conversation history as role/content pairs, appended on every turn, used as context for all Claude calls; (2) slots: the accumulated extracted slot values, updated incrementally as the user provides missing information across clarification turns, never reset mid-session; (3) last_search_results: the raw flight and hotel JSON from the most recent tool calls, retained so the itinerary composer can reference them without re-querying. On browser refresh all state is lost — this is acceptable per V1 scope which explicitly excludes saved itinerary history.

## Prompt Architecture
System prompt sections in order: (1) Role definition — the agent is a travel planning assistant that produces structured itineraries, not a booking engine; (2) Behavioral rules — ask one clarifying question at a time, never fabricate flight or hotel data, always use tool results verbatim for prices and times; (3) Output format contract — when composing an itinerary use day headers (Day 1: [date]), sub-sections for Flights / Accommodation / Activities, include price and time for every flight and hotel entry; (4) Scope guardrails — do not offer to book, do not invent prices, if data is unavailable say so explicitly. User prompt structure: the full messages array is passed as the conversation context; the current reasoning step appends a structured observation block containing the latest tool call name and its output JSON so the model can reason over real data rather than recalling it from training.

## Failure Modes
- SerpApi returns zero flight results for a valid route and date — agent must invoke compose_itinerary with flights=null and include a warning to the user that no live flight data was found for that segment rather than omitting the section silently.
- SerpApi returns an HTTP error or timeout on hotel search — agent must set hotels=null, surface the error string from the tool output in the warning field, and still compose the partial itinerary with whatever data is available.
- extract_intent_and_slots misclassifies a specific flight query as full_itinerary and searches hotels unnecessarily — agent should recheck intent against whether a destination + date-range pair implies a stay; if round-trip dates are identical, skip hotel search.
- The agent enters a clarification loop asking for the same missing slot repeatedly because the user's answer is not being merged into the slots object — slots must be merged from every assistant turn's extract_intent_and_slots output, not re-extracted from scratch each turn.
- Claude fabricates hotel names or prices in compose_itinerary when the hotels array is sparse — system prompt must instruct the model to use only entries present in the provided hotels array; if fewer than two options exist, say so rather than padding with invented options.
- User provides a city name that maps to multiple airports (e.g. London has LHR, LGW, STN) — search_flights must receive an IATA code; agent must resolve ambiguous city names to a primary IATA code before calling the tool, or ask the user to confirm.
- Conversation history grows very long (multi-leg trip with many clarification turns) causing Claude context window pressure — truncate messages sent to extract_intent_and_slots to the last 10 turns; always send full history to compose_itinerary to preserve travel context.

## Guardrails
- Never call compose_itinerary with fabricated data: the itinerary composer tool must receive the actual JSON output from search_flights and search_hotels; if both return errors, the agent must inform the user rather than generating a placeholder itinerary.
- Reject any tool call to search_flights or search_hotels that is missing a required input field — validate inputs before calling the SerpApi wrapper; if origin_iata or departure_date is absent, route back to generate_clarification_question instead.
- Cap the number of clarification turns at 4 per session: if after 4 turns the required slots are still not filled, the agent must state what is still missing and ask the user to provide all remaining fields in one message to prevent infinite loops.
- Do not expose raw API error messages from SerpApi to the user: catch exception strings in the tool wrapper and return a normalized error field; surface only a user-friendly message in the chat.
- Scope enforcement: if the user asks to book, pay, or confirm a reservation, the agent must respond that booking is out of scope for V1 and offer to refine the itinerary instead — this check runs before any tool call.
- All file or disk operations are prohibited: the agent has no write_file or export tool; any attempt to add such a tool call must be rejected at the orchestrator level since artifacts_path writes are reserved for the ClaudeForge pipeline, not the travel agent.
- API key access is restricted to environment variables loaded at startup via python-dotenv; the agent must never log, display, or include SERPAPI_API_KEY or ANTHROPIC_API_KEY in any tool input, output, or chat message.
