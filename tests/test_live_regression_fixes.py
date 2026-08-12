"""
tests/test_live_regression_fixes.py — Integration Tests for Live Regression Fixes

Covers:
  A. Shopify variant JSON parsing (ShopifyAnalytics & embedded JSON).
  B. Modern Shopify variant DOM extraction bypassing legacy selectors.
  C. Unselected prerequisites preventing Add to Cart (UNKNOWN).
  D. Selected out-of-stock variant verification (TRUE).
  E. Review widget detection (AggregateRating -> TRUE, Insufficient -> UNKNOWN).
  F. Upsell recommendation module detection (TRUE, Footer -> UNKNOWN).
  G. Sticky ATC verification (Sticky -> TRUE, Static -> UNKNOWN, Absence -> FALSE).
  H. Narrowed sold_out_detected signal verification.
  I. Product discovery candidate URL filtering.
"""
import pytest
from src.scanner.browser_factory import BrowserFactory
from src.scanner.variant_matrix import VariantMatrixScanner
from src.scanner.cro_stack_detector import CROStackDetector
from src.scanner.bis_checker import BISChecker
from src.scanner.product_discovery import ProductDiscoveryEngine
from src.scanner.detection_state import DetectionState


@pytest.fixture(scope="module")
def browser():
    bf = BrowserFactory(headless=True)
    bf.start()
    yield bf
    bf.close()


@pytest.fixture
def page(browser):
    context = browser.create_mobile_context()  # Use mobile context for sticky ATC checks
    p = context.new_page()
    yield p
    p.close()
    context.close()


# ---------------------------------------------------------------------------
# Test A & B & D: JS Variant Extraction & Real OOS Selection
# ---------------------------------------------------------------------------
def test_js_variant_extraction_and_oos_selection(page):
    # Setup page with ShopifyAnalytics product metadata representing an OOS variant
    html = """
    <html>
      <head>
        <script>
          window.ShopifyAnalytics = {
            meta: {
              product: {
                variants: [
                  { id: 12345, title: "Size 8 / Black", available: true },
                  { id: 67890, title: "Size 9 / Black", available: false }
                ]
              }
            }
          };
        </script>
      </head>
      <body>
        <div>Product Page</div>
      </body>
    </html>
    """
    page.set_content(html)
    scanner = VariantMatrixScanner(page)

    # Test inspect_variants (A)
    records = scanner.inspect_variants()
    assert len(records) == 2
    assert records[0].variant_id == "12345"
    assert records[0].is_available is True
    assert records[1].variant_id == "67890"
    assert records[1].is_available is False

    # Test discover_oos_variant_state (D)
    variant_name, variant_id, result = scanner.discover_oos_variant_state()
    assert result.state == DetectionState.TRUE
    assert variant_name == "Size 9 / Black"
    assert variant_id == "67890"


# ---------------------------------------------------------------------------
# Test C: Unselected Options Prerequisite Verification (UNKNOWN)
# ---------------------------------------------------------------------------
def test_unselected_options_guard(page):
    html = """
    <html>
      <body>
        <select>
          <option value="">Select Size</option>
          <option value="1">Small</option>
        </select>
        <button class="add-to-cart" disabled>Add to Cart</button>
      </body>
    </html>
    """
    page.set_content(html)
    scanner = VariantMatrixScanner(page)

    variant_name, variant_id, result = scanner.discover_oos_variant_state()
    assert result.state == DetectionState.UNKNOWN
    assert "unselected option prerequisites" in result.details


# ---------------------------------------------------------------------------
# Test E: Review Verification
# ---------------------------------------------------------------------------
def test_review_detection_states(page):
    detector = CROStackDetector(page)

    # 1. JSON-LD AggregateRating -> TRUE
    html_json_ld = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "aggregateRating": {
              "@type": "AggregateRating",
              "ratingValue": "4.5",
              "reviewCount": "23"
            }
          }
        </script>
      </head>
    </html>
    """
    page.set_content(html_json_ld)
    assert detector.detect_review_state().state == DetectionState.TRUE

    # 2. Text count pattern match in body -> TRUE
    html_text = "<html><body><div>Based on 523 reviews</div></body></html>"
    page.set_content(html_text)
    assert detector.detect_review_state().state == DetectionState.TRUE

    # 3. Insufficient evidence -> UNKNOWN (absence unprovable)
    html_empty = "<html><body><div>Plain text only</div></body></html>"
    page.set_content(html_empty)
    assert detector.detect_review_state().state == DetectionState.UNKNOWN


# ---------------------------------------------------------------------------
# Test F: Upsell Verification
# ---------------------------------------------------------------------------
def test_upsell_recommendations(page):
    detector = CROStackDetector(page)

    # 1. Real recommendations section -> TRUE
    html_real = """
    <html>
      <body>
        <div class="product-recommendations">
          <a href="/products/other-item">Other Product</a>
          <img src="other.jpg">
        </div>
      </body>
    </html>
    """
    page.set_content(html_real)
    assert detector.detect_upsell_state().state == DetectionState.TRUE

    # 2. Recommendation in footer -> UNKNOWN (Footer gets ignored)
    html_footer = """
    <html>
      <body>
        <footer>
          <div class="product-recommendations">
            <a href="/products/other-item">Other Product</a>
          </div>
        </footer>
      </body>
    </html>
    """
    page.set_content(html_footer)
    assert detector.detect_upsell_state().state == DetectionState.UNKNOWN


# ---------------------------------------------------------------------------
# Test G: Sticky ATC Verification
# ---------------------------------------------------------------------------
def test_sticky_atc_detection(page):
    detector = CROStackDetector(page)

    # 1. Valid sticky ATC -> TRUE
    page.set_viewport_size({"width": 375, "height": 667})
    html_sticky = """
    <html>
      <body>
        <div class="sticky-atc" style="position: fixed; bottom: 0;">
          <button>Add to Cart</button>
        </div>
      </body>
    </html>
    """
    page.set_content(html_sticky)
    page.wait_for_timeout(200)
    assert detector.detect_sticky_atc_state().state == DetectionState.TRUE

    # 2. Normal static ATC on a short page -> UNKNOWN
    page.set_viewport_size({"width": 375, "height": 400})
    html_static = """
    <html style="height: 200px; max-height: 200px; overflow: hidden;">
      <body style="height: 200px; max-height: 200px; margin: 0; padding: 0;">
        <button name="add">Add to Cart</button>
      </body>
    </html>
    """
    page.set_content(html_static)
    page.wait_for_timeout(200)
    assert detector.detect_sticky_atc_state().state == DetectionState.UNKNOWN

    # 3. Normal static ATC on a long page -> FALSE (computed absence verified)
    page.set_viewport_size({"width": 375, "height": 1500})
    html_long = """
    <html>
      <body style="margin: 0; padding: 0;">
        <div style="height: 1500px;">
          <button name="add" style="position: static;">Add to Cart</button>
        </div>
      </body>
    </html>
    """
    page.set_content(html_long)
    page.wait_for_timeout(200)
    assert detector.detect_sticky_atc_state().state == DetectionState.FALSE


# ---------------------------------------------------------------------------
# Test H: Narrowed sold_out_detected
# ---------------------------------------------------------------------------
def test_narrowed_sold_out_detected(page):
    checker = BISChecker(page)

    # 1. Generic disabled button (without text) -> sold_out_detected must be False
    html_generic = "<html><body><button disabled>Submit Form</button></body></html>"
    page.set_content(html_generic)
    _, sold_out_detected = checker.check_notify_mechanism()
    assert sold_out_detected is False

    # 2. Explicit sold-out class -> TRUE
    html_class = "<html><body><div class=\"sold-out\">Unavailable</div></body></html>"
    page.set_content(html_class)
    _, sold_out_detected = checker.check_notify_mechanism()
    assert sold_out_detected is True

    # 3. Disabled ATC with explicit text -> TRUE
    html_atc_text = "<html><body><button class=\"add-to-cart\" disabled>Sold Out</button></body></html>"
    page.set_content(html_atc_text)
    _, sold_out_detected = checker.check_notify_mechanism()
    assert sold_out_detected is True


# ---------------------------------------------------------------------------
# Test I: Product Discovery Candidate Filter
# ---------------------------------------------------------------------------
def test_product_discovery_slug_filtering():
    engine = ProductDiscoveryEngine()

    # Valid product path
    valid, reason = engine.is_valid_pdp_url("test.com", "https://test.com/products/luxe-sheet-set")
    assert valid is True
    assert "products" in reason

    # Content template pseudo-products -> must be rejected
    valid_content, reason_content = engine.is_valid_pdp_url("test.com", "https://test.com/products/content-luxe-bed-category")
    assert valid_content is False
    assert "content-" in reason_content

    # Size-guides -> must be rejected
    valid_size, reason_size = engine.is_valid_pdp_url("test.com", "https://test.com/products/size-guide")
    assert valid_size is False
    assert "size-guide" in reason_size
