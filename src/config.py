"""
src/config.py — Foundation Configuration Constants & System Versioning

Revenue Leak Scanner V2
"""
from pathlib import Path
from typing import Final

# System Versioning (Single Source of Truth)
SCANNER_VERSION: Final[str] = "2.3.1"
SCHEMA_VERSION: Final[str] = "2.0.0"

# Root Paths inside RevenueLeakScanner_V2
V2_ROOT_DIR: Final[Path] = Path(__file__).parent.parent.resolve()
SRC_DIR: Final[Path] = V2_ROOT_DIR / "src"
STORAGE_DIR: Final[Path] = V2_ROOT_DIR / "storage"
SESSIONS_DIR: Final[Path] = STORAGE_DIR / "sessions"
REPORTS_DIR: Final[Path] = STORAGE_DIR / "reports"
FIXTURES_DIR: Final[Path] = STORAGE_DIR / "fixtures"

# Ensure runtime directories exist
for _dir in (SESSIONS_DIR, REPORTS_DIR, FIXTURES_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# Image & Viewport Bounds
MIN_VIEWPORT_WIDTH: Final[int] = 1024
MIN_VIEWPORT_HEIGHT: Final[int] = 600
MIN_SCROLLABLE_PDP_HEIGHT: Final[int] = 1200
DEFAULT_VIEWPORT: Final[str] = "1365x900"

# Financial Loss Calculation Baseline Parameters
DEFAULT_BASELINE_CONVERSION_RATE: Final[float] = 0.02  # 2.0%
DEFAULT_AOV_FALLBACK_USD: Final[float] = 65.00
DEFAULT_TRAFFIC_FALLBACK_VISITS: Final[int] = 50000
