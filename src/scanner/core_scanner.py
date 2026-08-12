"""
src/scanner/core_scanner.py — Scanner Orchestration Engine

Layer 2: Core Store Scanner Orchestrator
"""
import logging
from playwright.sync_api import Page

from src.ingestion.store_loader import StoreRecord
from src.scanner.bis_checker import BISChecker
from src.scanner.cro_stack_detector import CROStackDetector
from src.scanner.models import (
    CommercialOpportunity,
    EvidenceStatus,
    OpportunityType,
    PDPScanResult,
    TransientScanContext,
)


from src.scanner.product_discovery import ProductDiscoveryEngine
from src.scanner.variant_matrix import VariantMatrixScanner
from src.scanner.page_validator import PageState, PageValidator
from src.scanner.detection_state import DetectionState

logger = logging.getLogger(__name__)


class IntegratedStoreScanner:
    """
    Orchestrates target store scanning across discovery, variant inspection, BIS detection, and CRO stack auditing.
    Outputs a TransientScanContext.
    Does NOT calculate financial loss, generate PDFs/HTML, or write SessionBundle artifacts.
    """

    def __init__(self, discovery_engine: ProductDiscoveryEngine | None = None) -> None:
        self.discovery_engine = discovery_engine or ProductDiscoveryEngine(max_candidates=3)
        self.page_validator = PageValidator()

    def scan_store(self, page: Page, store_record: StoreRecord) -> TransientScanContext:
        """
        Orchestrates scanning for a validated StoreRecord.
        Gracefully handles individual PDP failures without terminating the store run.
        """
        context = TransientScanContext(domain=store_record.domain)
        pdp_urls = self.discovery_engine.discover_pdp_urls(page, store_record.base_url)

        if not pdp_urls:
            logger.info("No candidate PDP URLs discovered for domain '%s'", store_record.domain)
            return context, page


        from src.scanner.navigation_helper import navigate_with_retry
        for url in pdp_urls:
            try:
                response = navigate_with_retry(page, url, wait_until="domcontentloaded", timeout=15000)
                
                # CONTRACT-PDP-001: Centralized Safety Boundary & Page Type Classifier
                validation = self.page_validator.validate_page(page, url, response=response)
                
                if validation.status != PageState.REAL_PRODUCT:
                    logger.warning(
                        "PDP Safety Gate BLOCKED non-product page '%s' (Status: %s, Reasons: %s). Skipping primary engines.",
                        url, validation.status.value, "; ".join(validation.reasons)
                    )
                    # Non-REAL_PRODUCT pages MUST NOT enter primary engines (CONTRACT-PDP-001)
                    # Record diagnostic non-commercial result with 0 opportunities
                    pdp_result = PDPScanResult(
                        product_name=validation.product_title or (page.title() or store_record.domain).split("|")[0].strip(),
                        product_url=url,
                        scanned_variant="Blocked / Non-Product Page",
                        out_of_stock=False,
                        notify_button_detected=False,
                        sold_out_detected=False,
                        page_state=validation.status,
                        opportunities=[],  # 0 Commercial Opportunities (Strict CONTRACT-PDP-001 enforcement)
                    )
                    context.pdp_results.append(pdp_result)
                    continue

                product_title = validation.product_title or (page.title() or store_record.domain).split("|")[0].strip()

                # Dismiss overlays, cookie banners, and popups before running detectors and screenshots
                try:
                    from src.scanner.navigation_helper import dismiss_overlays_and_popups
                    dismiss_overlays_and_popups(page)
                except Exception as exc:
                    logger.warning("Failed to dismiss overlays on '%s': %s", url, exc)

                # DOM extraction of contacts (Priority 3)
                if "contact_info" not in context.metadata:
                    try:
                        from urllib.parse import urlparse, urljoin
                        contacts = page.evaluate("""() => {
                            let result = {
                                email: null,
                                email_source: "NOT_FOUND",
                                phone: null,
                                phone_source: "NOT_FOUND",
                                contact_page: null,
                                contact_page_source: "NOT_FOUND",
                                instagram_url: null,
                                facebook_url: null,
                                linkedin_url: null,
                                tiktok_url: null,
                                youtube_url: null,
                                x_url: null
                            };
                            let mailtoEl = document.querySelector('a[href^="mailto:"]');
                            if (mailtoEl) {
                                let href = mailtoEl.getAttribute('href') || '';
                                let email = href.replace(/^mailto:/i, '').split('?')[0].trim();
                                if (email && email.includes('@')) {
                                    result.email = email;
                                    result.email_source = "MAILTO";
                                }
                            }
                            let telEl = document.querySelector('a[href^="tel:"]');
                            if (telEl) {
                                let href = telEl.getAttribute('href') || '';
                                let phone = href.replace(/^tel:/i, '').split('?')[0].trim();
                                if (phone) {
                                    result.phone = phone;
                                    result.phone_source = "TEL_LINK";
                                }
                            }
                            let links = Array.from(document.querySelectorAll('a'));
                            for (let link of links) {
                                let href = link.getAttribute('href') || '';
                                let hrefLower = href.toLowerCase();
                                let text = (link.textContent || '').toLowerCase();
                                if (
                                    (hrefLower.includes('/contact') || text.includes('contact us') || text === 'contact') && 
                                    !hrefLower.includes('mailto:') && 
                                    !hrefLower.includes('tel:')
                                ) {
                                    result.contact_page = href;
                                    result.contact_page_source = "FOOTER_LINK";
                                    break;
                                }
                            }
                            for (let link of links) {
                                let href = link.getAttribute('href') || '';
                                let hrefLower = href.toLowerCase();
                                if (hrefLower.includes('instagram.com/')) {
                                    result.instagram_url = href;
                                } else if (hrefLower.includes('facebook.com/')) {
                                    result.facebook_url = href;
                                } else if (hrefLower.includes('linkedin.com/')) {
                                    result.linkedin_url = href;
                                } else if (hrefLower.includes('tiktok.com/')) {
                                    result.tiktok_url = href;
                                } else if (hrefLower.includes('youtube.com/')) {
                                    result.youtube_url = href;
                                } else if (hrefLower.includes('x.com/') || hrefLower.includes('twitter.com/')) {
                                    result.x_url = href;
                                }
                            }
                            return result;
                        }""")
                        if contacts:
                            if contacts.get("contact_page"):
                                parsed_pdp = urlparse(url)
                                base_url = f"{parsed_pdp.scheme}://{parsed_pdp.netloc}"
                                contacts["contact_page"] = urljoin(base_url, contacts["contact_page"])
                            from src.enrichment.post_scan_enricher import PostScanEnricher
                            enricher = PostScanEnricher()
                            for k in ["instagram_url", "facebook_url", "linkedin_url", "tiktok_url", "youtube_url", "x_url"]:
                                if contacts.get(k):
                                    platform_name = k.replace("_url", "")
                                    if platform_name == "instagram":
                                        platform_name = "instagram.com"
                                    elif platform_name == "facebook":
                                        platform_name = "facebook.com"
                                    elif platform_name == "linkedin":
                                        platform_name = "linkedin.com"
                                    elif platform_name == "tiktok":
                                        platform_name = "tiktok.com"
                                    elif platform_name == "youtube":
                                        platform_name = "youtube.com"
                                    elif platform_name == "x":
                                        platform_name = "x.com"
                                    contacts[k] = enricher.sanitize_social_url(platform_name, contacts[k])
                            context.metadata["contact_info"] = contacts
                    except Exception as ev_exc:
                        logger.warning("Failed DOM extraction of contacts: %s", ev_exc)

                # 1. Variant Inspection (CONTRACT-VARIANT-001)
                variant_scanner = VariantMatrixScanner(page)
                inspected_variants = variant_scanner.inspect_variants()
                scanned_variant, scanned_variant_id, oos_det_result = variant_scanner.discover_oos_variant_state()

                out_of_stock = (oos_det_result.state == DetectionState.TRUE)
                variants_inspected = max(len(inspected_variants), 1)
                variants_oos = 1 if out_of_stock else 0

                validation_status = validation.status
                if variant_scanner.is_extraction_uncertain(inspected_variants):
                    validation_status = PageState.PARTIALLY_INSPECTED

                # 2. BIS Modal Inspection (3-State CONTRACT-STATE-001)
                bis_checker = BISChecker(page)
                bis_det_result = bis_checker.check_notify_state(out_of_stock=out_of_stock)
                notify_detected = (bis_det_result.state == DetectionState.TRUE)
                _, sold_out_detected = bis_checker.check_notify_mechanism()

                # 3. CRO Stack Detection (3-State CONTRACT-STATE-001)
                cro_detector = CROStackDetector(page)
                review_det_result = cro_detector.detect_review_state()
                review_widget_detected = (review_det_result.state == DetectionState.TRUE)
                review_platform = review_det_result.details if review_widget_detected else ""
                review_count = review_det_result.count

                upsell_det_result = cro_detector.detect_upsell_state()
                upsell_detected = (upsell_det_result.state == DetectionState.TRUE)

                sticky_det_result = cro_detector.detect_sticky_atc_state()
                sticky_atc_detected = (sticky_det_result.state == DetectionState.TRUE)

                # Independent Commercial Opportunity Evaluation Protocol (CONTRACT-STATE-001)
                opportunities: list[CommercialOpportunity] = []

                # Engine 1: Revenue Leak (CONTRACT-BIS-001 / Step 7)
                # REQUIRES:
                # 1. Confirmed OOS (TRUE)
                # 2. Verified Variant Identity (scanned_variant_id is non-empty)
                # 3. Confirmed BIS Absence (FALSE)
                # If OOS or BIS is UNKNOWN or variant_id is missing, 0 opportunities generated.
                if (
                    oos_det_result.state == DetectionState.TRUE
                    and bool(scanned_variant_id)
                    and bis_det_result.state == DetectionState.FALSE
                ):
                    opportunities.append(
                        CommercialOpportunity(
                            opportunity_type=OpportunityType.REVENUE_LEAK,
                            commercial_problem_summary=f"Out-of-Stock variant '{scanned_variant}' (ID: {scanned_variant_id}) has no Back-in-Stock capture modal",
                            sellable_service_angle="Back-In-Stock Restock Capture Flow",
                            is_valid_opportunity=True,
                            evidence_status=EvidenceStatus.VERIFIED,
                            inspected_surfaces=["buy_box", "variant_matrix", "bis_modal"],
                        )
                    )


                # Engine 2: Missing Social Proof
                # REQUIRES: Confirmed Review Absence (FALSE).
                # CONTRACT-STATE-001 REQUIREMENT: If review_det_result.state == UNKNOWN -> 0 opportunities!
                if review_det_result.state == DetectionState.FALSE:
                    opportunities.append(
                        CommercialOpportunity(
                            opportunity_type=OpportunityType.MISSING_SOCIAL_PROOF,
                            commercial_problem_summary="Buy Box fold lacks immediate customer review rating badges",
                            sellable_service_angle="Social Proof & Review Automation Setup",
                            is_valid_opportunity=True,
                            evidence_status=EvidenceStatus.VERIFIED,
                            inspected_surfaces=["buy_box_stars", "review_summary_badge"],
                        )
                    )

                # Engine 3: Missing Upsell
                # REQUIRES: Confirmed Upsell Absence (FALSE).
                # CONTRACT-STATE-001 REQUIREMENT: If upsell_det_result.state == UNKNOWN -> 0 opportunities!
                if upsell_det_result.state == DetectionState.FALSE:
                    opportunities.append(
                        CommercialOpportunity(
                            opportunity_type=OpportunityType.MISSING_UPSELL,
                            commercial_problem_summary="Product Detail Page lacks Cross-Sell / Upsell AOV expansion recommendations",
                            sellable_service_angle="Cart Drawer & Cross-Sell CRO Optimization",
                            is_valid_opportunity=True,
                            evidence_status=EvidenceStatus.PARTIALLY_VERIFIED,
                            inspected_surfaces=["pdp_buy_box", "recommendation_modules", "cart_drawer_container"],
                        )
                    )

                # Engine 4: Missing Sticky ATC
                # REQUIRES: Confirmed Sticky ATC Absence (FALSE).
                # CONTRACT-STATE-001 REQUIREMENT: If sticky_det_result.state == UNKNOWN -> 0 opportunities!
                if sticky_det_result.state == DetectionState.FALSE:
                    opportunities.append(
                        CommercialOpportunity(
                            opportunity_type=OpportunityType.MISSING_STICKY_ATC,
                            commercial_problem_summary="Scrollable mobile Product Detail Page lacks persistent Sticky Add-to-Cart UX",
                            sellable_service_angle="Mobile Sticky ATC & Sticky Nav UX Optimization",
                            is_valid_opportunity=True,
                            evidence_status=EvidenceStatus.VERIFIED,
                            inspected_surfaces=["mobile_viewport_375x667", "page_scroll_context", "lower_viewport_fold"],
                        )
                    )





                # 4. Immediate 1:1 Evidence Capture (CONTRACT-EVIDENCE-001)
                pdp_png_bytes: bytes | None = None
                pdp_boxes = None
                
                scroll_y_param = 0
                if any(opp.opportunity_type == OpportunityType.MISSING_STICKY_ATC for opp in opportunities):
                    scroll_y_param = 1200
                
                actual_scroll_y = 0
                val_identity = True
                val_buy_box = True
                val_social = True
                val_upsell = True
                try:
                    from src.evidence.evidence_collector import EvidenceCollector
                    evidence_collector = EvidenceCollector(page)
                    pdp_png_bytes, _ = evidence_collector.capture_screenshot_bytes(scroll_y=scroll_y_param, opportunities=opportunities, product_title=product_title)
                    actual_scroll_y = getattr(evidence_collector, "last_scroll_y", 0)
                    val_identity = getattr(evidence_collector, "product_identity_visible", True)
                    val_buy_box = getattr(evidence_collector, "buy_box_visible", True)
                    val_social = getattr(evidence_collector, "relevant_social_proof_region_visible", True)
                    val_upsell = getattr(evidence_collector, "relevant_upsell_region_visible", True)
                    pdp_boxes = evidence_collector.capture_bounding_boxes()
                except Exception as ev_exc:
                    logger.warning("Immediate evidence capture failed for PDP '%s': %s", url, ev_exc)

                inspected_prices = [
                    v.price_usd
                    for v in inspected_variants
                    if getattr(v, "price_usd", None) is not None and v.price_usd > 0.0
                ]

                pdp_result = PDPScanResult(
                    product_name=product_title,
                    product_url=url,
                    scanned_variant=scanned_variant,
                    scanned_variant_id=scanned_variant_id,
                    out_of_stock=out_of_stock,
                    notify_button_detected=notify_detected,
                    sold_out_detected=sold_out_detected,
                    page_state=validation_status,
                    review_widget_detected=review_widget_detected,
                    review_platform=review_platform,
                    review_count=review_count,
                    upsell_detected=upsell_detected,
                    sticky_atc_detected=sticky_atc_detected,
                    variants_inspected=variants_inspected,
                    variants_oos=variants_oos,
                    png_bytes=pdp_png_bytes,
                    bounding_boxes=pdp_boxes,
                    opportunities=opportunities,
                    scroll_y=actual_scroll_y,
                    inspected_prices=inspected_prices,
                    bis_detection_state=bis_det_result.state.value,
                    review_detection_state=review_det_result.state.value,
                    upsell_detection_state=upsell_det_result.state.value,
                    sticky_atc_detection_state=sticky_det_result.state.value,
                    has_unresolved_modal=getattr(page, "has_unresolved_modal", False),
                    product_identity_visible=val_identity,
                    buy_box_visible=val_buy_box,
                    relevant_social_proof_region_visible=val_social,
                    relevant_upsell_region_visible=val_upsell,
                )

                # CONTRACT-DEDUP-001: Store-scoped SKU Deduplication Boundary
                # Deduplicate by canonical identity (domain, scanned_variant_id)
                # If variant_id is non-empty and already present in context.pdp_results, skip appending duplicate record.
                if scanned_variant_id:
                    existing_variant_ids = {p.scanned_variant_id for p in context.pdp_results if p.scanned_variant_id}
                    if scanned_variant_id in existing_variant_ids:
                        logger.info("Duplicate variant ID '%s' detected on domain '%s'. Skipping duplicate record.", scanned_variant_id, store_record.domain)
                        continue

                context.pdp_results.append(pdp_result)





            except Exception as exc:
                session_str = str(getattr(page, "session_id", "None"))
                logger.error(
                    "ERROR | session=%s | component=core_scanner | url=%s | operation=scan_pdp | error=%s | message=%s",
                    session_str, url, type(exc).__name__, str(exc)
                )
                # Safely discard damaged execution context and open a clean Page
                try:
                    ctx = page.context
                    try:
                        page.close()
                    except Exception:
                        pass
                    # Keep session_id on the new page
                    page = ctx.new_page()
                    page.session_id = session_str
                except Exception as recovery_exc:
                    logger.warning("Could not recover page context for '%s': %s", url, recovery_exc)
                continue



        return context, page

