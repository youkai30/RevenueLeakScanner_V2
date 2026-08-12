import pytest
from src.scanner.cro_stack_detector import CROStackDetector
from src.scanner.bis_checker import BISChecker
from src.scanner.variant_matrix import VariantMatrixScanner
from src.scanner.detection_state import DetectionState
from src.scanner.page_validator import PageState
from src.evidence.evidence_collector import EvidenceCollector
from src.scanner.models import PDPScanResult, TransientScanContext, CommercialOpportunity, OpportunityType, EvidenceStatus
from src.scanner.page_validator import PageState
from src.evidence.models import BoundingBoxMap, CommercialImpact
from src.evidence.session_serializer import EvidenceBuilder
from src.commercial.lead_exporter import CommercialLeadExporter
from src.scanner.browser_factory import BrowserFactory

@pytest.fixture(scope="module")
def browser():
    bf = BrowserFactory(headless=True)
    bf.start()
    yield bf
    bf.close()


@pytest.fixture
def page(browser):
    context = browser.create_mobile_context()
    p = context.new_page()
    yield p
    p.close()
    context.close()


# ---------------------------------------------------------------------------
# CORE-01: Evidence Screenshot Integrity Tests
# ---------------------------------------------------------------------------
def test_core_01_scroll_integrity(page):
    # Setup scrollable page
    page.set_viewport_size({"width": 375, "height": 667})
    html_long = """
    <html>
      <body style="margin: 0; padding: 0;">
        <div style="height: 3000px;">
          <button id="primary-atc" style="position: absolute; top: 100px;">Add to Cart</button>
          <div id="spacer" style="height: 1500px;">Spacer</div>
          <button id="scrolled-element" style="position: absolute; top: 1600px;">Scrolled Area</button>
        </div>
      </body>
    </html>
    """
    page.set_content(html_long)
    page.wait_for_timeout(200)

    collector = EvidenceCollector(page)
    # Scroll to 1200
    png_bytes, duration = collector.capture_screenshot_bytes(scroll_y=1200)
    
    # Verify browser scrolled and actual offset matches
    assert collector.last_scroll_y > 0
    assert collector.last_scroll_y == 1200
    
    # Test short page safety
    page.set_content("<html><body style='height: 300px;'><button>Short</button></body></html>")
    page.wait_for_timeout(200)
    png_bytes, duration = collector.capture_screenshot_bytes(scroll_y=1200)
    # Since page height is short, actual scroll should be 0
    assert collector.last_scroll_y == 0


# ---------------------------------------------------------------------------
# CORE-02 & CORE-03: BIS / Newsletter Contamination & Async Bounded Polling
# ---------------------------------------------------------------------------
def test_core_02_03_bis_remediation(page):
    checker = BISChecker(page)

    # Test 1: Footer newsletter only ("get notified" / "subscribe") -> FALSE
    html_newsletter = """
    <html>
      <body>
        <main>
          <button>Add to Cart</button>
        </main>
        <footer>
          <form class="newsletter-form">
            <p>Sign up to our newsletter and get notified about new arrivals!</p>
            <input type="email" name="contact[email]" placeholder="Email address" />
            <button type="submit">Subscribe</button>
          </form>
        </footer>
      </body>
    </html>
    """
    page.set_content(html_newsletter)
    page.wait_for_timeout(200)
    assert checker.check_notify_state().state == DetectionState.FALSE

    # Test 2: Genuine BIS in buy-box -> TRUE
    html_genuine_bis = """
    <html>
      <body>
        <main>
          <div class="product-buy-box">
            <h3>Product Title</h3>
            <form action="/cart/add" method="post">
              <button disabled>Sold Out</button>
            </form>
            <div class="bis-trigger-container">
              <p>Email me when back in stock:</p>
              <input type="email" placeholder="email@address.com" />
              <button class="klaviyo-bis-trigger">Notify Me When Available</button>
            </div>
          </div>
        </main>
      </body>
    </html>
    """
    page.set_content(html_genuine_bis)
    page.wait_for_timeout(200)
    assert checker.check_notify_state().state == DetectionState.TRUE

    # Test 3: Newsletter + Genuine BIS -> TRUE (Genuine BIS wins)
    html_both = """
    <html>
      <body>
        <main>
          <div class="product-buy-box">
            <button class="klaviyo-bis-trigger">Notify Me when available</button>
          </div>
        </main>
        <footer>
          <p>Get notified about new arrivals</p>
        </footer>
      </body>
    </html>
    """
    page.set_content(html_both)
    page.wait_for_timeout(200)
    assert checker.check_notify_state().state == DetectionState.TRUE

    # Test 4: Dynamic BIS Modal (appears after 1000ms delay) -> TRUE (Successful polling)
    html_dynamic_base = """
    <html>
      <body>
        <div id="bis-modal-placeholder"></div>
      </body>
    </html>
    """
    page.set_content(html_dynamic_base)
    
    # Inject BIS modal after 1000ms using JS setTimeout
    page.evaluate("""() => {
        setTimeout(() => {
            const container = document.getElementById("bis-modal-placeholder");
            container.innerHTML = `
                <div class="klaviyo-bis-modal" style="display: block;">
                  <h3>Notify Me when available</h3>
                  <input type="email" name="email" />
                  <button>Submit</button>
                </div>
            `;
        }, 1000);
    }""")
    
    # Running notify state check must wait, poll, and find it
    assert checker.check_notify_state().state == DetectionState.TRUE


# ---------------------------------------------------------------------------
# CORE-04: Silent Variant Scanner Failure
# ---------------------------------------------------------------------------
def test_core_04_variant_uncertainty(page, dummy_png_bytes):
    scanner = VariantMatrixScanner(page)

    # Test 1: True variantless product (only Default Title) -> is_extraction_uncertain is False
    html_default = """
    <html>
      <body>
        <script type="application/json" id="ProductJson">
          {"variants": [{"id": 12345, "title": "Default Title", "available": true}]}
        </script>
      </body>
    </html>
    """
    page.set_content(html_default)
    page.wait_for_timeout(200)
    variants = scanner.inspect_variants()
    assert not scanner.is_extraction_uncertain(variants)

    # Test 2: Custom variant picker exists in DOM but extraction fails -> is_extraction_uncertain is True
    html_custom = """
    <html>
      <body>
        <main>
          <div class="custom-variant-selectors">
            <!-- Non-standard swatches without standard variant metadata -->
            <div class="swatch-element" data-val="Red" style="display: block;">Red</div>
            <div class="swatch-element" data-val="Blue" style="display: block;">Blue</div>
            <select name="options[Color]" class="single-option-selector">
              <option value="Red">Red</option>
              <option value="Blue">Blue</option>
            </select>
          </div>
        </main>
      </body>
    </html>
    """
    page.set_content(html_custom)
    page.wait_for_timeout(200)
    
    # Mock JS variants returning empty or None, but single-option-selector is visible in DOM
    # Let's inspect variants: if extraction returns empty list, it must be uncertain!
    # Because selector "select:not([name*='country'])..." is visible in DOM
    assert scanner.is_extraction_uncertain([])

    # Test 3: Downstream lead export propagation of PageState.PARTIALLY_INSPECTED
    pdp = PDPScanResult(
        product_name="Test Product",
        product_url="https://teststore.com/products/test",
        scanned_variant="",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        page_state=PageState.PARTIALLY_INSPECTED, # Marks it uncertain!
        variants_inspected=1,
        variants_oos=0,
        opportunities=[]
    )
    
    context = TransientScanContext(domain="teststore.com", pdp_results=[pdp])
    commercial = CommercialImpact(
        est_monthly_traffic=10000,
        oos_frequency_pct=0.0,
        variants_inspected=1,
        variants_oos=0,
        est_monthly_loss_usd=0.0,
        lead_priority="LOW",
        confidence_score=0.8
    )
    
    import uuid
    # Serialize finding and bundle
    builder = EvidenceBuilder()
    finding, _, _, _, _ = builder.build_finding(pdp, dummy_png_bytes, BoundingBoxMap(), uuid.uuid4())
    bundle = builder.compile_and_save_session("teststore.com", context, commercial, [(pdp, dummy_png_bytes, BoundingBoxMap())])
    
    exporter = CommercialLeadExporter()
    record = exporter.assemble_lead(bundle)
    
    # Record must be marked C — NOT SELLABLE, not a confirmed clean/safe $0.00 lead, and manual review required
    assert record.lead_class == "C — NOT SELLABLE"
    assert record.manual_review_required is True
    assert record.lead_type_category == "BLOCKED_OR_UNVERIFIED"
