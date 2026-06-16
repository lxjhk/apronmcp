# Reservation Write Capabilities — Design

**Date:** 2026-06-16
**Status:** Approved (design phase)
**Builds on:** the read-only paperless141-mcp server
(`docs/superpowers/specs/2026-06-15-paperless141-mcp-design.md`).

## Goal

Add the ability to **create**, **modify**, and **cancel** reservations in Paperless141,
exposed as MCP tools. The user typically gives a vague request ("a 172 next Tuesday
afternoon"); the agent finds concrete options, the user picks one, and the agent books it.

This moves the server from read-only to **read-write against a live, shared scheduling
system** — the highest-risk part of the project. Safety is a first-class design concern.

## Key constraint & risk

Booking is a **stateful, ViewState-heavy flow**, not a simple form POST. The user clicks
**"Make/Modify Schedules"** (`#ctl00_ContentPlaceHolder1_ButtMMS`) which flips the scheduler
board (`mstr7p.aspx`) into an editing mode; slot interaction then drives the booking.
Existing reservations open at `mstr7a.aspx?schednum=N`.

Static recon did **not** fully reveal the create/modify/cancel click-paths (slot postbacks
on a throwaway far-future date were benign and opened no visible form). Therefore the exact
flow must be pinned down by **guided discovery** on a throwaway slot before implementation —
analogous to the recon checkpoint used successfully in Phase A. There is genuine risk that
parts of the flow are fiddly to automate reliably; this is surfaced as work proceeds rather
than assumed away.

## Approach

**Playwright UI automation** — drive the real Make/Modify mode as a human does. This is the
only robust option: the browser handles ViewState/event-validation for free, whereas
replaying raw HTTP POSTs would be brittle and more dangerous (a malformed write to a live
system). Consistent with the existing navigation architecture (`browser.py`).

Rejected alternative: raw postback replay via httpx + manual ViewState — too brittle and
unsafe for writes.

## Tools

| Tool | Behaviour |
|------|-----------|
| `find_open_slots(date, type_or_tail=None, time_range=None)` | Turn a vague ask into concrete bookable options. Built on the existing availability reader; returns candidate (aircraft, date, start–end) options. Read-only. |
| `create_reservation(date, start, end, tail, cfi=None, category=None, note=None, confirm=False)` | `confirm=False` (default): **preview** — report exactly what would be booked, write nothing. `confirm=True`: perform the booking and return the new `schedule_number`. |
| `modify_reservation(schedule_number, date=None, start=None, end=None, tail=None, cfi=None, category=None, note=None, confirm=False)` | Change one or more fields of a single reservation. Preview-then-confirm. |
| `cancel_reservation(schedule_number, confirm=False)` | Cancel one reservation. Preview-then-confirm (preview echoes the reservation that would be cancelled). |

All write tools default to `confirm=False`. Times are explicit (e.g. `start`/`end` as
`YYYY-MM-DD HH:MM` or the app's accepted format, finalized during discovery).

## Safety model (core requirements)

1. **Preview-then-confirm** on every write tool — nothing is submitted unless `confirm=True`.
   The preview describes the intended change in concrete terms.
2. **Single-target only** — `modify`/`cancel` require an explicit `schedule_number`; tools
   never operate on lists, ranges, or "all".
3. **No collateral** — a write only ever touches the one slot/reservation named in the call.
4. **Audit log** — every write action (and its parameters, minus secrets) is logged.
5. **Test protocol** — all live testing uses a **far-future throwaway slot**, never the
   user's real bookings: `create` → verify via `get_my_schedule` → `modify` → verify →
   `cancel` → verify gone. Leaves zero trace.
6. **Confirmation in the loop** — the agent confirms concrete details with the user before
   calling any tool with `confirm=True`.

## Components

- **`browser.py`** — extend `BrowserSession` with a write-flow driver:
  - `enter_make_modify()` — click `ButtMMS`, confirm the board is in editing mode.
  - `open_slot(date, tail, start)` — navigate to date, select the target aircraft/time cell.
  - `submit_booking(fields)` / `submit_modify(...)` / `submit_cancel(...)` — fill and submit.
  - Exact selectors/click-path filled in during discovery. All serialized under the existing lock.
- **`writes.py`** (new) — orchestration for the three operations + `find_open_slots`,
  keeping `tools.py` thin. Pure-logic parts (parameter validation, preview formatting,
  option ranking) separated from the browser I/O so they are unit-testable.
- **`tools.py` / `server.py`** — register the four new tools.
- **`parsers/`** — add a parser for the booking confirmation / reservation-detail page
  (`mstr7a.aspx`) to extract the new `schedule_number` and confirm success.

## Phasing (decomposed — large + risky)

- **Phase W1 — Discovery + Create + Cancel.** Guided discovery of the exact booking
  click-path on a throwaway slot; implement `find_open_slots`, `create_reservation`,
  `cancel_reservation`; validate with a real create → verify → cancel round-trip. Cancel is
  built first alongside create so every test cleans up after itself.
- **Phase W2 — Modify.** Implement `modify_reservation` (time / aircraft / CFI / note) on the
  now-understood flow; validate create → modify → verify → cancel on a throwaway slot.

Each phase gets its own implementation plan.

## Error handling

- **Login/session expiry** — reuse the existing re-login-on-expiry path in `BrowserSession`.
- **Slot no longer free** (race) — detect that the booking did not succeed (confirmation page
  absent / slot still free) and return a clear error rather than a false success.
- **Validation errors** (bad date/time, unknown tail, end before start) — caught in the
  pure-logic layer with actionable messages before any browser interaction.
- **Partial/unknown state** — if a write's outcome is ambiguous, the tool reports uncertainty
  and suggests verifying via `get_my_schedule`, never claims success it didn't confirm.

## Testing

- **Offline unit tests** — parameter validation, preview formatting, option ranking, and the
  `mstr7a.aspx` confirmation parser (against committed synthetic fixtures).
- **Live validation** — the create→modify→cancel round-trip on a throwaway far-future slot,
  run deliberately (not in CI). The stateful browser flow cannot be unit-tested.

## Out of scope (YAGNI)

- Recurring/bulk booking, waitlists, check-in/check-out, squawks, payments.
- Modifying anyone else's reservations (only the user's own, by `schedule_number`).
- Any automatic booking without explicit `confirm=True` and user confirmation.
