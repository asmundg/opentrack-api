"""Browser management for OpenTrack automation."""

from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Callable, Generator, ParamSpec, TypeVar

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .config import OpenTrackConfig

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
    """Decorator that takes a screenshot when an exception occurs.
    
    Expects the first argument (self) to have a `page` attribute.
    """
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Try to get page from self (first arg)
            if args and hasattr(args[0], "page"):
                page = args[0].page
                try:
                    save_screenshot(page, f"error_{func.__name__}")
                    print(f"URL: {page.url}")
                except Exception:
                    pass
            raise
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
        self.page.get_by_role("link", name="Login / SignUp").click()
        
        # Fill login form
        self.page.get_by_role("textbox", name="Email:").click()
        self.page.get_by_role("textbox", name="Email:").fill(username)
        self.page.get_by_role("textbox", name="Password:").fill(password)
        self.page.get_by_role("button", name="Log in").click()
        
        # Wait for navigation to complete
        self.page.wait_for_load_state("networkidle")

    def is_logged_in(self) -> bool:
        """Check if currently logged in."""
        return self.page.locator("text=Log out").count() > 0 or self.page.locator("text=Logout").count() > 0
