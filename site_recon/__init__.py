"""Site Recon — deep, evidence-based website analysis."""
__version__ = "0.1.0"

# Add vendor directory to path for bundled dependencies
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
