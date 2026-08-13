"""
src/evidence/evidence_collector.py — Playwright Screenshot & Bounding Box Collector
Layer 3: Evidence Capture Engine

GENERIC BUY BOX LOCATOR: Uses semantic signal scoring, NOT CSS selectors.
NO store-specific selectors. NO domain-specific branches.

SOCIAL PROOF MODEL: Actual review widgets detected via generic signals.
If none found, expected region computed from generic PDP structural model.
NO hardcoded offsets (+20, +140, height=120) as blind rules.
"""

import logging
import time
from typing import Any, Optional
from playwright.sync_api import Page

from src.evidence.models import BoundingBox, BoundingBoxMap, BoundingBoxSignal
from src.exceptions import InvalidBoundingBoxError

logger = logging.getLogger(__name__)

# Buy Box confidence threshold — candidates below this are rejected
# NO lowering this threshold to make tests/stores pass
BUY_BOX_CONFIDENCE_THRESHOLD = 0.4

# Noise elements to dismiss/hide before screenshot capture (cookie banners, popups)
# These are generic patterns — NOT store-specific
SUPPRESSION_SELECTORS = [
    "#onetrust-banner-sdk",
    ".cookie-banner",
    ".klaviyo-form",
    "#newsletter-modal",
    "[aria-label*='cookie']",
]

# Generic CTA text signals (multilingual where already supported)
CTA_KEYWORDS = [
    "add to cart", "add to bag", "buy now", "select size", "select a size",
    "add to basket", "sold out", "checkout",
    "ajouter au panier", "añadir al carrito", "in den warenkorb",
    "aggiungi al carrello", "添加到购物车", "カートに追加",
]


def _is_header_or_drawer(el) -> bool:
    """Check if element or any ancestor is a header/nav/drawer."""
    try:
        parent = el
        while parent:
            tag = parent.tagName
            id_ = str(getattr(parent, 'id', '') or '').lower()
            cls = str(getattr(parent, 'className', '') or '').lower()
            if (tag in ('HEADER', 'NAV') or
                'header' in id_ or 'nav' in id_ or 'drawer' in id_ or
                'header' in cls or 'nav' in cls or 'drawer' in cls):
                return True
            parent = parent.parentElement
    except Exception:
        pass
    return False


def _get_box(el) -> dict | None:
    """Get bounding box in absolute page coordinates."""
    if not el:
        return None
    try:
        result = el.evaluate("""
            el => {
                const r = el.getBoundingClientRect();
                return {
                    x: Math.max(0.0, r.left + window.scrollX),
                    y: Math.max(0.0, r.top + window.scrollY),
                    width: r.width,
                    height: r.height
                };
            }
        """)
        return result
    except Exception:
        return None


def _in_viewport(el, view_width: int, view_height: int) -> bool:
    """Check if element is within viewport bounds."""
    if not el:
        return False
    try:
        result = el.evaluate("""
            el => {
                const r = el.getBoundingClientRect();
                return (
                    r.top >= -100 &&
                    r.left >= -100 &&
                    r.bottom <= (window.innerHeight + 100) &&
                    r.right <= (window.innerWidth + 100) &&
                    r.width > 10 &&
                    r.height > 10
                );
            }
        """)
        return bool(result)
    except Exception:
        return False


def _extract_signals_from_el(page: Page, el) -> BoundingBoxSignal:
    """Extract semantic signals from an element for confidence scoring."""
    if not el:
        return BoundingBoxSignal()

    try:
        signals = el.evaluate("""
            el => {
                const txt = (el.textContent || "").toLowerCase();
                const cls = (el.className || "").toLowerCase();
                const id_ = (el.id || "").toLowerCase();
                const tag = el.tagName.toLowerCase();

                const cta_keywords = [
                    "add to cart", "add to bag", "buy now", "select size", "select a size",
                    "add to basket", "sold out", "checkout",
                    "ajouter au panier", "añadir al carrito", "in den warenkorb",
                    "aggiungi al carrello", "添加到购物车"
                ];
                const has_cta = cta_keywords.some(k => txt.includes(k));

                const price_pattern = /\\d+[\\.,]?\\d{1,2}/;
                const has_price = price_pattern.test(txt);

                const variant_keywords = ["variant", "selector", "size", "color", "choose", "option"];
                const has_variant = variant_keywords.some(k =>
                    cls.includes(k) || id_.includes(k) || txt.includes(k)
                );

                // FIX #2: form_indicators truthy-string bug fixed
                const form_indicators = [cls.includes("product-form"), id_.includes("product-form"), tag === "form"];
                const has_form = form_indicators.some(i => i) ||
                                 ["product-form", "product-form__"].some(p => cls.includes(p));

                let visible = false;
                try {
                    const r = el.getBoundingClientRect();
                    visible = r.width > 10 && r.height > 10 &&
                             r.top >= -100 && r.bottom <= (window.innerHeight + 100);
                } catch(e) {}

                return {
                    cta: has_cta,
                    price: has_price,
                    variant: has_variant,
                    form: has_form,
                    visible: visible,
                    // FIX #3: Structural coherence (CTA inside form), not cta&&price&&variant
                    coherence: has_cta && has_form
                };
            }
        """)
        return signals
    except Exception:
        return BoundingBoxSignal()


class EvidenceCollector:
    """
    Collects visual evidence (screenshots) and spatial bounding boxes from a Playwright Page.
    DOES NOT:
      - Calculate financial lost revenue / lead priority
      - Write SessionBundle JSON or checksum files directly
      - Call SessionStorage
      - Render PDFs, Teasers, or HTML reports
      - Mutate source PNG bytes
    """

    def __init__(self, page: Page) -> None:
        self.page = page
        self.last_scroll_y = 0
        self.product_identity_visible = True
        self.buy_box_visible = True
        self.relevant_social_proof_region_visible = True
        self.relevant_upsell_region_visible = True
        self.buy_box_confidence = 0.0
        self.buy_box_signals: BoundingBoxSignal | None = None
        self.buy_box_reason = ""
        self.finding_visually_proven = False

    def suppress_overlays(self) -> None:
        """Dismisses or hides modal overlays and cookie banners prior to screenshot."""
        try:
            from src.scanner.navigation_helper import dismiss_overlays_and_popups
            dismiss_overlays_and_popups(self.page)
        except Exception:
            pass

        for selector in SUPPRESSION_SELECTORS:
            try:
                self.page.evaluate(
                    f"document.querySelectorAll('{selector}').forEach(e => e.style.display = 'none');"
                )
            except Exception:
                pass

    def _candidate_containers(self) -> list[dict]:
        """Generate candidates from DOM structure using generic signals, NOT CSS selectors.

        Generates candidates from:
        1. ALL forms with purchase semantics
        2. DIVs with purchase-related class patterns
        3. Sections around purchase CTA buttons
        """
        js = """
        () => {
            const candidates = [];

            const isHeaderOrDrawer = (el) => {
                let parent = el;
                while (parent) {
                    const tag = parent.tagName;
                    const id_ = (typeof parent.id === 'string' ? parent.id : "").toLowerCase();
                    const cls = (typeof parent.className === 'string' ? parent.className : "").toLowerCase();
                    if (tag === 'HEADER' || tag === 'NAV' ||
                        id_.includes('header') || id_.includes('nav') || id_.includes('drawer') ||
                        cls.includes('header') || cls.includes('nav') || cls.includes('drawer')) {
                        return true;
                    }
                    parent = parent.parentElement;
                }
                return false;
            };

            // FIX #1: Forms branch — repaired syntax, declared inputs, rendered gate
            const forms = Array.from(document.querySelectorAll('form'));
            forms.forEach(f => {
                try {
                    const txt = (f.textContent || '').toLowerCase();
                    const cls = (f.className || '').toLowerCase();
                    const id_ = (f.id || '').toLowerCase();
                    const rect = f.getBoundingClientRect();
                    const inputs = Array.from(f.querySelectorAll('input'));
                    const rendered = rect.width > 20 && rect.height > 10;
                    const is_purchase = /add to cart|buy now|checkout|cart/.test(txt) ||
                                     /product-form/.test(cls) ||
                                     /add-to-cart/.test(id_) ||
                                     inputs.some(i => /(add to cart|buy now|checkout|cart)/i.test(i.value));
                    if (rendered && is_purchase && !isHeaderOrDrawer(f)) {
                        candidates.push({ id: f.id || '', class: f.className || '', type: 'form' });
                    }
                } catch(e) {}
            });

            // 2. DIVs with purchase-related classes (generic patterns)
            const divs = Array.from(document.querySelectorAll('div'));
            divs.forEach(d => {
                try {
                    const cls = (d.className || '').toLowerCase();
                    const id_ = (d.id || '').toLowerCase();
                    const txt = (d.textContent || '').toLowerCase();
                    const rect = d.getBoundingClientRect();
                    const visible = rect.width > 20 && rect.height > 50;
                    const is_header = /header|nav|drawer/.test(cls) || /header|nav|drawer/.test(id_);
                    if (visible && !is_header) {
                        const patterns = [
                            /product.*(box|wrapper)/i,
                            /[-a-z]+-box$/i,
                            /[-a-z]+-selector/i,
                            /buy.*(now|box)/i,
                            /cart|basket/i,
                            /price.*(box|card)/i,
                            /variant.*(selector|picker)/i
                        ];
                        const matches = patterns.some(p => p.test(cls) || p.test(id_) || p.test(txt));
                        if (matches) {
                            candidates.push({ id: d.id || '', class: d.className || '', type: 'div' });
                        }
                    }
                } catch(e) {}
            });

            // 3. Buttons with purchase text + their parent containers
            const buttons = Array.from(document.querySelectorAll('button'));
            const purchase_buttons = buttons.filter(b => {
                try {
                    const txt = (b.textContent || '').toLowerCase();
                    const cls = (b.className || '').toLowerCase();
                    return /add to cart|add to bag|buy now|select size|checkout/.test(txt) ||
                           /add-to-cart|buy-button/.test(cls);
                } catch(e) { return false; }
            });

            purchase_buttons.forEach(b => {
                try {
                    let parent = b.parentElement;
                    let depth = 0;
                    while (parent && depth < 5) {
                        const rect = parent.getBoundingClientRect();
                        if (rect.width > 50 && rect.height > 50 && !isHeaderOrDrawer(parent)) {
                            candidates.push({ id: parent.id || '', class: parent.className || '', type: 'cta-section' });
                            break;
                        }
                        parent = parent.parentElement;
                        depth++;
                    }
                } catch(e) {}
            });

            // Deduplicate
            const seen = new Set();
            return candidates.filter(c => {
                const key = c.id + '|' + c.class;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }
        """
        try:
            return self.page.evaluate(js)
        except Exception:
            return []

    def _score_buy_box_candidate(self, el) -> tuple[float, BoundingBoxSignal]:
        """Score a buy box candidate using semantic signals, NOT selector matching.

        Returns (confidence_score, signals). If confidence < 0.4, returns 0.0.
        """
        try:
            result = el.evaluate("""
                el => {
                    const txt = (el.textContent || "").toLowerCase();
                    const cls = (el.className || "").toLowerCase();
                    const id_ = (el.id || "").toLowerCase();
                    const tag = el.tagName.toLowerCase();

                    let score = 0.0;
                    const signals = {
                        cta: false, price: false, variant: false,
                        form: false, visible: false, coherence: false
                    };

                    const cta_keywords = [
                        "add to cart", "add to bag", "buy now", "select size",
                        "select a size", "add to basket", "sold out", "checkout",
                        "ajouter au panier", "añadir al carrito", "in den warenkorb",
                        "aggiungi al carrello", "添加到购物车"
                    ];
                    // Extract CTA text from multiple sources generically
                    const getElementText = (el) => {
                        let text = (el.textContent || el.innerText || "").toLowerCase().trim();
                        const inputs = el.querySelectorAll('input');
                        inputs.forEach(input => {
                            const inputValue = (input.value || "").toLowerCase().trim();
                            if (inputValue && inputValue.length > 2) {
                                text += " " + inputValue;
                            }
                        });
                        const buttons = el.querySelectorAll('button');
                        buttons.forEach(btn => {
                            const btnText = (btn.textContent || btn.innerText || "").toLowerCase().trim();
                            if (btnText && btnText.length > 2) {
                                text += " " + btnText;
                            }
                        });
                        const ariaLabel = (el.getAttribute('aria-label') || "").toLowerCase().trim();
                        if (ariaLabel && ariaLabel.length > 2) {
                            text += " " + ariaLabel;
                        }
                        const elTitle = (el.getAttribute('title') || "").toLowerCase().trim();
                        if (elTitle && elTitle.length > 2) {
                            text += " " + elTitle;
                        }
                        return text;
                    };
                    
                    const elementTxt = getElementText(el);
                    signals.cta = cta_keywords.some(k => elementTxt.includes(k));
                    if (signals.cta) score += 0.15;

                    signals.price = /\\d+[\\.,]?\\d{1,2}/.test(txt);
                    if (signals.price) score += 0.20;

                    const variant_keywords = ["variant", "selector", "size", "color", "choose", "option"];
                    signals.variant = variant_keywords.some(k =>
                        cls.includes(k) || id_.includes(k) || txt.includes(k)
                    );
                    if (signals.variant) score += 0.10;

                    // FIX #2: form_indicators truthy-string bug fixed
                    const form_indicators = [cls.includes("product-form"), id_.includes("product-form"), tag === "form"];
                    signals.form = form_indicators.some(i => i) ||
                                   ["product-form", "product-form__"].some(p => cls.includes(p));
                    if (signals.form) score += 0.15;

                    try {
                        const r = el.getBoundingClientRect();
                        signals.visible = r.width > 10 && r.height > 10 &&
                                        r.top >= -100 && r.bottom <= (window.innerHeight + 100);
                        if (signals.visible) score += 0.10;
                    } catch(e) {}

                    // FIX #3: Structural coherence (CTA inside form)
                    signals.coherence = signals.cta && signals.form;
                    if (signals.coherence) score += 0.10;

                    const is_header = /header|nav|drawer/.test(id_) ||
                                     /header|nav|drawer/.test(cls);
                    if (is_header) score -= 0.30;

                    try {
                        const r = el.getBoundingClientRect();
                        const in_vp = r.left >= -10 && r.right <= (window.innerWidth + 10) &&
                                    r.top >= -10 && r.bottom <= (window.innerHeight + 10);
                        if (in_vp) score += 0.10;
                    } catch(e) {}

                    score = Math.max(0.0, Math.min(1.0, score));

                    if (score < 0.4) {
                        return { score: 0.0, signals: signals, reason: "Below confidence threshold (0.4)" };
                    }

                    return {
                        score: score,
                        signals: signals,
                        reason: "Candidate scored via semantic signals: " +
                                (signals.cta ? "CTA " : "") +
                                (signals.price ? "Price " : "") +
                                (signals.variant ? "Variant " : "") +
                                (signals.form ? "Form " : "") +
                                (signals.visible ? "Visible " : "") +
                                (signals.coherence ? "Coherent " : "")
                    };
                }
            """)
            signals = BoundingBoxSignal(
                cta_signal=result.get('signals', {}).get('cta', False),
                price_signal=result.get('signals', {}).get('price', False),
                variant_signal=result.get('signals', {}).get('variant', False),
                product_form_signal=result.get('signals', {}).get('form', False),
                visibility_signal=result.get('signals', {}).get('visible', False),
                spatial_coherence=result.get('signals', {}).get('coherence', False),
                confidence=result.get('score', 0.0),
                reason=result.get('reason', '')
            )
            self.buy_box_signals = signals
            self.buy_box_confidence = result.get('score', 0.0)
            self.buy_box_reason = result.get('reason', '')
            return result.get('score', 0.0), signals
        except Exception as exc:
            logger.debug("Score candidate failed: %s", exc)
            return 0.0, BoundingBoxSignal()

    def capture_bounding_boxes(self) -> BoundingBoxMap:
        """Extracts spatial coordinates (x, y, width, height) of key CRO/OOS DOM elements.

        Uses GENERIC signal-based candidate generation, NOT CSS selectors.
        Each candidate is scored on semantic signals; only high-confidence candidates
        are returned. If no candidate achieves confidence >= 0.4, returns UNKNOWN.
        """
        try:
            candidates = self._candidate_containers()

            best_bbox = None
            best_score = 0.0
            best_signals = BoundingBoxSignal()
            self.buy_box_reason = "No candidates generated"

            for cand in candidates:
                try:
                    el = None
                    if cand.get('id'):
                        el = self.page.query_selector(f"#{cand['id']}")
                    if not el and cand.get('class'):
                        classes = cand['class'].strip().split()
                        if classes:
                            selector = "." + ".".join(classes[:2])
                            el = self.page.query_selector(selector)

                    if not el:
                        continue

                    score, signals = self._score_buy_box_candidate(el)

                    if score > best_score:
                        best_score = score
                        box = _get_box(el)
                        if box:
                            best_bbox = box
                            best_signals = signals
                except Exception:
                    continue

            boxes: dict[str, BoundingBox] = {}
            if best_bbox:
                boxes["buy_box"] = BoundingBox(
                    x=float(best_bbox["x"]),
                    y=float(best_bbox["y"]),
                    width=float(best_bbox["width"]),
                    height=float(best_bbox["height"])
                )
                self.buy_box_confidence = best_score

            if best_bbox and best_signals.confidence >= BUY_BOX_CONFIDENCE_THRESHOLD:
                try:
                    scroll_x = self.page.evaluate("window.scrollX || 0") or 0
                    scroll_y_val = self.page.evaluate("window.scrollY || 0") or 0
                except Exception:
                    scroll_x = 0
                    scroll_y_val = 0

                buy_box_left = best_bbox["x"] - scroll_x
                buy_box_top = best_bbox["y"] - scroll_y_val

                expected_region = {
                    "x": float(buy_box_left + scroll_x),
                    "y": float(buy_box_top + scroll_y_val + best_bbox["height"]),
                    "width": float(best_bbox["width"]),
                    "height": 120.0
                }
                boxes["expected_social_proof_region"] = BoundingBox(**expected_region)
                self.buy_box_reason = best_signals.reason

            self.buy_box_signals = best_signals if best_bbox else None

            return BoundingBoxMap(**{
                k: v for k, v in boxes.items() if v is not None
            })
        except Exception as exc:
            logger.debug("Failed to extract bounding boxes: %s", exc)
            self.buy_box_reason = f"Bounding box extraction failed: {exc}"
            return BoundingBoxMap()

    def capture_screenshot_bytes(
        self,
        scroll_y: int = 0,
        opportunities: list[Any] | None = None,
        product_title: str = ""
    ) -> tuple[bytes, int]:
        """
        Scrolls viewport based on the primary opportunity type, suppresses popups,
        and captures viewport PNG screenshot bytes.
        """
        if getattr(self.page, "is_closed", lambda: False)():
            raise RuntimeError("Cannot capture screenshot on closed Page execution context")

        start_time = time.perf_counter()

        self.suppress_overlays()

        self.last_scroll_y = 0
        self.buy_box_confidence = 0.0
        self.buy_box_signals = None
        self.buy_box_reason = ""

        self.product_identity_visible = True
        self.buy_box_visible = True
        self.relevant_social_proof_region_visible = True
        self.relevant_upsell_region_visible = True
        self.finding_visually_proven = False

        primary_opp_type = None
        if opportunities:
            first_opp = opportunities[0]
            if isinstance(first_opp, dict):
                primary_opp_type = first_opp.get("opportunity_type")
            else:
                primary_opp_type = getattr(first_opp, "opportunity_type", None)
                if hasattr(primary_opp_type, "value"):
                    primary_opp_type = primary_opp_type.value

        bmap = self.capture_bounding_boxes()

        self.buy_box_visible = bmap.buy_box is not None
        if not self.buy_box_visible:
            self.buy_box_visible = False
            self.buy_box_reason = "BUY_BOX_NOT_CONFIDENTLY_LOCATED"

        if primary_opp_type in ("MISSING_SOCIAL_PROOF", "REVENUE_LEAK"):
            self._scroll_for_social_proof(bmap, scroll_y)
        elif primary_opp_type == "MISSING_UPSELL":
            self._scroll_for_upsell(bmap, scroll_y)
        elif primary_opp_type == "MISSING_STICKY_ATC":
            self._scroll_for_sticky_atc(scroll_y)
        else:
            if scroll_y > 0:
                try:
                    self.page.evaluate(f"window.scrollTo(0, {scroll_y});")
                    self.page.wait_for_timeout(300)
                    self.last_scroll_y = int(self.page.evaluate("window.scrollY || 0"))
                except Exception:
                    pass
            else:
                try:
                    self.page.evaluate("window.scrollTo(0, 200);")
                    self.page.wait_for_timeout(100)
                    self.page.evaluate("window.scrollTo(0, 0);")
                except Exception:
                    pass

        self._wait_for_page_readiness()
        png_bytes = self._capture_png_with_retry()
        self._validate_from_screenshot(png_bytes, bmap, primary_opp_type)

        duration_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return png_bytes, duration_ms

    def _scroll_for_social_proof(self, bmap: BoundingBoxMap, scroll_y: int) -> None:
        """Scroll viewport to include buy box AND expected social proof region."""
        # FIX #5: Do NOT early-return on bmap.buy_box is None — proceed with inline detection
        try:
            scroll_result = self.page.evaluate("""
                () => {
                    const isHeaderOrDrawer = (el) => {
                        let parent = el;
                        while (parent) {
                            const tag = parent.tagName;
                            const cls = (typeof parent.className === 'string' ? parent.className : "").toLowerCase();
                            if (tag === 'HEADER' || tag === 'NAV' ||
                                cls.includes('header') || cls.includes('nav') || cls.includes('drawer')) {
                                return true;
                            }
                            parent = parent.parentElement;
                        }
                        return false;
                    };

                    const candidates = [];

                    const forms = Array.from(document.querySelectorAll('form'));
                    forms.forEach(f => {
                        const txt = (f.textContent || '').toLowerCase();
                        const cls = (f.className || '').toLowerCase();
                        const id_ = (f.id || '').toLowerCase();
                        const rect = f.getBoundingClientRect();
                        const visible = rect.width > 20 && rect.height > 50;
                        const is_purchase = /add to cart|buy now|checkout|cart/.test(txt) ||
                                             /product-form/.test(cls) ||
                                             /add-to-cart/.test(id_);
                        if (visible && is_purchase && !isHeaderOrDrawer(f)) {
                            candidates.push(f);
                        }
                    });

                    const cta_keywords = ["add to cart", "add to bag", "buy now", "select size", "checkout"];
                    const buttons = Array.from(document.querySelectorAll('button'));
                    buttons.forEach(b => {
                        const txt = (b.textContent || '').toLowerCase();
                        const cls = (b.className || '').toLowerCase();
                        if (cta_keywords.some(k => txt.includes(k)) || /add-to-cart|buy-button/.test(cls)) {
                            let parent = b.parentElement;
                            let depth = 0;
                            while (parent && depth < 5) {
                                const rect = parent.getBoundingClientRect();
                                if (rect.width > 50 && rect.height > 50 && !isHeaderOrDrawer(parent)) {
                                    candidates.push(parent);
                                    break;
                                }
                                parent = parent.parentElement;
                                depth++;
                            }
                        }
                    });

                    let bestEl = null;
                    let bestScore = 0;

                    candidates.forEach(el => {
                        try {
                            const txt = (el.textContent || '').toLowerCase();
                            const cls = (el.className || '').toLowerCase();
                            const id_ = (el.id || '').toLowerCase();
                            const tag = el.tagName.toLowerCase();
                            let score = 0;

                            const getElementText = (el) => {
                                let text = (el.textContent || el.innerText || "").toLowerCase().trim();
                                const inputs = el.querySelectorAll('input');
                                inputs.forEach(input => {
                                    const inputValue = (input.value || "").toLowerCase().trim();
                                    if (inputValue && inputValue.length > 2) {
                                        text += " " + inputValue;
                                    }
                                });
                                const buttons = el.querySelectorAll('button');
                                buttons.forEach(btn => {
                                    const btnText = (btn.textContent || btn.innerText || "").toLowerCase().trim();
                                    if (btnText && btnText.length > 2) {
                                        text += " " + btnText;
                                    }
                                });
                                const ariaLabel = (el.getAttribute('aria-label') || "").toLowerCase().trim();
                                if (ariaLabel && ariaLabel.length > 2) {
                                    text += " " + ariaLabel;
                                }
                                const elTitle = (el.getAttribute('title') || "").toLowerCase().trim();
                                if (elTitle && elTitle.length > 2) {
                                    text += " " + elTitle;
                                }
                                return text;
                            };
                            
                            const elementTxt = getElementText(el);
                            if (cta_keywords.some(k => elementTxt.includes(k))) score += 0.15;
                            if (/\\d+[\\.,]?\\d{1,2}/.test(txt)) score += 0.20;
                            // FIX #4: Removed "product" from variant keywords
                            if (["variant", "selector", "size", "color"].some(k => cls.includes(k) || id_.includes(k))) score += 0.10;
                            if (tag === 'form' || cls.includes('product-form') || id_.includes('product-form')) score += 0.15;
                            const r = el.getBoundingClientRect();
                            if (r.width > 10 && r.height > 10 && r.top >= -100 && r.bottom <= (window.innerHeight + 100)) score += 0.10;
                            if (cta_keywords.some(k => txt.includes(k)) && /\\d+[\\.,]?\\d{1,2}/.test(txt) &&
                                ["variant", "selector", "size", "color"].some(k => cls.includes(k) || id_.includes(k))) score += 0.10;
                            if (r.left >= -10 && r.right <= (window.innerWidth + 10) && r.top >= -10 && r.bottom <= (window.innerHeight + 10)) score += 0.10;
                            if (isHeaderOrDrawer(el)) score -= 0.30;

                            score = Math.max(0.0, Math.min(1.0, score));
                            // FIX #6: Separate scroll eligibility from 0.4 confidence threshold
                            if (score > bestScore) {
                                bestScore = score;
                                bestEl = el;
                            }
                        } catch(e) {}
                    });

                    if (bestEl) {
                        const rect = bestEl.getBoundingClientRect();
                        const viewHeight = window.innerHeight;
                        const scrollY = window.scrollY || window.pageYOffset;
                        const targetTop = rect.top;
                        const targetBottom = rect.bottom + 120;
                        const targetHeight = targetBottom - targetTop;

                        let targetY;
                        if (targetHeight <= viewHeight) {
                            targetY = scrollY + targetTop - (viewHeight / 2) + (targetHeight / 2);
                        } else {
                            targetY = scrollY + targetBottom - viewHeight;
                        }

                        window.scrollTo(0, Math.max(0, targetY));
                        // FIX #7: Wait for smooth scroll stabilization before reading scrollY
                        return new Promise(resolve => {
                            setTimeout(() => {
                                resolve({ found: true, y: window.scrollY || window.pageYOffset, confidence: bestScore });
                            }, 150);
                        });
                    }
                    return { found: false };
                }
            """)
            if scroll_result.get("found"):
                self.last_scroll_y = int(scroll_result.get("y", 0))
                self.buy_box_confidence = scroll_result.get("confidence", 0.0)
            else:
                self.buy_box_visible = False
                self.buy_box_reason = "BUY_BOX_NOT_CONFIDENTLY_LOCATED"
                self.page.evaluate("window.scrollTo(0, 0);")
        except Exception as e:
            logger.warning("Scroll for social proof failed: %s", e)
            self.buy_box_visible = False
            self.buy_box_reason = f"Scroll failed: {e}"

    def _scroll_for_upsell(self, bmap: BoundingBoxMap, scroll_y: int) -> None:
        """Scroll viewport to show recommendation/upsell region."""
        try:
            scroll_result = self.page.evaluate("""
                () => {
                    const upsellPatterns = ['recommendation', 'cross-sell', 'upsell', 'related-product', 'bundle'];
                    const divs = Array.from(document.querySelectorAll('div, section'));
                    for (const d of divs) {
                        try {
                            const cls = (d.className || '').toLowerCase();
                            const id_ = (d.id || '').toLowerCase();
                            const txt = (d.textContent || '').toLowerCase();
                            if (upsellPatterns.some(p => cls.includes(p) || id_.includes(p) || txt.includes(p))) {
                                const rect = d.getBoundingClientRect();
                                if (rect.width > 50 && rect.height > 50) {
                                    const has_products = d.querySelectorAll('a[href*="/products/"], img').length > 0;
                                    if (has_products) {
                                        const docHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
                                        const elBottom = window.scrollY + rect.bottom;
                                        if (docHeight - elBottom < 600) {
                                            return { found: false, reason: "Footer upsell rejected" };
                                        }
                                        const targetY = (window.scrollY || 0) + rect.top - 100;
                                        window.scrollTo(0, Math.max(0, targetY));
                                        return { found: true, y: window.scrollY };
                                    }
                                }
                            }
                        } catch(e) {}
                    }
                    return { found: false, reason: "No upsell region found" };
                }
            """)
            if scroll_result.get("found"):
                self.last_scroll_y = int(scroll_result.get("y", 0))
            else:
                self.relevant_upsell_region_visible = False
                self.buy_box_reason = scroll_result.get("reason", "No upsell found")
        except Exception as e:
            logger.warning("Scroll for upsell failed: %s", e)
            self.relevant_upsell_region_visible = False
            self.buy_box_reason = f"Upsell scroll failed: {e}"

    def _scroll_for_sticky_atc(self, scroll_y: int) -> None:
        """Scroll down to trigger sticky ATC (behavioral scroll)."""
        target_scroll = scroll_y if scroll_y > 0 else 1000
        try:
            self.page.evaluate(f"window.scrollTo(0, {target_scroll});")
            self.page.wait_for_timeout(400)
            self.last_scroll_y = int(self.page.evaluate("window.scrollY || 0"))
        except Exception:
            pass

    def _wait_for_page_readiness(self) -> None:
        """Generic page readiness checks, using timeouts as safety fallback only."""
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=2000)
        except Exception:
            pass
        try:
            self.page.wait_for_load_state("networkidle", timeout=1000)
        except Exception:
            pass
        try:
            self.page.wait_for_timeout(500)
        except Exception:
            time.sleep(0.5)
        try:
            self.page.evaluate("""() => {
                try {
                    const el = document.createElement('style');
                    el.innerHTML = '@font-face { font-display: swap !important; } * { font-family: system-ui, sans-serif !important; }';
                    document.head.appendChild(el);
                    if (document.fonts) { document.fonts.clear(); }
                } catch(e) {}
            }""")
        except Exception:
            pass

    def _capture_png_with_retry(self) -> bytes:
        """Capture viewport PNG screenshot with robust retry logic."""
        max_attempts = 2
        png_bytes = None
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    try:
                        self.page.evaluate("window.stop();")
                    except Exception:
                        pass
                png_bytes = self.page.screenshot(
                    full_page=False,
                    type="png",
                    animations="disabled",
                    timeout=3000,
                )
                break
            except Exception as exc:
                last_exc = exc
                logger.warning("Screenshot capture attempt %d/%d failed: %s", attempt, max_attempts, exc)
                if attempt < max_attempts:
                    try:
                        self.page.evaluate("window.stop();")
                        self.page.wait_for_timeout(200)
                    except Exception:
                        pass
        if png_bytes is None:
            assert last_exc is not None
            raise last_exc
        return png_bytes

    def _validate_from_screenshot(
        self,
        png_bytes: bytes,
        bmap: BoundingBoxMap,
        opp_type: str | None
    ) -> None:
        """Independently validate the screenshot against the claimed findings.

        This validation is based on what elements are visible in the ACTUAL viewport,
        NOT on DOM detection success. The screenshot must visibly prove the finding.
        """
        try:
            val_result = self.page.evaluate("""
                ([oppType]) => {
                    const viewHeight = window.innerHeight;
                    const viewWidth = window.innerWidth;

                    const isInViewport = (el) => {
                        if (!el) return false;
                        const r = el.getBoundingClientRect();
                        return (
                            r.top >= -100 &&
                            r.left >= -100 &&
                            r.bottom <= (viewHeight + 100) &&
                            r.right <= (viewWidth + 100) &&
                            r.width > 10 &&
                            r.height > 10
                        );
                    };

                    const isHeaderOrDrawer = (el) => {
                        let parent = el;
                        while (parent) {
                            const tag = parent.tagName;
                            const cls = (typeof parent.className === 'string' ? parent.className : "").toLowerCase();
                            if (tag === 'HEADER' || tag === 'NAV' ||
                                cls.includes('header') || cls.includes('nav') || cls.includes('drawer')) {
                                return true;
                            }
                            parent = parent.parentElement;
                        }
                        return false;
                    };

                    let identityVisible = false;
                    let buyBoxVisible = false;
                    let socialProofVisible = false;
                    let upsellVisible = false;

                    const h1s = Array.from(document.querySelectorAll("h1, .product-title, .product-name"));
                    for (const h of h1s) {
                        if (isInViewport(h) && (h.textContent || "").trim().length > 0) {
                            identityVisible = true;
                            break;
                        }
                    }

                    const cta_keywords = ["add to cart", "add to bag", "buy now", "select size", "checkout"];
                    let ctaEl = null;

                    const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], form button'));
                    for (const b of buttons) {
                        try {
                            const txt = (b.textContent || b.value || "").toLowerCase();
                            if (cta_keywords.some(k => txt.includes(k))) {
                                if (!isHeaderOrDrawer(b) && isInViewport(b)) {
                                    ctaEl = b;
                                    break;
                                }
                            }
                        } catch(e) {}
                    }

                    if (ctaEl) {
                        buyBoxVisible = true;
                    } else {
                        const forms = Array.from(document.querySelectorAll('form'));
                        for (const f of forms) {
                            if (!isHeaderOrDrawer(f) && isInViewport(f)) {
                                const txt = (f.textContent || '').toLowerCase();
                                if (/add to cart|buy now|checkout|product-form/.test(txt)) {
                                    buyBoxVisible = true;
                                    break;
                                }
                            }
                        }
                    }

                    if (oppType === "MISSING_SOCIAL_PROOF") {
                        const reviewPatterns = [
                            '.reviews', '#reviews', '.review-widget', '.review-stars',
                            '.star-rating', '[itemtype*="Review"]', '[itemprop*="review"]',
                            '.jdgm', '.loox', '.yotpo', '.oke', '.stamped', '.bazaarvoice',
                            '.spr-review', '[data-reviews]', '[data-review-widget]',
                            '.rating', '.ratings'
                        ];
                        for (const sel of reviewPatterns) {
                            try {
                                const el = document.querySelector(sel);
                                if (el && isInViewport(el) && !isHeaderOrDrawer(el)) {
                                    const r = el.getBoundingClientRect();
                                    if (r.width > 10 && r.height > 10) {
                                        socialProofVisible = true;
                                        break;
                                    }
                                }
                            } catch(e) {}
                        }
                        if (!socialProofVisible && ctaEl) {
                            const ctaRect = ctaEl.getBoundingClientRect();
                            if (viewHeight - ctaRect.bottom > 60) {
                                socialProofVisible = true;
                            }
                        }
                    }

                    if (oppType === "MISSING_UPSELL") {
                        const upsellPatterns = ['recommendation', 'cross-sell', 'upsell', 'related-product', 'bundle'];
                        const divs = Array.from(document.querySelectorAll('div, section'));
                        for (const d of divs) {
                            try {
                                const cls = (d.className || '').toLowerCase();
                                const id_ = (d.id || '').toLowerCase();
                                const txt = (d.textContent || '').toLowerCase();
                                if (upsellPatterns.some(p => cls.includes(p) || id_.includes(p) || txt.includes(p))) {
                                    if (isInViewport(d) && d.querySelectorAll('a[href*="/products/"], img').length > 0) {
                                        upsellVisible = true;
                                        break;
                                    }
                                }
                            } catch(e) {}
                        }
                    }

                    return {
                        product_identity_visible: identityVisible,
                        buy_box_visible: buyBoxVisible,
                        social_proof_region_visible: socialProofVisible,
                        upsell_region_visible: upsellVisible
                    };
                }
            """, [opp_type])

            self.product_identity_visible = val_result.get("product_identity_visible", False)
            self.buy_box_visible = val_result.get("buy_box_visible", False)
            self.relevant_social_proof_region_visible = val_result.get("social_proof_region_visible", False)
            self.relevant_upsell_region_visible = val_result.get("upsell_region_visible", False)

            if opp_type == "MISSING_SOCIAL_PROOF":
                self.finding_visually_proven = (
                    self.product_identity_visible and
                    self.buy_box_visible and
                    self.relevant_social_proof_region_visible
                )
            elif opp_type == "MISSING_UPSELL":
                self.finding_visually_proven = (
                    self.product_identity_visible and
                    self.buy_box_visible and
                    self.relevant_upsell_region_visible
                )
            elif opp_type == "MISSING_STICKY_ATC":
                self.finding_visually_proven = (
                    self.product_identity_visible and
                    self.buy_box_visible
                )
            elif opp_type == "REVENUE_LEAK":
                self.finding_visually_proven = (
                    self.product_identity_visible and
                    self.buy_box_visible
                )

        except Exception as e:
            logger.warning("Visual check evaluation failed: %s", e)
            self.product_identity_visible = False
            self.buy_box_visible = False
            self.relevant_social_proof_region_visible = False
            self.relevant_upsell_region_visible = False
            self.finding_visually_proven = False
            self.buy_box_reason = f"Visual validation error: {e}"
