#!/usr/bin/env python3
"""
Unfollow accounts from follower_counts_sorted.csv whose follower count is
below a threshold (default 4500), one at a time, in a visible browser.

Flow:
  1. Your Google Chrome opens (separate profile in ./x_browser_profile) with an X
     tab. Log in there once, then press Enter in the terminal. Later runs stay
     logged in. If X's login page hangs, use --cookies instead.
  2. For each account: open a new tab -> unfollow -> close the tab ->
     wait 60 s + random 1-5 s -> next.  The login tab stays open throughout.

Usage:
    python x_unfollow.py --dry-run          # list who would be unfollowed, touch nothing
    python x_unfollow.py                    # do it
    python x_unfollow.py --threshold 3000   # different cutoff
    python x_unfollow.py --limit 20         # stop after 20 unfollows this run

Re-running is safe: accounts already in unfollow_log.csv as "unfollowed" or
"not_following" are skipped. Ctrl+C stops after the current account.
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
INPUT_CSV = HERE / "follower_counts_sorted.csv"
LOG_CSV = HERE / "unfollow_log.csv"
PROFILE_DIR = HERE / "x_browser_profile"   # keeps you logged in between runs (keep private)

BASE_WAIT = 60                 # seconds between accounts
JITTER = (1, 5)                # plus random 1-5 seconds
TIMEOUT = 20_000               # ms
MAX_CONSECUTIVE_FAILS = 3      # stop if X starts blocking

LOG_FIELDS = ["account_id", "handle", "followers", "status", "time"]


def load_targets(threshold):
    with INPUT_CSV.open(newline="") as f:
        rows = list(csv.DictReader(f))
    targets = []
    for r in rows:
        if r.get("status") != "ok" or not r.get("followers"):
            continue            # skip suspended / unknown counts
        if int(r["followers"]) < threshold:
            targets.append(r)
    return targets


def load_finished():
    if not LOG_CSV.exists():
        return set()
    with LOG_CSV.open(newline="") as f:
        return {r["account_id"] for r in csv.DictReader(f)
                if r["status"] in ("unfollowed", "not_following")}


def log(row):
    new = not LOG_CSV.exists()
    with LOG_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def is_logged_in(page):
    try:
        page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]', timeout=8000)
        return True
    except PWTimeout:
        return False


def add_cookies_from_prompt(ctx):
    """Log in by copying two cookies from a Chrome where you're already logged in to X."""
    print("In your normal Chrome (logged in to x.com): open DevTools (F12 / Cmd+Opt+I) -> "
          "Application -> Cookies -> https://x.com, and copy the Value of:")
    auth = input("  auth_token: ").strip()
    ct0 = input("  ct0: ").strip()
    ctx.add_cookies([
        {"name": n, "value": v, "domain": ".x.com", "path": "/",
         "secure": True, "httpOnly": n == "auth_token", "sameSite": "None"}
        for n, v in (("auth_token", auth), ("ct0", ct0))])


def unfollow_one(ctx, r):
    """Open a tab, unfollow, close the tab. Returns a status string."""
    handle = r.get("handle") or ""
    url = f"https://x.com/{handle}" if handle else r["profile_link"]
    page = ctx.new_page()
    try:
        page.goto(url, timeout=TIMEOUT, wait_until="domcontentloaded")
        if "intent/user" in url:
            page.wait_for_url(lambda u: "intent/user" not in u, timeout=TIMEOUT)

        # On a profile you follow, the button's testid ends in "-unfollow";
        # if you don't follow them it ends in "-follow".
        try:
            page.wait_for_selector(
                '[data-testid$="-unfollow"], [data-testid$="-follow"], '
                '[data-testid="emptyState"]', timeout=TIMEOUT)
        except PWTimeout:
            body = page.inner_text("body").lower()
            if "/login" in page.url:
                return "logged_out"
            return "rate_limited" if "rate limit" in body or "try again" in body else "timeout"

        btn = page.query_selector('[data-testid$="-unfollow"]')
        if not btn:
            if page.query_selector('[data-testid$="-follow"]'):
                return "not_following"
            body = page.inner_text("body").lower()
            return "suspended" if "suspended" in body else "not_found"

        btn.click()
        page.click('[data-testid="confirmationSheetConfirm"]', timeout=TIMEOUT)

        # confirm the button flipped back to "Follow"
        page.wait_for_selector('[data-testid$="-follow"]', timeout=TIMEOUT)
        return "unfollowed"
    except PWTimeout:
        return "timeout"
    finally:
        page.wait_for_timeout(800)
        page.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=4500)
    ap.add_argument("--limit", type=int, help="max unfollows this run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cookies", action="store_true",
                    help="log in by pasting auth_token and ct0 cookies from your normal browser")
    args = ap.parse_args()

    if not INPUT_CSV.exists():
        sys.exit(f"Missing {INPUT_CSV.name} next to this script.")

    finished = load_finished()
    targets = [r for r in load_targets(args.threshold) if r["account_id"] not in finished]
    if args.limit:
        targets = targets[:args.limit]

    print(f"{len(targets)} accounts under {args.threshold:,} followers to unfollow "
          f"({len(finished)} already done in earlier runs).")
    for r in targets:
        print(f"  @{r['handle'] or r['account_id']:<20} {int(r['followers']):>7,}")
    if args.dry_run or not targets:
        return

    est = len(targets) * (BASE_WAIT + 3 + 6) / 60
    if input(f"\nUnfollow these {len(targets)}? Takes about {est:.0f} min. [y/N] ").strip().lower() != "y":
        return

    with sync_playwright() as p:
        # Use your real Google Chrome with its own saved profile folder, and hide
        # the "controlled by automation" flags that make X's login page hang.
        launch = dict(user_data_dir=str(PROFILE_DIR), headless=False,
                      args=["--disable-blink-features=AutomationControlled"],
                      ignore_default_args=["--enable-automation"],
                      viewport=None)
        try:
            ctx = p.chromium.launch_persistent_context(channel="chrome", **launch)
        except Exception:
            print("Google Chrome not found — falling back to Playwright's Chromium.")
            ctx = p.chromium.launch_persistent_context(**launch)

        if args.cookies:
            add_cookies_from_prompt(ctx)

        # Tab 1: login tab, stays open the whole time
        home = ctx.pages[0] if ctx.pages else ctx.new_page()
        home.goto("https://x.com/home")
        if not is_logged_in(home):
            home.goto("https://x.com/login")
            input("Log in to X in the browser window, then press Enter here... ")
            home.goto("https://x.com/home")
            if not is_logged_in(home):
                sys.exit("Still not logged in. Try:  python x_unfollow.py --cookies")
        print("Logged in. Starting.\n")

        fails = 0
        try:
            for i, r in enumerate(targets, 1):
                status = unfollow_one(ctx, r)
                log({"account_id": r["account_id"], "handle": r["handle"],
                     "followers": r["followers"], "status": status,
                     "time": datetime.now().isoformat(timespec="seconds")})
                print(f"[{i}/{len(targets)}] @{r['handle']}: {status}")

                if status in ("logged_out", "rate_limited"):
                    print("X logged you out or is rate-limiting — stopping. Re-run later to resume.")
                    break
                fails = fails + 1 if status == "timeout" else 0
                if fails >= MAX_CONSECUTIVE_FAILS:
                    print(f"{fails} timeouts in a row — stopping. Re-run later to resume.")
                    break

                if i < len(targets):
                    wait = BASE_WAIT + random.uniform(*JITTER)
                    print(f"    waiting {wait:.1f}s")
                    time.sleep(wait)
        except KeyboardInterrupt:
            print("\nStopped by you. Re-run to resume.")

        ctx.close()


if __name__ == "__main__":
    main()