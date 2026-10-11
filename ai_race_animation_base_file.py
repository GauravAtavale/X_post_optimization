"""
Animated line-chart race like the "AI RACE: Monthly Active Users" video.
Black background, glowing lines, month-by-month reveal.

Requirements:
    pip install matplotlib numpy
    For MP4 output you also need ffmpeg installed.
    (Without ffmpeg, it will save a GIF instead.)

Run:
    python ai_race.py
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")  # no pop-up window; just saves the file
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ---------------------------------------------------------------- data ---
# Monthly active users, in millions. Replace with your own numbers.
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

data = {
    "ChatGPT":    [600, 620, 640, 660, 690, 720, 750, 770, 790, 800, 810, 830],
    "Gemini":     [350, 380, 400, 420, 450, 480, 500, 520, 540, 560, 590, 650],
    "Meta AI":    [400, 420, 450, 470, 500, 520, 540, 560, 580, 600, 620, 700],
    "Copilot":    [120, 130, 140, 150, 160, 175, 190, 200, 210, 220, 230, 250],
    "Grok":       [ 30,  40,  55,  70,  90, 110, 130, 150, 170, 190, 210, 230],
    "DeepSeek":   [ 10,  25,  60,  80,  95, 110, 125, 140, 155, 170, 185, 200],
    "Perplexity": [ 15,  18,  22,  28,  35,  45,  55,  65,  75,  85,  95, 110],
    "Claude":     [ 20,  24,  28,  32,  38,  44,  50,  56,  62,  68,  74,  82],
}

colors = {
    "ChatGPT":    "#4da3ff",  # blue
    "Gemini":     "#b366ff",  # purple
    "Meta AI":    "#4dd2ff",  # light blue
    "Copilot":    "#ff7043",  # orange
    "Grok":       "#e0e0e0",  # white/grey
    "DeepSeek":   "#4488ff",  # deep blue
    "Perplexity": "#33cc99",  # teal
    "Claude":     "#ff8c42",  # warm orange
}

# ------------------------------------------------------------- setup ---
plt.rcParams["font.family"] = "DejaVu Sans"
fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
fig.patch.set_facecolor("black")
ax.set_facecolor("black")

names = list(data.keys())
values = np.array([data[n] for n in names], dtype=float)  # shape: (tools, months)
n_months = len(months)
FRAMES_PER_MONTH = 12
n_frames = n_months * FRAMES_PER_MONTH

ax.set_xlim(0, n_months - 1)
ax.set_ylim(0, values.max() * 1.15)
ax.set_xticks(range(n_months))
ax.set_xticklabels(months, color="white", fontsize=9)
ax.tick_params(colors="white")
for spine in ax.spines.values():
    spine.set_color("#333333")
ax.grid(True, color="#222222", linewidth=0.5, alpha=0.7)
ax.set_ylabel("Monthly Active Users (millions)", color="white", fontsize=11)
ax.set_title("AI RACE: Monthly Active Users (2025)",
             color="white", fontsize=15, fontweight="bold", pad=12)

lines = {}
for name in names:
    # "Glow": a thick translucent line under the crisp main line
    ax.plot([], [], color=colors[name], linewidth=8, alpha=0.18,
            solid_capstyle="round")[0]
    line, = ax.plot([], [], color=colors[name], linewidth=2.5,
                    solid_capstyle="round", label=name)
    lines[name] = line

month_text = ax.text(0.98, 0.92, "", transform=ax.transAxes, color="white",
                     fontsize=22, fontweight="bold", ha="right", va="top")
ax.legend(facecolor="black", edgecolor="#333333", labelcolor="white",
          loc="upper left", fontsize=9)

# ---------------------------------------------------------- animation ---
def frame_values(t):
    """Interpolated values at continuous time t (in month units)."""
    i = int(np.clip(t, 0, n_months - 1))
    j = min(i + 1, n_months - 1)
    frac = np.clip(t - i, 0, 1)
    # ease in-out so motion looks smooth, not robotic
    frac = frac * frac * (3 - 2 * frac)
    return i, (1 - frac) * values[:, i] + frac * values[:, j]

def update(frame):
    t = frame / FRAMES_PER_MONTH
    month_idx, y = frame_values(t)
    for k, name in enumerate(names):
        # history up to current month + interpolated current point
        x_hist = list(range(month_idx + 1))
        y_hist = list(values[k, :month_idx + 1])
        if month_idx < n_months - 1:
            x_hist.append(t)
            y_hist.append(y[k])
        # glow line (thick, translucent) and main line share the same data
        ax.lines[2 * k].set_data(x_hist, y_hist)      # glow
        ax.lines[2 * k + 1].set_data(x_hist, y_hist)  # main
    month_text.set_text(months[month_idx])
    return list(ax.lines) + [month_text]

anim = FuncAnimation(fig, update, frames=n_frames, interval=50, blit=False)

# -------------------------------------------------------------- save ---
try:
    anim.save("ai_race.mp4", writer="ffmpeg", fps=24)
    print("Saved ai_race.mp4")
except Exception as e:
    print(f"ffmpeg not available ({e}), saving GIF instead…")
    anim.save("ai_race.gif", writer="pillow", fps=24)
    print("Saved ai_race.gif")
