#!/usr/bin/env python3
"""
Look up the follower count of each account in not_following_back.csv by
opening its profile link in a real (Chromium) browser.

Setup (once):
    pip install playwright
    python -m playwright install chromium

Try logged out first:
    python x_follower_counts.py --show --limit 3

If X blocks that with a login wall, log in once and run again:
    python x_follower_counts.py --login      # opens a browser window; log in to X, then press Enter here

Run:
    python x_follower_counts.py              # headless, resumes where it left off

Output: follower_counts.csv  (account_id, handle, name, followers, followers_raw, status, profile_link, checked_at)
"""

import argparse
import csv
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).resolve().parent
INPUT_CSV = HERE / "not_following_back.csv"
OUTPUT_CSV = HERE / "follower_counts.csv"
STATE_FILE = HERE / "x_session.json"   # your saved X login (keep private)

FIELDS = ["account_id", "handle", "name", "followers", "followers_raw",
          "status", "profile_link", "checked_at"]

MIN_DELAY, MAX_DELAY = 4, 9      # seconds between profiles, to avoid rate limits
PAGE_TIMEOUT = 25_000            # ms


def parse_count(text: str):
    """'1,234' -> 1234, '12.5K' -> 12500, '3.1M' -> 3100000."""
    t = text.strip().replace(",", "").upper()
    m = re.match(r"^([\d.]+)\s*([KMB])?$", t)
    if not m:
        return None
    n = float(m.group(1))
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2), 1)
    return int(round(n * mult))


def load_done():
    if not OUTPUT_CSV.exists():
        return set()
    with OUTPUT_CSV.open(newline="") as f:
        # retry anything that errored or got rate-limited last time
        return {r["account_id"] for r in csv.DictReader(f)
                if r["status"] in ("ok", "suspended", "not_found")}


def load_targets():
    with INPUT_CSV.open(newline="") as f:
        return [(r["account_id"], r["profile_link"]) for r in csv.DictReader(f)]


def login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://x.com/login")
        input("Log in to X in the browser window, then press Enter here... ")
        ctx.storage_state(path=str(STATE_FILE))
        browser.close()
    print(f"Saved session to {STATE_FILE}")


def scrape_one(page, account_id, link):
    row = {"account_id": account_id, "profile_link": link,
           "handle": "", "name": "", "followers": "", "followers_raw": "",
           "checked_at": datetime.now().isoformat(timespec="seconds")}
    try:
        page.goto(link, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        # the intent link redirects to x.com/<handle>
        page.wait_for_url(lambda u: "intent/user" not in u, timeout=PAGE_TIMEOUT)
    except PWTimeout:
        row["status"] = "timeout"
        return row

    if "/login" in page.url or "/i/flow/login" in page.url:
        row["status"] = "logged_out"
        return row

    m = re.match(r"https://(?:x|twitter)\.com/([A-Za-z0-9_]+)", page.url)
    row["handle"] = m.group(1) if m else ""

    try:
        page.wait_for_selector(
            'a[href$="/followers"], a[href$="/verified_followers"], '
            '[data-testid="emptyState"], [data-testid="error-detail"]',
            timeout=PAGE_TIMEOUT)
    except PWTimeout:
        body = page.inner_text("body")[:2000].lower()
        row["status"] = "rate_limited" if "rate limit" in body or "try again" in body else "timeout"
        return row

    body = page.inner_text("body").lower()
    if "account suspended" in body:
        row["status"] = "suspended"
        return row
    if "this account doesn" in body or "doesn’t exist" in body:
        row["status"] = "not_found"
        return row

    name_el = page.query_selector('[data-testid="UserName"] span')
    if name_el:
        row["name"] = name_el.inner_text().strip()

    for a in page.query_selector_all('a[href$="/verified_followers"], a[href$="/followers"]'):
        txt = a.inner_text().strip()            # e.g. "1,234 Followers"
        mm = re.match(r"([\d.,]+\s*[KMB]?)\s+Followers", txt, re.I)
        if mm:
            row["followers_raw"] = mm.group(1)
            row["followers"] = parse_count(mm.group(1))
            break

    row["status"] = "ok" if row["followers"] != "" else "no_count_found"
    return row


def run(headless: bool, limit: int | None):
    logged_in = STATE_FILE.exists()
    if not logged_in:
        print("No saved login — trying logged out. If X shows a login wall, "
              "run:  python x_follower_counts.py --login")
    if not INPUT_CSV.exists():
        sys.exit(f"Missing {INPUT_CSV.name} next to this script.")

    done = load_done()
    todo = [t for t in load_targets() if t[0] not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(done)} already done, {len(todo)} to check.")
    if not todo:
        return

    new_file = not OUTPUT_CSV.exists()
    with sync_playwright() as p, OUTPUT_CSV.open("a", newline="") as out:
        w = csv.DictWriter(out, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        browser = p.chromium.launch(headless=headless)
        ctx = (browser.new_context(storage_state=str(STATE_FILE)) if logged_in
               else browser.new_context(locale="en-US"))
        page = ctx.new_page()

        for i, (acc, link) in enumerate(todo, 1):
            row = scrape_one(page, acc, link)
            w.writerow(row)
            out.flush()
            print(f"[{i}/{len(todo)}] {row['handle'] or acc}: {row['followers'] or '-'} ({row['status']})")
            if row["status"] == "logged_out":
                print("X wants a login for this — run with --login, then run again."
                      if not logged_in else "Session expired — run with --login again.")
                break
            if row["status"] == "rate_limited":
                print("Rate limited by X — stopping; the next run will resume.")
                break
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        if logged_in:
            ctx.storage_state(path=str(STATE_FILE))   # keep cookies fresh
        browser.close()

    write_sorted()


def write_sorted():
    """Also write follower_counts_sorted.csv, latest result per account, biggest first."""
    with OUTPUT_CSV.open(newline="") as f:
        latest = {}
        for r in csv.DictReader(f):
            latest[r["account_id"]] = r
    rows = sorted(latest.values(),
                  key=lambda r: int(r["followers"]) if r["followers"] else -1,
                  reverse=True)
    with (HERE / "follower_counts_sorted.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print("Wrote follower_counts_sorted.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="log in once and save the session")
    ap.add_argument("--show", action="store_true", help="show the browser window while scraping")
    ap.add_argument("--limit", type=int, help="only check this many profiles this run")
    args = ap.parse_args()
    if args.login:
        login()
    else:
        run(headless=not args.show, limit=args.limit)