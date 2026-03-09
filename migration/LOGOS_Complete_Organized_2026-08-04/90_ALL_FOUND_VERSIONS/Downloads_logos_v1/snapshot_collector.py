"""
LOGOS V1 — Snapshot Collector
==============================
Polls the Polymarket CLOB API for current prices of all family markets.
Saves timestamped snapshots to a JSONL file.

No API key needed — price endpoints are public.

Usage:
    python snapshot_collector.py                  # Run once
    python snapshot_collector.py --loop 5         # Run every 5 minutes
    python snapshot_collector.py --loop 5 -n 100  # Run 100 times, every 5 minutes

Requirements:
    pip install requests
"""

import json
import time
import argparse
import ssl
from datetime import datetime, timezone
from pathlib import Path

# Try requests first, fall back to urllib
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import certifi
    HAS_REQUESTS = False

from families import FAMILIES

CLOB_BASE = "https://clob.polymarket.com"
OUTPUT_FILE = "snapshots.jsonl"


def fetch_price(token_id):
    """Fetch the current midpoint price for a single token from the CLOB API."""
    url = f"{CLOB_BASE}/midpoint?token_id={token_id}"
    try:
        if HAS_REQUESTS:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        else:
            ctx = ssl.create_default_context()
            try:
                import certifi
                ctx.load_verify_locations(certifi.where())
            except:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": "LOGOS/1.0"})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode())
        return float(data.get("mid", data.get("price", 0)))
    except Exception as e:
        print(f"    ERROR fetching {token_id[:20]}...: {e}")
        return None


def fetch_prices_batch(token_ids):
    """Fetch midpoint prices for multiple tokens. Uses individual calls (CLOB has no batch midpoint)."""
    prices = {}
    for tid in token_ids:
        price = fetch_price(tid)
        prices[tid] = price
        time.sleep(0.1)  # Small delay to avoid rate limiting
    return prices


def take_snapshot():
    """Take a snapshot of all family prices right now."""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"\n{'='*60}")
    print(f"SNAPSHOT: {timestamp}")
    print(f"{'='*60}")

    snapshot = {
        "timestamp": timestamp,
        "families": [],
    }

    for family in FAMILIES:
        print(f"\n  {family['name']} ({family['type']})")
        family_data = {
            "name": family["name"],
            "type": family["type"],
            "constraint": family["constraint"],
            "markets": [],
        }

        for market in family["markets"]:
            price = fetch_price(market["asset_id"])
            market_data = {
                "label": market["label"],
                "asset_id": market["asset_id"],
                "price": price,
            }
            family_data["markets"].append(market_data)
            price_str = f"{price:.4f}" if price is not None else "ERROR"
            print(f"    {market['label']:.<30} {price_str}")

        # Quick coherence check
        prices = [m["price"] for m in family_data["markets"] if m["price"] is not None]
        if family["type"] == "deadline_nesting":
            violations = sum(1 for i in range(len(prices)-1) if prices[i] > prices[i+1])
            family_data["violations"] = violations
            family_data["coherent"] = violations == 0
            status = "✓ coherent" if violations == 0 else f"✗ {violations} violation(s)"
        elif family["type"] == "threshold_chain":
            violations = sum(1 for i in range(len(prices)-1) if prices[i] < prices[i+1])
            family_data["violations"] = violations
            family_data["coherent"] = violations == 0
            status = "✓ coherent" if violations == 0 else f"✗ {violations} violation(s)"
        elif family["type"] == "mutually_exclusive":
            total = sum(prices)
            family_data["sum"] = round(total, 6)
            family_data["deviation"] = round(total - 1.0, 6)
            family_data["coherent"] = abs(total - 1.0) < 0.02
            status = f"sum={total:.4f} (dev={total-1:.4f})"
        else:
            status = "?"
        print(f"    → {status}")

        snapshot["families"].append(family_data)

    return snapshot


def save_snapshot(snapshot, filepath):
    """Append a snapshot as one JSON line to the output file."""
    with open(filepath, "a") as f:
        f.write(json.dumps(snapshot) + "\n")


def main():
    parser = argparse.ArgumentParser(description="LOGOS V1 Snapshot Collector")
    parser.add_argument("--loop", type=int, default=0, help="Minutes between snapshots (0 = run once)")
    parser.add_argument("-n", type=int, default=0, help="Number of snapshots to take (0 = infinite)")
    parser.add_argument("-o", "--output", type=str, default=OUTPUT_FILE, help="Output JSONL file")
    args = parser.parse_args()

    output_path = Path(args.output)
    print(f"LOGOS V1 Snapshot Collector")
    print(f"Output: {output_path.absolute()}")
    print(f"Families: {len(FAMILIES)}")
    total_markets = sum(len(f['markets']) for f in FAMILIES)
    print(f"Total markets: {total_markets}")

    if args.loop > 0:
        print(f"Mode: every {args.loop} minutes" + (f", {args.n} snapshots" if args.n > 0 else ", until stopped"))
    else:
        print(f"Mode: single snapshot")

    count = 0
    while True:
        snapshot = take_snapshot()
        save_snapshot(snapshot, output_path)
        count += 1
        print(f"\n  Saved snapshot #{count} to {output_path}")

        if args.loop <= 0:
            break
        if args.n > 0 and count >= args.n:
            print(f"\nDone. Took {count} snapshots.")
            break

        next_time = datetime.now(timezone.utc).isoformat()
        print(f"\n  Sleeping {args.loop} minutes... (next snapshot at ~{next_time})")
        try:
            time.sleep(args.loop * 60)
        except KeyboardInterrupt:
            print(f"\nStopped. Took {count} snapshots total.")
            break

    print(f"\nData saved to: {output_path.absolute()}")
    print(f"To load in Python/Jupyter:")
    print(f"  import json")
    print(f"  snapshots = [json.loads(line) for line in open('{args.output}')]")


if __name__ == "__main__":
    main()
