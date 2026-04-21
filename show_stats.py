"""
show_stats.py — run this in a separate process to display the stats dashboard.
Called by GameManager via subprocess.Popen so it never conflicts with pygame.
"""
import sys
from pathlib import Path

# Make sure we can import from the game package
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
from game.stats_analyzer import StatsAnalyzer


def main() -> None:
    root = tk.Tk()
    analyzer = StatsAnalyzer()
    analyzer.create_dashboard(root)
    root.mainloop()   # ← blocks here until the window is closed


if __name__ == "__main__":
    main()