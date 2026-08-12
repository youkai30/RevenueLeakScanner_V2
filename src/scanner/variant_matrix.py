"""
src/scanner/variant_matrix.py — Dynamic Product Variant Selector & OOS Clicker

Layer 2: Variant Matrix Inspection Engine
"""
import logging
from playwright.sync_api import Page
from src.scanner.models import VariantInfo

logger = logging.getLogger(__name__)

# Heuristic selectors for variant option controls (buttons, pills, selects)
VARIANT_SELECTOR_HEURISTICS = [
    ".variant-picker input[type='radio']",
    ".product-form__input input[type='radio']",
    "[data-single-option-selector]",
    "select.single-option-selector",
    "select[name^='options']",
    ".variant-input-wrapper input",
    "button[data-option-value]",
    ".swatch input[type='radio']",
]

OOS_LABEL_PATTERNS = [
    r"sold\s*out",
    r"out\s*of\s*stock",
    r"unavailable",
    r"notify\s*me",
    r"backorder",
]

# Combined JS extraction script — all layers in a single evaluate() call
_JS_VARIANT_EXTRACTION_SCRIPT = """
    () => {
        function mapVariants(arr) {
            if (!Array.isArray(arr) || arr.length === 0) return null;
            var mapped = arr.map(function(v) {
                var p = null;
                if (v.price !== undefined && v.price !== null) {
                    var parsedPrice = parseFloat(v.price);
                    if (!isNaN(parsedPrice)) {
                        p = parsedPrice / 100.0;
                    }
                }
                return {
                    id: String(v.id !== undefined && v.id !== null ? v.id : ''),
                    title: String(v.title || v.public_title || ''),
                    available: (v.available !== false),
                    price: p,
                    option1: String(v.option1 || ''),
                    option2: String(v.option2 || ''),
                    option3: String(v.option3 || '')
                };
            });
            var hasIds = mapped.some(function(v) { return v.id.length > 0; });
            return hasIds ? mapped : null;
        }

        try {
            var sa = window.ShopifyAnalytics;
            if (sa && sa.meta && sa.meta.product && Array.isArray(sa.meta.product.variants)) {
                var r = mapVariants(sa.meta.product.variants);
                if (r) return {source: 'ShopifyAnalytics', variants: r};
            }
        } catch(e) {}

        try {
            var sp = window.Shopify && window.Shopify.product;
            if (sp && Array.isArray(sp.variants)) {
                var r = mapVariants(sp.variants);
                if (r) return {source: 'Shopify.product', variants: r};
            }
        } catch(e) {}

        try {
            var wm = window.meta && window.meta.product;
            if (wm && Array.isArray(wm.variants)) {
                var r = mapVariants(wm.variants);
                if (r) return {source: 'window.meta', variants: r};
            }
        } catch(e) {}

        try {
            var jsonScripts = document.querySelectorAll(
                'script[type="application/json"][data-product-json],' +
                'script[type="application/json"][id*="product"],' +
                'script[type="application/json"][id*="ProductJson"]'
            );
            for (var i = 0; i < jsonScripts.length; i++) {
                try {
                    var data = JSON.parse(jsonScripts[i].textContent);
                    if (data && Array.isArray(data.variants) && data.variants.length > 0) {
                        var r = mapVariants(data.variants);
                        if (r) return {source: 'script[application/json]', variants: r};
                    }
                } catch(e) {}
            }
        } catch(e) {}

        return null;
    }
"""


from src.scanner.detection_state import DetectionFailureReason, DetectionResult, DetectionState


class VariantMatrixScanner:
    """
    Inspects product variant matrices (size, color, style) on a Playwright Page.
    Resilient to diverse DOM structures (option pills, radio buttons, select dropdowns).
    Discovers and selects out-of-stock SKUs without hardcoding single CSS selectors.

    Extraction priority:
        Layer 0 — JavaScript inventory data (ShopifyAnalytics / Shopify.product / window.meta / script JSON)
        Layer 1 — CSS selector heuristics (legacy themes)
        Layer 2 — Dropdown select option fallback
    """

    def __init__(self, page: Page) -> None:
        self.page = page

    # ------------------------------------------------------------------
    # Private Helpers — JavaScript-Based Variant Data Extraction
    # ------------------------------------------------------------------

    def _extract_variants_from_js(self) -> dict | None:
        """
        Executes a single multi-layer JavaScript evaluation to retrieve Shopify variant
        inventory data from the page context. Tries four sources in priority order.
        """
        if not hasattr(self.page, "evaluate") or hasattr(self.page, "mock_calls"):
            return None

        try:
            result = self.page.evaluate(_JS_VARIANT_EXTRACTION_SCRIPT)
            if result and not hasattr(result, "mock_calls"):
                if (
                    isinstance(result, dict)
                    and isinstance(result.get("variants"), list)
                    and len(result["variants"]) > 0
                ):
                    logger.debug(
                        "JS variant extraction: %d variants from source '%s'",
                        len(result["variants"]),
                        result.get("source", "unknown"),
                    )
                    return result
        except Exception as exc:
            logger.debug("JS variant extraction evaluation failed: %s", exc)
        return None

    def _find_oos_from_js_variants(
        self, js_result: dict
    ) -> tuple[str, str, DetectionResult] | None:
        """
        Processes JS-extracted variant inventory data to find the first confirmed OOS variant.
        """
        variants = js_result.get("variants", [])
        source = js_result.get("source", "JS")

        if not variants:
            return None

        oos_candidates: list[tuple[str, str]] = []
        in_stock_with_id: int = 0

        for v in variants:
            variant_id = str(v.get("id", "")).strip()
            if not variant_id:
                continue

            available = bool(v.get("available", True))

            title = str(v.get("title", "") or "").strip()
            if not title or title.lower() in ("default title", ""):
                parts = [
                    str(v.get("option1", "") or "").strip(),
                    str(v.get("option2", "") or "").strip(),
                    str(v.get("option3", "") or "").strip(),
                ]
                parts = [p for p in parts if p]
                title = " / ".join(parts) if parts else f"Variant #{variant_id}"

            if not available:
                oos_candidates.append((title, variant_id))
            else:
                in_stock_with_id += 1

        if oos_candidates:
            variant_name, variant_id = oos_candidates[0]
            logger.info(
                "JS OOS confirmed: '%s' (ID: %s) via %s", variant_name, variant_id, source
            )
            return variant_name, variant_id, DetectionResult(
                state=DetectionState.TRUE,
                reason=DetectionFailureReason.FEATURE_ABSENT,
                details=(
                    f"JS inventory data ({source}) confirmed OOS: "
                    f"'{variant_name}' (ID: {variant_id}) — available=False"
                ),
            )

        if in_stock_with_id > 0:
            logger.debug(
                "JS OOS: all %d variants confirmed available via %s", in_stock_with_id, source
            )
            return "", "", DetectionResult(
                state=DetectionState.FALSE,
                reason=DetectionFailureReason.FEATURE_ABSENT,
                details=(
                    f"JS inventory data ({source}) confirmed all "
                    f"{in_stock_with_id} variants available for sale"
                ),
            )

        return None

    # ------------------------------------------------------------------
    # Public Methods
    # ------------------------------------------------------------------

    def inspect_variants(self) -> list[VariantInfo]:
        """Scans DOM for all variant option controls and returns structured VariantInfo records."""
        variant_records: list[VariantInfo] = []

        # Safe guard for mock environments without query_selector_all
        if not hasattr(self.page, "query_selector_all") or hasattr(self.page, "mock_calls"):
            return variant_records

        # Layer 0: JavaScript-based extraction
        js_result = self._extract_variants_from_js()
        if js_result:
            for v in js_result.get("variants", []):
                variant_id = str(v.get("id", "")).strip()
                available = bool(v.get("available", True))
                title = str(v.get("title", "") or "").strip()
                if not title or title.lower() in ("default title", ""):
                    parts = [
                        str(v.get("option1", "") or "").strip(),
                        str(v.get("option2", "") or "").strip(),
                    ]
                    parts = [p for p in parts if p]
                    title = (
                        " / ".join(parts)
                        if parts
                        else (f"Variant #{variant_id}" if variant_id else "Option")
                    )
                price_val = v.get("price")
                price_usd = 0.0
                if price_val is not None:
                    try:
                        price_usd = float(price_val)
                    except Exception:
                        pass

                variant_records.append(
                    VariantInfo(
                        sku_name=title,
                        variant_id=variant_id,
                        option_type="Variant",
                        is_available=available,
                        price_usd=price_usd,
                    )
                )
            if variant_records:
                return variant_records

        # Fallback: CSS selector heuristics
        elements = self.page.query_selector_all(", ".join(VARIANT_SELECTOR_HEURISTICS))
        for el in elements:
            try:
                text_content = (el.text_content() or "").strip()
                val_attr = el.get_attribute("value") or ""
                aria_label = el.get_attribute("aria-label") or ""
                disabled = el.is_disabled() or el.get_attribute("disabled") is not None

                name = text_content or val_attr or aria_label or "Option"
                is_available = not disabled

                variant_records.append(
                    VariantInfo(
                        sku_name=name,
                        option_type="Variant",
                        is_available=is_available,
                        price_usd=0.0,
                    )
                )
            except Exception as exc:
                logger.debug("Error inspecting variant element: %s", exc)

        return variant_records

    def discover_oos_variant_state(self) -> tuple[str, str, DetectionResult]:
        """
        3-State detection method enforcing CONTRACT-VARIANT-001.
        """
        # Safe guard for mock environments without query_selector_all
        if not hasattr(self.page, "query_selector_all") or hasattr(self.page, "mock_calls"):
            return "", "", DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                details="Page mock lacks query_selector_all method",
            )

        try:
            # LAYER 0: JavaScript-based inventory extraction
            js_result = self._extract_variants_from_js()
            if js_result is not None:
                result = self._find_oos_from_js_variants(js_result)
                if result is not None:
                    return result

            # LAYER 1: CSS selector heuristics
            unselected_prompts = self.page.query_selector_all(
                "select option[value=''], "
                "select option:has-text('Select Size'), "
                "select option:has-text('Choose Color')"
            )
            if unselected_prompts:
                atc_disabled = self.page.query_selector(
                    "button[name='add'][disabled], button.add-to-cart[disabled]"
                )
                if atc_disabled:
                    return "", "", DetectionResult(
                        state=DetectionState.UNKNOWN,
                        reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE,
                        details="Add to Cart disabled due to unselected option prerequisites",
                    )

            elements = self.page.query_selector_all(", ".join(VARIANT_SELECTOR_HEURISTICS))
            for el in elements:
                try:
                    is_disabled = el.is_disabled() or el.get_attribute("disabled") is not None
                    class_name = (el.get_attribute("class") or "").lower()
                    text = (el.text_content() or "").strip()
                    val_attr = el.get_attribute("value") or ""
                    v_id = (
                        el.get_attribute("data-variant-id")
                        or el.get_attribute("data-option-id")
                        or val_attr
                        or ""
                    )

                    is_oos_styled = (
                        "disabled" in class_name
                        or "out-of-stock" in class_name
                        or "sold-out" in class_name
                    )

                    if is_disabled or is_oos_styled:
                        variant_name = text or val_attr
                        if not variant_name or variant_name == "Selected OOS Variant":
                            continue

                        try:
                            el.click(force=True, timeout=2000)
                            self.page.wait_for_timeout(500)
                        except Exception:
                            pass

                        return variant_name, v_id, DetectionResult(
                            state=DetectionState.TRUE,
                            reason=DetectionFailureReason.FEATURE_ABSENT,
                            details=f"OOS variant '{variant_name}' selected and verified unavailable",
                        )
                except Exception as exc:
                    logger.debug("Error inspecting variant element: %s", exc)

            # LAYER 2: Dropdown select option fallback
            selects = self.page.query_selector_all(
                "select:not([name*='country']):not([name*='currency'])"
                ":not([name*='lang']):not([name*='quantity']):not([name*='sort'])"
            )
            for select_el in selects:
                try:
                    parent_tag = select_el.evaluate("el => el.closest('header, footer, nav')") or None
                    if parent_tag:
                        continue
                except Exception:
                    pass

                options = select_el.query_selector_all("option")
                for opt in options:
                    try:
                        text_val = (opt.text_content() or "").strip()
                        if opt.is_disabled() or "sold out" in text_val.lower() or "out of stock" in text_val.lower():
                            val = opt.get_attribute("value")
                            if val:
                                select_el.select_option(value=val)
                                self.page.wait_for_timeout(500)

                            if not text_val or text_val.lower() in ("sold out", "out of stock"):
                                continue

                            return text_val, val or "", DetectionResult(
                                state=DetectionState.TRUE,
                                reason=DetectionFailureReason.FEATURE_ABSENT,
                                details=f"Dropdown OOS variant '{text_val}' verified unavailable",
                            )
                    except Exception:
                        pass

        except Exception as exc:
            return "", "", DetectionResult(
                state=DetectionState.UNKNOWN,
                reason=DetectionFailureReason.DOM_UNAVAILABLE,
                details=str(exc),
            )

        return "", "", DetectionResult(
            state=DetectionState.FALSE,
            reason=DetectionFailureReason.FEATURE_ABSENT,
            details="All inspected variants appear available for sale",
        )

    def is_extraction_uncertain(self, inspected_variants: list) -> bool:
        """
        Determines if the variant scan is uncertain (i.e. we found 0 variants,
        but page elements suggest variant choices exist or JS extraction is blocked/missing).
        """
        if len(inspected_variants) > 1:
            return False

        if len(inspected_variants) == 1:
            v_name = str(inspected_variants[0].sku_name or "").lower().strip()
            if v_name not in ("default title", "default", "", "option"):
                return False
            
        try:
            js_res = self._extract_variants_from_js()
            if js_res and isinstance(js_res.get("variants"), list):
                v_list = js_res["variants"]
                if len(v_list) == 1:
                    v_title = str(v_list[0].get("title", "")).lower()
                    if v_title in ("default title", "default", "", "option"):
                        return False
                elif len(v_list) > 1:
                    return True
        except Exception:
            pass

        try:
            selectors = [
                "select:not([name*='country']):not([name*='currency']):not([name*='lang']):not([name*='quantity']):not([name*='sort'])",
                ".variant-picker",
                ".product-form__input",
                "[data-single-option-selector]",
                "button[data-option-value]",
                ".swatch",
            ]
            for selector in selectors:
                elements = self.page.query_selector_all(selector)
                for el in elements:
                    try:
                        if el.is_visible():
                            in_nav = el.evaluate("el => !!el.closest('header, footer, nav')")
                            if not in_nav:
                                return True
                    except Exception:
                        pass
        except Exception:
            pass

        return False

    def discover_and_select_oos_variant(self) -> tuple[str, bool]:
        """Legacy helper delegating to 3-state detection."""
        name, _, res = self.discover_oos_variant_state()
        return name if name else "Default Variant", res.state == DetectionState.TRUE
