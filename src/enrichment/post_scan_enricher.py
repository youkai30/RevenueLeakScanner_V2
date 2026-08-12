"""
src/enrichment/post_scan_enricher.py — Isolated Post-Scan Commercial Lead Enricher

Extracts company name, email, phone, contact page, social handles, and country metadata
from SessionBundle DOM findings without modifying core scan engines.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from src.evidence.models import SessionBundle

logger = logging.getLogger(__name__)

# Blacklisted company names
COMPANY_BLACKLIST = {
    "home", "welcome", "shopify", "online store", "page not found", "cart",
    "checkout", "search", "account", "login", "register"
}

# Country lookup maps
TLD_COUNTRY_MAP = {
    "uk": ("United Kingdom", "GB"),
    "co.uk": ("United Kingdom", "GB"),
    "de": ("Germany", "DE"),
    "fr": ("France", "FR"),
    "se": ("Sweden", "SE"),
    "no": ("Norway", "NO"),
    "dk": ("Denmark", "DK"),
    "fi": ("Finland", "FI"),
    "nl": ("Netherlands", "NL"),
    "ca": ("Canada", "CA"),
    "au": ("Australia", "AU"),
    "nz": ("New Zealand", "NZ"),
    "es": ("Spain", "ES"),
    "it": ("Italy", "IT"),
    "pt": ("Portugal", "PT"),
    "pl": ("Poland", "PL"),
    "ch": ("Switzerland", "CH"),
    "at": ("Austria", "AT"),
    "be": ("Belgium", "BE"),
    "ie": ("Ireland", "IE"),
    "jp": ("Japan", "JP"),
}

LANG_COUNTRY_MAP = {
    "sv-se": ("Sweden", "SE"),
    "da-dk": ("Denmark", "DK"),
    "nb-no": ("Norway", "NO"),
    "de-de": ("Germany", "DE"),
    "fr-fr": ("France", "FR"),
    "it-it": ("Italy", "IT"),
    "es-es": ("Spain", "ES"),
    "en-gb": ("United Kingdom", "GB"),
    "en-ca": ("Canada", "CA"),
    "fr-ca": ("Canada", "CA"),
    "en-au": ("Australia", "AU"),
    "en-nz": ("New Zealand", "NZ"),
}


class PostScanEnricher:
    """
    Stateless, post-scan enrichment parser.
    Operates strictly AFTER SessionBundle persistence.
    """

    def enrich_bundle(self, bundle: SessionBundle) -> dict[str, Any]:
        enrichment_errors: list[str] = []
        start_ts = datetime.now(timezone.utc).isoformat()

        # Target metadata defaults
        company_name = None
        company_name_source = "NOT_FOUND"

        contact_email = None
        contact_email_source = "NOT_FOUND"

        contact_page = None
        contact_page_source = "NOT_FOUND"

        contact_phone = None
        contact_phone_source = "NOT_FOUND"

        country_name = None
        country_code = None
        country_source = "UNKNOWN"
        country_confidence = "NONE"

        instagram_url = None
        facebook_url = None
        linkedin_url = None
        tiktok_url = None
        youtube_url = None
        x_url = None

        try:
            # Load extracted contact info from bundle if present (Priority 3)
            contact_info_dict = getattr(bundle, "contact_info", {}) or {}

            contact_email = contact_info_dict.get("email")
            contact_email_source = contact_info_dict.get("email_source", "NOT_FOUND") if contact_email else "NOT_FOUND"

            contact_page = contact_info_dict.get("contact_page")
            contact_page_source = contact_info_dict.get("contact_page_source", "NOT_FOUND") if contact_page else "NOT_FOUND"

            contact_phone = contact_info_dict.get("phone")
            contact_phone_source = contact_info_dict.get("phone_source", "NOT_FOUND") if contact_phone else "NOT_FOUND"

            instagram_url = contact_info_dict.get("instagram_url")
            facebook_url = contact_info_dict.get("facebook_url")
            linkedin_url = contact_info_dict.get("linkedin_url")
            tiktok_url = contact_info_dict.get("tiktok_url")
            youtube_url = contact_info_dict.get("youtube_url")
            x_url = contact_info_dict.get("x_url")

            # 1. Extract Country / Geography from TLD
            domain_parts = bundle.domain.lower().split(".")
            if len(domain_parts) >= 2:
                tld = ".".join(domain_parts[1:]) if len(domain_parts) > 2 and domain_parts[-2] in ["co", "com", "net", "org"] else domain_parts[-1]
                if tld in TLD_COUNTRY_MAP:
                    country_name, country_code = TLD_COUNTRY_MAP[tld]
                    country_source = "TLD"
                    country_confidence = "HIGH"

            # 2. Extract Store / Company Brand Name (DEF-01 Fix: Domain/Store context, NOT product titles)
            if bundle.domain:
                company_name, company_name_source = self._derive_company_name_from_domain(bundle.domain)

            # 3. Extract Product URL for Contact Context (DEF-02 Fix: Provenance accuracy)
            if not contact_page:
                for finding in bundle.findings:
                    if finding.product_url:
                        parsed_pdp = urlparse(finding.product_url)
                        base_url = f"{parsed_pdp.scheme}://{parsed_pdp.netloc}"

                        # Standard contact page inference fallback
                        contact_page = urljoin(base_url, "/pages/contact")
                        contact_page_source = "INFERRED_DOMAIN_PATH"
                        break

            # 4. Determine Enrichment Success Status (DEF-03 Fix: Require actual contactability)
            has_contact_data = bool(contact_email or contact_phone or instagram_url or facebook_url or linkedin_url or x_url)
            if has_contact_data and company_name:
                status = "SUCCESS"
            elif company_name or contact_page:
                status = "PARTIAL"
            else:
                status = "PARTIAL"

        except Exception as exc:
            domain_name = bundle.domain if bundle else "UNKNOWN"
            logger.warning("Post-scan enrichment exception for '%s': %s", domain_name, str(exc))
            enrichment_errors.append(f"Enrichment exception: {str(exc)}")
            status = "FAILED"


        return {
            "company_name": company_name,
            "company_name_source": company_name_source,
            "contact_email": contact_email,
            "contact_email_source": contact_email_source,
            "contact_page": contact_page,
            "contact_page_source": contact_page_source,
            "contact_phone": contact_phone,
            "contact_phone_source": contact_phone_source,
            "country_name": country_name,
            "country_code": country_code,
            "country_source": country_source,
            "country_confidence": country_confidence,
            "instagram_url": instagram_url,
            "facebook_url": facebook_url,
            "linkedin_url": linkedin_url,
            "tiktok_url": tiktok_url,
            "youtube_url": youtube_url,
            "x_url": x_url,
            "enrichment_attempted": True,
            "enrichment_status": status,
            "enrichment_timestamp": start_ts,
            "enrichment_errors": enrichment_errors,
        }

    def _derive_company_name_from_domain(self, domain: str) -> tuple[str, str]:
        if not domain:
            return "Unknown Store", "NOT_FOUND"
        clean = domain.lower().strip()
        for prefix in ["https://", "http://", "www."]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
        base_name = clean.split(".")[0]
        formatted_name = base_name.replace("-", " ").replace("_", " ").title()
        return formatted_name, "DOMAIN_NAME"

    def _clean_company_name(self, raw_title: str) -> str | None:
        if not raw_title or not isinstance(raw_title, str):
            return None

        # Split title by common delimiters
        title_segment = re.split(r"[|\-—]", raw_title)[0].strip()
        if not title_segment or title_segment.lower() in COMPANY_BLACKLIST:
            return None

        if 2 <= len(title_segment) <= 60:
            return title_segment
        return None

    def sanitize_social_url(self, platform: str, url: str) -> str | None:
        """Strips query parameters and validates social media profile URLs."""
        if not url or not isinstance(url, str):
            return None

        url_lower = url.lower()
        if platform not in url_lower:
            return None

        # Rejection of homepages and generic sharing endpoints
        if platform == "instagram.com" and (url_lower.rstrip("/") in ["https://instagram.com", "https://www.instagram.com", "http://instagram.com"]):
            return None
        if platform == "facebook.com" and ("sharer" in url_lower or url_lower.rstrip("/") in ["https://facebook.com", "https://www.facebook.com"]):
            return None
        if platform == "linkedin.com" and ("sharearticle" in url_lower or url_lower.rstrip("/") in ["https://linkedin.com", "https://www.linkedin.com"]):
            return None
        if platform == "x.com" and ("intent" in url_lower or url_lower.rstrip("/") in ["https://x.com", "https://twitter.com"]):
            return None

        # Strip tracking params
        parsed = urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        return clean_url
