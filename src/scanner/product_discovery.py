"""
src/scanner/product_discovery.py — Product Detail Page (PDP) Crawler & Discovery Engine

Layer 2: PDP URL Crawler & Candidate Filter
"""
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from playwright.sync_api import Page, Response

logger = logging.getLogger(__name__)

# Standard non-product path patterns to reject
REJECTED_PATH_PATTERNS = [
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
    # Reject Shopify content/marketing custom template handles stored as pseudo-products
    r"/products/content-",
    r"/products/size-guide",
    r"/products/template-",
]



class ProductDiscoveryEngine:
    """
    Discovers valid Product Detail Page (PDP) URLs from a StoreRecord.
    Rejects obvious non-product URLs, logs diagnostics, and deduplicates candidates.
    Does NOT calculate commercial loss or write SessionBundle artifacts.
    """

    def __init__(self, max_candidates: int = 5) -> None:
        self.max_candidates = max_candidates

    def is_valid_pdp_url(self, base_domain: str, candidate_url: str) -> tuple[bool, str]:
        """
        Evaluates a candidate URL against hostname & non-product regex rules.
        Returns tuple of (is_valid: bool, rejection_reason: str).
        """
        if not candidate_url or not isinstance(candidate_url, str):
            return False, "Empty or non-string URL"

        parsed_candidate = urlparse(candidate_url)
        parsed_base = urlparse(base_domain if "://" in base_domain else f"https://{base_domain}")

        # Rule 1: Hostname match check
        candidate_host = parsed_candidate.netloc.lower().replace("www.", "")
        base_host = parsed_base.netloc.lower().replace("www.", "")

        if candidate_host and candidate_host != base_host:
            return False, f"Domain mismatch (candidate: '{candidate_host}', target: '{base_host}')"

        path = parsed_candidate.path.lower()

        # Rule 3: Positive PDP signals checked FIRST (with template checks)
        if "/products/" in path:
            # Exclude known template handles
            for pat in [r"/products/content-", r"/products/size-guide", r"/products/template-"]:
                if re.search(pat, path):
                    return False, f"Shopify content/template page matched pattern: '{pat}'"
            # Reject bare /products/ index page
            if path.rstrip("/") == "/products" or path.rstrip("/") == "/collections/products":
                return False, "Collection index path '/products'"
            return True, "Valid Shopify PDP pattern '/products/<slug>'"

        # Rule 2: Reject non-product system paths (only evaluated if not a positive /products/ slug)
        for pattern in REJECTED_PATH_PATTERNS:
            if re.search(pattern, path):
                return False, f"Matched non-product path pattern: '{pattern}'"

        # Fallback check for general product-like paths
        if len(path.strip("/").split("/")) >= 1 and any(char.isdigit() for char in path):
            return True, "Potential product URL with SKU/ID"

        return False, "Does not match PDP criteria"

    def discover_pdp_urls(self, page: Page, base_url: str) -> list[str]:
        """
        Navigates to store base URL or /products.json API to discover candidate PDP URLs.
        Deduplicates results and logs rejected candidates.
        """
        discovered_urls: list[str] = []
        rejected_candidates: list[dict[str, str]] = []

        # Strategy 1: Try Shopify products.json API
        from src.scanner.navigation_helper import navigate_with_retry
        products_json_url = urljoin(base_url, "/products.json?limit=10")
        try:
            response: Response | None = navigate_with_retry(page, products_json_url, wait_until="domcontentloaded", timeout=10000)
            if response and response.status == 200:
                data = response.json()
                products = data.get("products", [])
                for prod in products:
                    handle = prod.get("handle")
                    if handle:
                        pdp_url = urljoin(base_url, f"/products/{handle}")
                        valid, reason = self.is_valid_pdp_url(base_url, pdp_url)
                        if valid and pdp_url not in discovered_urls:
                            discovered_urls.append(pdp_url)
                            if len(discovered_urls) >= self.max_candidates:
                                break
                        elif not valid:
                            rejected_candidates.append({"url": pdp_url, "reason": reason})
        except Exception as exc:
            logger.debug("Shopify products.json discovery failed on '%s': %s", base_url, exc)

        if discovered_urls:
            return discovered_urls

        # Strategy 2: Fallback to DOM href links on homepage
        try:
            navigate_with_retry(page, base_url, wait_until="domcontentloaded", timeout=15000)
            href_elements = page.eval_on_selector_all("a[href]", "elements => elements.map(e => e.href)")
            for href in href_elements:
                full_url = urljoin(base_url, href)
                valid, reason = self.is_valid_pdp_url(base_url, full_url)
                if valid:
                    if full_url not in discovered_urls:
                        discovered_urls.append(full_url)
                        if len(discovered_urls) >= self.max_candidates:
                            break
                else:
                    rejected_candidates.append({"url": full_url, "reason": reason})
        except Exception as exc:
            logger.warning("DOM link discovery failed on '%s': %s", base_url, exc)

        if discovered_urls:
            return discovered_urls

        # Strategy 3: Domain-Agnostic Standard XML Sitemap Discovery (/sitemap.xml & /sitemap_products_1.xml)
        sitemap_candidates = [
            urljoin(base_url, "/sitemap_products_1.xml"),
            urljoin(base_url, "/sitemap.xml"),
        ]

        for sitemap_url in sitemap_candidates:
            try:
                response = navigate_with_retry(page, sitemap_url, wait_until="domcontentloaded", timeout=10000)
                if response and response.status == 200:
                    content = page.content()
                    # Extract URLs from XML sitemap or sitemap index via regex
                    urls_in_xml = re.findall(r"<loc>(.*?)</loc>", content, re.IGNORECASE)
                    
                    # If this is a sitemap index containing sub-sitemaps (e.g. product sitemaps)
                    sub_sitemaps = [u for u in urls_in_xml if "product" in u.lower() or "sitemap" in u.lower()]
                    for sub_url in sub_sitemaps[:3]:
                        try:
                            sub_resp = navigate_with_retry(page, sub_url, wait_until="domcontentloaded", timeout=10000)
                            if sub_resp and sub_resp.status == 200:
                                sub_content = page.content()
                                urls_in_xml.extend(re.findall(r"<loc>(.*?)</loc>", sub_content, re.IGNORECASE))
                        except Exception:
                            pass

                    for candidate in urls_in_xml:
                        candidate_clean = candidate.strip()
                        valid, reason = self.is_valid_pdp_url(base_url, candidate_clean)
                        if valid and candidate_clean not in discovered_urls:
                            discovered_urls.append(candidate_clean)
                            if len(discovered_urls) >= self.max_candidates:
                                break
                        elif not valid:
                            rejected_candidates.append({"url": candidate_clean, "reason": reason})

                    if discovered_urls:
                        logger.info("XML Sitemap Discovery successfully extracted %d PDP URLs from '%s'", len(discovered_urls), sitemap_url)
                        break
            except Exception as exc:
                logger.debug("XML Sitemap Discovery failed on '%s': %s", sitemap_url, exc)

        for rej in rejected_candidates[:10]:
            logger.debug("Rejected candidate PDP URL '%s': %s", rej["url"], rej["reason"])

        return discovered_urls

