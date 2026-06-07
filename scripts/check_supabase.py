"""Verify Supabase connectivity + a read/write round-trip.

Run AFTER applying src/db/schema.sql in the Supabase SQL editor:
    .\.venv\Scripts\python.exe scripts\check_supabase.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import supabase_client as db  # noqa: E402


def main() -> int:
    try:
        db.ping()
        print("[ok] connected; tables reachable")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "does not exist" in msg or "schema cache" in msg or "PGRST205" in msg:
            print("[connection ok, schema missing] Run src/db/schema.sql in the "
                  "Supabase SQL editor, then re-run this script.")
            print("   detail:", msg[:200])
            return 2
        print("[FAILED] could not query Supabase:", msg[:300])
        return 1

    # seller_profile round-trip
    db.save_seller_profile({
        "product_description": "AP automation software",
        "value_prop": "cut AP teams' manual invoice work by ~10 hrs/week",
        "default_tone": "consultative",
    })
    print("[ok] seller_profile saved:", db.get_seller_profile())

    # run round-trip
    rid = db.create_run({"company": "Acme", "company_key": "acme", "status": "test"})
    print("[ok] run created:", rid)
    found = db.find_runs_by_company("acme")
    print(f"[ok] find_runs_by_company('acme') -> {len(found)} run(s)")
    print(f"[ok] list_runs -> {len(db.list_runs())} total")
    print("\nALL GOOD — Supabase is wired up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
