---
name: calendar_manager
description: >-
  Use this skill for all calendar management tasks. Trigger it with phrases like: "Schedule a meeting...",
  "Move my event...", or "Show my schedule for [timeframe]". This skill utilizes
  `agentic_mcp_create_calendar_event`, `agentic_mcp_update_calendar_event`, and
  `agentic_mcp_list_calendar_events`.
license: MIT
metadata:
  author: Skill Creator
  version: 1.0.0
compatibility:
  - Requires tools: agentic_mcp_create_calendar_event, agentic_mcp_update_calendar_event, agentic_mcp_list_calendar_events.
  - Assumes: Access to a calendar API service for execution.
---

# Calendar Management Skill

This skill provides a structured workflow for handling all calendar-related requests by routing the user's intent to the appropriate underlying tool.

## Workflow

The skill processes user requests by first identifying the intent (Schedule, Update, or List) and then constructing the appropriate tool call with the necessary parameters.

### 1. Schedule a New Event
**Trigger:** Phrases like "Schedule a meeting with [Person] at [Time/Date]." or "Schedule a focus block from [Time] to [Time]."
**Tool Used:** `agentic_mcp_create_calendar_event`
**Input Parameters:**
*   `event_title` (string): The subject or title of the event.
*   `start_time` (datetime): The precise start time of the event.
*   `end_time` (datetime): The precise end time of the event.
*   `attendees` (list[string]): A list of participants (optional).

**Day Plan / Focus Block Handling:**
For requests like "Plan my typical workday schedule for Monday," the skill will interpret the request as a series of required blocks. It will use `agentic_mcp_create_calendar_event` sequentially for each block, determining appropriate times based on the requested day (e.g., Monday) and the specified duration. This allows for generating entire schedules.

**Example Input 1 (Meeting):** "Schedule a meeting with John tomorrow at 10 AM."
**Agent Action 1:** The skill will parse "tomorrow at 10 AM" into specific `start_time` and `end_time` objects and call `agentic_mcp_create_calendar_event(event_title="Meeting with John", start_time=<calculated_time>, end_time=<calculated_time>, attendees=["John"])`.

**Example Input 2 (Focus Block):** "Schedule a focus block from 10 AM to 12 PM."
**Agent Action 2:** The skill will parse the time range and call `agentic_mcp_create_calendar_event(event_title="Focus Block", start_time=<10:00 AM datetime>, end_time=<12:00 PM datetime>, attendees=[])`.


### 2. Modify an Existing Event
**Trigger:** Phrases like "Move my [Time] event to [New Time]," or "Change the time for [Event Name]."
**Tool Used:** `agentic_mcp_update_calendar_event`
**Input Parameters:**
*   `event_id` (string): The unique identifier of the event to modify.
*   `new_start_time` (datetime, optional): The new start time.
*   `new_end_time` (datetime, optional): The new end time.
*   `event_title` (string, optional): The updated title.

**Example Input:** "Move my 3 PM event to 4 PM."
**Agent Action:** The skill will attempt to resolve the "3 PM event" (requiring a lookup or context from previous calls) to an `event_id`, and then call `agentic_mcp_update_calendar_event(event_id=<found_id>, new_start_time=<4:00 PM datetime>)`.


### 3. Retrieve Calendar Information
**Trigger:** Phrases like "Show me my schedule for [Timeframe]," or "What events do I have today?"
**Tool Used:** `agentic_mcp_list_calendar_events`
**Input Parameters:**
*   `timeframe` (string, optional): A specification for the desired range (e.g., "next week", "today", "next month").
*   `details` (boolean, optional): If True, return detailed information (e.g., location, description).

**Example Input:** "Show me my schedule for next week."
**Agent Action:** The skill will parse "next week" as the `timeframe` and call `agentic_mcp_list_calendar_events(timeframe="next week", details=False)`.


## Edge Cases and Failure Handling

1.  **Ambiguous Times:** If the user provides an ambiguous time (e.g., "sometime next Tuesday"), the skill must prompt the user for clarification before calling any tool. Do not guess.
2.  **Event ID Not Found:** If the user asks to move or delete an event, and the system cannot resolve the `event_id`, return a clear message to the user stating the ID is missing and ask them to provide it.
3.  **API Failure:** If any of the underlying tools return a service error (e.g., calendar API is down), the skill must inform the user clearly about the failure and suggest retrying later.

## Supporting Resources

No supporting files (`scripts/`, `references/`, `assets/`) are required for this skill as the functionality is entirely handled by calling pre-defined external tools.