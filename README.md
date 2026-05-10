# Guardian Frog 🐸

## Project Description

- **Project by:** Kasithat Panya (6810545450)
- **Course:** Computer Programming II (01219116), Section 450, Semester 2/2025
- **Game Genre:** Action, Survival, Platformer

Guardian Frog is a 2D side-scrolling action-survival game built with Python and Pygame-CE. Play as a frog who snatches insect enemies with its tongue, swallows them to steal their elemental powers, and survives endless waves — including a repeating Queen Bee boss battle every 25 kills.

The project includes a live statistics dashboard (Tkinter + Matplotlib) that records and visualises player behaviour data in real time.

---

## Installation

### Clone the repository

```sh
git clone https://github.com/<your-username>/guardian-frog.git
cd guardian-frog
```

### Create and activate a virtual environment

**Windows:**
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS:**
```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running Guide

After activating the virtual environment, run the game with:

**Windows:**
```bat
python main.py
```

**macOS:**
```sh
python3 main.py
```

The game window will open at **960 × 620**. Click **Play** on the main menu to start.

To run the statistics dashboard standalone (without starting the game):

**Windows:**
```bat
python show_stats.py
```

**macOS:**
```sh
python3 show_stats.py
```

> The game also opens the dashboard automatically when you click the **Statistics** button in the main menu.

---

## Tutorial / Usage

### Basic Controls

| Action | Key |
|---|---|
| Move left / right | `A` / `D` or `←` / `→` |
| Jump (multi-jump up to 20×) | `W` or `↑` |
| Hover (slow fall) | Hold `W` or `↑` while airborne |
| Snatch enemy with tongue | `J` (no enemy held) |
| Spit enemy as projectile | `J` (enemy held in mouth) |
| Swallow enemy to copy power | `S` or `↓` (enemy held in mouth) |
| Use ability | `K` |
| Hold for continuous flamethrower | Hold `K` (fire ability only) |
| Discard current ability | `Q` |

### How to Play

1. **Survive** — enemies spawn in endless waves from the sides of the screen
2. **Snatch** — press `J` near an enemy to catch it with your tongue
3. **Choose** — spit it out (`J`) as a projectile, or swallow it (`↓`) to copy its power
4. **Power-Swap Rule** — if you already have an ability, press `Q` to discard it before swallowing a new one
5. **Boss** — after every 25 kills the Queen Bee spawns; defeat her to keep your kill streak going

### Abilities

| Enemy | Ability Gained | How to Use |
|---|---|---|
| Fire Wasp | Flamethrower | Hold `K` to continuously shoot fire |
| Ice Beetle | Snowfall | Press `K` to drop an ice wall |
| Sword Mantis | Sword Whirlwind | Press `K` for a forward slash arc |

### Statistics Dashboard

- Click **Statistics** in the main menu to open the dashboard
- **Summary tab** — descriptive statistics table and distribution cards
- **Graphs tab** — pie chart, histogram, line/bar chart, one per data feature
- Use the **Sessions** sidebar to filter by a specific play session

---

## Game Features

- **Ability absorption** — snatch an enemy with your tongue, then swallow it to steal its power: Flamethrower, Snowfall (ice wall), or Sword Whirlwind
- **Power-Swap Gate** — must press `Q` to discard the current ability before swallowing a new one, adding strategic decision-making
- **Multi-jump & hover** — up to 20 jumps with decaying velocity; hold the jump key to hover and slow your fall
- **Three enemy archetypes** — Fire Wasp (fast, 0.5 HP damage), Ice Beetle (slow, 1.0 HP damage), Sword Mantis (very fast, 0.25 HP damage), each with animated pixel-art sprites
- **Flying variants** — 25% of enemies ignore gravity and float directly toward the player
- **Repeating Queen Bee boss** — spawns every 25 kills, floats freely, fires aimed stingers, and has 20 HP segments
- **Granular HP system** — 4-state HP bar segments (full / ¾ / ½ / ¼) matching the four damage values
- **8-bit pixel art VFX** — all effects (flamethrower cone, sword slash arc, star projectile, defeat burst) drawn on a fixed pixel grid
- **Animated menu** — main menu with animated fireflies, logo, and clickable buttons
- **Live statistics dashboard** — separate Tkinter + Matplotlib window with session selector, summary statistics table, and four graph types
- **Custom pixel font** — all HUD text rendered with a hand-authored 5×7 bitmap font (no external font files)
- **Real-time CSV logging** — six event types recorded per-event during gameplay for statistical analysis

---

## Known Bugs

- Background music (`bg_music.wav`) uses a relative path — launching the game from a directory other than the project root may cause an audio load error. **Workaround:** always run `python main.py` (or `python3 main.py`) from the project root folder.

---

## Unfinished Works

- Boss difficulty does not scale between waves — every Queen Bee encounter is currently identical in speed and attack rate. A `difficulty_level` parameter exists in `QueenBeeBoss` but is not yet passed from `GameManager`.

---

## External Sources

### Libraries & Frameworks

| Library | Purpose | License |
|---|---|---|
| [Pygame-CE 2.5.x](https://pyga.me/) | Game loop, rendering, input, audio | LGPL-2.1 |
| [pandas](https://pandas.pydata.org/) | CSV data loading and manipulation | BSD-3 |
| [matplotlib](https://matplotlib.org/) | Statistical graph rendering | BSD-style |
| [seaborn](https://seaborn.pydata.org/) | Graph styling | BSD-3 |
| tkinter (stdlib) | Statistics dashboard UI | PSF License |

### Visual & Audio Assets

All sprite art (player frog, fire wasp, ice beetle, sword mantis, Queen Bee boss, menu backgrounds, logo), visual effects, and background music (`bg_music.wav`) were **generated with AI assistance (Claude, Anthropic)** and are original to this project. No third-party art or audio assets were sourced from external repositories.

### Font

The `PixelFont` class and its complete 5×7 bitmap glyph set (A–Z, 0–9, symbols) were **written from scratch** as original code with no external font files or libraries.