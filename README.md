# Guardian Frog 🐸

A 2D side-scrolling action game built with Python and Pygame.  
Play as a Kirby-inspired frog who snatches insect enemies, swallows their powers, and survives endless waves — including a repeating Queen Bee boss battle.

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
| Move left / right | `A` / `D` or `←` / `→` |
| Jump (multi-jump) | `W` or `↑` |
| Hover | Hold `Space` |
| Snatch enemy | `J` (no enemy held) |
| Spit star ★ | `J` (enemy held in mouth) |
| Swallow power | `↓ Down` (enemy held in mouth) |
| Use ability | `K` (after swallowing) |
| Hold for flamethrower | Hold `K` (fire ability only) |
| Discard ability | `Q` |

---

## Project Structure

```
guardian-frog/
├── main.py                  # Entry point
├── show_stats.py            # Standalone stats dashboard launcher
├── requirements.txt
├── README.md
├── DESCRIPTION.md
├── .gitignore
├── LICENSE
├── assets/
│   ├── frog/                # Player sprites
│   ├── fire/                # Fire wasp sprites
│   ├── ice/                 # Ice beetle sprites
│   ├── sword/               # Sword mantis sprites
│   ├── icons/               # Ability icons, heart icons
│   ├── sounds/              # Sound effects
│   └── menu/                # Menu background, logo, lose screen
├── game/
│   ├── __init__.py
│   ├── settings.py          # Global constants
│   ├── entities.py          # Entity base class, Player
│   ├── enemies.py           # InsectEnemy, QueenBeeBoss, spawn helper
│   ├── projectiles.py       # Projectile, SnowWall, BossStinger
│   ├── game_manager.py      # Main game loop and orchestration
│   ├── data_logger.py       # CSV event logger
│   └── stats_analyzer.py    # Tkinter statistics dashboard
├── logs/                    # Auto-generated CSV log files (git-ignored)
└── screenshots/
    ├── gameplay/
    └── visualization/
        └── VISUALIZATION.md
```

---

## Logs

CSV log files are written automatically to the `logs/` directory during gameplay. They are excluded from version control via `.gitignore`.
