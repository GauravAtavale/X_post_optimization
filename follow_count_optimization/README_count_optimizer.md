# follow_count_optimization

Clean up who you follow on X (Twitter):

1. **Find who doesn't follow you back** using your X data export.
2. **Look up each of those accounts' follower counts.**
3. **Unfollow the ones below a follower threshold** (default 4,500), one at a time with a ~1-minute gap.

Everything runs locally on your computer, from your own X data export, with no X API key.

---

## Quick start

```bash
cd follow_count_optimization
# copy following.js and follower.js from your X export into this folder (see below)
chmod +x run_all.sh
./run_all.sh --dry-run      # see who would be unfollowed, change nothing
./run_all.sh                # do it for real (asks y/N before unfollowing)
```

---

## Requirements

- **macOS or Linux** with **Python 3.9+** (`python3 --version`)
- **Google Chrome** installed. The unfollow step uses it so X's login page works.
- An internet connection

On the first run, `run_all.sh` creates a `.venv/` here and installs Playwright plus its Chromium browser. You don't need to install anything yourself.

---

## Get your X data export

1. On X: **Settings → Your account → Download an archive of your data**. X takes up to a day or so to prepare it.
2. Unzip it. Inside the `data/` folder, find **`following.js`** and **`follower.js`**.
3. Copy both into this `follow_count_optimization/` folder.

---

## Running the whole pipeline: `run_all.sh`

| Command | What it does |
|---|---|
| `./run_all.sh` | Full run: find non-followers → get follower counts → unfollow those under 4,500 |
| `./run_all.sh --dry-run` | Everything except unfollowing; prints the list that would be unfollowed |
| `./run_all.sh --fresh` | Use with a **new** X export; clears old results first |
| `./run_all.sh --threshold 3000` | Change the cutoff to 3,000 followers |
| `./run_all.sh --limit 20` | Unfollow at most 20 accounts this run |
| `./run_all.sh --skip-counts` | Reuse existing `follower_counts_sorted.csv` (skips step 2) |
| `./run_all.sh --skip-unfollow` | Stop after step 2 (just the reports) |
| `./run_all.sh --cookies` | Log in to X by pasting cookies. Use this if the login page hangs (see Troubleshooting). |
| `./run_all.sh --help` | Show these options |

Options can be combined, e.g. `./run_all.sh --skip-counts --threshold 3000 --limit 25`.

### What happens at each step

**Step 1: who doesn't follow back** (`x_not_following_back.py`, a few seconds)
Compares `following.js` with `follower.js` and writes:
- `not_following_back.csv`: account ID and profile link for each one
- `not_following_back.html`: a clickable list you can open in a browser

**Step 2: follower counts** (`x_follower_counts.py`, ~6 s per account, so ~20 min for ~180 accounts)
Opens each profile in a hidden browser, without logging in, and writes:
- `follower_counts.csv`: handle, name and follower count for each account, saved as it goes
- `follower_counts_sorted.csv`: the same list, biggest accounts first

It resumes where it left off if interrupted. It also retries any accounts that timed out last time.

**Step 3: unfollow** (`x_unfollow.py`, ~65 s per account)
1. Lists every account under the threshold and asks **y/N**.
2. Opens Chrome on an X tab. Log in there the first time, then press Enter in the terminal. Later runs stay logged in.
3. For each account it opens a new tab, clicks **Unfollow**, confirms, checks the button turned back to "Follow", closes the tab, and waits **60 s + a random 1–5 s**.
4. Writes each result to `unfollow_log.csv`.

Accounts that were suspended or whose count couldn't be read are never unfollowed.

---

## While it's running

- You can **use other apps and other Chrome windows** normally.
- **Don't close or click inside the automation Chrome window.** Leave it open, even behind other windows.
- Keep the terminal open. On a Mac the script uses `caffeinate` so the computer doesn't sleep.
- **Ctrl+C** stops after the current account. Run the same command again to resume. Anyone already unfollowed is skipped.
- The unfollow step stops by itself if X logs you out, rate-limits you, or times out 3 times in a row. Wait a while and re-run.

---

## Running the scripts individually

```bash
source .venv/bin/activate          # after run_all.sh has created it once

python x_not_following_back.py                       # step 1
python x_follower_counts.py --show --limit 3         # step 2, watch 3 profiles as a test
python x_follower_counts.py                          # step 2, all
python x_unfollow.py --dry-run                       # step 3, preview
python x_unfollow.py --threshold 4500 --limit 20     # step 3, real
```

---

## Troubleshooting

**X's login page freezes after entering email/username.**
X is blocking the automated browser. Run with `--cookies` instead:
1. In your **everyday** Chrome, where you're logged in to x.com, open DevTools: `Cmd+Option+I` on Mac, `F12` on Windows/Linux.
2. Go to **Application → Cookies → https://x.com**.
3. Copy the values of **`auth_token`** and **`ct0`** and paste them when the script asks.

**Follower-count step shows `timeout` for some accounts.**
Run it again. It only retries the unfinished ones.

**"Google Chrome not found".**
Install Chrome. The script otherwise falls back to Playwright's Chromium, but X's login is more likely to hang there.

**`Missing following.js`.**
Copy `following.js` and `follower.js` from your export's `data/` folder into this folder.

---

## Privacy: don't commit these

These files hold your **X login** and must never be pushed to GitHub:

- `x_browser_profile/`: the Chrome profile the unfollow step stays logged in with
- `x_session.json`: a saved login, if you ever used `x_follower_counts.py --login`

Your export files (`following.js`, `follower.js`), `.venv/` and the generated CSV/HTML files also don't need to be in the repo. The included `.gitignore` excludes all of these.

---

## Caution

Automated browsing and bulk unfollowing are against X's terms of service. The 60-second spacing keeps this gentle. For more than ~100 unfollows, use `--limit` and spread them over a few days.

---

## Files

| File | Purpose |
|---|---|
| `run_all.sh` | Runs the full pipeline |
| `x_not_following_back.py` | Step 1: export → who doesn't follow back |
| `x_follower_counts.py` | Step 2: follower count per account |
| `x_unfollow.py` | Step 3: unfollow accounts under the threshold |
| `following.js`, `follower.js` | Your X export (you add these) |
| `not_following_back.csv/.html` | Output of step 1 |
| `follower_counts.csv`, `follower_counts_sorted.csv` | Output of step 2 |
| `unfollow_log.csv` | Output of step 3 |
