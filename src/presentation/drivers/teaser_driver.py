"""
src/presentation/drivers/teaser_driver.py — Cold Outreach Teaser PNG Driver

Layer 5: Presentation Teaser Generator Driver
"""
import io
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from src.config import REPORTS_DIR, SESSIONS_DIR
from src.evidence.models import SessionBundle
from src.exceptions import InvalidBundleException, SessionNotFoundException
from src.presentation.models import EmailPayload
from src.presentation.payload_compiler import PayloadCompiler

logger = logging.getLogger(__name__)


class TeaserDriver:
    """
    Generates a cold-outreach teaser image snippet (teaser.png) from verified evidence.
    CRITICAL RULE: NEVER modifies source evidence PNG files. Reads source PNG read-only
    and writes derived teaser PNG to storage/reports/<domain>/<session_id>/teaser.png.
    """

    def __init__(self, reports_dir: Path | None = None, sessions_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or REPORTS_DIR
        self.sessions_dir = sessions_dir or SESSIONS_DIR

    def generate_teaser(self, session_bundle: SessionBundle, payload: EmailPayload) -> Path:
        """
        Loads source PNG read-only, crops upper PDP callout region, renders callout overlay,
        and saves separate teaser PNG to storage/reports/<domain>/<session_id>/teaser.png.
        """
        session_str = str(session_bundle.session_id)
        domain = session_bundle.domain

        # Source evidence PNG path (finding-specific evidence screenshot)
        primary_finding = session_bundle.findings[0] if session_bundle.findings else None
        if primary_finding and primary_finding.evidence and primary_finding.evidence.image_file:
            source_png_path = self.sessions_dir / domain / session_str / primary_finding.evidence.image_file
        else:
            source_png_path = self.sessions_dir / domain / session_str / f"session_{session_str}.png"

        if not source_png_path.exists():
            # Fallback to generic session PNG if the UUID one doesn't exist
            fallback_png = self.sessions_dir / domain / session_str / f"session_{session_str}.png"
            if fallback_png.exists():
                source_png_path = fallback_png
            else:
                raise SessionNotFoundException(f"Source evidence PNG missing: {source_png_path}")

        # Target report directory
        target_dir = self.reports_dir / domain / session_str
        target_dir.mkdir(parents=True, exist_ok=True)
        teaser_path = target_dir / "teaser.png"

        # Read source PNG strictly read-only
        with open(source_png_path, "rb") as f:
            png_bytes = f.read()

        # Inspect opportunities to determine if this is a healthy benchmark or a leak/opportunity
        opp_type = None
        has_any_opp = False

        for f in session_bundle.findings:
            opps = getattr(f, "opportunities", [])
            if opps:
                has_any_opp = True
                if not opp_type:
                    opp_dict = opps[0] if isinstance(opps[0], dict) else opps[0].model_dump(mode="json")
                    opp_type = opp_dict.get("opportunity_type")

        if not opp_type and primary_finding and primary_finding.out_of_stock and not primary_finding.notify_button_detected:
            opp_type = "REVENUE_LEAK"
            has_any_opp = True

        # Dynamic BoundingBox Map Consumption & Viewport Scroll mapping
        headline_finding = payload.headline_finding
        box_to_use = None

        if headline_finding:
            finding_obj = session_bundle.findings[0] if session_bundle.findings else None
            if finding_obj and finding_obj.bounding_boxes:
                bmap = finding_obj.bounding_boxes
                # Prefer reviews for social proof, upsell for upsell, otherwise fallback
                if opp_type == "MISSING_SOCIAL_PROOF":
                    # Use actual reviews box if exists, otherwise use expected_social_proof_region
                    # NEVER fallback to buy_box for MISSING_SOCIAL_PROOF - that would be misleading
                    box_to_use = bmap.reviews or bmap.expected_social_proof_region
                elif opp_type == "MISSING_UPSELL":
                    box_to_use = bmap.upsell
                elif opp_type == "MISSING_STICKY_ATC":
                    box_to_use = bmap.sticky_atc
                else:
                    box_to_use = bmap.cta or bmap.buy_box or bmap.notify

        scroll_y = 0
        if primary_finding and primary_finding.evidence:
            scroll_y = getattr(primary_finding.evidence, "scroll_y", 0)

        buf = io.BytesIO(png_bytes)
        with Image.open(buf) as img:
            width, height = img.size
            
            # Perform cropping centered around highlight rect if we have box coordinates
            if box_to_use and has_any_opp:
                scale_x = width / 375.0
                scale_y = height / 667.0
                
                box_x = int(box_to_use.x * scale_x)
                # Map from absolute document Y to viewport coordinate Y in screenshot
                box_y = int((box_to_use.y - scroll_y) * scale_y)
                box_w = int(box_to_use.width * scale_x)
                box_h = int(box_to_use.height * scale_y)
                
                # Center the 600px crop around the highlight box center
                crop_y1 = max(0, min(height - 600, box_y + (box_h // 2) - 300))
                crop_y2 = crop_y1 + 600
                
                cropped_img = img.crop((0, crop_y1, width, crop_y2)).copy()
                
                box_y_adjusted = box_y - crop_y1
                highlight_rect = [(box_x, box_y_adjusted), (box_x + box_w, box_y_adjusted + box_h)]
            else:
                crop_y1 = 0
                crop_y2 = min(600, height)
                cropped_img = img.crop((0, crop_y1, width, crop_y2)).copy()
                
                rel_x1 = int(width * 0.55)
                rel_y1 = int((crop_y2 - crop_y1) * 0.20)
                rel_x2 = int(width * 0.95)
                rel_y2 = int((crop_y2 - crop_y1) * 0.45)
                highlight_rect = [(rel_x1, rel_y1), (rel_x2, rel_y2)]

        # Create overlay canvas on top of cropped copy
        draw = ImageDraw.Draw(cropped_img)

        # Draw header banner (Red for leak/opportunity, Green for healthy benchmark)
        banner_height = 40
        if has_any_opp:
            draw.rectangle([(0, 0), (width, banner_height)], fill=(220, 38, 38))  # Red header banner
        else:
            draw.rectangle([(0, 0), (width, banner_height)], fill=(22, 163, 74))  # Green header banner

        if not has_any_opp:
            headline_text = f"CONVERSION AUDIT: High-Performance UX Verified on {domain}"
        elif opp_type == "REVENUE_LEAK" and session_bundle.commercial.est_monthly_loss_usd > 0:
            loss_str = f"${session_bundle.commercial.est_monthly_loss_usd:,.0f}"
            headline_text = f"REVENUE LEAK DETECTED: Est. {loss_str} / month lost revenue on {domain}"
        elif opp_type == "MISSING_SOCIAL_PROOF":
            headline_text = f"SOCIAL PROOF OPPORTUNITY DETECTED: Missing Customer Reviews on {domain}"
        elif opp_type == "MISSING_UPSELL":
            headline_text = f"UPSELL OPPORTUNITY DETECTED: Missing Cross-Sell Recommendations on {domain}"
        elif opp_type == "MISSING_STICKY_ATC":
            headline_text = f"STICKY ATC OPPORTUNITY DETECTED: Missing Mobile Sticky Add-To-Cart on {domain}"
        else:
            headline_text = f"CONVERSION OPPORTUNITY DETECTED: CRO Optimization Flow on {domain}"

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        draw.text((15, 12), headline_text, fill=(255, 255, 255), font=font)

        # Draw highlight callout box outline (only if opportunities exist and evidence is valid)
        has_valid_evidence = primary_finding.evidence.valid if (primary_finding and primary_finding.evidence) else False
        if has_any_opp and has_valid_evidence:
            draw.rectangle(highlight_rect, outline=(220, 38, 38), width=4)

        # Save brand new teaser PNG file separately
        cropped_img.save(teaser_path, format="PNG", optimize=True)
        logger.info("Cold outreach teaser PNG generated at: '%s'", teaser_path)

        return teaser_path
