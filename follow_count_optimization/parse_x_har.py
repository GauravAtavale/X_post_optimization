#!/usr/bin/env python3
"""
Offline: pull X users out of HAR files you saved from Chrome DevTools while
scrolling an X search (Latest or People tab), a followers list, or a List.

No requests are made to X — this only reads the files you saved.

How to make a HAR file:
  1. In Chrome, open x.com and run your search (e.g. the Latest tab).
  2. Open DevTools (Cmd+Opt+I / F12) -> Network tab. Type "graphql" in the filter box.
  3. Reload the page, then scroll down slowly for as long as you want results.
  4. Right-click any request in the list -> "Save all as HAR" (or the download
     arrow icon "Export HAR"). Save it into this folder.

Usage:
  python parse_x_har.py search1.har search2.har
  python parse_x_har.py *.har --min-followers 100 --max-followers 1000
  python parse_x_har.py *.har --max-followers 1000 --keywords "ai,ml,llm,machine learning"
  python parse_x_har.py *.har --max-followers 1000 --min-follow-back-ratio 0.8

Output:
  x_users.csv  - one row per user, best matches first

HAR files can contain your login cookies. Don't share or commit them; delete them when done.
"""

import argparse
import base64
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

DEFAULT_KEYWORDS = ("ai, ml, llm, llms, machine learning, deep learning, nlp, genai, "
                    "agents, rag, pytorch, transformers, data science, researcher, "
                    "ml engineer, ai engineer, phd, computer vision, rl")

FIELDS = ["handle", "name", "followers", "following", "follow_back_ratio", "posts", "matching_posts",
          "last_post", "bio_score", "score", "bio", "location", "joined",
          "you_follow", "follows_you", "protected", "blue_verified", "user_id", "profile_url", "example_post_url", "example_post"]


def to_dt(s):
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except (TypeError, ValueError):
        return None


def iter_json_bodies(har_path):
    har = json.loads(Path(har_path).read_text(encoding="utf-8"))
    for e in har.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        if "x.com" not in url and "twitter.com" not in url:
            continue
        content = e.get("response", {}).get("content", {})
        text = content.get("text")
        if not text:
            continue
        if content.get("encoding") == "base64":
            try:
                text = base64.b64decode(text).decode("utf-8", "replace")
            except Exception:
                continue
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            continue


def parse_user(u):
    """u = a GraphQL user result (typename User). Handles old and new X layouts."""
    if not isinstance(u, dict) or u.get("__typename") != "User":
        return None
    leg = u.get("legacy") or {}
    core = u.get("core") or {}
    rc = u.get("relationship_counts") or {}        # 2026 layout
    tc = u.get("tweet_counts") or {}
    rp = u.get("relationship_perspectives") or {}
    handle = core.get("screen_name") or leg.get("screen_name")
    followers = rc.get("followers", leg.get("followers_count"))
    if not handle or followers is None:
        return None
    loc = u.get("location") or {}
    bio = (u.get("profile_bio") or {}).get("description") or leg.get("description") or ""
    return {
        "user_id": u.get("rest_id", ""),
        "handle": handle,
        "name": core.get("name") or leg.get("name", ""),
        "followers": followers,
        "following": rc.get("following", leg.get("friends_count", 0)),
        "posts": tc.get("tweets", leg.get("statuses_count", 0)),
        "bio": bio.replace("\n", " ").strip(),
        "location": loc.get("location", "") if isinstance(loc, dict) else leg.get("location", ""),
        "joined": core.get("created_at") or leg.get("created_at", ""),
        "blue_verified": bool(u.get("is_blue_verified")),
        "you_follow": bool(rp.get("following", leg.get("following", False))),
        "follows_you": bool(rp.get("followed_by", leg.get("followed_by", False))),
        "protected": bool((u.get("privacy") or {}).get("protected", leg.get("protected", False))),
    }


def walk(node, users, posts):
    """Recursively find User and Tweet objects anywhere in the response."""
    if isinstance(node, dict):
        tn = node.get("__typename")
        if tn == "User":
            p = parse_user(node)
            if p:
                users.setdefault(p["user_id"], {}).update(p)
        elif tn in ("Tweet", "TweetWithVisibilityResults"):
            t = node.get("tweet", node)
            leg = t.get("legacy") or {}
            author = (((t.get("core") or {}).get("user_results") or {}).get("result")) or {}
            a = parse_user(author)
            if a and leg.get("full_text") and t.get("rest_id"):
                posts.setdefault(a["user_id"], {})[t["rest_id"]] = {
                    "text": leg["full_text"].replace("\n", " "),
                    "created": leg.get("created_at"),
                    "handle": a["handle"],
                }
        for v in node.values():
            walk(v, users, posts)
    elif isinstance(node, list):
        for v in node:
            walk(v, users, posts)


def bio_score(bio, keywords):
    b = bio.lower()
    return sum(1 for k in keywords if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", b))


def main():
    ap = argparse.ArgumentParser(description="Extract X users from saved HAR files (offline).")
    ap.add_argument("har", nargs="+", help="one or more .har files")
    ap.add_argument("--min-followers", type=int, default=0)
    ap.add_argument("--max-followers", type=int, default=None)
    ap.add_argument("--keywords", default=DEFAULT_KEYWORDS,
                    help="comma-separated bio keywords for scoring")
    ap.add_argument("--max-ratio", type=float, default=10.0,
                    help="drop accounts following > this x their followers (follow-back farms); 0 = off")
    ap.add_argument("--min-follow-back-ratio", type=float, default=None,
                    help="keep only accounts with following/followers >= this (e.g. 0.8)")
    ap.add_argument("--new-only", action="store_true",
                    help="skip accounts you already follow")
    ap.add_argument("--out", default=str(HERE / "x_users.csv"))
    args = ap.parse_args()

    keywords = [k.strip().lower() for k in args.keywords.split(",") if k.strip()]
    users, posts = {}, {}
    for h in args.har:
        n = 0
        for body in iter_json_bodies(h):
            walk(body, users, posts)
            n += 1
        print(f"{h}: read {n} responses")

    rows = []
    for uid, u in users.items():
        f = u["followers"]
        if f < args.min_followers or (args.max_followers is not None and f > args.max_followers):
            continue
        if args.new_only and u.get("you_follow"):
            continue
        if args.max_ratio and u["following"] > args.max_ratio * max(f, 1) and u["following"] > 500:
            continue
        # follow_back_ratio = following / followers (followers 0 -> treated as infinitely high)
        fbr = u["following"] / f if f else float("inf")
        if args.min_follow_back_ratio is not None and fbr < args.min_follow_back_ratio:
            continue
        ups = posts.get(uid, {})
        last = max((to_dt(p["created"]) for p in ups.values() if to_dt(p["created"])), default=None)
        ex_id, ex = next(iter(ups.items()), ("", {}))
        bs = bio_score(u["bio"], keywords)
        rows.append({
            **u,
            "matching_posts": len(ups),
            "last_post": last.date().isoformat() if last else "",
            "bio_score": bs,
            "score": bs + 2 * len(ups),
            "follow_back_ratio": "inf" if fbr == float("inf") else round(fbr, 2),
            "joined": (to_dt(u["joined"]).date().isoformat() if to_dt(u["joined"]) else u["joined"]),
            "profile_url": f"https://x.com/{u['handle']}",
            "example_post_url": f"https://x.com/{u['handle']}/status/{ex_id}" if ex_id else "",
            "example_post": ex.get("text", "")[:280],
        })

    rows.sort(key=lambda r: (r["score"], r["matching_posts"]), reverse=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\nFound {len(users)} unique users; {len(rows)} after filters -> {args.out}")
    for r in rows[:15]:
        print(f"  @{r['handle']:<18} {r['followers']:>7,} followers  ratio:{r['follow_back_ratio']:<5} "
              f"posts:{r['matching_posts']}  bio:{r['bio_score']}  {r['bio'][:50]}")
    if not users:
        print("No users found. Make sure the HAR was saved after scrolling, with the "
              "Network tab open before you reloaded the page.", file=sys.stderr)


if __name__ == "__main__":
    main()