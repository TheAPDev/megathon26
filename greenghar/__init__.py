"""Green Ghar: home energy score, retrofit engine, grounded advisor and lender portfolio for Indian homes."""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency): KEY=VALUE lines, '#' comments, quotes stripped.
    Real environment variables always win, so Docker/hosting settings override the file."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip().removeprefix("export ").strip(), val.strip()
        if val[:1] in "\"'" and val[-1:] == val[:1] and len(val) >= 2:
            val = val[1:-1]
        elif val.startswith("#"):
            val = ""  # "KEY=   # where to get it": empty value with a trailing note
        elif " #" in val:
            val = val.split(" #", 1)[0].rstrip()
        os.environ.setdefault(key, val)


_ROOT = Path(__file__).resolve().parent.parent
if os.environ.get("GG_ENV_FILE"):
    _load_dotenv(Path(os.environ["GG_ENV_FILE"]))
else:  # .env first; local.env is the same file under a name some sync tools allow (values in .env win)
    _load_dotenv(_ROOT / ".env")
    _load_dotenv(_ROOT / "local.env")
