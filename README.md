# Guardian Frog 🐸

A 2D side-scrolling action game built with Python and Pygame.  
Play as a frog who snatches insect enemies, swallows their powers, and survives endless waves — including a repeating Queen Bee boss battle.

---

## Requirements

- Python **3.10** or higher
- pip

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/guardian-frog.git
cd guardian-frog
```

### 2. (Recommended) Create and activate a virtual environment

```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running the Game

```bash
python main.py
```

The game window will open at 960 × 620. Use the **Play** button on the main menu to start.

---

## Running the Statistics Dashboard (standalone)

The stats dashboard can also be launched independently without starting the game:

```bash
python show_stats.py
```

> **Note:** The game automatically launches the dashboard in a separate process when you click the **Stats** button in the main menu, so you don't need to run this manually during normal play.

---

## Controls

| Action | Key(s) |
|--------|--------|
| Move left / right | `A` / `D` or `Left` / `Right` |
| Jump (multi-jump) | `W` or `UP` |
| Hover | Hold `W or UP` |
| Snatch enemy | `J` (no enemy held) |
| Spit star ★ | `J` (enemy held in mouth) |
| Swallow power | `S or Down` (enemy held in mouth) |
| Use ability | `K` (after swallowing) |
| Hold for flamethrower | Hold `K` (fire ability only) |
| Discard ability | `Q` |

---

## Project Structure

```
guardian-frog/
├── main.py                  # Entry point
├── show_stats.py            # Standalone stats dashboard launcher
├── bg_music.wav             # Background music (loops during gameplay)
├── requirements.txt
├── README.md
├── DESCRIPTION.md
├── gitignore
├── assets/
│   ├── frog/                # Player sprites
│   ├── fire/                # Fire wasp sprites
│   ├── ice/                 # Ice beetle sprites
│   ├── sword/               # Sword mantis sprites
│   ├── sounds/              # Sound effects
│   └── menu/                # Menu background, logo, lose screen
├── game/
│   ├── __init__.py
│   ├── settings.py          # Global constants
│   ├── entities.py          # Entity base class, Player
│   ├── enemies.py           # InsectEnemy, QueenBeeBoss, spawn helper
│   ├── projectiles.py       # Projectile, SnowWall, BossStinger
│   ├── game_manager.py      # Main game loop and orchestration
│   ├── pixel_font.py        # Custom 5×7 bitmap HUD font
│   ├── data_logger.py       # CSV event logger
│   └── stats_analyzer.py    # Tkinter statistics dashboard
├── logs/                    # Auto-generated CSV log files
└── screenshots/
    └── visualization/
        └── VISUALIZATION.md
```

---

## Logs

CSV log files are written automatically to the `logs/` directory during gameplay.

---

## Game Features

- **Ability absorption** — snatch an enemy with your tongue, then swallow it to steal its power: flamethrower, snowfall (ice wall), or sword swing
- **Multi-jump & hover** — up to 20 jumps with decaying velocity; hold the jump key in the air to hover and slow your fall
- **Three enemy archetypes** — Fire Wasp (fast, moderate damage), Ice Beetle (slow, hard hit), Sword Mantis (very fast, light damage), each with animated sprites
- **Flying variants** — 25% of enemies ignore gravity and float directly toward the player
- **Repeating Queen Bee boss** — spawns every 25 kills, floats sinusoidally, fires spread stingers, and has 20 HP
- **Discard mechanic** — press `Q` to launch the current ability as a spinning projectile
- **Particle VFX** — defeat explosions, hover glow, screen shake on boss death, and combo pop-ups
- **Animated menu** — main menu with animated fireflies, logo, and mouse-clickable buttons
- **Live statistics dashboard** — separate Tkinter + Matplotlib window showing per-session graphs and summary stats
- **Custom pixel font** — all HUD text rendered with a hand-authored 5×7 bitmap font (no external font files)

---

## Known Bugs

- Background music (`bg_music.wav`) is loaded with a hardcoded relative path, so launching the game from a different working directory will cause a crash.

---

## Unfinished Works

- Boss difficulty does not currently scale between waves — the `difficulty_level` parameter exists on `QueenBeeBoss` but is never passed from `GameManager`, so every boss encounter is identical.

---

## External Sources

Visual & Audio Assets
All sprite art (player frog, fire wasp, ice beetle, sword mantis, Queen Bee boss, menu backgrounds, logo), visual effects, and background music (bg_music.wav) were generated with AI assistance (Claude, Anthropic) and are original to this project. No third-party art or audio assets were used from external sources.

Font
The PixelFont class and its 5×7 bitmap glyph set were written from scratch as original code — no external font files or libraries.