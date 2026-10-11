"""
AI RACE: GPQA Diamond, Nov 2022 -> Oct 2026
Black background, glowing lines, month-by-month reveal.

Each line is a lab's BEST GPQA Diamond score so far (a lab's line only
steps up when it ships a model that beats its own previous best). The head
of each line shows the lab's current best model.

Requirements:
    pip install matplotlib numpy
    ffmpeg for MP4 output (falls back to GIF without it)

Run:
    python ai_race.py
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ---------------------------------------------------------------- data ---
# (release "YYYY-MM", lab, model, GPQA Diamond %)
# Scores are developer-reported unless the comment says otherwise.
#   [retro]  measured after release (GPQA was published Nov 2023), from the
#            GPQA paper / later evals
#   [scaled] headline uses parallel test-time compute / majority voting;
#            the single-run number is lower (given in the comment)
#   [indep]  no developer number found; independent (Artificial Analysis)
RELEASES = [
    # OpenAI
    ("2022-11", "OpenAI",    "GPT-3.5 (ChatGPT)",   28.1),  # [retro] GPQA paper
    ("2023-03", "OpenAI",    "GPT-4",               38.8),  # [retro] GPQA paper
    ("2024-05", "OpenAI",    "GPT-4o",              53.6),
    ("2024-09", "OpenAI",    "o1-preview",          73.3),
    ("2024-12", "OpenAI",    "o1",                  78.0),
    ("2025-01", "OpenAI",    "o3-mini (high)",      79.7),
    ("2025-02", "OpenAI",    "GPT-4.5",             71.4),
    ("2025-04", "OpenAI",    "o3",                  83.3),
    ("2025-08", "OpenAI",    "GPT-5 Pro",           88.4),  # GPT-5 Thinking: 85.7
    ("2025-11", "OpenAI",    "GPT-5.1",             88.1),
    ("2025-12", "OpenAI",    "GPT-5.2",             92.4),  # Pro: 93.2
    ("2026-03", "OpenAI",    "GPT-5.4",             92.8),
    ("2026-04", "OpenAI",    "GPT-5.5",             93.6),
    ("2026-09", "OpenAI",    "GPT-6 Astra",         96.0),

    # Anthropic
    ("2024-03", "Anthropic", "Claude 3 Opus",       50.4),
    ("2024-06", "Anthropic", "Claude 3.5 Sonnet",   59.4),
    ("2024-10", "Anthropic", "Claude 3.5 Sonnet v2", 65.0),
    ("2025-02", "Anthropic", "Claude 3.7 Sonnet",   84.8),  # [scaled] single run 78.2
    ("2025-05", "Anthropic", "Claude Opus 4",       79.6),
    ("2025-08", "Anthropic", "Claude Opus 4.1",     80.9),
    ("2025-09", "Anthropic", "Claude Sonnet 4.5",   83.4),
    ("2025-11", "Anthropic", "Claude Opus 4.5",     87.0),
    ("2026-02", "Anthropic", "Claude Opus 4.6",     91.3),
    ("2026-04", "Anthropic", "Claude Opus 4.7",     94.2),
    ("2026-05", "Anthropic", "Claude Opus 4.8",     93.6),

    # Google
    ("2024-05", "Google",    "Gemini 1.5 Pro",      46.2),
    ("2025-01", "Google",    "Gemini 2.0 Flash Thinking", 74.2),
    ("2025-03", "Google",    "Gemini 2.5 Pro",      84.0),
    ("2025-06", "Google",    "Gemini 2.5 Pro (GA)", 86.4),
    ("2025-11", "Google",    "Gemini 3 Pro",        91.9),
    ("2026-02", "Google",    "Gemini 3.1 Pro",      94.3),
    ("2026-09", "Google",    "Gemini 3.8 Flash",    95.3),  # [indep]

    # xAI
    ("2024-08", "xAI",       "Grok 2",              56.0),
    ("2025-02", "xAI",       "Grok 3 (Think)",      84.6),  # [scaled]
    ("2025-07", "xAI",       "Grok 4",              87.5),  # Heavy: 88.9
    ("2026-08", "xAI",       "Grok 4.6",            94.9),  # [indep]

    # DeepSeek
    ("2024-12", "DeepSeek",  "DeepSeek V3",         59.1),
    ("2025-01", "DeepSeek",  "DeepSeek R1",         71.5),
    ("2025-05", "DeepSeek",  "DeepSeek R1-0528",    81.0),
    ("2025-12", "DeepSeek",  "DeepSeek V3.2",       82.4),
    ("2026-04", "DeepSeek",  "DeepSeek V4-Pro",     90.1),

    # Meta
    ("2024-07", "Meta",      "Llama 3.1 405B",      51.1),
    ("2025-04", "Meta",      "Llama 4 Maverick",    69.8),
]

START, END = "2022-11", "2026-10"

colors = {
    "OpenAI":    "#4da3ff",
    "Anthropic": "#ff8c42",
    "Google":    "#b366ff",
    "xAI":       "#e0e0e0",
    "DeepSeek":  "#33cc99",
    "Meta":      "#ff5c8a",
}

PHD_EXPERTS = 69.7   # OpenAI's recruited PhD-expert panel on GPQA Diamond
RANDOM_GUESS = 25.0  # 4-option multiple choice

# ------------------------------------------------- build monthly series ---
def month_index(ym):
    y, m = map(int, ym.split("-"))
    sy, sm = map(int, START.split("-"))
    return (y - sy) * 12 + (m - sm)

n_months = month_index(END) + 1
labels = []
for i in range(n_months):
    sy, sm = map(int, START.split("-"))
    tot = sy * 12 + (sm - 1) + i
    labels.append((tot // 12, tot % 12 + 1))
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

labs = list(colors.keys())
values = np.full((len(labs), n_months), np.nan)   # best-so-far score
heads = [[None] * n_months for _ in labs]          # model holding that best
for k, lab in enumerate(labs):
    rel = sorted((month_index(d), s, m) for d, l, m, s in RELEASES if l == lab)
    best, best_model = np.nan, None
    for i in range(n_months):
        for mi, s, m in rel:
            if mi == i and (np.isnan(best) or s > best):
                best, best_model = s, m
        values[k, i] = best
        heads[k][i] = best_model

# ------------------------------------------------------------- setup ---
plt.rcParams["font.family"] = "DejaVu Sans"
fig, ax = plt.subplots(figsize=(12, 6.75), dpi=150)
fig.patch.set_facecolor("black")
ax.set_facecolor("black")
fig.subplots_adjust(left=0.07, right=0.80, top=0.88, bottom=0.09)

FRAMES_PER_MONTH = 10
HOLD_FRAMES = 48  # pause on the final frame
n_frames = (n_months - 1) * FRAMES_PER_MONTH + HOLD_FRAMES

ax.set_xlim(0, n_months - 1)
ax.set_ylim(20, 100)
year_ticks = [i for i, (y, m) in enumerate(labels) if m == 1]
ax.set_xticks(year_ticks)
ax.set_xticklabels([str(labels[i][0]) for i in year_ticks], color="white", fontsize=10)
ax.set_yticks(range(20, 101, 10))
ax.set_yticklabels([f"{v}%" for v in range(20, 101, 10)], color="white", fontsize=9)
ax.tick_params(colors="white")
for spine in ax.spines.values():
    spine.set_color("#333333")
ax.grid(True, color="#222222", linewidth=0.5, alpha=0.7)
ax.set_ylabel("GPQA Diamond accuracy", color="white", fontsize=11)
fig.suptitle("AI RACE: PhD-level science (GPQA Diamond)",
             color="white", fontsize=16, fontweight="bold", y=0.96)
fig.text(0.07, 0.905, "Best score per lab so far · developer-reported where available",
         color="#888888", fontsize=9)

# reference lines
for yv, txt in [(PHD_EXPERTS, f"PhD experts {PHD_EXPERTS}%"),
                (RANDOM_GUESS, "Random guessing 25%")]:
    ax.axhline(yv, color="#666666", linestyle="--", linewidth=1)
    ax.text(0.3, yv + 0.8, txt, color="#888888", fontsize=8, va="bottom")

glow_lines, main_lines, dots, tags = [], [], [], []
for lab in labs:
    g, = ax.plot([], [], color=colors[lab], linewidth=8, alpha=0.18,
                 solid_capstyle="round")
    l, = ax.plot([], [], color=colors[lab], linewidth=2.5,
                 solid_capstyle="round", label=lab)
    d, = ax.plot([], [], "o", color=colors[lab], markersize=6)
    t = ax.text(0, 0, "", color=colors[lab], fontsize=8.5, fontweight="bold",
                va="center", ha="left", clip_on=False)
    glow_lines.append(g); main_lines.append(l); dots.append(d); tags.append(t)

date_text = ax.text(0.98, 0.06, "", transform=ax.transAxes, color="white",
                    fontsize=24, fontweight="bold", ha="right", va="bottom",
                    alpha=0.85)
ax.legend(facecolor="black", edgecolor="#333333", labelcolor="white",
          loc="upper left", fontsize=9)

# ---------------------------------------------------------- animation ---
def spread(ys, min_gap):
    """Nudge label y-positions apart so tags don't overlap."""
    order = np.argsort(ys)[::-1]          # highest first
    out = np.array(ys, dtype=float)
    out[order[0]] = min(out[order[0]], 98.5)
    for a, b in zip(order[:-1], order[1:]):
        if out[a] - out[b] < min_gap:     # push lower label down
            out[b] = out[a] - min_gap
    return out

def update(frame):
    t = min(frame / FRAMES_PER_MONTH, n_months - 1)
    i = int(t)
    j = min(i + 1, n_months - 1)
    frac = t - i
    frac = frac * frac * (3 - 2 * frac)  # ease in-out

    head_y, head_idx = [], []
    for k in range(len(labs)):
        row = values[k]
        valid = np.where(~np.isnan(row[:i + 1]))[0]
        if len(valid) == 0:
            for art in (glow_lines[k], main_lines[k], dots[k]):
                art.set_data([], [])
            tags[k].set_text("")
            continue
        xs = list(valid.astype(float))
        ys = list(row[valid])
        if j > i and not np.isnan(row[j]):
            yc = (1 - frac) * row[i] + frac * row[j]
            xs.append(t); ys.append(yc)
        glow_lines[k].set_data(xs, ys)
        main_lines[k].set_data(xs, ys)
        dots[k].set_data([xs[-1]], [ys[-1]])
        head_y.append(ys[-1]); head_idx.append(k)
        model = heads[k][i]
        tags[k].set_text(f"{model}  {row[i]:.1f}%")

    if head_y:
        ly = spread(head_y, 3.2)
        for k, y in zip(head_idx, ly):
            tags[k].set_position((t + 0.6, y))

    y, m = labels[i]
    date_text.set_text(f"{MONTH_NAMES[m - 1]} {y}")
    return glow_lines + main_lines + dots + tags + [date_text]

anim = FuncAnimation(fig, update, frames=n_frames, interval=1000 / 24, blit=False)

# -------------------------------------------------------------- save ---
if __name__ == "__main__":
    try:
        anim.save("ai_race.mp4", writer="ffmpeg", fps=24,
                  savefig_kwargs={"facecolor": "black"})
        print("Saved ai_race.mp4")
    except Exception as e:
        print(f"ffmpeg not available ({e}), saving GIF instead...")
        anim.save("ai_race.gif", writer="pillow", fps=24,
                  savefig_kwargs={"facecolor": "black"})
        print("Saved ai_race.gif")
