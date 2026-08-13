"""
src/scanner/navigation_helper.py — Reusable navigation helper with retry logic.
P3: Built-in stealth anti-detection (no external dependency).
"""
import logging
import time
from playwright.sync_api import Page, Response

logger = logging.getLogger(__name__)


def apply_stealth_builtin(page: Page) -> bool:
    """
    Apply built-in stealth anti-detection scripts to a Page.
    Covers the 7 most important anti-bot detection vectors.
    Safe to call multiple times — uses page._stealth_applied flag.
    Returns True if stealth was applied successfully.
    
    Techniques applied:
    1. Hide navigator.webdriver (Playwright detection flag)
    2. Spoof chrome.runtime (mimic real Chrome)
    3. Spoof permissions query API
    4. Spoof WebGL vendor/renderer (Intel GPU)
    5. Spoof plugins array (3 plugins like real Chrome)
    6. Spoof navigator.languages (en-US, en)
    7. Spoof navigator.platform (Win32)
    """
    if getattr(page, "_stealth_applied", False):
        return True
    try:
        # Stealth scripts injected at init time (before any navigation)
        page.add_init_script("""
            // 1. Hide navigator.webdriver (Playwright/Chrome flag)
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // 2. Spoof chrome.runtime (makes Playwright look like real Chrome)
            window.chrome = window.chrome || {};
            window.chrome.runtime = {
                connect: () => {},
                sendMessage: () => {},
            };

            // 3. Spoof permissions query (prevent bot detection via Permissions API)
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );

            // 4. Spoof WebGL vendor and renderer
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function (parameter) {
                if (parameter === 37445) return 'Intel Inc.';           // UNMASKED_VENDOR_WEBGL
                if (parameter === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
                return getParameter.call(this, parameter);
            };

            // 5. Spoof plugins array (real Chrome has at least one plugin)
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' },
                    ];
                    plugins.length = 3;
                    return plugins;
                },
            });

            // 6. Spoof languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });

            // 7. Spoof platform (prevent detection via OS check)
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32',
            });
        """)
        page._stealth_applied = True
        logger.info("Applied built-in stealth anti-detection to page")
        return True
    except Exception as exc:
        logger.warning("Failed to apply built-in stealth: %s", exc)
        return False


def is_retryable_error(exc: Exception) -> bool:
    """Checks if a Playwright navigation exception is transient/retryable."""
    err_msg = str(exc).lower()
    retryable_keywords = [
        "timeout",
        "connection reset",
        "connection closed",
        "connection refused",
        "name not resolved",
        "net::err_connection_reset",
        "net::err_connection_closed",
        "net::err_connection_refused",
        "net::err_name_not_resolved",
        "net::err_timed_out",
        "network error",
        "load state",
    ]
    return any(kw in err_msg for kw in retryable_keywords)


def navigate_with_retry(
    page: Page,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout: int = 15000,
    max_attempts: int = 3,
) -> Response | None:
    """
    Navigates a Playwright Page to a URL with a retry mechanism.
    Enforces retryable vs non-retryable boundaries with logging.
    P3: Applies built-in stealth anti-detection before first navigation.
    """
    # P3 — Apply stealth before first navigation (idempotent)
    apply_stealth_builtin(page)

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Navigation attempt=%d/%d url=%s", attempt, max_attempts, url)
            response = page.goto(url, wait_until=wait_until, timeout=timeout)

            # Non-retryable HTTP client errors (404, 400)
            if response and response.status in (400, 404):
                logger.warning("FAILED non-retryable HTTP status %d url=%s", response.status, url)
                return response

            if attempt > 1:
                logger.info("SUCCESS attempt=%d/%d url=%s", attempt, max_attempts, url)
            return response

        except Exception as exc:
            # Distinguish retryable vs non-retryable errors
            if not is_retryable_error(exc):
                logger.warning("FAILED non-retryable error url=%s error=%s: %s", url, type(exc).__name__, exc)
                raise exc

            if attempt == max_attempts:
                logger.error("FAILED after %d attempts url=%s error=%s: %s", max_attempts, url, type(exc).__name__, exc)
                raise exc

            logger.warning("RETRY attempt=%d/%d url=%s error=%s: %s", attempt, max_attempts, url, type(exc).__name__, exc)

            # P3 — Add jitter delay between retries (anti-detection)
            import random
            jitter = random.uniform(0.5, 1.5)
            time.sleep((attempt * 0.5) + jitter)

    return None


def dismiss_overlays_and_popups(page: Page) -> None:
    """
    Dismisses geolocation selectors, newsletter popups, cookie consent banners,
    and other overlays that contaminate screenshots and block page elements.
    """
    # 1. Simulate pressing Escape key to dismiss simple modals/overlays
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    except Exception:
        pass

    # 2. Run a Javascript selector-based click script for cookie consent, country select, and newsletters
    try:
        page.evaluate("""() => {
            // Cookie banners accept selectors
            const cookieSelectors = [
                '#onetrust-accept-btn-handler',
                '.cookie-accept',
                '.js-accept-cookie',
                '#btn-accept-cookies',
                '#accept-cookies',
                '[id*="cookie" i] button[class*="accept" i]',
                '[class*="cookie" i] button[class*="accept" i]',
                '#shopify-pc-btn-accept',
                '.accept-cookies-button',
                '#accept-all-cookies'
            ];
            for (const sel of cookieSelectors) {
                try {
                    const el = document.querySelector(sel);
                    if (el && el.offsetHeight > 0) {
                        el.click();
                    }
                } catch(e) {}
            }

            // Click buttons containing common confirmation/accept keywords
            try {
                const buttons = Array.from(document.querySelectorAll('button, a'));
                for (const btn of buttons) {
                    if (btn.offsetHeight > 0) {
                        const text = (btn.textContent || '').trim().toLowerCase();
                        if (['accept', 'accept all', 'accepter', 'tout accepter', 'accept cookies',
                             'agree', 'ok', 'accept and close', 'confirm', 'i accept'].includes(text)) {
                            btn.click();
                        }
                    }
                }
            } catch(e) {}

            // Newsletter/promotion and country close/dismiss selectors
            const closeSelectors = [
                'button[aria-label*="close" i]',
                '[class*="close-modal" i]',
                '[class*="modal-close" i]',
                '.modal-close',
                '.close-modal',
                '.close-btn',
                'button.close',
                '[class*="close" i] button',
                '[class*="Newsletter" i] [class*="close" i]',
                '.klaviyo-form button[tabindex="0"]:not([type="submit"])',
                '.klaviyo-form [class*="close" i]',
                '.rego-close-button',
                '.newsletter-close',
                '.close-icon',
                '.icon-close',
                '.popup-close',
                '#popup-close'
            ];
            for (const sel of closeSelectors) {
                try {
                    const el = document.querySelector(sel);
                    if (el && el.offsetHeight > 0) {
                        el.click();
                    }
                } catch(e) {}
            }

            // Click buttons/links containing common dismiss keywords
            try {
                const els = Array.from(document.querySelectorAll('button, a, div, span'));
                for (const el of els) {
                    if (el.offsetHeight > 0 && el.tagName.toLowerCase() in {button: 1, a: 1, span: 1, div: 1}) {
                        const text = (el.textContent || '').trim().toLowerCase();
                        if (['close', 'no thanks', 'dismiss', 'decline', 'x', 'non merci',
                             'tout rejeter', 'reject all'].includes(text)) {
                            el.click();
                        }
                    }
                }
            } catch(e) {}
        }""")
        page.wait_for_timeout(400)
    except Exception as e:
        logger.debug("Failed JS-based overlay dismissal: %s", e)

    # 3. Check if there is an unresolved visible modal overlay
    try:
        has_unresolved_modal = page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll(
                'div, section, aside, [role="dialog"], [role="alertdialog"]'));
            return els.some(el => {
                const style = window.getComputedStyle(el);
                const isVisible = el.offsetHeight > 200 && el.offsetWidth > 200
                    && style.display !== 'none' && style.visibility !== 'hidden'
                    && parseFloat(style.opacity || '1') > 0;
                if (!isVisible) return false;

                // Check if it is a modal/popup/cookie banner container
                const idOrClass = ((el.id || '') + ' ' + (el.className || '')).toLowerCase();
                const isModal = idOrClass.includes('modal') || idOrClass.includes('popup')
                    || idOrClass.includes('cookie') || idOrClass.includes('banner')
                    || el.getAttribute('role') === 'dialog'
                    || el.getAttribute('aria-modal') === 'true';
                if (!isModal) return false;

                // Make sure it sits on top of others
                const zIndex = parseInt(style.zIndex);
                return zIndex > 5 || style.position === 'fixed';
            });
        }""")
        page.has_unresolved_modal = bool(has_unresolved_modal)
        if page.has_unresolved_modal:
            logger.warning("Unresolved modal detected on the page after dismissal attempts.")
    except Exception:
        page.has_unresolved_modal = False
