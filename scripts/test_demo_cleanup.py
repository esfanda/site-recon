"""Phase 3 self-test: stale demo_data files are deleted, fresh ones kept."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["SITE_RECON_PUBLIC_DEMO"] = "1"

import site_recon.demo as demo  # noqa: E402
from site_recon.demo import cleanup_demo_data  # noqa: E402


def main() -> int:
    tmp = Path(__file__).resolve().parent.parent / "demo_data" / "_cleanup_test"
    demo.DEMO_ROOT = tmp
    tmp.mkdir(parents=True, exist_ok=True)

    stale = tmp / "reports" / "old.example.com.md"
    fresh = tmp / "reports" / "new.example.com.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("old", encoding="utf-8")
    fresh.write_text("new", encoding="utf-8")

    old_time = time.time() - (49 * 3600)
    os.utime(stale, (old_time, old_time))

    removed = cleanup_demo_data()
    assert not stale.exists(), "stale file should be gone"
    assert fresh.exists(), "fresh file should remain"
    assert stale in removed or any(str(stale) == str(p) for p in removed)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print("PASS: stale demo_data file deleted, fresh file kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
