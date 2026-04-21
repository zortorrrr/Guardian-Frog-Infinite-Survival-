from __future__ import annotations

import csv
from pathlib import Path
from collections import Counter
import statistics

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.backends.backend_tkagg as tkagg
import tkinter as tk
from tkinter import ttk


class StatsAnalyzer:
    def __init__(self) -> None:
        self.logs_dir = Path(__file__).resolve().parent.parent / "logs"
        self.data: dict[str, list] = self._load_data()

    # ──────────────────────────────────────────────────────────────────────────
    #  Data loading
    # ──────────────────────────────────────────────────────────────────────────

    def _load_data(self) -> dict[str, list]:
        """Load all CSV data into memory."""
        data: dict[str, list] = {
            "attack_type":    [],
            "enemy_defeat":   [],
            "hover_duration": [],
            "damage_taken":   [],
            "survival_time":  [],
            "ability_loss":   [],   # "discard" or "hit"
        }

        for csv_type in data.keys():
            csv_path = self.logs_dir / f"{csv_type}.csv"
            if csv_path.exists():
                try:
                    with open(csv_path, "r") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row and "value" in row:
                                try:
                                    value = float(row["value"])
                                    data[csv_type].append(value)
                                except ValueError:
                                    data[csv_type].append(row["value"])
                except Exception:
                    pass

        return data

    # ──────────────────────────────────────────────────────────────────────────
    #  Statistical summaries
    # ──────────────────────────────────────────────────────────────────────────

    def get_summary_stats(self) -> dict:
        """Calculate summary statistics for all numerical features."""
        stats = {}

        def _num_stats(key: str) -> dict | None:
            nums = [v for v in self.data[key] if isinstance(v, (int, float))]
            if not nums:
                return None
            return {
                "mean":   statistics.mean(nums),
                "median": statistics.median(nums),
                "stdev":  statistics.stdev(nums) if len(nums) > 1 else 0.0,
                "min":    min(nums),
                "max":    max(nums),
                "count":  len(nums),
            }

        for key, label in [
            ("hover_duration", "hover_duration"),
            ("damage_taken",   "damage_taken"),
            ("survival_time",  "survival_time"),
        ]:
            s = _num_stats(key)
            if s:
                stats[label] = s

        # Enemy defeat — count only
        if self.data["enemy_defeat"]:
            stats["enemy_defeat"] = {"total": len(self.data["enemy_defeat"])}

        return stats

    def get_attack_distribution(self) -> dict[str, int]:
        """Attack type counts (string values only)."""
        counter: Counter = Counter()
        for value in self.data["attack_type"]:
            if isinstance(value, str):
                counter[value] += 1
        return dict(counter)

    def get_ability_loss_distribution(self) -> dict[str, int]:
        """Ability loss counts split by cause: 'discard' vs 'hit'."""
        counter: Counter = Counter()
        for value in self.data["ability_loss"]:
            if isinstance(value, str):
                counter[value] += 1
        return dict(counter)

    # ──────────────────────────────────────────────────────────────────────────
    #  Dashboard
    # ──────────────────────────────────────────────────────────────────────────

    def create_dashboard(self, root: tk.Tk | None = None) -> tk.Tk:
        """Create and display the statistics dashboard."""
        if root is None:
            root = tk.Tk()

        root.title("Guardian Frog — Statistics Dashboard")
        root.geometry("1400x900")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        summary_frame = ttk.Frame(notebook)
        notebook.add(summary_frame, text="Summary Statistics")
        self._create_summary_tab(summary_frame)

        graphs_frame = ttk.Frame(notebook)
        notebook.add(graphs_frame, text="Graphs")
        self._create_graphs_tab(graphs_frame)

        root.bind("<Escape>", lambda e: root.destroy())
        return root

    # ──────────────────────────────────────────────────────────────────────────
    #  Tab 1 — Summary statistics
    # ──────────────────────────────────────────────────────────────────────────

    def _create_summary_tab(self, parent: ttk.Frame) -> None:
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        ttk.Label(scrollable_frame, text="Summary Statistics", font=("Arial", 16, "bold")).pack(pady=10)

        stats = self.get_summary_stats()

        section_cfg = [
            ("hover_duration", "Hover Duration (ms)"),
            ("damage_taken",   "Damage Taken (HP)"),
            ("survival_time",  "Survival Time (seconds)"),
        ]
        for key, title in section_cfg:
            if key in stats:
                self._add_stat_section(scrollable_frame, title, stats[key])

        if "enemy_defeat" in stats:
            frame = ttk.LabelFrame(scrollable_frame, text="Enemy Defeat", padding=10)
            frame.pack(fill="x", padx=10, pady=5)
            ttk.Label(frame, text=f"Total Enemies Defeated: {stats['enemy_defeat']['total']}").pack()

        # Ability loss breakdown
        loss_dist = self.get_ability_loss_distribution()
        if loss_dist:
            frame = ttk.LabelFrame(scrollable_frame, text="Ability Loss", padding=10)
            frame.pack(fill="x", padx=10, pady=5)
            total = sum(loss_dist.values())
            for cause, count in sorted(loss_dist.items()):
                pct = count / total * 100 if total else 0
                ttk.Label(frame, text=f"{cause.title()}: {count}  ({pct:.1f}%)").pack(anchor="w")
            ttk.Label(frame, text=f"Total: {total}").pack(anchor="w")

        # Attack type breakdown
        atk_dist = self.get_attack_distribution()
        if atk_dist:
            frame = ttk.LabelFrame(scrollable_frame, text="Attack Type Distribution", padding=10)
            frame.pack(fill="x", padx=10, pady=5)
            total = sum(atk_dist.values())
            for atk, count in sorted(atk_dist.items(), key=lambda x: -x[1]):
                pct = count / total * 100 if total else 0
                ttk.Label(frame, text=f"{atk}: {count}  ({pct:.1f}%)").pack(anchor="w")

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _add_stat_section(self, parent: ttk.Frame, title: str, stats_dict: dict) -> None:
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.pack(fill="x", padx=10, pady=5)
        for key, value in stats_dict.items():
            label_text = (
                f"{key.replace('_', ' ').title()}: {value:.2f}"
                if isinstance(value, float)
                else f"{key.replace('_', ' ').title()}: {value}"
            )
            ttk.Label(frame, text=label_text).pack(anchor="w")

    # ──────────────────────────────────────────────────────────────────────────
    #  Tab 2 — Graphs (2 × 2 grid)
    # ──────────────────────────────────────────────────────────────────────────

    def _create_graphs_tab(self, parent: ttk.Frame) -> None:
        """2 × 2 grid of graphs matching the proposal."""
        top_row = ttk.Frame(parent)
        top_row.pack(fill="both", expand=True)
        bot_row = ttk.Frame(parent)
        bot_row.pack(fill="both", expand=True)

        # Graph 1 — Pie: Attack Type Distribution
        pie_frame = ttk.LabelFrame(top_row, text="Graph 1 — Attack Type Distribution (Pie)")
        pie_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        pie_canvas = tk.Canvas(pie_frame)
        pie_canvas.pack(fill="both", expand=True)
        self._draw_attack_pie(pie_canvas)

        # Graph 2 — Histogram: Hover Duration
        hist_frame = ttk.LabelFrame(top_row, text="Graph 2 — Hover Duration Distribution (Histogram)")
        hist_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        hist_canvas = tk.Canvas(hist_frame)
        hist_canvas.pack(fill="both", expand=True)
        self._draw_hover_histogram(hist_canvas)

        # Graph 3 — Line: Cumulative Enemy Defeats Over Time
        line_frame = ttk.LabelFrame(bot_row, text="Graph 3 — Cumulative Enemy Defeats Over Time (Line)")
        line_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        line_canvas = tk.Canvas(line_frame)
        line_canvas.pack(fill="both", expand=True)
        self._draw_survival_line(line_canvas)

        # Graph 4 — Bar: Ability Loss Cause (Discard vs Hit)  ← fixed!
        bar_frame = ttk.LabelFrame(bot_row, text="Graph 4 — Ability Loss Cause (Bar)")
        bar_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        bar_canvas = tk.Canvas(bar_frame)
        bar_canvas.pack(fill="both", expand=True)
        self._draw_ability_loss_bar(bar_canvas)

    # ──────────────────────────────────────────────────────────────────────────
    #  Individual graph methods
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_attack_pie(self, canvas: tk.Canvas) -> None:
        """Pie chart — proportion of attack types used."""
        fig, ax = plt.subplots(figsize=(4, 4))
        attack_dist = self.get_attack_distribution()
        if not attack_dist:
            ax.text(0.5, 0.5, "No attack data yet", ha="center", va="center", fontsize=12)
            ax.axis("off")
        else:
            labels = list(attack_dist.keys())
            sizes  = list(attack_dist.values())
            colors = ["#FF7846", "#7BD4FF", "#B0E857", "#FFD166", "#C3B1FF"]
            ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90,
                   colors=colors[:len(labels)])
            ax.set_title("Attack Type Distribution", fontsize=12)
        self._embed_figure(fig, canvas)

    def _draw_hover_histogram(self, canvas: tk.Canvas) -> None:
        """Histogram — distribution of individual hover durations (ms)."""
        fig, ax = plt.subplots(figsize=(4, 4))
        hover_data = [v for v in self.data["hover_duration"] if isinstance(v, (int, float)) and v > 0]
        if not hover_data:
            ax.text(0.5, 0.5, "No hover data yet", ha="center", va="center", fontsize=12)
            ax.axis("off")
        else:
            ax.hist(hover_data, bins=20, color="#7BD4FF", edgecolor="black", alpha=0.8)
            ax.set_xlabel("Duration (ms)")
            ax.set_ylabel("Frequency")
            ax.set_title("Hover Duration Distribution", fontsize=12)
            ax.grid(axis="y", alpha=0.4)
        self._embed_figure(fig, canvas)

    def _draw_survival_line(self, canvas: tk.Canvas) -> None:
        """Line graph — cumulative enemy defeats over survival time."""
        fig, ax = plt.subplots(figsize=(4, 4))
        survival_data = sorted(v for v in self.data["survival_time"] if isinstance(v, (int, float)))
        enemy_count   = len(self.data["enemy_defeat"])

        if not survival_data or enemy_count == 0:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center", fontsize=12)
            ax.axis("off")
        else:
            # Map survival time samples to cumulative enemy count linearly
            n = min(len(survival_data), enemy_count)
            xs = survival_data[:n]
            ys = list(range(1, n + 1))
            ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.5, color="#FF7846")
            ax.set_xlabel("Survival Time (s)")
            ax.set_ylabel("Cumulative Enemies Defeated")
            ax.set_title("Cumulative Enemy Defeats Over Time", fontsize=12)
            ax.grid(alpha=0.3)
        self._embed_figure(fig, canvas)

    def _draw_ability_loss_bar(self, canvas: tk.Canvas) -> None:
        """Bar graph — ability loss by cause: Discard vs Hit (from taking damage)."""
        fig, ax = plt.subplots(figsize=(4, 4))
        loss_dist = self.get_ability_loss_distribution()

        if not loss_dist:
            ax.text(0.5, 0.5, "No ability-loss data yet", ha="center", va="center", fontsize=12)
            ax.axis("off")
        else:
            causes = list(loss_dist.keys())
            counts = [loss_dist[c] for c in causes]
            bar_colors = {"discard": "#7BD4FF", "hit": "#FF7846"}
            colors = [bar_colors.get(c, "#C3B1FF") for c in causes]

            bars = ax.bar(causes, counts, color=colors, edgecolor="black", alpha=0.85)
            ax.bar_label(bars, padding=3)
            ax.set_xlabel("Cause of Ability Loss")
            ax.set_ylabel("Total Count")
            ax.set_title("Ability Loss: Discard vs Hit", fontsize=12)
            ax.grid(axis="y", alpha=0.4)
            # Capitalise x-tick labels
            ax.set_xticklabels([c.title() for c in causes])
        self._embed_figure(fig, canvas)

    # ──────────────────────────────────────────────────────────────────────────
    #  Embed helper
    # ──────────────────────────────────────────────────────────────────────────

    def _embed_figure(self, fig: plt.Figure, canvas: tk.Canvas) -> None:
        tk_agg = tkagg.FigureCanvasTkAgg(fig, master=canvas)
        tk_agg.draw()
        tk_agg.get_tk_widget().pack(fill="both", expand=True)
        plt.close(fig)