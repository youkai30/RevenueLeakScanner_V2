"""
src/evidence/evidence_collector.py — Playwright Screenshot & Bounding Box Collector
Layer 3: Evidence Capture Engine

P2 — GENERIC BUY BOX LOCATOR (unified definitions):
- ONE JS helpers block (isHeaderOrDrawer / isInViewport / getElementText / CTA keywords).
- ONE viewport tolerance source of truth (VIEWPORT_TOLERANCE).
- Review detection: structural/schema first; platform classes are OPTIONAL adapters only.
- Diagnostics: candidates count, rejection reasons, best rejected, chosen, scroll target.
- BoundingBoxMap fully populated (cta / notify / reviews / upsell / sticky_atc).
- Occlusion check (elementFromPoint) in visual validation.
NO store-specific selectors. NO domain branches. NO threshold/weight changes.
"""
import json
import logging
import time
from typing import Any
from playwright.sync_api import Page

from src.evidence.models import BoundingBox, BoundingBoxMap, BoundingBoxSignal
from src.exceptions import InvalidBoundingBoxError

logger = logging.getLogger(__name__)

# Buy Box confidence threshold — candidates below this are rejected.
# NO lowering this threshold to make tests/stores pass.
BUY_BOX_CONFIDENCE_THRESHOLD = 0.4

# P2 — single source of truth for viewport tolerances (pixels)
VIEWPORT_TOLERANCE = 100   # "visible in viewport" checks
STRICT_TOLERANCE = 10      # reserved for "fully inside" checks

# Noise elements to dismiss/hide before screenshot capture (generic patterns)
SUPPRESSION_SELECTORS = [
    "#onetrust-banner-sdk",
    ".cookie-banner",
    ".klaviyo-form",
    "#newsletter-modal",
    "[aria-label*='cookie']",
]

# P2 — canonical CTA keywords (cleaned: no trailing spaces, mojibake fixed)
CTA_KEYWORDS = [
    "add to cart", "add to bag", "buy now", "select size", "select a size",
    "add to basket", "sold out", "checkout",
    "ajouter au panier", "añadir al carrito", "in den warenkorb",
    "aggiungi al carrello", "添加到购物车", "カートに追加",
]

# P2 — CORE structural review detection (schema-based, generic)
CORE_REVIEW_SELECTORS = [
    ".reviews", "#reviews", ".review-widget", ".review-stars",
    "[itemtype*='Review']", "[itemprop*='review']",
    "[data-reviews]", "[data-review-widget]",
]

# P2 — OPTIONAL platform adapters (never used as sole core evidence)
OPTIONAL_PLATFORM_REVIEW_ADAPTERS = [
    ".jdgm", ".loox", ".yotpo", ".oke", ".stamped", ".bazaarvoice", ".spr-review",
]

# P2 — ONE shared JS helpers block, injected inside every evaluate body.
JS_HELPERS = (
    "const VIEW_TOL = " + str(VIEWPORT_TOLERANCE) + ";\n"
    "const CTA_KEYWORDS = " + json.dumps(CTA_KEYWORDS, ensure_ascii=False) + ";\n"
    "const CORE_REVIEW_SELECTORS = " + json.dumps(CORE_REVIEW_SELECTORS) + ";\n"
    "const ADAPTER_REVIEW_SELECTORS = " + json.dumps(OPTIONAL_PLATFORM_REVIEW_ADAPTERS) + ";\n"
    "const PURCHASE_RE = /add to cart|buy now|checkout|cart/;\n"
    "const isHeaderOrDrawer = (el) => {\n"
    "    let parent = el;\n"
    "    while (parent) {\n"
    "        const tag = parent.tagName;\n"
    "        const id_ = (typeof parent.id === 'string' ? parent.id : '').toLowerCase();\n"
    "        const cls = (typeof parent.className === 'string' ? parent.className : '').toLowerCase();\n"
    "        if (tag === 'HEADER' || tag === 'NAV' ||\n"
    "            id_.includes('header') || id_.includes('nav') || id_.includes('drawer') ||\n"
    "            cls.includes('header') || cls.includes('nav') || cls.includes('drawer')) {\n"
    "            return true;\n"
    "        }\n"
    "        parent = parent.parentElement;\n"
    "    }\n"
    "    return false;\n"
    "};\n"
    "const isInViewport = (el, tol) => {\n"
    "    if (!el) return false;\n"
    "    const t = (typeof tol === 'number') ? tol : VIEW_TOL;\n"
    "    const r = el.getBoundingClientRect();\n"
    "    return (r.top >= -t && r.left >= -t &&\n"
    "            r.bottom <= (window.innerHeight + t) &&\n"
    "            r.right <= (window.innerWidth + t) &&\n"
    "            r.width > 10 && r.height > 10);\n"
    "};\n"
    "const isOccluded = (el) => {\n"
    "    if (!el) return true;\n"
    "    try {\n"
    "        const r = el.getBoundingClientRect();\n"
    "        const cx = Math.max(0, Math.min(window.innerWidth - 1, r.left + r.width / 2));\n"
    "        const cy = Math.max(0, Math.min(window.innerHeight - 1, r.top + r.height / 2));\n"
    "        const topEl = document.elementFromPoint(cx, cy);\n"
    "        if (!topEl) return true;\n"
    "        return !(el === topEl || el.contains(topEl) || topEl.contains(el));\n"
    "    } catch (e) { return false; }\n"
    "};\n"
    "const getElementText = (el) => {\n"
    "    let text = (el.textContent || el.innerText || '').toLowerCase().trim();\n"
    "    el.querySelectorAll('input').forEach(input => {\n"
    "        const v = (input.value || '').toLowerCase().trim();\n"
    "        if (v && v.length > 2) text += ' ' + v;\n"
    "    });\n"
    "    el.querySelectorAll('button').forEach(btn => {\n"
    "        const b = (btn.textContent || btn.innerText || '').toLowerCase().trim();\n"
    "        if (b && b.length > 2) text += ' ' + b;\n"
    "    });\n"
    "    const aria = (el.getAttribute('aria-label') || '').toLowerCase().trim();\n"
    "    if (aria && aria.length > 2) text += ' ' + aria;\n"
    "    const ttl = (el.getAttribute('title') || '').toLowerCase().trim();\n"
    "    if (ttl && ttl.length > 2) text += ' ' + ttl;\n"
    "    return text;\n"
    "};\n"
    "const hasCtaText = (text) => CTA_KEYWORDS.some(k => text.includes(k));\n"
    "const getBox = (el) => {\n"
    "    if (!el) return null;\n"
    "    const r = el.getBoundingClientRect();\n"
    "    return { x: Math.max(0.0, r.left + window.scrollX), y: Math.max(0.0, r.top + window.scrollY),\n"
    "             width: r.width, height: r.height };\n"
    "};\n"
)


def _get_box(el) -> dict | None:
    """Get bounding box in absolute page coordinates (Python-side helper)."""
    if not el:
        return None
    try:
        return el.evaluate("el => { " + JS_HELPERS + "return getBox(el); }")
    except Exception:
        return None


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
        # P2 — diagnostics (auditability, no behavior change)
        self.last_diagnostics: dict[str, Any] = {}

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

    # ─────────────────────────────────────────────────────────────
    # P2 — Candidate generation (unified helpers, repaired forms branch)
    # ─────────────────────────────────────────────────────────────
    def _candidate_containers(self) -> list[dict]:
        """Generate candidates from DOM structure using generic signals, NOT CSS selectors."""
        js = "() => {\n" + JS_HELPERS + """
            const candidates = [];

            // 1. ALL forms with purchase semantics (repaired: inputs declared, rendered gate, SVG-safe id)
            const forms = Array.from(document.querySelectorAll('form'));
            forms.forEach(f => {
                try {
                    const txt = (f.textContent || '').toLowerCase();
                    const cls = (f.className || '').toLowerCase();
                    const id_ = (typeof f.id === 'string' ? f.id : '').toLowerCase();
                    const rect = f.getBoundingClientRect();
                    const inputs = Array.from(f.querySelectorAll('input'));
                    const rendered = rect.width > 20 && rect.height > 10;
                    const is_purchase = PURCHASE_RE.test(txt) ||
                                     /product-form/.test(cls) ||
                                     /add-to-cart/.test(id_) ||
                                     inputs.some(i => /(add to cart|buy now|checkout|cart)/i.test(i.value));
                    if (rendered && is_purchase && !isHeaderOrDrawer(f)) {
                        candidates.push({ id: f.id || '', class: f.className || '', type: 'form' });
                    }
                } catch(e) {}
            });

            // 2. DIVs with purchase-related class patterns (regex grouping fixed)
            const divs = Array.from(document.querySelectorAll('div'));
            divs.forEach(d => {
                try {
                    const cls = (d.className || '').toLowerCase();
                    const id_ = (typeof d.id === 'string' ? d.id : '').toLowerCase();
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
                        if (patterns.some(p => p.test(cls) || p.test(id_))) {
                            candidates.push({ id: d.id || '', class: d.className || '', type: 'div' });
                        }
                    }
                } catch(e) {}
            });

            // 3. Sections around purchase CTA buttons
            const buttons = Array.from(document.querySelectorAll('button'));
            const purchase_buttons = buttons.filter(b => {
                try {
                    const txt = getElementText(b) + ' ' + ((b.value || '').toLowerCase());
                    return hasCtaText(txt) || /add-to-cart|buy-button/.test((b.className || '').toLowerCase());
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
        }"""
        try:
            return self.page.evaluate(js)
        except Exception:
            return []

    # ─────────────────────────────────────────────────────────────
    # Scoring (weights & threshold UNCHANGED; definitions unified)
    # ─────────────────────────────────────────────────────────────
    def _score_buy_box_candidate(self, el) -> tuple[float, BoundingBoxSignal]:
        """Score a buy box candidate using semantic signals. If confidence < 0.4, returns 0.0."""
        try:
            result = el.evaluate("el => { " + JS_HELPERS + """
                const txt = (el.textContent || '').toLowerCase();
                const cls = (el.className || '').toLowerCase();
                const id_ = (typeof el.id === 'string' ? el.id : '').toLowerCase();
                const tag = el.tagName.toLowerCase();

                let score = 0.0;
                const signals = { cta: false, price: false, variant: false,
                                  form: false, visible: false, coherence: false };

                const elementTxt = getElementText(el);
                signals.cta = hasCtaText(elementTxt);
                if (signals.cta) score += 0.15;

                signals.price = /\\d+[\\.,]?\\d{1,2}/.test(txt);
                if (signals.price) score += 0.20;

                const variant_keywords = ["variant", "selector", "size", "color", "choose", "option"];
                signals.variant = variant_keywords.some(k =>
                    cls.includes(k) || id_.includes(k) || txt.includes(k));
                if (signals.variant) score += 0.10;

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

                // Structural coherence: CTA inside form/container
                signals.coherence = signals.cta && signals.form;
                if (signals.coherence) score += 0.10;

                const is_header = /header|nav|drawer/.test(id_) || /header|nav|drawer/.test(cls);
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
                            (signals.cta ? "CTA " : "") + (signals.price ? "Price " : "") +
                            (signals.variant ? "Variant " : "") + (signals.form ? "Form " : "") +
                            (signals.visible ? "Visible " : "") + (signals.coherence ? "Coherent " : "")
                };
            }""")
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

    # ─────────────────────────────────────────────────────────────
    # P2 — Bounding boxes: diagnostics + full map population
    # ─────────────────────────────────────────────────────────────
    def capture_bounding_boxes(self) -> BoundingBoxMap:
        """Extract spatial coordinates for buy box + auxiliary PDP elements (generic)."""
        try:
            candidates = self._candidate_containers()

            best_bbox = None
            best_el = None
            best_score = 0.0
            best_signals = BoundingBoxSignal()
            chosen_entry = None
            rejected: list[dict[str, Any]] = []
            self.buy_box_reason = "No candidates generated"

            for cand in candidates:
                try:
                    el = None
                    if cand.get('id'):
                        el = self.page.query_selector(f"#{cand['id']}")
                    if not el and cand.get('class'):
                        classes = cand['class'].strip().split()
                        if classes:
                            el = self.page.query_selector("." + ".".join(classes[:2]))
                    if not el:
                        continue

                    score, signals = self._score_buy_box_candidate(el)
                    entry = {"type": cand.get('type', ''), "score": round(score, 3),
                             "reason": signals.reason or ""}
                    if score > best_score:
                        best_score = score
                        box = _get_box(el)
                        if box:
                            best_bbox = box
                            best_el = el
                            best_signals = signals
                            chosen_entry = entry
                    else:
                        rejected.append(entry)
                except Exception:
                    continue

            # P2 — diagnostics
            self.last_diagnostics = {
                "candidates_count": len(candidates),
                "rejected": rejected,
                "best_rejected": max(rejected, key=lambda r: r["score"]) if rejected else None,
                "chosen": chosen_entry,
                "scroll_target_y": self.last_scroll_y,
            }
            logger.debug("BuyBox diagnostics: %s", self.last_diagnostics)

            boxes: dict[str, BoundingBox] = {}
            if best_bbox:
                boxes["buy_box"] = BoundingBox(**{k: float(v) for k, v in best_bbox.items()})
                self.buy_box_confidence = best_score

                # P2 — auxiliary boxes inside chosen candidate
                try:
                    aux_chosen = best_el.evaluate("el => { " + JS_HELPERS + """
                        let ctaEl = null;
                        for (const c of el.querySelectorAll('button, input[type="submit"], a')) {
                            const t = getElementText(c) + ' ' + ((c.value || '').toLowerCase());
                            if (hasCtaText(t)) { ctaEl = c; break; }
                        }
                        let notifyEl = null;
                        for (const b of el.querySelectorAll('button, a, span')) {
                            const t = (b.textContent || '').toLowerCase();
                            if (t.includes('notify me') || t.includes('back in stock') || t.includes('restock')) { notifyEl = b; break; }
                        }
                        let reviewsEl = null;
                        for (const sel of CORE_REVIEW_SELECTORS) { reviewsEl = el.querySelector(sel); if (reviewsEl) break; }
                        if (!reviewsEl) { for (const sel of ADAPTER_REVIEW_SELECTORS) { reviewsEl = el.querySelector(sel); if (reviewsEl) break; } }
                        return { cta: getBox(ctaEl), notify: getBox(notifyEl), reviews: getBox(reviewsEl) };
                    }""")
                except Exception:
                    aux_chosen = {}

                # P2 — page-level auxiliary boxes (reviews fallback / upsell / sticky)
                try:
                    aux_page = self.page.evaluate("() => { " + JS_HELPERS + """
                        let reviewsEl = null;
                        for (const sel of CORE_REVIEW_SELECTORS) { reviewsEl = document.querySelector(sel); if (reviewsEl) break; }
                        if (!reviewsEl) { for (const sel of ADAPTER_REVIEW_SELECTORS) { reviewsEl = document.querySelector(sel); if (reviewsEl) break; } }
                        let notifyEl = null;
                        for (const b of document.querySelectorAll('button, a, span')) {
                            const t = (b.textContent || '').toLowerCase();
                            if (t.includes('notify me') || t.includes('back in stock') || t.includes('restock')) { notifyEl = b; break; }
                        }
                        let upsellEl = null;
                        const upsellPatterns = ['recommendation', 'cross-sell', 'upsell', 'related-product', 'bundle'];
                        for (const d of document.querySelectorAll('div, section')) {
                            const cls = (typeof d.className === 'string' ? d.className : '').toLowerCase();
                            const id_ = (typeof d.id === 'string' ? d.id : '').toLowerCase();
                            if (upsellPatterns.some(p => cls.includes(p) || id_.includes(p))) {
                                if (d.querySelectorAll('a, img, button').length > 0) { upsellEl = d; break; }
                            }
                        }
                        const stickyEl = document.querySelector('.sticky-atc, .sticky-add-to-cart, [class*="sticky-atc"], [class*="sticky"][class*="cart"]');
                        return { reviews: getBox(reviewsEl), notify: getBox(notifyEl),
                                 upsell: getBox(upsellEl), sticky_atc: getBox(stickyEl) };
                    }""")
                except Exception:
                    aux_page = {}

                for key, src in (("cta", aux_chosen), ("notify", aux_chosen), ("reviews", aux_chosen)):
                    val = (src or {}).get(key) or (aux_page or {}).get(key)
                    if val:
                        boxes[key] = BoundingBox(**{k: float(v) for k, v in val.items()})
                for key in ("upsell", "sticky_atc"):
                    val = (aux_page or {}).get(key)
                    if val:
                        boxes[key] = BoundingBox(**{k: float(v) for k, v in val.items()})

            # Expected social proof region (structural estimate; unchanged)
            if best_bbox and best_signals.confidence >= BUY_BOX_CONFIDENCE_THRESHOLD:
                try:
                    scroll_x = self.page.evaluate("window.scrollX || 0") or 0
                    scroll_y_val = self.page.evaluate("window.scrollY || 0") or 0
                except Exception:
                    scroll_x = 0
                    scroll_y_val = 0
                expected_region = {
                    "x": float(best_bbox["x"]),
                    "y": float(best_bbox["y"] + best_bbox["height"]),
                    "width": float(best_bbox["width"]),
                    "height": 120.0,
                }
                boxes["expected_social_proof_region"] = BoundingBox(**expected_region)
                self.buy_box_reason = best_signals.reason
                _ = scroll_x, scroll_y_val  # kept for API clarity

            self.buy_box_signals = best_signals if best_bbox else None

            return BoundingBoxMap(**{k: v for k, v in boxes.items() if v is not None})
        except Exception as exc:
            logger.debug("Failed to extract bounding boxes: %s", exc)
            self.buy_box_reason = f"Bounding box extraction failed: {exc}"
            return BoundingBoxMap()

    # ─────────────────────────────────────────────────────────────
    # Screenshot capture orchestration (signatures unchanged)
    # ─────────────────────────────────────────────────────────────
    def capture_screenshot_bytes(
        self,
        scroll_y: int = 0,
        opportunities: list[Any] | None = None,
        product_title: str = ""
    ) -> tuple[bytes, int]:
        """Scrolls per opportunity type, suppresses popups, captures viewport PNG."""
        if getattr(self.page, "is_closed", lambda: False)():
            raise RuntimeError("Cannot capture screenshot on closed Page execution context")

        start_time = time.perf_counter()
        self.suppress_overlays()

        self.last_scroll_y = 0
        self.buy_box_confidence = 0.0
        self.buy_box_signals = None
        self.buy_box_reason = ""
        self.last_diagnostics = {}

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

        self.last_diagnostics["scroll_target_y"] = self.last_scroll_y
        duration_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return png_bytes, duration_ms

    # ─────────────────────────────────────────────────────────────
    # P0 preserved: no early return; eligibility separated from confidence
    # ─────────────────────────────────────────────────────────────
    def _scroll_for_social_proof(self, bmap: BoundingBoxMap, scroll_y: int) -> None:
        """Scroll viewport to include buy box AND expected social proof region."""
        # NOTE (P0): do NOT early-return when bmap.buy_box is None — inline detection proceeds.
        try:
            scroll_result = self.page.evaluate("() => { " + JS_HELPERS + """
                const candidates = [];

                // FIX: SVG-safe id extraction
                const forms = Array.from(document.querySelectorAll('form'));
                forms.forEach(f => {
                    const txt = (f.textContent || '').toLowerCase();
                    const cls = (f.className || '').toLowerCase();
                    const id_ = (typeof f.id === 'string' ? f.id : '').toLowerCase();
                    const rect = f.getBoundingClientRect();
                    const visible = rect.width > 20 && rect.height > 50;
                    const is_purchase = PURCHASE_RE.test(txt) || /product-form/.test(cls) || /add-to-cart/.test(id_);
                    if (visible && is_purchase && !isHeaderOrDrawer(f)) candidates.push(f);
                });

                const buttons = Array.from(document.querySelectorAll('button'));
                buttons.forEach(b => {
                    const txt = getElementText(b) + ' ' + ((b.value || '').toLowerCase());
                    if (hasCtaText(txt) || /add-to-cart|buy-button/.test((b.className || '').toLowerCase())) {
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
                        const id_ = (typeof el.id === 'string' ? el.id : '').toLowerCase();
                        const tag = el.tagName.toLowerCase();
                        let score = 0;

                        if (hasCtaText(getElementText(el))) score += 0.15;
                        if (/\\d+[\\.,]?\\d{1,2}/.test(txt)) score += 0.20;
                        if (["variant", "selector", "size", "color"].some(k => cls.includes(k) || id_.includes(k))) score += 0.10;
                        if (tag === 'form' || cls.includes('product-form') || id_.includes('product-form')) score += 0.15;
                        const r = el.getBoundingClientRect();
                        if (r.width > 10 && r.height > 10 && r.top >= -100 && r.bottom <= (window.innerHeight + 100)) score += 0.10;
                        if (hasCtaText(txt) && /\\d+[\\.,]?\\d{1,2}/.test(txt) &&
                            ["variant", "selector", "size", "color"].some(k => cls.includes(k) || id_.includes(k))) score += 0.10;
                        if (r.left >= -10 && r.right <= (window.innerWidth + 10) && r.top >= -10 && r.bottom <= (window.innerHeight + 10)) score += 0.10;
                        if (isHeaderOrDrawer(el)) score -= 0.30;

                        score = Math.max(0.0, Math.min(1.0, score));
                        // P0: scroll eligibility separated from 0.4 confidence threshold
                        if (score > bestScore) { bestScore = score; bestEl = el; }
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
                    // P0: smooth-scroll stabilization before reading scrollY
                    return new Promise(resolve => {
                        setTimeout(() => {
                            resolve({ found: true, y: window.scrollY || window.pageYOffset, confidence: bestScore });
                        }, 150);
                    });
                }
                return { found: false };
            }""")
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
        """Scroll viewport to show recommendation/upsell region (NOT footer)."""
        try:
            scroll_result = self.page.evaluate("() => { " + JS_HELPERS + """
                const upsellPatterns = ['recommendation', 'cross-sell', 'upsell', 'related-product', 'bundle'];
                const divs = Array.from(document.querySelectorAll('div, section'));
                for (const d of divs) {
                    try {
                        const cls = (typeof d.className === 'string' ? d.className : '').toLowerCase();
                        const id_ = (typeof d.id === 'string' ? d.id : '').toLowerCase();
                        if (upsellPatterns.some(p => cls.includes(p) || id_.includes(p))) {
                            const rect = d.getBoundingClientRect();
                            if (rect.width > 50 && rect.height > 50) {
                                if (d.querySelectorAll('a[href*="/products/"], img').length > 0) {
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
            }""")
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
        """Behavioral scroll to trigger sticky ATC."""
        target_scroll = scroll_y if scroll_y > 0 else 1000
        try:
            self.page.evaluate(f"window.scrollTo(0, {target_scroll});")
            self.page.wait_for_timeout(400)
            self.last_scroll_y = int(self.page.evaluate("window.scrollY || 0"))
        except Exception:
            pass

    def _wait_for_page_readiness(self) -> None:
        """Generic readiness checks; timeouts are safety fallbacks only."""
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
        """Capture viewport PNG with robust retry."""
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
                    full_page=False, type="png", animations="disabled", timeout=3000,
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

    # ─────────────────────────────────────────────────────────────
    # P2 — validation with occlusion check; proven flags unchanged (P1.5 contract)
    # ─────────────────────────────────────────────────────────────
    def _validate_from_screenshot(self, png_bytes: bytes, bmap: BoundingBoxMap, opp_type: str | None) -> None:
        """Independently validate what is ACTUALLY visible (and not occluded) in the viewport."""
        try:
            val_result = self.page.evaluate("([oppType]) => { " + JS_HELPERS + """
                const visibleAndClear = (el) => isInViewport(el) && !isOccluded(el);

                let identityVisible = false;
                for (const h of document.querySelectorAll('h1, .product-title, .product-name')) {
                    if (visibleAndClear(h) && (h.textContent || '').trim().length > 0) { identityVisible = true; break; }
                }

                let ctaEl = null;
                for (const b of document.querySelectorAll('button, input[type="submit"], form button')) {
                    try {
                        const t = getElementText(b) + ' ' + ((b.value || '').toLowerCase());
                        if (hasCtaText(t) && !isHeaderOrDrawer(b) && visibleAndClear(b)) { ctaEl = b; break; }
                    } catch(e) {}
                }
                let buyBoxVisible = !!ctaEl;
                if (!buyBoxVisible) {
                    for (const f of document.querySelectorAll('form')) {
                        if (!isHeaderOrDrawer(f) && visibleAndClear(f)) {
                            const t = (f.textContent || '').toLowerCase();
                            if (/add to cart|buy now|checkout|product-form/.test(t)) { buyBoxVisible = true; break; }
                        }
                    }
                }

                let socialProofVisible = false;
                if (oppType === "MISSING_SOCIAL_PROOF") {
                    for (const sel of CORE_REVIEW_SELECTORS) {
                        try {
                            const el = document.querySelector(sel);
                            if (el && visibleAndClear(el) && !isHeaderOrDrawer(el)) { socialProofVisible = true; break; }
                        } catch(e) {}
                    }
                    if (!socialProofVisible) {
                        for (const sel of ADAPTER_REVIEW_SELECTORS) {
                            try {
                                const el = document.querySelector(sel);
                                if (el && visibleAndClear(el) && !isHeaderOrDrawer(el)) { socialProofVisible = true; break; }
                            } catch(e) {}
                        }
                    }
                    if (!socialProofVisible && ctaEl) {
                        const ctaRect = ctaEl.getBoundingClientRect();
                        if (window.innerHeight - ctaRect.bottom > 60) { socialProofVisible = true; }
                    }
                }

                let upsellVisible = false;
                if (oppType === "MISSING_UPSELL") {
                    const upsellPatterns = ['recommendation', 'cross-sell', 'upsell', 'related-product', 'bundle'];
                    for (const d of document.querySelectorAll('div, section')) {
                        try {
                            const cls = (typeof d.className === 'string' ? d.className : '').toLowerCase();
                            const id_ = (typeof d.id === 'string' ? d.id : '').toLowerCase();
                            if (upsellPatterns.some(p => cls.includes(p) || id_.includes(p))) {
                                if (visibleAndClear(d) && d.querySelectorAll('a[href*="/products/"], img').length > 0) { upsellVisible = true; break; }
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
            }""", [opp_type])

            self.product_identity_visible = val_result.get("product_identity_visible", False)
            self.buy_box_visible = val_result.get("buy_box_visible", False)
            self.relevant_social_proof_region_visible = val_result.get("social_proof_region_visible", False)
            self.relevant_upsell_region_visible = val_result.get("upsell_region_visible", False)

            if opp_type == "MISSING_SOCIAL_PROOF":
                self.finding_visually_proven = (
                    self.product_identity_visible and self.buy_box_visible and self.relevant_social_proof_region_visible)
            elif opp_type == "MISSING_UPSELL":
                self.finding_visually_proven = (
                    self.product_identity_visible and self.buy_box_visible and self.relevant_upsell_region_visible)
            elif opp_type in ("MISSING_STICKY_ATC", "REVENUE_LEAK"):
                self.finding_visually_proven = (
                    self.product_identity_visible and self.buy_box_visible)
        except Exception as e:
            logger.warning("Visual check evaluation failed: %s", e)
            self.product_identity_visible = False
            self.buy_box_visible = False
            self.relevant_social_proof_region_visible = False
            self.relevant_upsell_region_visible = False
            self.finding_visually_proven = False
            self.buy_box_reason = f"Visual validation error: {e}"
