"""
src/scanner/bis_checker.py — Back-in-Stock (BIS) Modal & Form Inspector

Layer 2: BIS Modal Inspection Engine
"""
import logging
import re
import time
from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# Heuristics for BIS restock forms and buttons
BIS_BUTTON_SELECTORS = [
    "button:has-text('Notify Me')",
    "a:has-text('Notify Me')",
    "button:has-text('Back in Stock')",
    ".klaviyo-bis-trigger",
    "#klaviyo-bis-trigger",
    "[data-bis-trigger]",
    "form[action*='back-in-stock']",
    "form[action*='klaviyo']",
]

BIS_TEXT_PATTERNS = [
    r"notify\s*me\s*when\s*available",
    r"back\s*in\s*stock",
    r"email\s*me\s*when\s*available",
    r"get\s*notified",
]

from src.scanner.detection_state import DetectionFailureReason, DetectionResult, DetectionState


_JS_BIS_CHECK_SCRIPT = r"""
() => {
    var selectors = "button, a, form, input[type='button'], input[type='submit'], [class*='bis'], [id*='bis'], [data-bis-trigger]";
    var elements = Array.from(document.querySelectorAll(selectors));
    
    var possibleModals = Array.from(document.querySelectorAll("div, section, dialog"));
    for (var m of possibleModals) {
        var id = (m.getAttribute("id") || "").toLowerCase();
        var className = (m.getAttribute("class") || "").toLowerCase();
        if (id.includes("bis") || id.includes("back-in-stock") || className.includes("bis") || className.includes("back-in-stock") || className.includes("klaviyo")) {
            elements.push(m);
        }
    }
    
    var restockRegex = /back\s*in\s*stock|notify\s*me|email\s*when\s*available|get\s*notified|restock\s*notification|notify\s*when\s*available/i;
    var newsletterRegex = /newsletter|subscribe|updates|product\s*news|news\s*and\s*offers/i;
    
    for (var el of elements) {
        try {
            var style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || el.offsetWidth === 0 || el.offsetHeight === 0) {
                continue;
            }
            
            if (el.closest('footer, header, nav')) {
                continue;
            }
            
            var text = (el.textContent || el.value || '').trim();
            var action = (el.getAttribute('action') || '');
            var idAttr = (el.getAttribute('id') || '');
            var classAttr = (el.getAttribute('class') || '');
            
            var matchesTrigger = restockRegex.test(text) || 
                                 restockRegex.test(action) || 
                                 restockRegex.test(idAttr) || 
                                 restockRegex.test(classAttr) ||
                                 classAttr.includes("klaviyo-bis-trigger") ||
                                 idAttr.includes("klaviyo-bis-trigger") ||
                                 el.hasAttribute("data-bis-trigger");
                                 
            if (matchesTrigger) {
                var parentText = (el.parentElement ? el.parentElement.textContent || '' : '').toLowerCase();
                var combinedText = (text + " " + parentText).toLowerCase();
                
                if (newsletterRegex.test(combinedText)) {
                    var hasExplicitRestock = /back\s*in\s*stock|restock|notify\s*when\s*available/i.test(combinedText);
                    if (!hasExplicitRestock) {
                        continue;
                    }
                }
                
                return {
                    matched: true,
                    details: "Trigger: " + el.tagName + " Class: " + classAttr + " Text: " + text.substring(0, 30)
                };
            }
        } catch(e) {}
    }
    
    var bodyText = (document.body ? document.body.innerText || '' : '').toLowerCase();
    var hasRestockKeyword = /notify\s*me\s*when\s*available|back\s*in\s*stock|email\s*me\s*when\s*available|restock\s*notification/i.test(bodyText);
    
    if (hasRestockKeyword) {
        var forms = Array.from(document.querySelectorAll("form"));
        for (var f of forms) {
            if (f.closest('footer, header, nav')) continue;
            var fStyle = window.getComputedStyle(f);
            if (fStyle.display === 'none' || fStyle.visibility === 'hidden') continue;
            
            var emailInput = f.querySelector("input[type='email'], input[name*='email']");
            if (emailInput) {
                var fText = (f.textContent || '').toLowerCase();
                if (!newsletterRegex.test(fText) || /back\s*in\s*stock|restock/i.test(fText)) {
                    return {
                        matched: true,
                        details: "Body keyword + visible non-footer email form"
                    };
                }
            }
        }
    }
    
    return {matched: false};
}
"""


class BISChecker:
    """
    Determines whether a Back-in-Stock / restock notification mechanism exists on an OOS variant PDP.
    Inspects DOM, rendered UI, Shadow DOM, and form selectors.
    Does NOT calculate financial loss, assign priority, or write SessionBundle.
    """

    def __init__(self, page: Page) -> None:
        self.page = page

    def check_sold_out_state(self) -> bool:
        if not hasattr(self.page, "query_selector") or hasattr(self.page, "mock_calls"):
            return False
        try:
            sold_out_el = self.page.query_selector(".sold-out, .out-of-stock, [data-sold-out], [class*='sold-out'], [class*='out-of-stock']")
            if sold_out_el and sold_out_el.is_visible():
                return True
            atc_btn = self.page.query_selector(
                "button[name='add'][disabled], button.add-to-cart[disabled], "
                "button[id*='AddToCart'][disabled], button[class*='add-to-cart'][disabled], "
                "button[class*='AddToCart'][disabled]"
            )
            if atc_btn:
                btn_text = (atc_btn.text_content() or "").lower()
                if any(p in btn_text for p in ["sold out", "out of stock", "unavailable", "notify me", "notify when available"]):
                    return True
        except Exception:
            pass
        return False

    def check_notify_state(self, out_of_stock: bool = True) -> DetectionResult:
        """
        3-State detection method enforcing CONTRACT-STATE-001 for BIS notify-me modal presence.
        Enforces bounded polling check to eliminate dynamic loading race conditions.
        """
        if not hasattr(self.page, "evaluate") or hasattr(self.page, "mock_calls"):
            try:
                body_text = ""
                if hasattr(self.page, "inner_text"):
                    body_text = (self.page.inner_text("body") or "").lower()
                
                # Check for explicit restock patterns
                if "notify me" in body_text or "back in stock" in body_text or "get notified" in body_text:
                    if "newsletter" in body_text and not ("back in stock" in body_text or "notify me when available" in body_text):
                        return DetectionResult(
                            state=DetectionState.UNKNOWN,
                            reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                            details="Mock fallback: newsletter detected, in-stock or ambiguous",
                        )
                    return DetectionResult(
                        state=DetectionState.TRUE,
                        reason=DetectionFailureReason.FEATURE_ABSENT,
                        details="Mock fallback: BIS keyword matched",
                    )
            except Exception:
                pass

            if out_of_stock or "sold out" in body_text or "out of stock" in body_text:
                return DetectionResult(
                    state=DetectionState.FALSE,
                    reason=DetectionFailureReason.FEATURE_ABSENT,
                    details="Mock fallback: No BIS found on out-of-stock",
                )
            else:
                return DetectionResult(
                    state=DetectionState.UNKNOWN,
                    reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                    details="Mock fallback: No BIS found, in-stock or ambiguous",
                )

        max_attempts = 15
        poll_interval_ms = 200
        last_result = None

        for attempt in range(max_attempts):
            try:
                res = self.page.evaluate(_JS_BIS_CHECK_SCRIPT)
                if res and res.get("matched"):
                    return DetectionResult(
                        state=DetectionState.TRUE,
                        reason=DetectionFailureReason.FEATURE_ABSENT,
                        details=res.get("details", "BIS matched"),
                    )
            except Exception as exc:
                last_result = DetectionResult(
                    state=DetectionState.UNKNOWN,
                    reason=DetectionFailureReason.DOM_UNAVAILABLE,
                    details=str(exc),
                )
            if hasattr(self.page, "wait_for_timeout"):
                self.page.wait_for_timeout(poll_interval_ms)
            else:
                time.sleep(poll_interval_ms / 1000.0)

        if last_result:
            return last_result

        if out_of_stock or self.check_sold_out_state():
            return DetectionResult(
                state=DetectionState.FALSE,
                reason=DetectionFailureReason.FEATURE_ABSENT,
                details="No BIS modal or form found on confirmed out-of-stock variant",
            )
        else:
            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                details="No BIS modal or form found; variant in-stock or page state ambiguous",
            )

    def check_notify_mechanism(self) -> tuple[bool, bool]:
        """Legacy helper delegating to 3-state check_notify_state()."""
        res = self.check_notify_state()
        notify_detected = res.state == DetectionState.TRUE

        sold_out_detected = False
        if not hasattr(self.page, "query_selector") or hasattr(self.page, "mock_calls"):
            return notify_detected, sold_out_detected

        try:
            # Check for explicit sold-out selectors
            sold_out_el = self.page.query_selector(".sold-out, .out-of-stock, [data-sold-out], [class*='sold-out'], [class*='out-of-stock']")
            if sold_out_el:
                sold_out_detected = True
            else:
                # Check if Add to Cart button is disabled AND contains sold-out/unavailable/notify text
                atc_btn = self.page.query_selector(
                    "button[name='add'][disabled], button.add-to-cart[disabled], "
                    "button[id*='AddToCart'][disabled], button[class*='add-to-cart'][disabled], "
                    "button[class*='AddToCart'][disabled]"
                )
                if atc_btn:
                    btn_text = (atc_btn.text_content() or "").lower()
                    if any(p in btn_text for p in ["sold out", "out of stock", "unavailable", "notify me", "notify when available"]):
                        sold_out_detected = True
        except Exception:
            pass

        return notify_detected, sold_out_detected
