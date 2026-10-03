---
name: trip-planner-routing
description: Explains when and how to delegate to the trip_planner subagent tool instead of handling a request directly. Use this whenever the person's message touches trip planning, travel dates, itineraries, things to do or eat at/near a destination, travel budgets, or booking sequencing for a trip - even if they only mention one piece of it (e.g. just "when should I visit Kyoto" or "restaurants near my hotel in Shibuya"). Also covers follow-ups that refine a trip already being planned in this conversation. Consult this before answering any destination- or trip-specific question yourself.
---

# Routing to trip_planner

You have a `trip_planner` subagent available as a tool. It handles trip
planning end-to-end: picking travel dates, weather checks, day-by-day
itineraries, bookings checklists, budget estimates, and finding places to eat
or visit at a destination. It has its own web search access and does this
research itself — you don't need to research the destination before calling
it, and you shouldn't try to answer these questions yourself from memory.

## When to call it

Call `trip_planner` whenever the person's request is about planning, timing, or
exploring a specific trip or destination — even if they only mention one piece
of it. That includes:

- Planning a trip or vacation, in whole or in part ("plan me a week in Lisbon",
  "help me put together an itinerary for Japan")
- Asking when to go somewhere ("what's the best time to visit Kyoto", "should I
  go in spring or fall")
- Deciding between candidate destinations for a trip
- Asking what to do, see, or eat at or near a specific place ("things to do near
  my hotel in Shibuya", "good restaurants in Alfama")
- Wanting a budget estimate for a trip
- Wanting help sequencing bookings (flights, hotels, activities) for a trip
- Any follow-up that refines or continues a trip already being planned in this
  conversation

Don't call it for things that only sound travel-adjacent but aren't about a
specific trip: general geography or culture questions ("what language do they
speak in Portugal"), visa/entry-requirement lookups with no trip context,
translating a phrase, or booking/purchasing actions once the plan is already
decided (`trip_planner` plans trips, it doesn't execute bookings).

## How to call it

`trip_planner` is single-shot — it does its own research and returns a
complete answer, but it can't ask you clarifying questions back and forth. So
before calling it:

1. **Gather what's already in the conversation.** Destination, origin,
   dates/timeframe, number of travelers, budget level, interests — anything the
   person has already told you, pass it along. Don't make `trip_planner`
   re-derive context you already have.
2. **If a genuinely blocking piece is missing** (e.g. the person said "plan me
   a trip" with no destination at all), ask the person directly yourself first
   rather than sending an underspecified task to `trip_planner` — it will just
   have to guess or ask a clarifying question in its response, which is a
   wasted round trip.
3. **If it's just missing nice-to-haves** (budget level, exact interests,
   pace), don't block on it — pass the task along as-is. `trip_planner` is
   built to make sensible assumptions and state them, same as you would.

Pass the task as a clear, self-contained natural-language instruction, not a
terse keyword string. Include every relevant detail you have. For example:

> Plan a 5-day trip to Lisbon, Portugal from London for early October.
> Mid-range budget, traveling as a couple, interested in food and history.

or for a narrow request:

> What's the best time of year to visit Kyoto, Japan, balancing weather and
> crowds?

## Handling the result

`trip_planner` returns a complete markdown response (tables, day-by-day
sections, checklists as applicable). Relay it to the person largely as-is —
it's meant to be read directly, not summarized or paraphrased down. You can add
a short framing sentence before or after if it helps the conversation flow, but
don't rewrite its itinerary, budget table, or recommendations. If the person
asks a follow-up that changes the trip (new dates, added city, different
budget), call `trip_planner` again with the updated context rather than trying
to patch its previous answer yourself.