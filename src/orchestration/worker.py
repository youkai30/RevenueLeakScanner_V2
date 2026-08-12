"""
src/orchestration/worker.py — Process-Isolated Worker Execution Runner

Layer 6: Worker Execution Sandbox
"""
import logging
import time
from pathlib import Path
from uuid import uuid4

from src.commercial.impact_calculator import CommercialImpactCalculator
from src.evidence.evidence_collector import EvidenceCollector
from src.evidence.models import BoundingBoxMap
from src.evidence.session_serializer import EvidenceBuilder
from src.evidence.session_storage import SessionStorage
from src.ingestion.store_loader import StoreRecord
from src.ingestion.tenant_config import TenantConfig
from src.orchestration.models import StoreExecutionResult, StoreExecutionStatus
from src.presentation.drivers.pdf_driver import PDFDriver
from src.presentation.drivers.teaser_driver import TeaserDriver
from src.presentation.payload_compiler import PayloadCompiler
from src.scanner.browser_factory import BrowserFactory
from src.scanner.core_scanner import IntegratedStoreScanner

logger = logging.getLogger(__name__)


def execute_single_store_worker(
    store_record_dict: dict,
    tenant_config_dict: dict | None = None,
    measured_traffic: int | None = None,
    max_retries: int = 2,
) -> dict:
    """
    Standalone, serializable worker function executed inside an isolated ProcessPoolExecutor worker process.
    
    GUARANTEES:
      - Process-local Playwright initialization via BrowserFactory
      - 100% browser context and page cleanup in finally block
      - Zero live Playwright objects crossing process boundaries (returns raw dict)
      - Failure isolation: catches exceptions and returns structured StoreExecutionResult dict
      - Calls existing Phase C (CommercialImpactCalculator), Phase D (EvidenceBuilder), Phase E (PDF/Teaser Drivers)
    """
    start_time = time.perf_counter()
    store = StoreRecord.model_validate(store_record_dict)
    tenant = TenantConfig.model_validate(tenant_config_dict) if tenant_config_dict else TenantConfig()

    browser_factory = BrowserFactory()

    session_id = uuid4()

    for attempt in range(1, max_retries + 1):
        context = None
        page = None
        try:
            browser_factory.start()
            context = browser_factory.create_mobile_context()
            page = context.new_page()
            # Attach session_id for structured log tracking down the pipeline
            page.session_id = session_id

            # 1. Layer 2 Scanning (Phase B)
            scanner = IntegratedStoreScanner()
            transient_context, page = scanner.scan_store(page, store)

            # 2. Layer 3 Commercial Calculation (Phase C)
            commercial_calc = CommercialImpactCalculator()
            commercial_impact = commercial_calc.build_commercial_impact_dto(
                scan_context=transient_context,
                measured_traffic=measured_traffic,
            )

            # 3. Layer 3 Evidence Compilation (CONTRACT-EVIDENCE-001: 1:1 Evidence Binding)
            pdp_evidence_items = []
            if transient_context.pdp_results:
                for pdp in transient_context.pdp_results:
                    if pdp.png_bytes is not None:
                        boxes = pdp.bounding_boxes or BoundingBoxMap()
                        pdp_evidence_items.append((pdp, pdp.png_bytes, boxes))
                    else:
                        logger.warning("No immediate PNG bytes captured for PDP '%s'. Skipping evidence item generation.", pdp.product_url)

            # 4. Layer 3 Evidence Serialization & Storage (Phase D)
            storage = SessionStorage()
            evidence_builder = EvidenceBuilder(storage=storage)

            build_id = uuid4()

            viewport_str = "375x667"
            if page and page.viewport_size:
                viewport_str = f"{page.viewport_size['width']}x{page.viewport_size['height']}"

            session_bundle = evidence_builder.compile_and_save_session(
                domain=store.domain,
                transient_context=transient_context,
                commercial_impact=commercial_impact,
                pdp_evidence_items=pdp_evidence_items,
                session_id=session_id,
                build_id=build_id,
                viewport=viewport_str,
            )

            # 5. Layer 5 Presentation Output Drivers (Phase E)
            compiler = PayloadCompiler(tenant_config=tenant)
            pdf_payload = compiler.compile_pdf_payload(session_bundle)
            email_payload = compiler.compile_email_payload(session_bundle)

            pdf_driver = PDFDriver()
            pdf_path = pdf_driver.generate_pdf(session_bundle, pdf_payload)

            teaser_driver = TeaserDriver()
            teaser_path = teaser_driver.generate_teaser(session_bundle, email_payload)

            exec_duration = max(1, int((time.perf_counter() - start_time) * 1000))
            session_json_path = storage.get_session_dir(store.domain, session_id) / f"session_{session_id}.json"

            result = StoreExecutionResult(
                domain=store.domain,
                status=StoreExecutionStatus.SUCCESS,
                session_id=str(session_id),
                build_id=str(build_id),
                duration_ms=exec_duration,
                session_json_path=str(session_json_path),
                pdf_report_path=str(pdf_path),
                teaser_image_path=str(teaser_path),
                est_monthly_loss_usd=commercial_impact.est_monthly_loss_usd,
                lead_priority=commercial_impact.lead_priority,
            )
            return result.model_dump(mode="json")

        except Exception as exc:
            logger.warning("Worker execution failed for '%s' (Attempt %d/%d): %s", store.domain, attempt, max_retries, str(exc))

            if attempt == max_retries:
                exec_duration = max(1, int((time.perf_counter() - start_time) * 1000))
                exc_str = str(exc).lower()
                is_anti_bot = "cloudflare" in exc_str or "anti-bot" in exc_str or "antibot" in exc_str or "challenge" in exc_str or "captcha" in exc_str or "access denied" in exc_str

                status = StoreExecutionStatus.BLOCKED if is_anti_bot else StoreExecutionStatus.FAILED
                error_type = "AntiBotBlockError" if is_anti_bot else exc.__class__.__name__

                result = StoreExecutionResult(
                    domain=store.domain,
                    status=status,
                    duration_ms=exec_duration,
                    error_type=error_type,
                    error_message=str(exc),
                )
                return result.model_dump(mode="json")
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            browser_factory.close()
