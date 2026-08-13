"""
src/scanner/browser_factory.py — Process-Isolated Playwright Browser Lifecycle Manager
Layer 2: Browser Engine
"""
import logging
from typing import Any
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
from src.config import MIN_VIEWPORT_HEIGHT, MIN_VIEWPORT_WIDTH

logger = logging.getLogger(__name__)


class BrowserFactory:
    """
    Manages process-isolated Playwright browser instances and clean contexts.
    Does NOT inspect DOM, write JSON, calculate metrics, or render reports.
    """

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._active_contexts: list[BrowserContext] = []

    def start(self) -> None:
        """Starts Playwright engine and launches Chromium instance for this worker process."""
        if self._browser is None or not self._browser.is_connected():
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-remote-fonts",
                ],
            )

    def _enforce_context_limit(self) -> None:
        """Enforces limits on concurrent BrowserContext objects to prevent resource leaks."""
        MAX_CONCURRENT_CONTEXTS = 3
        while len(self._active_contexts) >= MAX_CONCURRENT_CONTEXTS:
            oldest = self._active_contexts.pop(0)
            try:
                logger.info("Closing oldest active BrowserContext to enforce concurrency limit.")
                oldest.close()
            except Exception as exc:
                logger.debug("Error closing oldest BrowserContext: %s", exc)

    def create_clean_context(
        self,
        viewport_width: int = MIN_VIEWPORT_WIDTH,
        viewport_height: int = MIN_VIEWPORT_HEIGHT,
        user_agent: str | None = None,
    ) -> BrowserContext:
        """Creates a fresh, isolated BrowserContext with clean cookies, storage, and custom UA."""
        if self._browser is None or not self._browser.is_connected():
            self.start()

        self._enforce_context_limit()

        ua = (
            user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 RevenueLeakScanner/2.3.1"
        )
        assert self._browser is not None
        context = self._browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            user_agent=ua,
            device_scale_factor=1.0,
            is_mobile=False,
            has_touch=False,
        )
        self._active_contexts.append(context)
        return context

    def create_mobile_context(
        self,
        viewport_width: int = 375,
        viewport_height: int = 667,
        user_agent: str | None = None,
    ) -> BrowserContext:
        """Creates a fresh, isolated mobile BrowserContext with clean cookies, storage, and mobile UA."""
        if self._browser is None or not self._browser.is_connected():
            self.start()

        self._enforce_context_limit()

        ua = (
            user_agent
            or "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1 RevenueLeakScannerMobile/2.3.1"
        )
        assert self._browser is not None
        context = self._browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            user_agent=ua,
            device_scale_factor=3.0,
            is_mobile=True,
            has_touch=True,
        )
        self._active_contexts.append(context)
        return context

    def create_clean_page(
        self,
        viewport_width: int = MIN_VIEWPORT_WIDTH,
        viewport_height: int = MIN_VIEWPORT_HEIGHT,
    ) -> Page:
        """Creates a clean context and opens a single Playwright Page."""
        context = self.create_clean_context(viewport_width, viewport_height)
        page = context.new_page()
        page.set_default_timeout(15000)  # 15s default navigation/action timeout

        # P3 — Apply stealth anti-detection
        from src.scanner.navigation_helper import apply_stealth_if_available
        apply_stealth_if_available(page)

        return page

    def close(self) -> None:
        """Cleans up browser context and stops Playwright instance for this process."""
        for ctx in list(self._active_contexts):
            try:
                ctx.close()
            except Exception:
                pass
        self._active_contexts.clear()
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self) -> "BrowserFactory":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
