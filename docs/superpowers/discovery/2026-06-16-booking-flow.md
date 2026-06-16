# Booking Flow Discovery (Paperless141)

**Date:** 2026-06-16
**Validated live** with a throwaway booking: created #688530 (15MJ, 2026-07-13 14:00–14:30)
and then deleted it; the user's real reservations were untouched throughout.

## Create a reservation

The booking form is an **iframe modal** (`mstr7apop.aspx`, titled "Make or Change Schedule")
shown over the scheduler board via the AjaxControlToolkit `ModalPopupBehavior`.

Steps:
1. Open the scheduler board on the target date (`open_scheduler("#ctl00_BtnSched", "YYYY-MM-DD")`).
   The board date is an ASP.NET `type=date` input `#ctl00_ContentPlaceHolder1_DropDate1` (autopostback).
2. Open the modal by firing **any** free-slot postback:
   `__doPostBack('ctl00$ContentPlaceHolder1$GridView2','<row>$<col>')`. Any rendered free anchor
   works — we then set the real aircraft/time in the modal, so the specific cell clicked does not matter.
   (NB: the board lazily renders clickable free anchors only for the leftmost ~2 columns in the
   automation viewport, so do NOT rely on finding a rendered anchor for a specific aircraft.)
3. In the iframe (`mstr7apop.aspx`), set the fields:
   - `#DropAC` — aircraft, option label like `15MJ (C172S G1000)`.
   - `#DropStartDT` / `#DropEndDT` — dates (prefilled from the board date).
   - `#DropStartTM` / `#DropEndTM` — `HH:MM` (30-min options). **Must be set explicitly** — the modal
     defaults `DropStartTM` to `00:00`, NOT the clicked cell's time. (This was the root cause of early
     silent rejections: booking midnight / out-of-hours.)
   - `#DropCFI` — `SOLO` or an instructor name.
   - `#DropCategory` — e.g. `Flight`.
   - `#txtSchedNote` — free-text note.
4. Click `#ButtMakeSched` ("Make Schedule").
5. Verify: the new reservation appears in `get_my_schedule()` (and at `mstr7a.aspx?schednum=N`).

Rejection notes (booking silently fails — modal stays / no new reservation):
- The aircraft+time must actually be **free** for that aircraft, **in operating hours**
  (late-night slots are "unavailable"), and the user must be **checked out** on the aircraft
  (twins like 111XX rejected). Booking an aircraft the user flies (e.g. 15MJ) at a free daytime
  slot succeeds.

## Cancel (delete) a reservation

The reservation detail page `mstr7a.aspx?schednum=N` carries the action buttons.

Steps:
1. Navigate to `https://<base>/mstr7a.aspx?schednum=<N>`.
2. Click `#ctl00_ContentPlaceHolder1_ButtCancelSched` ("Delete Schedule"). This reveals a
   confirmation section: a set of **reason checkboxes** plus confirm/abort buttons.
3. Check exactly one reason checkbox (required). Available reason checkboxes:
   - `#ctl00_ContentPlaceHolder1_ChkCWeather` — Weather
   - `#ctl00_ContentPlaceHolder1_ChkCMaint` — Aircraft Maintenance
   - `#ctl00_ContentPlaceHolder1_ChkCStudent` — Student Cancel
   - `#ctl00_ContentPlaceHolder1_ChkCSchedError` — Schedule Error
   - `#ctl00_ContentPlaceHolder1_ChkCNoShow` — No Show / No Call
   - `#ctl00_ContentPlaceHolder1_ChkCInstructor` — Instructor availability
   - `#ctl00_ContentPlaceHolder1_ChkCOther` — Other (Fill in Text) → also fill `#txtCancelReason`
   (checking a box triggers a postback; wait for it to settle.)
4. Click `#ctl00_ContentPlaceHolder1_ButtCancelSched0` (the confirm "Delete Schedule").
5. Verify: the reservation no longer appears in `get_my_schedule()`.

## Modify a reservation (Phase W2)

`mstr7a.aspx?schednum=N` also exposes `#ctl00_ContentPlaceHolder1_ButModSched` ("Modify Schedule")
and the same field controls as the create modal (`DropAC`, `DropStartTM`/`DropEndTM`, `DropCFI`,
`DropCategory`, `txtSchedNote`). Modify = change those fields then click `ButModSched`. (Implement in W2.)

## Other controls on mstr7a.aspx
- `#ctl00_ContentPlaceHolder1_ButtReturn` ("Return"), `#...ButtReturn0` ("Do not delete").
- Cancel-reason free text: `#ctl00_ContentPlaceHolder1_txtCancelReason` (only needed for "Other").
