#!/usr/bin/env python3
"""
יוצר/גוזר API credentials של Polymarket ומדפיס אותם להעתקה ל-.env.

שימוש:
    python scripts/create_api_keys.py

דרישות: PMMB_PRIVATE_KEY מוגדר ב-.env (או במשתני הסביבה).
"""
from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def main() -> int:
    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        print("חסר py-clob-client. הרץ: pip install -r requirements-live.txt", file=sys.stderr)
        return 1

    pk = os.getenv("PMMB_PRIVATE_KEY")
    if not pk:
        print("חסר PMMB_PRIVATE_KEY. הוסף אותו ל-.env ונסה שוב.", file=sys.stderr)
        return 1

    client = ClobClient(
        "https://clob.polymarket.com",
        key=pk,
        chain_id=137,
        signature_type=int(os.getenv("PMMB_SIGNATURE_TYPE", "0")),
        funder=os.getenv("PMMB_FUNDER_ADDRESS") or None,
    )
    creds = client.create_or_derive_api_creds()
    print("העתק את השורות הבאות ל-.env:\n")
    print(f"PMMB_API_KEY={creds.api_key}")
    print(f"PMMB_API_SECRET={creds.api_secret}")
    print(f"PMMB_API_PASSPHRASE={creds.api_passphrase}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
