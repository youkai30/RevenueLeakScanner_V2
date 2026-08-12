"""
tests/test_pdp_validation.py — Unit & Integration Test Suite for CONTRACT-PDP-001 PageValidator

Covers:
  1. REAL Shopify product page validation -> REAL_PRODUCT.
  2. Cloudflare challenge page validation -> CLOUDFLARE_BLOCKED.
  3. HTTP 404 / 500 error page validation -> ERROR.
  4. Shopify collection page validation -> NOT_PRODUCT.
  5. Blog article / editorial page validation -> NOT_PRODUCT.
  6. Ambiguous page with /products/ slug but insufficient product signals -> UNKNOWN.
  7. Architectural Integration Boundary Test:
     When PageValidator != REAL_PRODUCT:
       VariantMatrixScanner, BISChecker, and CROStackDetector DO NOT execute,
       and ZERO commercial opportunities are generated.
"""
from unittest.mock import MagicMock
import pytest
from src.ingestion.store_loader import StoreRecord
from src.scanner.core_scanner import IntegratedStoreScanner
from src.scanner.page_validator import PageState, PageValidationResult, PageValidator
from src.scanner.product_discovery import ProductDiscoveryEngine


# ---------------------------------------------------------------------------
# 1. PageValidator Unit Tests
# ---------------------------------------------------------------------------
def test_pdp_validator_real_product_page():
    """Verifies that a valid Shopify product page with multiple signals returns REAL_PRODUCT."""
    validator = PageValidator()

    class MockElem:
        def __init__(self, text=""):
            self._text = text
        def text_content(self):
            return self._text

    class DummyProductPage:
        def title(self):
            return "Men's Wool Runner | Allbirds"

        def query_selector(self, selector):
            if "cart/add" in selector or "product-form" in selector:
                return MockElem()
            if "og:type" in selector:
                return MockElem()
            return None

        def query_selector_all(self, selector):
            if "ld+json" in selector:
                return [MockElem('{"@context":"https://schema.org","@type":"Product","name":"Wool Runner"}')]
            return []

        def evaluate(self, script):
            if "ShopifyAnalytics" in script:
                return True
            return False

    dummy_page = DummyProductPage()
    res = validator.validate_page(dummy_page, "https://example.com/products/wool-runner")

    assert res.status == PageState.REAL_PRODUCT
    assert res.confidence >= 0.8
    assert "wool-runner" in res.url
    assert res.product_title == "Men's Wool Runner"


def test_pdp_validator_cloudflare_challenge_page():
    """Verifies that Cloudflare challenge pages return CLOUDFLARE_BLOCKED."""
    validator = PageValidator()

    class DummyCloudflarePage:
        def title(self):
            return "Connexion en cours de vérification..."

        def query_selector(self, selector):
            if "cf-browser-verification" in selector or "challenge-running" in selector:
                return True
            return None

        def query_selector_all(self, selector):
            return []

    dummy_page = DummyCloudflarePage()
    res = validator.validate_page(dummy_page, "https://drinkhydrant.com/products/variety-pack")

    assert res.status == PageState.CLOUDFLARE_BLOCKED
    assert res.confidence == 1.0
    assert any("Cloudflare" in r for r in res.reasons)


def test_pdp_validator_http_error_response():
    """Verifies that HTTP 404 / 500 error responses return ERROR status."""
    validator = PageValidator()

    class DummyErrorResponse:
        def __init__(self, status):
            self.status = status
            self.headers = {}

    class DummyPage:
        def title(self):
            return "404 Not Found"
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []

    dummy_page = DummyPage()

    # 404 Error
    resp_404 = DummyErrorResponse(404)
    res_404 = validator.validate_page(dummy_page, "https://example.com/products/missing", response=resp_404)
    assert res_404.status == PageState.ERROR

    # 500 Server Error
    resp_500 = DummyErrorResponse(500)
    res_500 = validator.validate_page(dummy_page, "https://example.com/products/error", response=resp_500)
    assert res_500.status == PageState.ERROR


def test_pdp_validator_collection_page_rejection():
    """Verifies that collection and non-product routes return NOT_PRODUCT."""
    validator = PageValidator()

    class DummyPage:
        def title(self):
            return "All Collections | Brand"
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []

    dummy_page = DummyPage()

    res_collection = validator.validate_page(dummy_page, "https://example.com/collections/frontpage")
    assert res_collection.status == PageState.NOT_PRODUCT

    res_blog = validator.validate_page(dummy_page, "https://example.com/blogs/news/announcement")
    assert res_blog.status == PageState.NOT_PRODUCT

    res_index = validator.validate_page(dummy_page, "https://example.com/products")
    assert res_index.status == PageState.NOT_PRODUCT


def test_pdp_validator_ambiguous_url_returns_unknown():
    """Verifies that a URL with /products/ slug but insufficient product signals returns UNKNOWN."""
    validator = PageValidator()

    class DummyAmbiguousPage:
        def title(self):
            return "Ambiguous Page"
        def query_selector(self, selector):
            return None  # No product form, no og:type
        def query_selector_all(self, selector):
            return []    # No JSON-LD
        def evaluate(self, script):
            return False

    dummy_page = DummyAmbiguousPage()
    res = validator.validate_page(dummy_page, "https://example.com/products/ambiguous-item")

    # Only 1 signal (/products/ in path), requires >= 2 -> UNKNOWN
    assert res.status == PageState.UNKNOWN
    assert res.confidence == 0.5
    assert any("Insufficient positive product signals" in r for r in res.reasons)


# ---------------------------------------------------------------------------
# 2. Architectural Integration Boundary Test
# ---------------------------------------------------------------------------
class DummyDiscoveryEngine(ProductDiscoveryEngine):
    def discover_pdp_urls(self, page, base_url):
        return [
            "https://example.com/products/cloudflare-page",
            "https://example.com/products/real-shoe"
        ]


def test_integration_boundary_non_product_blocks_primary_engines():
    """
    INTEGRATION TEST (CONTRACT-PDP-001):
    Proves that when PageValidator != REAL_PRODUCT:
      - Primary engines DO NOT execute
      - ZERO commercial opportunities (REVENUE_LEAK, CRO, BIS) are generated.
    """
    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())

    # Mock PageValidator to return CLOUDFLARE_BLOCKED for URL 1, REAL_PRODUCT for URL 2
    def mock_validate(page, url, response=None):
        if "cloudflare-page" in url:
            return PageValidationResult(
                status=PageState.CLOUDFLARE_BLOCKED,
                confidence=1.0,
                reasons=["Cloudflare block simulated"],
                url=url,
                product_title="Cloudflare Interstitial",
            )
        return PageValidationResult(
            status=PageState.REAL_PRODUCT,
            confidence=0.95,
            reasons=["Confirmed real product"],
            url=url,
            product_title="Real Shoe",
        )

    scanner.page_validator.validate_page = MagicMock(side_effect=mock_validate)

    class DummyPlaywrightPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Real Shoe"
        def query_selector_all(self, s):
            return []
        def query_selector(self, s):
            return None
        def evaluate(self, s):
            return False

    dummy_page = DummyPlaywrightPage()
    scan_context, _ = scanner.scan_store(dummy_page, store)

    assert len(scan_context.pdp_results) == 2

    # PDP 1 (Cloudflare Blocked):
    pdp1 = scan_context.pdp_results[0]
    assert pdp1.page_state == PageState.CLOUDFLARE_BLOCKED
    assert pdp1.scanned_variant == "Blocked / Non-Product Page"
    # ABSOLUTE ACCEPTANCE CRITERIA: 0 Opportunities generated on blocked page
    assert len(pdp1.opportunities) == 0

    # PDP 2 (Real Product):
    pdp2 = scan_context.pdp_results[1]
    assert pdp2.page_state == PageState.REAL_PRODUCT
    assert pdp2.product_name == "Real Shoe"


# ---------------------------------------------------------------------------
# 3. CONTRACT-PDP-001 Hardening & Safety Tests
# ---------------------------------------------------------------------------
def test_pdp_scan_result_requires_explicit_page_state():
    """Verifies CONTRACT-PDP-001: PDPScanResult MUST NOT silently default to REAL_PRODUCT."""
    from pydantic import ValidationError
    from src.scanner.models import PDPScanResult

    # Attempt instantiation without page_state MUST raise ValidationError
    with pytest.raises(ValidationError, match="page_state"):
        PDPScanResult(
            product_name="Unvalidated Page",
            product_url="https://example.com/item",
            scanned_variant="Default",
            out_of_stock=False,
            notify_button_detected=False,
            sold_out_detected=False,
        )

    # Explicit construction with page_state succeeds
    pdp = PDPScanResult(
        product_name="Validated Page",
        product_url="https://example.com/item",
        scanned_variant="Default",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        page_state=PageState.REAL_PRODUCT,
    )
    assert pdp.page_state == PageState.REAL_PRODUCT


def test_unknown_state_blocks_primary_engines():
    """Verifies that PageState.UNKNOWN blocks primary engines and yields 0 commercial opportunities."""
    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=["https://example.com/products/unknown"])

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.UNKNOWN,
        confidence=0.5,
        reasons=["Insufficient signals"],
        url="https://example.com/products/unknown",
        product_title="Unknown Page",
    ))

    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Unknown Page"

    scan_context, _ = scanner.scan_store(DummyPage(), store)
    assert len(scan_context.pdp_results) == 1
    pdp = scan_context.pdp_results[0]
    assert pdp.page_state == PageState.UNKNOWN
    assert len(pdp.opportunities) == 0


# ---------------------------------------------------------------------------
# 4. CONTRACT-STATE-001 3-State Detection Architecture Tests
# ---------------------------------------------------------------------------
def test_contract_state_001_selector_missing_yields_unknown():
    """CONTRACT-STATE-001: Missing CSS selector yields DetectionState.UNKNOWN (NOT FALSE)."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class EmptyPage:
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []

    detector = CROStackDetector(EmptyPage())
    res_review = detector.detect_review_state()
    res_upsell = detector.detect_upsell_state()
    res_sticky = detector.detect_sticky_atc_state()

    assert res_review.state == DetectionState.UNKNOWN
    assert res_upsell.state == DetectionState.UNKNOWN
    assert res_sticky.state == DetectionState.UNKNOWN


def test_contract_state_001_unknown_detector_state_yields_zero_opportunities():
    """CONTRACT-STATE-001: When detector returns UNKNOWN, 0 commercial opportunities are created."""
    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=["https://example.com/products/item"])

    # REAL_PRODUCT page but all detectors return UNKNOWN
    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT,
        confidence=0.9,
        reasons=["Valid product"],
        url="https://example.com/products/item",
        product_title="Test Item",
    ))

    class EmptyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Test Item"
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []

    scan_context, _ = scanner.scan_store(EmptyPage(), store)
    assert len(scan_context.pdp_results) == 1
    pdp = scan_context.pdp_results[0]
    # UNKNOWN detector states MUST NOT generate opportunities!
    assert len(pdp.opportunities) == 0


# ---------------------------------------------------------------------------
# 5. CONTRACT-VARIANT-001 OOS / Variant Identity Tests
# ---------------------------------------------------------------------------
def test_contract_variant_001_unselected_option_yields_unknown():
    """CONTRACT-VARIANT-001: Disabled ATC due to unselected option prerequisites yields UNKNOWN (NOT OOS)."""
    from src.scanner.variant_matrix import VariantMatrixScanner
    from src.scanner.detection_state import DetectionState

    class MockElem:
        def text_content(self):
            return "Select Size"

    class UnselectedOptionPage:
        def query_selector_all(self, s):
            if "select option" in s:
                return [MockElem()]
            return []
        def query_selector(self, s):
            if "button[name='add']" in s:
                return True
            return None

    scanner = VariantMatrixScanner(UnselectedOptionPage())
    v_name, v_id, res = scanner.discover_oos_variant_state()
    assert res.state == DetectionState.UNKNOWN
    assert "unselected option prerequisites" in res.details


def test_contract_variant_001_genuine_oos_selected_variant_yields_true():
    """CONTRACT-VARIANT-001: Verified unavailable selected SKU yields DetectionState.TRUE."""
    from src.scanner.variant_matrix import VariantMatrixScanner
    from src.scanner.detection_state import DetectionState

    class MockOptionElem:
        def is_disabled(self):
            return True
        def get_attribute(self, attr):
            if attr == "value":
                return "Size 10"
            if attr == "data-variant-id":
                return "var_12345"
            return None
        def text_content(self):
            return "Size 10 - Sold Out"
        def click(self, **kwargs):
            pass

    class OOSPage:
        def query_selector_all(self, s):
            if "select option" in s:
                return []
            return [MockOptionElem()]
        def query_selector(self, s):
            return None
        def wait_for_timeout(self, ms):
            pass

    scanner = VariantMatrixScanner(OOSPage())
    v_name, v_id, res = scanner.discover_oos_variant_state()
    assert res.state == DetectionState.TRUE
    assert v_name == "Size 10 - Sold Out"
    assert v_id == "var_12345"


def test_contract_variant_001_oos_unknown_never_generates_revenue_leak():
    """CONTRACT-VARIANT-001: OOS = UNKNOWN prevents REVENUE_LEAK opportunity creation."""
    from src.scanner.bis_checker import BISChecker
    from src.scanner.models import OpportunityType
    from src.scanner.detection_state import DetectionResult, DetectionState, DetectionFailureReason
    from unittest.mock import patch

    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=["https://example.com/products/item"])

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT, confidence=0.9, reasons=["Valid product"],
        url="https://example.com/products/item", product_title="Item",
    ))

    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Item"
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []

    with patch('src.scanner.core_scanner.VariantMatrixScanner') as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.inspect_variants.return_value = []
        mock_instance.discover_oos_variant_state.return_value = (
            "", "", DetectionResult(state=DetectionState.UNKNOWN, reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE, details="Unselected options")
        )
        scan_context, _ = scanner.scan_store(DummyPage(), store)

    assert len(scan_context.pdp_results) == 1
    pdp = scan_context.pdp_results[0]
    # ZERO REVENUE_LEAK opportunities MUST be created!
    rev_leaks = [opp for opp in pdp.opportunities if opp.opportunity_type == OpportunityType.REVENUE_LEAK]
    assert len(rev_leaks) == 0


# ---------------------------------------------------------------------------
# 6. CONTRACT-BIS-001 Back-In-Stock Test Matrix
# ---------------------------------------------------------------------------
def test_contract_bis_001_empty_variant_id_prevents_revenue_leak():
    """CONTRACT-BIS-001 Step 7: OOS TRUE with empty variant_id MUST NOT generate REVENUE_LEAK."""
    from src.scanner.models import OpportunityType
    from src.scanner.detection_state import DetectionResult, DetectionState, DetectionFailureReason
    from unittest.mock import patch

    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=["https://example.com/products/item"])

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT, confidence=0.9, reasons=["Valid product"],
        url="https://example.com/products/item", product_title="Item",
    ))

    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Item"
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []

    with patch('src.scanner.core_scanner.VariantMatrixScanner') as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.inspect_variants.return_value = []
        mock_instance.discover_oos_variant_state.return_value = (
            "Selected Variant", "", DetectionResult(state=DetectionState.TRUE, reason=DetectionFailureReason.FEATURE_ABSENT, details="OOS")
        )
        scan_context, _ = scanner.scan_store(DummyPage(), store)

    assert len(scan_context.pdp_results) == 1
    pdp = scan_context.pdp_results[0]
    rev_leaks = [opp for opp in pdp.opportunities if opp.opportunity_type == OpportunityType.REVENUE_LEAK]
    assert len(rev_leaks) == 0  # Blocked due to empty variant_id!


def test_contract_bis_001_verified_variant_oos_and_bis_false_creates_revenue_leak():
    """CONTRACT-BIS-001: Verified OOS + non-empty variant_id + BIS FALSE creates REVENUE_LEAK."""
    from src.scanner.models import OpportunityType
    from src.scanner.detection_state import DetectionResult, DetectionState, DetectionFailureReason
    from unittest.mock import patch

    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=["https://example.com/products/item"])

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT, confidence=0.9, reasons=["Valid product"],
        url="https://example.com/products/item", product_title="Item",
    ))

    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Item"
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []
        def inner_text(self, s):
            return ""

    with patch('src.scanner.core_scanner.VariantMatrixScanner') as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.inspect_variants.return_value = []
        mock_instance.discover_oos_variant_state.return_value = (
            "Size 10", "var_9988", DetectionResult(state=DetectionState.TRUE, reason=DetectionFailureReason.FEATURE_ABSENT, details="OOS")
        )
        scan_context, _ = scanner.scan_store(DummyPage(), store)

    assert len(scan_context.pdp_results) == 1
    pdp = scan_context.pdp_results[0]
    rev_leaks = [opp for opp in pdp.opportunities if opp.opportunity_type == OpportunityType.REVENUE_LEAK]
    assert len(rev_leaks) == 1
    assert rev_leaks[0].opportunity_type == OpportunityType.REVENUE_LEAK
    assert "var_9988" in rev_leaks[0].commercial_problem_summary

# ---------------------------------------------------------------------------
# 7. CONTRACT-REVIEW-001 Multi-Layer Review Test Matrix
# ---------------------------------------------------------------------------
def test_contract_review_001_json_ld_schema_yields_true():
    """CONTRACT-REVIEW-001: Layer 2 JSON-LD AggregateRating schema yields DetectionState.TRUE."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class MockElem:
        def text_content(self):
            return '{"@context":"https://schema.org","@type":"Product","aggregateRating":{"ratingValue":"4.8","reviewCount":"150"}}'

    class JSONLDPage:
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            if "ld+json" in s:
                return [MockElem()]
            return []

    detector = CROStackDetector(JSONLDPage())
    res = detector.detect_review_state()
    assert res.state == DetectionState.TRUE
    assert "JSON-LD AggregateRating" in res.details


def test_contract_review_001_shopify_analytics_metadata_yields_true():
    """CONTRACT-REVIEW-001: Layer 3 Shopify Analytics window metadata yields DetectionState.TRUE."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class AnalyticsPage:
        def query_selector(self, s):
            return None
        def query_selector_all(self, s):
            return []
        def evaluate(self, script):
            if "ShopifyAnalytics" in script:
                return True
            return False

    detector = CROStackDetector(AnalyticsPage())
    res = detector.detect_review_state()
    assert res.state == DetectionState.TRUE
    assert "Shopify Analytics Review Metadata" in res.details



def test_contract_review_001_weak_generic_class_without_content_yields_unknown():
    """CONTRACT-REVIEW-001 Hardened: Weak class name alone (e.g. '.star-rating' without digits/stars) returns UNKNOWN."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class WeakElem:
        def is_visible(self):
            return True
        def text_content(self):
            return "Read our review policy"  # No numeric rating, no star symbol!

    class WeakPage:
        def query_selector(self, s):
            if "star-rating" in s:
                return WeakElem()
            return None
        def query_selector_all(self, s):
            return []

    detector = CROStackDetector(WeakPage())
    res = detector.detect_review_state()
    assert res.state == DetectionState.UNKNOWN


def test_contract_review_001_unknown_review_yields_zero_social_proof_opportunities():
    """CONTRACT-REVIEW-001 Hardened: UNKNOWN review state creates ZERO MISSING_SOCIAL_PROOF opportunities."""
    from src.scanner.models import OpportunityType
    from src.scanner.detection_state import DetectionResult, DetectionState, DetectionFailureReason
    from unittest.mock import patch

    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=["https://example.com/products/item"])

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT, confidence=0.9, reasons=["Valid product"],
        url="https://example.com/products/item", product_title="Item",
    ))

    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Item"

    with patch('src.scanner.core_scanner.CROStackDetector') as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.detect_review_state.return_value = DetectionResult(
            state=DetectionState.UNKNOWN, reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE, details="Absence unprovable"
        )
        mock_instance.detect_upsell_state.return_value = DetectionResult(state=DetectionState.UNKNOWN, reason=DetectionFailureReason.SELECTOR_NOT_FOUND, details="")
        mock_instance.detect_sticky_atc_state.return_value = DetectionResult(state=DetectionState.UNKNOWN, reason=DetectionFailureReason.SELECTOR_NOT_FOUND, details="")
        scan_context, _ = scanner.scan_store(DummyPage(), store)

    assert len(scan_context.pdp_results) == 1
    pdp = scan_context.pdp_results[0]
    social_proof_opps = [opp for opp in pdp.opportunities if opp.opportunity_type == OpportunityType.MISSING_SOCIAL_PROOF]
# ---------------------------------------------------------------------------
# 8. CONTRACT-DEDUP-001 Store-Scoped SKU Deduplication Test Matrix
# ---------------------------------------------------------------------------
def test_contract_dedup_001_duplicate_variant_id_across_urls_deduplicated():
    """CONTRACT-DEDUP-001: Same variant ID discovered through two PDP URLs produces exactly ONE PDPScanResult."""
    from src.scanner.detection_state import DetectionResult, DetectionState, DetectionFailureReason
    from unittest.mock import patch

    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT, confidence=0.9, reasons=["Valid product"],
        url="https://example.com/products/item-a", product_title="Item A",
    ))
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=[
        "https://example.com/products/item-a",
        "https://example.com/products/item-b",
    ])

    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Item"

    with patch('src.scanner.core_scanner.VariantMatrixScanner') as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.inspect_variants.return_value = []
        mock_instance.discover_oos_variant_state.return_value = (
            "Size 10", "var_7788", DetectionResult(state=DetectionState.TRUE, reason=DetectionFailureReason.FEATURE_ABSENT, details="OOS")
        )
        scan_context, _ = scanner.scan_store(DummyPage(), store)

    assert len(scan_context.pdp_results) == 1  # Deduplicated to 1 record!
    assert scan_context.pdp_results[0].scanned_variant_id == "var_7788"


def test_contract_dedup_001_different_variant_ids_remain_separate():
    """CONTRACT-DEDUP-001: Legitimate different variant IDs remain separate PDPScanResult records."""
    from src.scanner.detection_state import DetectionResult, DetectionState, DetectionFailureReason
    from unittest.mock import patch

    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT, confidence=0.9, reasons=["Valid product"],
        url="https://example.com/products/item", product_title="Item",
    ))
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=[
        "https://example.com/products/item-1",
        "https://example.com/products/item-2",
    ])

    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Item"

    with patch('src.scanner.core_scanner.VariantMatrixScanner') as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.inspect_variants.return_value = []
        mock_instance.discover_oos_variant_state.side_effect = [
            ("Size 9", "var_1111", DetectionResult(state=DetectionState.TRUE, reason=DetectionFailureReason.FEATURE_ABSENT, details="OOS")),
            ("Size 10", "var_2222", DetectionResult(state=DetectionState.TRUE, reason=DetectionFailureReason.FEATURE_ABSENT, details="OOS")),
        ]
        scan_context, _ = scanner.scan_store(DummyPage(), store)

    assert len(scan_context.pdp_results) == 2  # Both legitimate variants preserved!
    assert scan_context.pdp_results[0].scanned_variant_id == "var_1111"
    assert scan_context.pdp_results[1].scanned_variant_id == "var_2222"


# ---------------------------------------------------------------------------
# 9. CONTRACT-UPSELL-001 & CONTRACT-STICKY-ATC-001 Phase 1H Test Matrix
# ---------------------------------------------------------------------------
def test_contract_upsell_001_footer_recommendations_not_true_upsell():
    """CONTRACT-UPSELL-001: Recommendation containers inside footer/nav MUST NOT yield TRUE."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class FooterElem:
        def is_visible(self):
            return True
        def evaluate(self, script):
            if "closest" in script:
                return True  # Is in footer
            return False

    class FooterPage:
        def query_selector(self, s):
            if "product-recommendations" in s:
                return FooterElem()
            return None

    detector = CROStackDetector(FooterPage())
    res = detector.detect_upsell_state()
    assert res.state == DetectionState.UNKNOWN


def test_contract_upsell_001_verified_upsell_yields_true():
    """CONTRACT-UPSELL-001: Verified upsell module containing product links outside footer yields TRUE."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class ValidUpsellElem:
        def is_visible(self):
            return True
        def evaluate(self, script):
            if "closest" in script:
                return False  # Not in footer
            if "querySelectorAll" in script:
                return True   # Has product links
            return False

    class UpsellPage:
        def query_selector(self, s):
            if "product-recommendations" in s:
                return ValidUpsellElem()
            return None

    detector = CROStackDetector(UpsellPage())
    res = detector.detect_upsell_state()
    assert res.state == DetectionState.TRUE
    assert "Verified upsell" in res.details


def test_contract_sticky_atc_001_normal_static_atc_yields_unknown():
    """CONTRACT-STICKY-ATC-001: Normal static Add to Cart button MUST NOT produce Sticky ATC TRUE."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class StaticPage:
        def query_selector(self, s):
            # STICKY_ATC_SELECTORS fail to match static form button
            return None

    detector = CROStackDetector(StaticPage())
    res = detector.detect_sticky_atc_state()
    assert res.state == DetectionState.UNKNOWN


def test_contract_sticky_atc_001_verified_fixed_sticky_atc_yields_true():
    """CONTRACT-STICKY-ATC-001: Verified sticky ATC element with position:fixed/sticky yields TRUE."""
    from src.scanner.cro_stack_detector import CROStackDetector
    from src.scanner.detection_state import DetectionState

    class StickyATCElem:
        def is_visible(self):
            return True
        def text_content(self):
            return "Add to Cart - $45"
        def query_selector(self, s):
            return None
        def evaluate(self, script):
            if "getComputedStyle" in script:
                return "fixed"
            return None

    class StickyPage:
        def query_selector(self, s):
            if "sticky-atc" in s:
                return StickyATCElem()
            return None

    detector = CROStackDetector(StickyPage())
    res = detector.detect_sticky_atc_state()
    assert res.state == DetectionState.TRUE
    assert "Verified Sticky ATC" in res.details


def test_phase_1h_production_boundary_scan_store_unknown_yields_zero_opportunities():
    """Phase 1H Production Boundary: UNKNOWN upsell/sticky_atc states through scan_store() yield 0 commercial opportunities."""
    from src.scanner.models import OpportunityType
    from src.scanner.detection_state import DetectionResult, DetectionState, DetectionFailureReason
    from unittest.mock import patch

    store = StoreRecord(domain="example.com", base_url="https://example.com")
    scanner = IntegratedStoreScanner(discovery_engine=DummyDiscoveryEngine())
    scanner.discovery_engine.discover_pdp_urls = MagicMock(return_value=["https://example.com/products/item"])

    scanner.page_validator.validate_page = MagicMock(return_value=PageValidationResult(
        status=PageState.REAL_PRODUCT, confidence=0.9, reasons=["Valid product"],
        url="https://example.com/products/item", product_title="Item",
    ))

    # All detectors return UNKNOWN
    class DummyPage:
        def goto(self, url, **kwargs):
            return None
        def title(self):
            return "Item"

    with patch('src.scanner.core_scanner.CROStackDetector') as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.detect_review_state.return_value = DetectionResult(state=DetectionState.UNKNOWN, reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE, details="")
        mock_instance.detect_upsell_state.return_value = DetectionResult(state=DetectionState.UNKNOWN, reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE, details="")
        mock_instance.detect_sticky_atc_state.return_value = DetectionResult(state=DetectionState.UNKNOWN, reason=DetectionFailureReason.INSUFFICIENT_EVIDENCE, details="")
        scan_context, _ = scanner.scan_store(DummyPage(), store)

    assert len(scan_context.pdp_results) == 1
    pdp = scan_context.pdp_results[0]
    
    upsell_opps = [opp for opp in pdp.opportunities if opp.opportunity_type == OpportunityType.MISSING_UPSELL]
    sticky_opps = [opp for opp in pdp.opportunities if opp.opportunity_type == OpportunityType.MISSING_STICKY_ATC]
    
    assert len(upsell_opps) == 0
    assert len(sticky_opps) == 0








