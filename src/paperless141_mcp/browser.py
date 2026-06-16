"""Persistent Playwright browser session for postback-navigated Paperless141 pages.

Paperless141 navigates entirely via ASP.NET postbacks (menu buttons run
``SetDestination(...)`` then submit the form), so a stateless httpx GET cannot reach
the inner pages. This session logs in once, keeps a single browser/page alive, and
re-uses it for every navigation. Calls are serialised with a lock because one page
cannot service two postback navigations at once.
"""
from __future__ import annotations
import asyncio
from playwright.async_api import async_playwright

from .config import Config
from .session import (
    LOGIN_URL_PATH,
    LoginError,
    submit_login,
    looks_like_login_page,
)

# The scheduler board's date input (HTML5 date control, ASP.NET autopostback).
SCHED_DATE_INPUT = "#ctl00_ContentPlaceHolder1_DropDate1"
SCHEDULER_BTN = "#ctl00_BtnSched"  # landing-page menu button → scheduler board

# Booking modal (mstr7apop.aspx iframe) field selectors — see docs/superpowers/discovery.
_BOOK_AC = "#DropAC"
_BOOK_START_TM = "#DropStartTM"
_BOOK_END_TM = "#DropEndTM"
_BOOK_CFI = "#DropCFI"
_BOOK_CATEGORY = "#DropCategory"
_BOOK_NOTE = "#txtSchedNote"
_BOOK_SUBMIT = "#ButtMakeSched"

# Reservation detail page (mstr7a.aspx) cancel controls.
_CANCEL_BTN = "#ctl00_ContentPlaceHolder1_ButtCancelSched"
_CANCEL_CONFIRM = "#ctl00_ContentPlaceHolder1_ButtCancelSched0"
_CANCEL_REASON_TEXT = "#ctl00_ContentPlaceHolder1_txtCancelReason"
CANCEL_REASON_CHECKBOXES = {
    "Weather": "#ctl00_ContentPlaceHolder1_ChkCWeather",
    "Aircraft Maintenance": "#ctl00_ContentPlaceHolder1_ChkCMaint",
    "Student Cancel": "#ctl00_ContentPlaceHolder1_ChkCStudent",
    "Schedule Error": "#ctl00_ContentPlaceHolder1_ChkCSchedError",
    "No Show / No Call": "#ctl00_ContentPlaceHolder1_ChkCNoShow",
    "Instructor availability": "#ctl00_ContentPlaceHolder1_ChkCInstructor",
    "Other": "#ctl00_ContentPlaceHolder1_ChkCOther",
}

# JS to return any rendered free-slot postback href, used only to pop the booking modal.
_FREE_ANCHOR_JS = (
    "() => {const a=[...document.querySelectorAll("
    "'#ctl00_ContentPlaceHolder1_GridView2 a')].find(e=>"
    "(e.getAttribute('href')||'').includes('__doPostBack') && e.textContent.trim()==='');"
    "return a ? a.getAttribute('href') : null;}"
)


class BookingError(Exception):
    """Raised when a create/cancel browser flow cannot be completed."""


class BrowserSession:
    """A logged-in, reusable Playwright page for the user's own Paperless141 account."""

    def __init__(self, config: Config):
        self.config = config
        self._pw = None
        self._browser = None
        self._page = None
        self._landing_url: str | None = None
        self._lock = asyncio.Lock()

    @property
    def logged_in(self) -> bool:
        return self._page is not None and self._landing_url is not None

    async def start(self) -> None:
        """Launch the browser and log in. Idempotent — a no-op once logged in."""
        if self.logged_in:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        try:
            await self._login()
        except Exception:
            # Don't leak the Chromium process / Playwright driver on a failed login.
            await self.close()
            raise

    async def _login(self) -> None:
        await self._page.goto(
            self.config.base_url + LOGIN_URL_PATH, wait_until="networkidle"
        )
        await submit_login(self._page, self.config)
        html = await self._page.content()
        if looks_like_login_page(html):
            raise LoginError("Login failed — still on the login page (check credentials).")
        self._landing_url = self._page.url

    async def open_menu(self, button_selector: str) -> str:
        """Navigate to a menu destination by clicking its postback button; return HTML.

        Re-logs-in once if the session has expired between calls.
        """
        async with self._lock:
            return await self._open_locked(button_selector)

    async def open_scheduler(
        self, button_selector: str, date: str | None = None
    ) -> str:
        """Open the scheduler board, optionally for a specific date (YYYY-MM-DD).

        The date is applied via the board's date input (an ASP.NET autopostback
        control), all within one held lock so the navigation and date change are atomic.
        """
        async with self._lock:
            html = await self._open_locked(button_selector)
            if date:
                html = await self._set_scheduler_date(date)
            return html

    async def _open_locked(self, button_selector: str) -> str:
        await self.start()
        html = await self._navigate(button_selector)
        if looks_like_login_page(html):
            # Session expired — re-login and retry once.
            await self._login()
            html = await self._navigate(button_selector)
        return html

    async def _set_scheduler_date(self, date: str) -> str:
        await self._page.fill(SCHED_DATE_INPUT, date)
        await self._page.dispatch_event(SCHED_DATE_INPUT, "change")
        await self._page.wait_for_load_state("networkidle")
        return await self._page.content()

    def _booking_frame(self):
        """Return the open booking-modal iframe frame, or None."""
        return next((f for f in self._page.frames if "mstr7apop" in f.url), None)

    async def _open_booking_modal(self):
        """Pop the booking modal (mstr7apop.aspx iframe) from the current board; return its frame.

        Any rendered free-slot postback opens the modal — we then set the real aircraft/time,
        so which slot is clicked does not matter.
        """
        href = None
        for _ in range(8):
            href = await self._page.evaluate(_FREE_ANCHOR_JS)
            if href:
                break
            await self._page.wait_for_timeout(800)
        if not href:
            raise BookingError("no free slot available to open the booking form on this date")
        await self._page.evaluate(href.replace("javascript:", ""))
        await self._page.wait_for_timeout(3000)
        frame = self._booking_frame()
        if frame is None:
            raise BookingError("booking modal did not open")
        return frame

    async def book_slot(
        self,
        date: str,
        start: str,
        end: str,
        tail: str,
        cfi: str | None = None,
        category: str | None = None,
        note: str | None = None,
    ) -> str:
        """Create a reservation via the booking modal; return the resulting page HTML.

        date=YYYY-MM-DD, start/end=HH:MM (24h). The aircraft+time must be genuinely free
        and the user checked out on the aircraft, else the booking is silently rejected.
        """
        async with self._lock:
            await self._open_locked(SCHEDULER_BTN)
            await self._set_scheduler_date(date)
            frame = await self._open_booking_modal()
            opts = await frame.eval_on_selector_all(
                _BOOK_AC + " option", "els => els.map(e => e.textContent.trim())"
            )
            ac = next((o for o in opts if o.split()[0] == tail), None)
            if ac is None:
                raise BookingError(f"aircraft {tail!r} not found in booking dropdown")
            await frame.select_option(_BOOK_AC, label=ac)
            await frame.wait_for_timeout(800)
            frame = self._booking_frame() or frame  # re-acquire after AC postback
            await frame.select_option(_BOOK_START_TM, label=start)
            await frame.select_option(_BOOK_END_TM, label=end)
            if cfi:
                await frame.select_option(_BOOK_CFI, label=cfi)
            if category:
                await frame.select_option(_BOOK_CATEGORY, label=category)
            if note is not None:
                await frame.fill(_BOOK_NOTE, note)
            await frame.click(_BOOK_SUBMIT)
            await self._page.wait_for_timeout(4500)
            return await self._page.content()

    async def cancel_reservation_flow(
        self, schedule_number: str, reason: str = "Schedule Error"
    ) -> str:
        """Delete a reservation by schedule_number; return the resulting page HTML.

        Drives the mstr7a.aspx confirm flow: Delete → tick a reason checkbox → confirm.
        """
        async with self._lock:
            await self.start()
            checkbox = CANCEL_REASON_CHECKBOXES.get(
                reason, CANCEL_REASON_CHECKBOXES["Schedule Error"]
            )
            url = f"{self.config.base_url}/mstr7a.aspx?schednum={schedule_number}"
            await self._page.goto(url, wait_until="networkidle")
            if looks_like_login_page(await self._page.content()):
                # Session expired — re-login and reload the detail page once.
                await self._login()
                await self._page.goto(url, wait_until="networkidle")
            await self._page.click(_CANCEL_BTN)
            await self._page.wait_for_timeout(2500)
            await self._page.check(checkbox)
            await self._page.wait_for_timeout(1500)
            if reason == "Other":
                await self._page.fill(_CANCEL_REASON_TEXT, "Cancelled via MCP")
            await self._page.click(_CANCEL_CONFIRM)
            await self._page.wait_for_timeout(4000)
            return await self._page.content()

    async def _navigate(self, button_selector: str) -> str:
        await self._page.goto(self._landing_url, wait_until="networkidle")
        await self._page.click(button_selector)
        await self._page.wait_for_load_state("networkidle")
        return await self._page.content()

    async def close(self) -> None:
        """Tear down the browser and Playwright. Safe to call multiple times."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
        self._page = None
        self._landing_url = None
