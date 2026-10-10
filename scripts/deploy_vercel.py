"""One-command Vercel deploy from your laptop (the cloud sandbox cannot reach Vercel).

    python scripts/deploy_vercel.py            # login if needed, link, copy env vars from .env / local.env, deploy to production
    python scripts/deploy_vercel.py --dry-run  # only show which variables would be sent (values hidden)

Needs Node.js (npx). Secrets are read from your own .env / local.env and sent to Vercel as sensitive variables; nothing is printed."""
from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEND = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "NVIDIA_API_KEY", "NVIDIA_MODEL", "NVIDIA_THINKING",
        "NVIDIA_REASONING_BUDGET", "GROQ_API_KEY", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "GG_LINK_SECRET", "GG_USERNAME_DOMAIN",
        "SUPABASE_JWT_SECRET", "TELEGRAM_WEBHOOK_SECRET"]
FIXED = {"GG_ENV": "prod", "GG_REPO": "supabase", "GG_LOGIN": "on", "GG_RUNTIME_DIR": "/tmp/gg"}


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in (".env", "local.env"):
        p = ROOT / name
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    v = "" if v.strip().startswith("#") else v.split(" #", 1)[0]
                    if v.strip():
                        out.setdefault(k.strip(), v.strip())
    return out


def vercel(*args: str, stdin: str | None = None) -> int:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        sys.exit("Node.js is required: install it from https://nodejs.org and run this again.")
    return subprocess.run([npx, "--yes", "vercel", *args], cwd=ROOT, input=stdin, text=True).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    env = read_env()
    vars_ = {**FIXED, **{k: env[k] for k in SEND if env.get(k)}}
    analyst = secrets.token_urlsafe(32)
    vars_["GG_ANALYST_KEYS"] = analyst
    vars_["GG_ADMIN_KEYS"] = secrets.token_urlsafe(32)
    print("Variables to send:", ", ".join(sorted(vars_)))
    if a.dry_run:
        return 0
    if vercel("whoami") != 0:
        vercel("login")
    if not (ROOT / ".vercel" / "project.json").exists() and vercel("link", "--yes", "--project", "green-ghar") != 0:
        return 1
    for k, v in vars_.items():
        flags = ["--sensitive"] if any(t in k for t in ("KEY", "TOKEN", "SECRET")) else []
        vercel("env", "add", k, "production", "--force", *flags, stdin=v)
    print(f"\nLender-portfolio key (X-API-Key header / saved for you): {analyst}")
    (ROOT / "analyst_key.txt").write_text(analyst + "\n")
    rc = vercel("--prod", "--yes")
    if rc == 0:
        print("\nDeployed. Register the Telegram webhook (see README) and open /app on the new URL.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
