"""
LOGOS - Asset ID Fetcher
========================
This script fetches token_ids (asset IDs) for any Polymarket event.
No API key needed — the Gamma API is public and read-only.

Usage:
    python get_asset_ids.py

To change the event, edit the SLUGS list below.
"""

import urllib.request
import json

# ============================================================
# EDIT THIS: Add your event slugs here
# You can find the slug in the Polymarket URL:
#   https://polymarket.com/event/us-x-iran-ceasefire-by
#                                  ^^^^^^^^^^^^^^^^^^^^^^^^ this part
# ============================================================
SLUGS = [
    "us-x-iran-ceasefire-by",
    "what-price-will-bitcoin-hit-in-march-2026",
    "2026-nba-champion",
    "democratic-presidential-nominee-2028",
    "fed-rate-cut-by-629",
    "how-many-fed-rate-cuts-in-2026",
]


def fetch_event(slug):
    """Fetch event data from the Gamma API."""
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ERROR fetching {slug}: {e}")
        return None


def main():
    for slug in SLUGS:
        print(f"\n{'='*70}")
        print(f"EVENT: {slug}")
        print(f"{'='*70}")

        data = fetch_event(slug)
        if not data:
            continue

        # The response is a list of events (usually just one)
        events = data if isinstance(data, list) else [data]

        for event in events:
            title = event.get("title", event.get("question", "Unknown"))
            print(f"\nTitle: {title}")

            markets = event.get("markets", [])
            if not markets:
                print("  No markets found in this event.")
                continue

            print(f"Found {len(markets)} markets:\n")
            print(f"  {'Question':<50} {'Token IDs'}")
            print(f"  {'-'*50} {'-'*30}")

            for m in markets:
                question = m.get("question", m.get("groupItemTitle", "???"))
                # Token IDs can be in different fields depending on API version
                token_ids = m.get("clobTokenIds", m.get("clob_token_ids", []))
                outcome_prices = m.get("outcomePrices", m.get("outcome_prices", ""))
                
                # Try to parse token IDs if they're a JSON string
                if isinstance(token_ids, str):
                    try:
                        token_ids = json.loads(token_ids)
                    except:
                        token_ids = [token_ids] if token_ids else []

                # Try to parse prices
                if isinstance(outcome_prices, str):
                    try:
                        outcome_prices = json.loads(outcome_prices)
                    except:
                        outcome_prices = []

                # Display
                short_q = question[:48] if len(question) > 48 else question
                print(f"\n  {short_q}")
                
                if token_ids:
                    outcomes = ["Yes", "No"] if len(token_ids) == 2 else [f"Outcome {i}" for i in range(len(token_ids))]
                    for i, tid in enumerate(token_ids):
                        price_str = ""
                        if outcome_prices and i < len(outcome_prices):
                            try:
                                price_str = f" (price: {float(outcome_prices[i]):.2f})"
                            except:
                                pass
                        outcome_label = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
                        print(f"    {outcome_label}: {tid}{price_str}")
                else:
                    # Try condition_id as fallback
                    cid = m.get("conditionId", m.get("condition_id", ""))
                    if cid:
                        print(f"    condition_id: {cid}")
                    print(f"    (no token_ids found - try condition_id with CLOB API)")

    print(f"\n{'='*70}")
    print("WHAT TO DO WITH THESE:")
    print("  1. Copy the 'Yes' token_id for each market you want to track")
    print("  2. Paste them into the asset_ids list in live.py")
    print("  3. That's it — live.py will subscribe to those markets")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
