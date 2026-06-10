"""Send a UZPR license key to a buyer via email.

Usage::

    python scripts/licensing/send_license.py --email buyer@example.com [--name "Rui"]

Reads SMTP config from ~/.uzpr-vendor/smtp.json.
Creates a template if missing and exits with instructions.

Gmail note: use an App Password (not your account password).
Generate one at https://myaccount.google.com/apppasswords with
2-Step Verification enabled.
"""

from __future__ import annotations

import argparse
import json
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText
from pathlib import Path

_VENDOR_DIR = Path.home() / ".uzpr-vendor"
_SMTP_FILE = _VENDOR_DIR / "smtp.json"

_SMTP_TEMPLATE = {
    "host": "smtp.gmail.com",
    "port": 587,
    "user": "you@gmail.com",
    "password": "your-app-password",
    "from_addr": "you@gmail.com",
}

_EMAIL_BODY = """\
Hi {name},

Thank you for supporting UZPR!

Your license key:
{token}

To activate: open UZPR -> click "I have a license key" -> paste the key above.

Enjoy!
Luis
"""


def _load_smtp() -> dict:
    if not _SMTP_FILE.exists():
        _VENDOR_DIR.mkdir(parents=True, exist_ok=True)
        _SMTP_FILE.write_text(json.dumps(_SMTP_TEMPLATE, indent=2), encoding="utf-8")
        print(
            f"Created SMTP config template at {_SMTP_FILE}\n"
            "Fill in host, port, user, password, and from_addr, then re-run.\n"
            "For Gmail: set host=smtp.gmail.com, port=587, and use a Gmail App Password.",
            file=sys.stderr,
        )
        sys.exit(1)
    return json.loads(_SMTP_FILE.read_text(encoding="utf-8"))


def _issue_token(email: str) -> str:
    script = Path(__file__).parent / "issue_license.py"
    result = subprocess.run(
        [sys.executable, str(script), "--email", email, "--tier", "pro"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "issue_license.py failed")
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("issue_license.py returned empty token")
    return token


def _send(smtp_cfg: dict, to_addr: str, name: str, token: str) -> None:
    body = _EMAIL_BODY.format(name=name, token=token)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "Your UZPR license key"
    msg["From"] = smtp_cfg["from_addr"]
    msg["To"] = to_addr

    with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"]) as conn:
        conn.ehlo()
        conn.starttls()
        conn.login(smtp_cfg["user"], smtp_cfg["password"])
        conn.sendmail(smtp_cfg["from_addr"], [to_addr], msg.as_string())


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue and email a UZPR license key")
    parser.add_argument("--email", required=True, help="Buyer's email address")
    parser.add_argument("--name", default="there", help="Buyer's first name (default: 'there')")
    args = parser.parse_args()

    try:
        smtp_cfg = _load_smtp()
        print(f"Issuing license for {args.email}...")
        token = _issue_token(args.email)
        print(f"Token: {token}")
        print(f"Sending email to {args.email}...")
        _send(smtp_cfg, args.email, args.name, token)
        print("Done. Email sent successfully.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
