"""Browser management for OpenTrack automation."""

import logging
import time
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Generator, ParamSpec, TypeVar

from playwright.sync_api import Browser, BrowserContext, Page, Response, sync_playwright
from playwright_stealth import Stealth

from .config import OpenTrackConfig

logger = logging.getLogger(__name__)

_stealth = Stealth()

# Upstream / Cloudflare error statuses we transparently retry on.
_RETRYABLE_STATUSES = {502, 503, 504}
_MAX_UPSTREAM_RETRIES = 4
_UPSTREAM_RETRY_WAIT = 5.0


def _is_upstream_error_page(page: Page, response: Response | None) -> bool:
    """Return True if the most recent navigation landed on a 5xx / Cloudflare
    error page. Falls back to inspecting the page title when the response
    object isn't available (e.g., after click-driven navigation)."""
    if response is not None and response.status in _RETRYABLE_STATUSES:
        return True
    try:
        title = (page.title() or "").lower()
    except Exception:
        return False
    return (
        "bad gateway" in title
        or "gateway time-out" in title
        or "gateway timeout" in title
    )


def _install_upstream_retry(page: Page) -> None:
    """Make all navigations resilient to Cloudflare / upstream 5xx errors.

    Two complementary mechanisms:

    1. Wrap `page.goto` (and `page.reload`) so direct navigations retry
       after a short wait when the response status is 5xx.

    2. Listen for main-frame document responses; when one comes back 5xx
       (e.g. from a `link.click()` that triggered navigation), schedule a
       reload via in-page `setTimeout`. Subsequent waits naturally tolerate
       the reload because their selectors are still pending.

    The real browser navigation is preserved end-to-end so Cloudflare's bot
    detection sees a normal session.
    """
    # --- 1. retry page.goto / page.reload directly ---------------------
    original_goto = page.goto
    original_reload = page.reload

    @wraps(original_goto)
    def goto_with_retry(url: str, **kwargs: Any) -> Response | None:
        last_response: Response | None = None
        for attempt in range(1, _MAX_UPSTREAM_RETRIES + 1):
            last_response = original_goto(url, **kwargs)
            if not _is_upstream_error_page(page, last_response):
                return last_response
            status = last_response.status if last_response else "(no response)"
            logger.warning(
                "Upstream %s at %s (attempt %d/%d), retrying after %.1fs",
                status, url, attempt, _MAX_UPSTREAM_RETRIES, _UPSTREAM_RETRY_WAIT,
            )
            time.sleep(_UPSTREAM_RETRY_WAIT)
        return last_response

    @wraps(original_reload)
    def reload_with_retry(**kwargs: Any) -> Response | None:
        last_response: Response | None = None
        for attempt in range(1, _MAX_UPSTREAM_RETRIES + 1):
            last_response = original_reload(**kwargs)
            if not _is_upstream_error_page(page, last_response):
                return last_response
            status = last_response.status if last_response else "(no response)"
            logger.warning(
                "Upstream %s on reload of %s (attempt %d/%d), retrying after %.1fs",
                status, page.url, attempt, _MAX_UPSTREAM_RETRIES, _UPSTREAM_RETRY_WAIT,
            )
            time.sleep(_UPSTREAM_RETRY_WAIT)
        return last_response

    page.goto = goto_with_retry  # type: ignore[assignment]
    page.reload = reload_with_retry  # type: ignore[assignment]


# Directory for error screenshots
SCREENSHOT_DIR = Path("screenshots")

P = ParamSpec("P")
T = TypeVar("T")


def save_screenshot(page: Page, name: str) -> Path:
    """Save a screenshot to the screenshots directory.
    
    Args:
        page: Playwright page to screenshot
        name: Name for the screenshot (timestamp will be prepended)
        
    Returns:
        Path to the saved screenshot
    """
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    path = SCREENSHOT_DIR / f"{timestamp}_{name}.png"
    page.screenshot(path=str(path))
    print(f"Screenshot: {path}")
    return path


def screenshot_on_error(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator that captures a screenshot when an exception occurs, and
    transparently recovers from Cloudflare upstream 5xx errors.

    If the wrapped method raises and the page is currently showing a
    Cloudflare bad-gateway / gateway-timeout page, reload (which has its
    own retry-on-5xx loop) and re-invoke the method once. Only screenshots
    + re-raises if the second attempt still fails (or the page wasn't on a
    5xx page to begin with).

    Expects the first argument (self) to have a `page` attribute.
    """
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except Exception as first_exc:
            page = args[0].page if args and hasattr(args[0], "page") else None

            if page is not None and _is_upstream_error_page(page, None):
                logger.warning(
                    "Cloudflare upstream error during %s, reloading and retrying once",
                    func.__name__,
                )
                try:
                    page.reload(wait_until="load")
                except Exception:
                    logger.exception("Reload while recovering from upstream error failed")
                else:
                    if not _is_upstream_error_page(page, None):
                        try:
                            return func(*args, **kwargs)
                        except Exception as retry_exc:
                            first_exc = retry_exc

            if page is not None:
                try:
                    save_screenshot(page, f"error_{func.__name__}")
                    print(f"URL: {page.url}")
                except Exception:
                    pass
            raise first_exc
    return wrapper


@contextmanager
def create_browser(config: OpenTrackConfig) -> Generator[tuple[Browser, BrowserContext, Page], None, None]:
    """Create a browser instance with the given configuration.
    
    Usage:
        with create_browser(config) as (browser, context, page):
            page.goto(config.base_url)
            # ... do stuff
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.headless,
            slow_mo=config.slow_mo,
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        _stealth.apply_stealth_sync(page)

        try:
            yield browser, context, page
        finally:
            context.close()
            browser.close()


class OpenTrackSession:
    """A session for interacting with OpenTrack."""

    def __init__(self, config: OpenTrackConfig | None = None):
        self.config = config or OpenTrackConfig.from_env()
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> "OpenTrackSession":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        self._page = self._context.new_page()
        _stealth.apply_stealth_sync(self._page)
        # Transparent retry on Cloudflare/upstream 5xx errors for all
        # page.goto() calls — keeps the real browser navigation intact
        # (avoids triggering Cloudflare bot detection).
        _install_upstream_retry(self._page)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Session not started. Use 'with OpenTrackSession() as session:'")
        return self._page

    def goto_home(self) -> None:
        """Navigate to the OpenTrack home page."""
        self.page.goto(self.config.base_url)

    def login(self, username: str | None = None, password: str | None = None) -> None:
        """Log in to OpenTrack.
        
        Uses provided credentials or falls back to config.
        """
        username = username or self.config.username
        password = password or self.config.password

        if not username or not password:
            raise ValueError("Username and password are required. Set OPENTRACK_USERNAME and OPENTRACK_PASSWORD env vars.")

        # Navigate to home and click login
        self.page.goto(self.config.base_url)
        self.page.get_by_role("link", name="Login / Sign Up").click()
        
        # Fill login form
        self.page.get_by_role("textbox", name="Email").click()
        self.page.get_by_role("textbox", name="Email").fill(username)
        self.page.get_by_role("textbox", name="Password").fill(password)
        self.page.get_by_role("button", name="Log in").click()
        
        # Wait for navigation to complete
        self.page.wait_for_load_state("networkidle")

    def is_logged_in(self) -> bool:
        """Check if currently logged in."""
        return self.page.locator("text=Log out").count() > 0 or self.page.locator("text=Logout").count() > 0
