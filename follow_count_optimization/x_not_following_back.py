#!/usr/bin/env python3
"""
Find accounts you follow on X that don't follow you back, using the
following.js and follower.js files from your X data export.

Usage:
    python x_not_following_back.py
    python x_not_following_back.py --following path/to/following.js --follower path/to/follower.js

Outputs (next to this script):
    not_following_back.csv   - #, account_id, profile_link  (input for x_follower_counts.py)
    not_following_back.html  - clickable list you can open in a browser
"""

import argparse
import csv
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_ids(path: Path, key: str):
    """X export files look like:  window.YTD.following.part0 = [ {...}, ... ]"""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text[text.index("["):])
    return [item[key]["accountId"] for item in data]


def profile_link(account_id: str) -> str:
    # The export only has numeric IDs; this link redirects to the @handle's profile.
    return f"https://x.com/intent/user?user_id={account_id}"


def write_html(path: Path, ids, n_following, n_followers):
    rows = "\n".join(
        f'<tr><td>{i}</td><td><a href="{profile_link(a)}" target="_blank" rel="noopener">'
        f"{html.escape(a)}</a></td></tr>"
        for i, a in enumerate(ids, 1))
    path.write_text(f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Not Following Back</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:640px;margin:auto;padding:24px 16px}}
p{{color:#666}} table{{width:100%;border-collapse:collapse}}
td{{padding:6px 4px;border-bottom:1px solid #ddd}} td:first-child{{color:#888;width:3em}}
a{{color:#1d6fd6;text-decoration:none;word-break:break-all}}
</style></head><body>
<h1>{len(ids)} accounts don't follow you back</h1>
<p>Out of {n_following} you follow ({n_followers} followers). Click an ID to open the profile on X.</p>
<table>
{rows}
</table></body></html>
""", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--following", default=HERE / "following.js", type=Path)
    ap.add_argument("--follower", default=HERE / "follower.js", type=Path)
    args = ap.parse_args()

    following = load_ids(args.following, "following")
    followers = set(load_ids(args.follower, "follower"))

    # keep the export's order, drop any duplicates
    seen, not_back = set(), []
    for a in following:
        if a not in followers and a not in seen:
            seen.add(a)
            not_back.append(a)

    print(f"You follow:            {len(set(following))}")
    print(f"Your followers:        {len(followers)}")
    print(f"Don't follow you back: {len(not_back)}\n")
    for i, a in enumerate(not_back, 1):
        print(f"{i:>4}. {profile_link(a)}")

    csv_path = HERE / "not_following_back.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "account_id", "profile_link"])
        for i, a in enumerate(not_back, 1):
            w.writerow([i, a, profile_link(a)])

    html_path = HERE / "not_following_back.html"
    write_html(html_path, not_back, len(set(following)), len(followers))

    print(f"\nSaved {csv_path.name} and {html_path.name}")


if __name__ == "__main__":
    main()
