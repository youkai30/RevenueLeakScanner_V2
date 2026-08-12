"""
src/scanner/page_validator.py — PDP Validation & Page Type Classifier Engine

Layer 2: Product Detail Page (PDP) Safety Gate & Validator
Contract: CONTRACT-PDP-001
"""
import logging
import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field
from playwright.sync_api import Page, Response

logger = logging.getLogger(__name__)


class PageState(str, Enum):
    REAL_PRODUCT = "REAL_PRODUCT"
    CLOUDFLARE_BLOCKED = "CLOUDFLARE_BLOCKED"
    NOT_PRODUCT = "NOT_PRODUCT"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"
    PARTIALLY_INSPECTED = "PARTIALLY_INSPECTED"


class PageValidationResult(BaseModel):
    """
    Structured outcome of PDP safety gate inspection.
    Enforces CONTRACT-PDP-001 requirements.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: PageState = Field(description="Validated page type state")
    confidence: float = Field(ge=0.0, le=1.0, description="Validation certainty score")
    reasons: list[str] = Field(default_factory=list, description="Diagnostic signals and reasons")
    url: str = Field(description="Inspected page URL")
    product_title: str | None = Field(default=None, description="Extracted clean product title if valid")


# High-confidence Cloudflare & Anti-Bot challenge title patterns
CLOUDFLARE_TITLE_PATTERNS = [
    r"connexion\s+en\s+cours",
    r"just\s+a\s+moment",
    r"attention\s+required",
    r"verify\s+you\s+are\s+human",
    r"access\s+denied",
    r"security\s+check",
    r"ddos-guard",
    r"cf-browser-verification",
]

# Standard non-product path regexes
NON_PRODUCT_PATH_PATTERNS = [
    r"^/collections",
    r"^/cart",
    r"^/checkout",
    r"^/account",
    r"^/pages",
    r"^/blogs",
    r"^/search",
    r"^/policies",
    r"^/contact",
    r"^/about",
    r"^/faq",
]


class PageValidator:
    """
    Centralized safety boundary enforcing CONTRACT-PDP-001.
    Evaluates multi-signal evidence to positively confirm authentic Shopify PDPs
    and reject Cloudflare walls, non-product pages, error pages, and ambiguous URLs.
    """

    def validate_page(
        self,
        page: Page,
        target_url: str,
        response: Response | None = None,
    ) -> PageValidationResult:
        reasons: list[str] = []

        # 1. Inspect HTTP response status & headers if available
        if response:
            if response.status in (403, 429, 503):
                # Check for Cloudflare / bot block status
                server_header = (response.headers.get("server") or "").lower()
                if "cloudflare" in server_header or response.status in (403, 503):
                    reasons.append(f"HTTP {response.status} with security block header")
                    return PageValidationResult(
                        status=PageState.CLOUDFLARE_BLOCKED,
                        confidence=1.0,
                        reasons=reasons,
                        url=target_url,
                    )
            elif response.status >= 400:
                reasons.append(f"HTTP {response.status} Client/Server error response")
                return PageValidationResult(
                    status=PageState.ERROR,
                    confidence=1.0,
                    reasons=reasons,
                    url=target_url,
                )

        # 2. Check for Cloudflare / Anti-Bot Challenge via Title & DOM
        try:
            page_title = (page.title() or "").strip()
            title_lower = page_title.lower()

            for pattern in CLOUDFLARE_TITLE_PATTERNS:
                if re.search(pattern, title_lower):
                    reasons.append(f"Cloudflare/Challenge title matched pattern '{pattern}'")
                    return PageValidationResult(
                        status=PageState.CLOUDFLARE_BLOCKED,
                        confidence=1.0,
                        reasons=reasons,
                        url=target_url,
                        product_title=page_title,
                    )

            # Check Cloudflare DOM elements
            cf_elements = page.query_selector(
                "#challenge-running, .cf-browser-verification, #cf-wrapper, iframe[src*='challenges.cloudflare.com'], "
                "#challenge-form, #cf-challenge-form, .cf-turnstile, .g-recaptcha, iframe[src*='turnstile']"
            )
            if cf_elements:
                reasons.append("Cloudflare challenge DOM container detected")
                return PageValidationResult(
                    status=PageState.CLOUDFLARE_BLOCKED,
                    confidence=1.0,
                    reasons=reasons,
                    url=target_url,
                    product_title=page_title,
                )

            # Check page body content for bot challenge/verification indicators
            body_text = ""
            try:
                body_text = (page.locator("body").inner_text() or "").lower()
            except Exception:
                try:
                    body_text = (page.content() or "").lower()
                except Exception:
                    pass

            if body_text:
                cf_body_keywords = [
                    "checking your browser",
                    "bot verification",
                    "verify you are human",
                    "verify you're human",
                    "ddos-guard",
                    "access denied",
                ]
                for kw in cf_body_keywords:
                    if kw in body_text:
                        reasons.append(f"Cloudflare/Challenge body text matched keyword '{kw}'")
                        return PageValidationResult(
                            status=PageState.CLOUDFLARE_BLOCKED,
                            confidence=1.0,
                            reasons=reasons,
                            url=target_url,
                            product_title=page_title,
                        )
                if "cloudflare" in body_text and any(term in body_text for term in ["challenge", "turnstile", "checking your browser", "ray id"]):
                    reasons.append("Cloudflare challenge keywords matched in body")
                    return PageValidationResult(
                        status=PageState.CLOUDFLARE_BLOCKED,
                        confidence=1.0,
                        reasons=reasons,
                        url=target_url,
                        product_title=page_title,
                    )
        except Exception as exc:
            logger.debug("Error inspecting page title/DOM/body for Cloudflare: %s", exc)

        # 3. Check for obvious Error Page indicators
        try:
            if "404" in title_lower or "page not found" in title_lower or "error" in title_lower:
                reasons.append(f"Error page title detected: '{page_title}'")
                return PageValidationResult(
                    status=PageState.ERROR,
                    confidence=0.9,
                    reasons=reasons,
                    url=target_url,
                )
        except Exception:
            pass

        # 4. Check URL Path for Non-Product Routes
        parsed_url = urlparse(target_url)
        path = parsed_url.path.lower()

        for pattern in NON_PRODUCT_PATH_PATTERNS:
            if re.search(pattern, path):
                reasons.append(f"URL path matched non-product route pattern '{pattern}'")
                return PageValidationResult(
                    status=PageState.NOT_PRODUCT,
                    confidence=1.0,
                    reasons=reasons,
                    url=target_url,
                )

        if path.rstrip("/") == "/products":
            reasons.append("URL is collection index path '/products'")
            return PageValidationResult(
                status=PageState.NOT_PRODUCT,
                confidence=1.0,
                reasons=reasons,
                url=target_url,
            )

        # 5. Multi-Signal Positive PDP Verification
        product_signals_count = 0

        # Signal A: Shopify /products/ URL pattern
        if "/products/" in path:
            product_signals_count += 1
            reasons.append("URL path contains Shopify '/products/<slug>' structure")

        # Signal B: Product Form / Buy Box DOM Container
        try:
            product_form = page.query_selector(
                "form[action*='/cart/add'], input[name='id'], .product-form, [data-product-form]"
            )
            if product_form:
                product_signals_count += 1
                reasons.append("Product cart form container found in DOM")
        except Exception as exc:
            logger.debug("DOM product form check error: %s", exc)

        # Signal C: JSON-LD Product Structured Data
        try:
            json_ld_elements = page.query_selector_all("script[type='application/ld+json']")
            for elem in json_ld_elements:
                content = (elem.text_content() or "").lower()
                if '"@type":"product"' in content or '"@type": "product"' in content:
                    product_signals_count += 1
                    reasons.append("JSON-LD schema.org Product metadata detected")
                    break
        except Exception as exc:
            logger.debug("JSON-LD product check error: %s", exc)

        # Signal D: Open Graph Meta Product Type
        try:
            og_type = page.query_selector("meta[property='og:type'][content*='product']")
            if og_type:
                product_signals_count += 1
                reasons.append("Open Graph og:type 'product' meta tag detected")
        except Exception as exc:
            logger.debug("OG meta product check error: %s", exc)

        # Signal E: Shopify Analytics Meta Object
        try:
            has_shopify_meta = page.evaluate("() => typeof window.ShopifyAnalytics !== 'undefined' && !!window.ShopifyAnalytics.meta.product")
            if has_shopify_meta:
                product_signals_count += 1
                reasons.append("ShopifyAnalytics product metadata object detected")
        except Exception:
            pass

        # Signal F: Product Price meta tags or elements
        try:
            price_meta = page.query_selector(
                "meta[property='product:price:amount'], meta[property='og:price:amount'], "
                "[itemprop='price'], .price, #price, [class*='price']"
            )
            if price_meta:
                product_signals_count += 1
                reasons.append("Product price metadata or element detected")
        except Exception as exc:
            logger.debug("Price check error: %s", exc)

        # Signal G: Add to Cart button / CTA
        try:
            atc_button = page.query_selector(
                "button[name='add'], button.add-to-cart, [class*='add-to-cart'], "
                "button[id*='AddToCart'], button[class*='AddToCart']"
            )
            if atc_button:
                product_signals_count += 1
                reasons.append("Add to Cart button or CTA found in DOM")
        except Exception as exc:
            logger.debug("ATC button check error: %s", exc)

        # Clean product title
        clean_title = (page_title or "Product").split("|")[0].split("-")[0].strip()

        # Decision Rule: Require at least 2 independent positive product signals
        if product_signals_count >= 2:
            confidence = min(1.0, 0.5 + (product_signals_count * 0.15))
            reasons.append(f"Confirmed REAL_PRODUCT with {product_signals_count} positive signals")
            return PageValidationResult(
                status=PageState.REAL_PRODUCT,
                confidence=round(confidence, 2),
                reasons=reasons,
                url=target_url,
                product_title=clean_title,
            )

        # Conservative Fallback: Insufficient signals -> UNKNOWN (never default UNKNOWN to REAL_PRODUCT)
        reasons.append(f"Insufficient positive product signals ({product_signals_count}/2 required)")
        return PageValidationResult(
            status=PageState.UNKNOWN,
            confidence=0.5,
            reasons=reasons,
            url=target_url,
            product_title=clean_title,
        )
