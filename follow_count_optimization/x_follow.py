#!/usr/bin/env python3
"""
Follow the accounts in x_users.csv (from parse_x_har.py), one at a time,
in a visible browser.

Flow:
  1. Your Google Chrome opens (separate profile in ./x_browser_profile, shared
     with x_unfollow.py) with an X tab. Log in there once, then press Enter in
     the terminal. Later runs stay logged in. If X's login page hangs, use --cookies.
  2. For each account: open a new tab -> Follow -> close the tab ->
     wait 60 s + random 1-5 s -> next. The login tab stays open throughout.

Usage:
    python x_follow.py --dry-run          # list who would be followed, touch nothing
    python x_follow.py                    # follow up to 50 this run (default cap)
    python x_follow.py --limit 100        # different cap for this run
    python x_follow.py --input other.csv  # a different list

Skips: accounts you already follow, protected (private) accounts, and anyone
already in follow_log.csv as "followed" / "already_following".
Re-running is safe and resumes. Ctrl+C stops after the current account.
"""

import argparse
import csv
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).resolve().parent
LOG_CSV = HERE / "follow_log.csv"
PROFILE_DIR = HERE / "x_browser_profile"   # keeps you logged in between runs (keep private)

BASE_WAIT = 60                 # seconds between accounts
JITTER = (1, 5)                # plus random 1-5 seconds
TIMEOUT = 20_000               # ms
MAX_CONSECUTIVE_FAILS = 3      # stop if X starts blocking
DEFAULT_LIMIT = 50             # per run; X restricts accounts that follow too many too fast

LOG_FIELDS = ["handle", "profile_url", "followers", "status", "time"]

LIMIT_PHRASES = ("unable to follow more", "follow limit", "rate limit",
                 "something went wrong", "try again later")


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def load_targets(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    targets, skipped = [], {"no_url": 0, "already_following": 0, "protected": 0}
    for r in rows:
        if not r.get("profile_url"):
            skipped["no_url"] += 1
        elif truthy(r.get("you_follow")):
            skipped["already_following"] += 1
        elif truthy(r.get("protected")):
            skipped["protected"] += 1
        else:
            targets.append(r)
    return targets, skipped


def load_finished():
    if not LOG_CSV.exists():
        return set()
    with LOG_CSV.open(newline="") as f:
        return {r["profile_url"] for r in csv.DictReader(f)
                if r["status"] in ("followed", "already_following", "requested",
                                   "not_found", "suspended")}


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


def follow_one(ctx, url):
    """Open a tab, follow, close the tab. Returns a status string."""
    page = ctx.new_page()
    try:
        page.goto(url, timeout=TIMEOUT, wait_until="domcontentloaded")
        # Follow button testid ends in "-follow"; once followed it ends in "-unfollow";
        # a pending request to a private account ends in "-cancel".
        try:
            page.wait_for_selector(
                '[data-testid$="-follow"], [data-testid$="-unfollow"], '
                '[data-testid$="-cancel"], [data-testid="emptyState"]', timeout=TIMEOUT)
        except PWTimeout:
            if "/login" in page.url:
                return "logged_out"
            body = page.inner_text("body").lower()
            return "rate_limited" if any(p in body for p in LIMIT_PHRASES) else "timeout"

        if page.query_selector('[data-testid$="-unfollow"]'):
            return "already_following"
        if page.query_selector('[data-testid$="-cancel"]'):
            return "requested"
        btn = page.query_selector('[data-testid$="-follow"]')
        if not btn:
            body = page.inner_text("body").lower()
            return "suspended" if "suspended" in body else "not_found"

        btn.click()
        try:
            page.wait_for_selector('[data-testid$="-unfollow"], [data-testid$="-cancel"]',
                                   timeout=TIMEOUT)
        except PWTimeout:
            body = page.inner_text("body").lower()
            return "rate_limited" if any(p in body for p in LIMIT_PHRASES) else "timeout"
        return "requested" if page.query_selector('[data-testid$="-cancel"]') else "followed"
    except PWTimeout:
        return "timeout"
    finally:
        page.wait_for_timeout(800)
        page.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(HERE / "x_users.csv"))
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"max follows this run (default {DEFAULT_LIMIT})")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cookies", action="store_true",
                    help="log in by pasting auth_token and ct0 cookies from your normal browser")
    args = ap.parse_args()

    if not Path(args.input).exists():
        sys.exit(f"Missing {args.input} — run parse_x_har.py first.")

    targets, skipped = load_targets(args.input)
    finished = load_finished()
    targets = [r for r in targets if r["profile_url"] not in finished]
    total = len(targets)
    targets = targets[:args.limit]

    print(f"{total} accounts to follow ({len(finished)} done in earlier runs; skipped: "
          f"{skipped['already_following']} already followed, {skipped['protected']} private, "
          f"{skipped['no_url']} without a profile_url).")
    if total > len(targets):
        print(f"This run is capped at {len(targets)} (--limit). Re-run later for the rest.")
    for r in targets:
        f = r.get("followers") or "?"
        print(f"  @{r.get('handle') or r['profile_url']:<20} {f:>7} followers")
    if args.dry_run or not targets:
        return

    est = len(targets) * (BASE_WAIT + 3 + 6) / 60
    if input(f"\nFollow these {len(targets)}? Takes about {est:.0f} min. [y/N] ").strip().lower() != "y":
        return

    with sync_playwright() as p:
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
                sys.exit("Still not logged in. Try:  python x_follow.py --cookies")
        print("Logged in. Starting.\n")

        fails = 0
        try:
            for i, r in enumerate(targets, 1):
                status = follow_one(ctx, r["profile_url"])
                log({"handle": r.get("handle", ""), "profile_url": r["profile_url"],
                     "followers": r.get("followers", ""), "status": status,
                     "time": datetime.now().isoformat(timespec="seconds")})
                print(f"[{i}/{len(targets)}] @{r.get('handle') or r['profile_url']}: {status}")

                if status in ("logged_out", "rate_limited"):
                    print("X logged you out or is limiting follows — stopping. "
                          "Wait several hours before re-running.")
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
