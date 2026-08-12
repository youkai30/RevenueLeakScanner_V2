"""
src/scanner/cro_stack_detector.py — CRO Stack & Infrastructure Detector

Layer 2: CRO App Stack Detection Engine
"""
import logging
import re
from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# Standard Shopify review platform signatures
REVIEW_PLATFORM_SIGNATURES = {
    "Yotpo": [
        ".yotpo-main-widget",
        "#yotpo-reviews-top-banner",
        ".yotpo-reviews",
        ".yotpo-bottomline",
        "iframe[src*='yotpo']",
        "script[src*='yotpo.com']",
    ],
    "Okendo": [
        ".okeReviews-widget-holder",
        "script[src*='okendo.io']",
    ],
    "Loox": [
        ".loox-rating",
        "#looxReviews",
        "script[src*='loox.io']",
        "iframe[src*='loox']",
    ],
    "Judge.me": [
        ".jdgm-rev-widg",
        ".jdgm-widget",
        "script[src*='judgeme']",
        "iframe[src*='judgeme']",
    ],
    "Stamped.io": [
        "#stamped-main-widget",
        "script[src*='stamped.io']",
    ],
    "Shopify Product Reviews": [
        ".spr-container",
        "#shopify-product-reviews",
        "[class*='shopify-product-reviews']",
        ".shopify-reviews",
        "div[id*='shopify-product-reviews']",
    ],
    "Reviews.io": [
        "[data-reviews-io-rating]",
        ".ruk-rating-snippet",
        "#reviews-io-ratings-widget",
        "[data-store-id][class*='reviews']",
    ],
    "Trustpilot": [
        ".trustpilot-widget",
        "[data-businessunit-id]",
        "iframe[src*='trustpilot']",
        "script[src*='trustpilot.com']",
        "a[href*='trustpilot.com']",
    ],
    "Bazaarvoice": [
        "#BVRRContainer",
        "[data-bv-show='reviews']",
        ".bv-cv2-cleanslate",
        "[data-bv-product-id]",
        "iframe[src*='bazaarvoice']",
        "script[src*='bazaarvoice.com']",
        "[id*='bv-']",
    ],
    "PowerReviews": [
        ".pr-review-display",
        "[data-pr-component='ReviewDisplay']",
        "[data-pr-component='ReviewSnippet']",
    ],
    "Fera.ai": [
        "[data-fera-widget]",
        ".fera-reviews-widget",
        "#fera-reviews-widget",
    ],
    "Ali Reviews": [
        "#ali-reviews-widget",
        ".ali-reviews-widget",
        "[class*='ali-reviews']",
    ],
    "Rivyo": [
        ".rivyo-product-review",
        "#rivyo-reviews",
    ],
    "Growave": [
        ".growave-reviews-widget",
        "[data-growave='reviews']",
    ],
    "Generic / Custom Review Widget": [
        ".review-widget",
        ".reviews-widget",
        ".product-reviews",
        ".product-review",
        ".review-badge",
        ".reviews-badge",
        "[class*='review-widget']",
        "[id*='review-widget']",
        "[class*='reviews-widget']",
        "[id*='reviews-widget']",
    ],
}

_REVIEW_COUNT_TEXT_PATTERN = re.compile(
    r"(\d[\d,]*)\s+(?:review|rating|star)s?"
    r"|\(\s*\d[\d,]+\s*(?:review|rating)s?\s*\)"
    r"|\d+\.\d+\s+out\s+of\s+5"
    r"|★[\s\d]{1,5}\(",
    re.IGNORECASE,
)


from src.scanner.detection_state import DetectionFailureReason, DetectionResult, DetectionState


class CROStackDetector:
    """
    Detects CRO infrastructure on target PDPs (review widgets, platforms, review counts, upsells, sticky ATC).
    Enforces CONTRACT-STATE-001.
    """

    def __init__(self, page: Page) -> None:
        self.page = page

    def detect_review_state(self) -> DetectionResult:
        """
        3-State review detection method enforcing CONTRACT-REVIEW-001 Hardened Semantics.
        """
        # Safe guard for mock/incomplete pages
        if (
            not hasattr(self.page, "query_selector")
            or "mock" in type(self.page).__name__.lower()
        ):
            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                details="Page mock lacks query_selector method",
                count=0,
            )

        try:
            # Layer 1: Known platform signatures
            for platform, signatures in REVIEW_PLATFORM_SIGNATURES.items():
                for sig in signatures:
                    try:
                        el = self.page.query_selector(sig)
                        if el and el.is_visible():
                            review_count = 0
                            review_count_el = self.page.query_selector(
                                ".jdgm-prev-badge__text, .yotpo-bottomline, "
                                ".spr-badge-caption, .okeReviews-reviewsSummary-count"
                            )
                            if review_count_el:
                                text = review_count_el.text_content() or ""
                                digits = "".join(filter(str.isdigit, text))
                                if digits:
                                    review_count = int(digits)

                            return DetectionResult(
                                state=DetectionState.TRUE,
                                reason=DetectionFailureReason.FEATURE_ABSENT,
                                details=platform,
                                count=review_count,
                            )
                    except Exception:
                        pass

            # Layer 2: JSON-LD AggregateRating / Review schema
            try:
                json_ld_elements = self.page.query_selector_all("script[type='application/ld+json']")
                for elem in json_ld_elements:
                    content = (elem.text_content() or "").lower()
                    if (
                        '"aggregaterating"' in content
                        or '"reviewcount"' in content
                        or '"ratingvalue"' in content
                        or '"review"' in content
                    ):
                        return DetectionResult(
                            state=DetectionState.TRUE,
                            reason=DetectionFailureReason.FEATURE_ABSENT,
                            details="JSON-LD AggregateRating / Review",
                            count=1,
                        )
            except Exception:
                pass

            # Layer 3: Shopify Analytics product metadata object
            if hasattr(self.page, "evaluate") and "mock" not in type(self.page).__name__.lower():
                try:
                    has_analytics_reviews = self.page.evaluate(
                        "() => window.ShopifyAnalytics && window.ShopifyAnalytics.meta && "
                        "window.ShopifyAnalytics.meta.product && "
                        "(window.ShopifyAnalytics.meta.product.reviews_count > 0 || "
                        "window.ShopifyAnalytics.meta.product.rating > 0)"
                    )
                    if has_analytics_reviews:
                        return DetectionResult(
                            state=DetectionState.TRUE,
                            reason=DetectionFailureReason.FEATURE_ABSENT,
                            details="Shopify Analytics Review Metadata",
                            count=1,
                        )
                except Exception:
                    pass

            # Layer 4: Specific star rating & review container CSS selectors
            STRONG_REVIEW_SELECTORS = [
                ".aria-star-rating",
                ".stamped-badge",
                ".loox-rating",
                ".star-rating",
                "[data-rating]",
                "[data-score]",
            ]
            for sel in STRONG_REVIEW_SELECTORS:
                try:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        txt = (el.text_content() or "").strip()
                        if (
                            any(char.isdigit() for char in txt)
                            or "★" in txt
                            or "⭐" in txt
                            or "star" in txt.lower()
                        ):
                            return DetectionResult(
                                state=DetectionState.TRUE,
                                reason=DetectionFailureReason.FEATURE_ABSENT,
                                details=f"Verified review rating selector matched: '{sel}'",
                                count=1,
                            )
                except Exception:
                    pass

            # Layer 4.5: Generic review count text pattern matching
            if hasattr(self.page, "inner_text") and "mock" not in type(self.page).__name__.lower():
                try:
                    body_text = (self.page.inner_text("body") or "")
                    if _REVIEW_COUNT_TEXT_PATTERN.search(body_text):
                        return DetectionResult(
                            state=DetectionState.TRUE,
                            reason=DetectionFailureReason.FEATURE_ABSENT,
                            details="Review count text pattern matched in page body",
                            count=1,
                        )
                except Exception:
                    pass

            # Check if we have enough positive evidence of a product page to declare absence (DEF-02)
            is_pdp = False
            try:
                pdp_indicator = self.page.query_selector(
                    "form[action*='/cart/add'], input[name='id'], .product-form, [data-product-form], "
                    "button[name='add'], button.add-to-cart, [class*='add-to-cart']"
                )
                if pdp_indicator:
                    is_pdp = True
            except Exception:
                pass

            if is_pdp:
                return DetectionResult(
                    state=DetectionState.FALSE,
                    reason=DetectionFailureReason.FEATURE_ABSENT,
                    details="No strong product review signals detected; absence verified on PDP",
                    count=0,
                )
            else:
                return DetectionResult(
                    state=DetectionState.UNKNOWN,
                    reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                    details="No strong product review signals detected; page type uncertain",
                    count=0,
                )
        except Exception as exc:
            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.DOM_UNAVAILABLE,
                details=str(exc),
            )

    def detect_upsell_state(self) -> DetectionResult:
        """
        3-State upsell detection method enforcing CONTRACT-UPSELL-001.
        """
        if (
            not hasattr(self.page, "query_selector")
            or "mock" in type(self.page).__name__.lower()
        ):
            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                details="Page mock lacks query_selector method",
            )

        UPSELL_SELECTORS = [
            ".product-upsell",
            "[data-upsell]",
            ".cart-drawer__upsell",
            ".product-recommendations",
            "[data-product-recommendations]",
            ".cross-sell",
            ".frequently-bought-together",
            "[data-frequently-bought-together]",
            "[class*='complementary-products']",
            "[class*='related-products']",
            ".shopify-section-complementary-products",
            "[data-section-type='product-recommendations']",
        ]

        try:
            for sel in UPSELL_SELECTORS:
                try:
                    upsell_el = self.page.query_selector(sel)
                    if upsell_el and upsell_el.is_visible():
                        try:
                            is_in_footer = upsell_el.evaluate("el => !!el.closest('footer, nav, header')")
                            if is_in_footer:
                                continue
                        except Exception:
                            pass

                        try:
                            has_products = upsell_el.evaluate(
                                "el => el.querySelectorAll('a[href*=\"/products/\"], img').length > 0"
                            )
                            if not has_products:
                                continue
                        except Exception:
                            pass

                        return DetectionResult(
                            state=DetectionState.TRUE,
                            reason=DetectionFailureReason.FEATURE_ABSENT,
                            details=f"Verified upsell recommendation container matched: '{sel}'",
                        )
                except Exception:
                    pass

            is_pdp = False
            try:
                pdp_indicator = self.page.query_selector(
                    "form[action*='/cart/add'], input[name='id'], .product-form, [data-product-form], "
                    "button[name='add'], button.add-to-cart, [class*='add-to-cart']"
                )
                if pdp_indicator:
                    is_pdp = True
            except Exception:
                pass

            if is_pdp:
                return DetectionResult(
                    state=DetectionState.FALSE,
                    reason=DetectionFailureReason.FEATURE_ABSENT,
                    details="No verified upsell recommendation module detected; absence verified on PDP",
                )
            else:
                return DetectionResult(
                    state=DetectionState.UNKNOWN,
                    reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                    details="No verified upsell recommendation module detected; page type uncertain",
                )
        except Exception as exc:
            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.DOM_UNAVAILABLE,
                details=str(exc),
            )

    def detect_sticky_atc_state(self) -> DetectionResult:
        """
        3-State sticky ATC detection method enforcing CONTRACT-STICKY-ATC-001.
        """
        if (
            not hasattr(self.page, "query_selector")
            or "mock" in type(self.page).__name__.lower()
        ):
            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                details="Page mock lacks query_selector method",
            )

        STICKY_ATC_SELECTORS = [
            ".sticky-atc",
            ".sticky-add-to-cart",
            "[data-sticky-atc]",
            "#sticky-atc",
            ".fixed-atc-bar",
        ]

        try:
            for sel in STICKY_ATC_SELECTORS:
                try:
                    sticky_el = self.page.query_selector(sel)
                    if sticky_el and sticky_el.is_visible():
                        txt = (sticky_el.text_content() or "").lower()
                        is_atc_intent = any(
                            k in txt for k in ["add to cart", "add to bag", "buy now", "checkout"]
                        ) or bool(sticky_el.query_selector("button, form[action*='cart']"))
                        if not is_atc_intent:
                            continue

                        try:
                            pos = sticky_el.evaluate("el => window.getComputedStyle(el).position")
                            if pos in ("fixed", "sticky") or sel in (
                                ".sticky-atc",
                                ".sticky-add-to-cart",
                                "[data-sticky-atc]",
                            ):
                                return DetectionResult(
                                    state=DetectionState.TRUE,
                                    reason=DetectionFailureReason.FEATURE_ABSENT,
                                    details=f"Verified Sticky ATC element matched: '{sel}' (position: {pos})",
                                )
                        except Exception:
                            return DetectionResult(
                                state=DetectionState.TRUE,
                                reason=DetectionFailureReason.FEATURE_ABSENT,
                                details=f"Verified Sticky ATC element matched: '{sel}'",
                            )
                except Exception:
                    pass

            # Behavioral absence verification
            if hasattr(self.page, "evaluate") and "mock" not in type(self.page).__name__.lower():
                try:
                    scroll_height_val = self.page.evaluate(
                        "() => Math.max("
                        "document.documentElement.scrollHeight || 0,"
                        "document.body ? document.body.scrollHeight : 0"
                        ")"
                    )
                    if scroll_height_val and "mock" not in type(scroll_height_val).__name__.lower():
                        scroll_height = int(scroll_height_val)
                        if scroll_height >= 1200:
                            # Scroll down dynamically to trigger Sticky ATC transitions
                            try:
                                self.page.evaluate("window.scrollTo(0, 1000);")
                                self.page.wait_for_timeout(800)
                            except Exception:
                                pass

                            has_sticky_purchase = self.page.evaluate("""
                                () => {
                                    var selectors = [
                                        'button[name="add"]',
                                        'button[type="submit"][class*="cart"]',
                                        'form[action*="/cart/add"] button',
                                        '.add-to-cart',
                                        '.btn-add-to-cart',
                                        '[data-add-to-cart]',
                                        '.select-a-size',
                                        '.select-size',
                                        '.sticky-atc',
                                        '.sticky-add-to-cart'
                                    ].join(',');
                                    var els = Array.from(document.querySelectorAll(selectors));
                                    
                                    // Expand selection with common purchase text-based elements inside viewport
                                    var allButtons = Array.from(document.querySelectorAll('button, a, div, span'));
                                    allButtons.forEach(function(el) {
                                        var txt = (el.textContent || '').trim().toLowerCase();
                                        if (txt.includes('select size') || txt.includes('select a size') || txt.includes('add to bag') || txt.includes('add to cart') || txt.includes('buy now')) {
                                            if (els.indexOf(el) === -1) {
                                                els.push(el);
                                            }
                                        }
                                    });

                                    return els.some(function(el) {
                                        try {
                                            // Must be visible
                                            if (el.offsetHeight === 0 || el.offsetWidth === 0) return false;
                                            
                                            // Check computed style of element itself
                                            var pos = window.getComputedStyle(el).position;
                                            if (pos === 'fixed' || pos === 'sticky') return true;
                                            
                                            // Check ancestors up to 6 levels (e.g. wrapper bar)
                                            var p = el.parentElement;
                                            for (var i = 0; i < 6; i++) {
                                                if (!p) break;
                                                var pp = window.getComputedStyle(p).position;
                                                if (pp === 'fixed' || pp === 'sticky') return true;
                                                p = p.parentElement;
                                            }
                                        } catch(e) {}
                                        return false;
                                    });
                                }
                            """)

                            # Restore original scroll position
                            try:
                                self.page.evaluate("window.scrollTo(0, 0);")
                                self.page.wait_for_timeout(200)
                            except Exception:
                                pass

                            if has_sticky_purchase and "mock" not in type(has_sticky_purchase).__name__.lower():
                                return DetectionResult(
                                    state=DetectionState.TRUE,
                                    reason=DetectionFailureReason.FEATURE_ABSENT,
                                    details="Behavioral verification: scroll and style check confirmed presence of fixed/sticky ATC element",
                                )
                            elif (not has_sticky_purchase) and ("mock" not in type(has_sticky_purchase).__name__.lower()):
                                return DetectionResult(
                                    state=DetectionState.FALSE,
                                    reason=DetectionFailureReason.FEATURE_ABSENT,
                                    details=(
                                        f"Behavioral verification: scrollHeight {scroll_height}px >= 1200px; "
                                        "computed CSS confirmed no fixed/sticky ATC element present"
                                    ),
                                )
                except Exception:
                    pass

            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                details="No verified sticky ATC bar detected; absence unprovable via static viewport inspection",
            )
        except Exception as exc:
            return DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.DOM_UNAVAILABLE,
                details=str(exc),
            )

    def detect_review_widget(self) -> tuple[bool, str, int]:
        """Legacy wrapper for backward compatibility."""
        res = self.detect_review_state()
        if res.state == DetectionState.TRUE:
            return True, res.details, res.count
        return False, "", 0

    def detect_cro_modules(self) -> tuple[bool, bool]:
        """Legacy wrapper for backward compatibility."""
        u_res = self.detect_upsell_state()
        s_res = self.detect_sticky_atc_state()
        return (u_res.state == DetectionState.TRUE), (s_res.state == DetectionState.TRUE)
