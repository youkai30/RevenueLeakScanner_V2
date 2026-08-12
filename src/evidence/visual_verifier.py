"""
src/evidence/visual_verifier.py — Screenshot Stream Integrity & Canvas Verifier

Layer 3: Evidence Integrity Verification
"""
import io
import logging
from PIL import Image

from src.config import MIN_VIEWPORT_HEIGHT, MIN_VIEWPORT_WIDTH
from src.evidence.checksum import calculate_png_hash_hex
from src.exceptions import EvidenceTamperedException

logger = logging.getLogger(__name__)


class VisualVerifier:
    """
    Verifies screenshot PNG binary byte stream integrity and dimensions.
    STRICTLY READ-ONLY: MUST NOT mutate image pixels, crop, annotate, or alter PNG bytes.
    """

    def verify_png_bytes(
        self,
        png_bytes: bytes,
        min_width: int = MIN_VIEWPORT_WIDTH,
        min_height: int = MIN_VIEWPORT_HEIGHT,
    ) -> tuple[bool, str, int, int, str]:
        """
        Validates PNG byte stream, dimensions, extrema canvas check, and returns metadata.
        Returns tuple of (valid: bool, reason: str, width: int, height: int, sha256_hash: str).
        """
        if not png_bytes or len(png_bytes) == 0:
            return False, "Empty or zero-byte PNG stream", 0, 0, ""

        sha256_hash = calculate_png_hash_hex(png_bytes)

        try:
            buf = io.BytesIO(png_bytes)
            with Image.open(buf) as img:
                img.verify()  # Verify image stream integrity

            # Re-open after verify() to inspect properties
            buf.seek(0)
            with Image.open(buf) as img:
                width, height = img.size
                format_type = img.format

                if format_type != "PNG":
                    return False, f"Image format must be PNG, got: {format_type}", width, height, sha256_hash

                if width < min_width or height < min_height:
                    return (
                        False,
                        f"Image dimensions ({width}x{height}) below required minimum ({min_width}x{min_height})",
                        width,
                        height,
                        sha256_hash,
                    )

                # Canvas Extrema Check (Blank/Uniform Color Detection)
                extrema = img.getextrema()
                if extrema:
                    # Check if all color channels have zero variance (blank single-color canvas)
                    is_blank = True
                    for channel_ext in extrema:
                        if isinstance(channel_ext, tuple) and channel_ext[0] != channel_ext[1]:
                            is_blank = False
                            break
                    if is_blank:
                        return False, "Image is a blank uniform-color canvas", width, height, sha256_hash

                return True, "OK", width, height, sha256_hash

        except Exception as exc:
            logger.warning("Visual Verification failed on PNG byte stream: %s", exc)
            return False, f"Corrupted PNG image stream: {exc}", 0, 0, sha256_hash
