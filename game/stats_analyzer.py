from __future__ import annotations

import csv
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.backends.backend_tkagg as tkagg
import tkinter as tk
from tkinter import ttk

# ── iPhone Dark Mode palette ───────────────────────────────────────────────────
BG_PRIMARY   = "#000000"
BG_SECONDARY = "#1C1C1E"
BG_TERTIARY  = "#2C2C2E"
BG_ELEVATED  = "#3A3A3C"
SEP          = "#38383A"
LBL_PRIMARY  = "#FFFFFF"
LBL_SECONDARY= "#8E8E93"
LBL_TERTIARY = "#48484A"
SEL_BG       = "#1D3557"

IOS_BLUE   = "#0A84FF"
IOS_GREEN  = "#30D158"
IOS_ORANGE = "#FF9F0A"
IOS_RED    = "#FF453A"
IOS_PURPLE = "#BF5AF2"
IOS_PINK   = "#FF375F"
IOS_TEAL   = "#40CBE0"
IOS_INDIGO = "#5E5CE6"
IOS_YELLOW = "#FFD60A"

KEYS = ["attack_type", "enemy_defeat", "hover_duration",
        "damage_taken", "survival_time", "ability_loss"]


class StatsAnalyzer:
    def __init__(self) -> None:
        self.logs_dir = Path(__file__).resolve().parent.parent / "logs"
        self._all_data, self._sessions = self._load_data()

        # Shared state: None = "All Sessions", int = specific session_id
        self._selected_sid: int | None = None

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self) -> tuple[dict, dict]:
        all_data = {k: [] for k in KEYS}
        sessions: dict[int, dict] = {}

        for key in KEYS:
            path = self.logs_dir / f"{key}.csv"
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if not row or "value" not in row:
                            continue
                        raw = row["value"]
                        try:
                            val = float(raw)
                        except ValueError:
                            val = raw

                        sid = int(row.get("session_id", 0) or 0)

                        all_data[key].append(val)
                        if sid not in sessions:
                            sessions[sid] = {k: [] for k in KEYS}
                        sessions[sid][key].append(val)
            except Exception:
                pass

        return all_data, sessions

    # ── Derived stats ─────────────────────────────────────────────────────────

    @staticmethod
    def _num_stats(values: list) -> dict | None:
        nums = [v for v in values if isinstance(v, (int, float))]
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

    @staticmethod
    def _distribution(values: list) -> dict[str, int]:
        return dict(Counter(v for v in values if isinstance(v, str)))

    def _summary(self, data: dict) -> dict:
        out = {}
        for key in ("hover_duration", "damage_taken", "survival_time"):
            s = self._num_stats(data[key])
            if s:
                out[key] = s
        if data["enemy_defeat"]:
            out["enemy_defeat"] = {"total": len(data["enemy_defeat"])}
        return out

    def _data_for_sid(self, sid: int | None) -> dict:
        return self._all_data if sid is None else self._sessions.get(sid, {k: [] for k in KEYS})

    # ── Dashboard shell ───────────────────────────────────────────────────────

    def create_dashboard(self, root: tk.Tk | None = None) -> tk.Tk:
        if root is None:
            root = tk.Tk()

        root.title("Guardian Frog — Statistics")
        root.geometry("1380x860")
        root.configure(bg=BG_PRIMARY)
        root.resizable(True, True)
        self._apply_style(root)

        nb = ttk.Notebook(root, style="iOS.TNotebook")
        nb.pack(fill="both", expand=True)

        sf = tk.Frame(nb, bg=BG_PRIMARY)
        nb.add(sf, text="   Summary   ")
        gf = tk.Frame(nb, bg=BG_PRIMARY)
        nb.add(gf, text="   Graphs   ")

        self._build_summary_tab(sf)
        self._build_graphs_tab(gf)

        # When switching to Graphs tab, sync graphs to current session selection
        nb.bind("<<NotebookTabChanged>>", lambda e: self._sync_graphs_to_selection())

        root.bind("<Escape>", lambda e: root.destroy())
        return root

    def _apply_style(self, root: tk.Tk) -> None:
        s = ttk.Style(root)
        s.theme_use("clam")

        s.configure("iOS.TNotebook",
                    background=BG_SECONDARY, borderwidth=0, tabmargins=[0, 0, 0, 0])
        s.configure("iOS.TNotebook.Tab",
                    background=BG_SECONDARY, foreground=LBL_SECONDARY,
                    padding=[26, 10], font=("Arial", 11), borderwidth=0)
        s.map("iOS.TNotebook.Tab",
              background=[("selected", BG_PRIMARY)],
              foreground=[("selected", IOS_BLUE)])

        s.configure("iOS.Treeview",
                    background=BG_SECONDARY, foreground=LBL_PRIMARY,
                    fieldbackground=BG_SECONDARY, rowheight=36,
                    font=("Arial", 11), borderwidth=0, relief="flat")
        s.configure("iOS.Treeview.Heading",
                    background=BG_TERTIARY, foreground=LBL_SECONDARY,
                    font=("Arial", 10, "bold"), relief="flat", padding=[8, 6])
        s.map("iOS.Treeview",
              background=[("selected", BG_ELEVATED)],
              foreground=[("selected", LBL_PRIMARY)])

        s.configure("iOS.Vertical.TScrollbar",
                    background=BG_TERTIARY, troughcolor=BG_SECONDARY,
                    arrowcolor=LBL_TERTIARY, borderwidth=0, relief="flat")

    # ── Summary tab ───────────────────────────────────────────────────────────

    def _build_summary_tab(self, parent: tk.Frame) -> None:
        hdr = tk.Frame(parent, bg=BG_SECONDARY, height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="Statistics",
                 font=("Arial", 17, "bold"),
                 fg=LBL_PRIMARY, bg=BG_SECONDARY).pack(side="left", padx=20, pady=14)
        tk.Frame(parent, bg=SEP, height=1).pack(fill="x")

        body = tk.Frame(parent, bg=BG_PRIMARY)
        body.pack(fill="both", expand=True)

        # ── Left: session list ────────────────────────────────────────────────
        sidebar = tk.Frame(body, bg=BG_SECONDARY, width=230)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="SESSIONS",
                 font=("Arial", 10), fg=LBL_SECONDARY, bg=BG_SECONDARY,
                 anchor="w").pack(fill="x", padx=14, pady=(14, 6))

        lb_frame = tk.Frame(sidebar, bg=BG_SECONDARY)
        lb_frame.pack(fill="both", expand=True)

        self._session_lb = tk.Listbox(
            lb_frame,
            bg=BG_SECONDARY, fg=LBL_PRIMARY,
            selectbackground=SEL_BG, selectforeground=LBL_PRIMARY,
            activestyle="none",
            font=("Arial", 12),
            borderwidth=0, highlightthickness=0,
            relief="flat",
        )
        lb_sb = tk.Scrollbar(lb_frame, orient="vertical",
                             command=self._session_lb.yview,
                             bg=BG_TERTIARY, troughcolor=BG_SECONDARY,
                             activebackground=BG_ELEVATED,
                             highlightthickness=0, bd=0, relief="flat", width=6)
        self._session_lb.configure(yscrollcommand=lb_sb.set)
        lb_sb.pack(side="right", fill="y")
        self._session_lb.pack(side="left", fill="both", expand=True)

        sorted_sids = sorted(self._sessions.keys(), reverse=True)
        self._sidebar_ids: list[int | None] = [None] + sorted_sids

        self._session_lb.insert("end", "  All Sessions")
        for idx, sid in enumerate(sorted_sids):
            label = self._session_label(sid, len(sorted_sids) - idx)
            self._session_lb.insert("end", label)

        self._session_lb.select_set(0)
        self._session_lb.bind("<<ListboxSelect>>", self._on_session_select)

        tk.Frame(body, bg=SEP, width=1).pack(side="left", fill="y")

        # ── Right: stats panel ────────────────────────────────────────────────
        self._stats_panel = tk.Frame(body, bg=BG_PRIMARY)
        self._stats_panel.pack(side="left", fill="both", expand=True)

        self._render_stats(self._all_data)

    def _session_label(self, sid: int, num: int) -> str:
        kills = len(self._sessions[sid]["enemy_defeat"])
        surv  = self._sessions[sid]["survival_time"]
        secs  = int(max(surv)) if surv else 0
        m, s  = secs // 60, secs % 60

        if sid == 0:
            return f"  Legacy Data  —  {kills} kills"
        try:
            dt = datetime.fromtimestamp(sid)
            date_str = dt.strftime("%b %d  %H:%M")
        except Exception:
            date_str = "Unknown"

        return f"  Session {num}   ·   {date_str}\n  {kills} kills  ·  {m:02d}:{s:02d}"

    def _on_session_select(self, _event: tk.Event | None = None) -> None:
        sel = self._session_lb.curselection()
        if not sel:
            return
        idx  = sel[0]
        sid  = self._sidebar_ids[idx]
        self._selected_sid = sid
        data = self._data_for_sid(sid)
        self._render_stats(data)

    # ── Stats panel renderer ──────────────────────────────────────────────────

    def _render_stats(self, data: dict) -> None:
        for w in self._stats_panel.winfo_children():
            w.destroy()

        stats     = self._summary(data)
        loss_dist = self._distribution(data["ability_loss"])
        atk_dist  = self._distribution(data["attack_type"])

        cv  = tk.Canvas(self._stats_panel, bg=BG_PRIMARY, highlightthickness=0)
        vsb = ttk.Scrollbar(self._stats_panel, orient="vertical", command=cv.yview,
                            style="iOS.Vertical.TScrollbar")
        cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(cv, bg=BG_PRIMARY)
        wid   = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",
                lambda e: cv.itemconfig(wid, width=e.width))
        cv.bind("<MouseWheel>",
                lambda e: cv.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._group_lbl(inner, "NUMERICAL FEATURES")
        self._build_table(inner, stats)
        self._build_chips(inner, stats)

        cards_row = tk.Frame(inner, bg=BG_PRIMARY)
        cards_row.pack(fill="x", padx=16, pady=(4, 20))
        cards_row.columnconfigure((0, 1, 2), weight=1)

        col = 0
        if "enemy_defeat" in stats:
            self._enemy_card(cards_row, stats).grid(
                row=0, column=col, padx=(0, 10), sticky="nsew"); col += 1

        if loss_dist:
            self._dist_card(cards_row, "ABILITY LOSS", loss_dist,
                            label_map={"discard": "Discarded (Q)", "hit": "Lost on Hit"},
                            color_map={"discard": IOS_BLUE, "hit": IOS_RED}
                            ).grid(row=0, column=col, padx=(0, 10), sticky="nsew"); col += 1

        if atk_dist:
            cmap = {"star_spit": IOS_PINK, "snatch": IOS_GREEN,
                    "snowfall": IOS_TEAL, "whirlwind": IOS_PURPLE,
                    "flamethrower": IOS_ORANGE, "snatch_miss": LBL_SECONDARY}
            self._dist_card(cards_row, "ATTACK USAGE", atk_dist,
                            color_map=cmap
                            ).grid(row=0, column=col, sticky="nsew")

    # ── Widget builders ───────────────────────────────────────────────────────

    def _group_lbl(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text,
                 font=("Arial", 10), fg=LBL_SECONDARY,
                 bg=BG_PRIMARY, anchor="w").pack(fill="x", padx=16, pady=(14, 4))

    def _build_table(self, parent: tk.Frame, stats: dict) -> None:
        wrap = tk.Frame(parent, bg=BG_SECONDARY)
        wrap.pack(fill="x", padx=16, pady=(0, 4))

        cols   = ("feature", "mean", "median", "stdev", "min", "max", "n")
        hdrs   = ("Feature",       "Mean", "Median", "Std Dev", "Min", "Max", "n")
        widths = (180, 85, 85, 85, 75, 75, 50)

        tree = ttk.Treeview(wrap, columns=cols, show="headings",
                            style="iOS.Treeview", selectmode="none", height=3)
        for col, hdr, w in zip(cols, hdrs, widths):
            tree.heading(col, text=hdr, anchor="center")
            tree.column(col,  width=w,  anchor="center", stretch=True)
        tree.column("feature", anchor="w")

        defs = [("hover_duration","Hover Duration","ms"),
                ("damage_taken",  "Damage Taken",  "HP"),
                ("survival_time", "Survival Time", "s")]
        for i, (key, lbl, unit) in enumerate(defs):
            if key not in stats:
                continue
            s = stats[key]
            tree.insert("", "end",
                        tags=("alt" if i%2 else "base",),
                        values=(f"{lbl}  ({unit})",
                                f"{s['mean']:.2f}", f"{s['median']:.2f}",
                                f"{s['stdev']:.2f}", f"{s['min']:.2f}",
                                f"{s['max']:.2f}", str(s["count"])))

        tree.tag_configure("base", background=BG_SECONDARY)
        tree.tag_configure("alt",  background=BG_TERTIARY)

        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview,
                           style="iOS.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _build_chips(self, parent: tk.Frame, stats: dict) -> None:
        row = tk.Frame(parent, bg=BG_PRIMARY)
        row.pack(fill="x", padx=16, pady=10)

        defs = [("hover_duration","Avg Hover",   "ms", IOS_TEAL),
                ("damage_taken",  "Avg Damage",  "HP", IOS_RED),
                ("survival_time", "Avg Survival","s",  IOS_GREEN)]
        for col, (key, lbl, unit, color) in enumerate(defs):
            row.columnconfigure(col, weight=1)
            if key not in stats:
                continue
            val  = stats[key]["mean"]
            chip = tk.Frame(row, bg=BG_SECONDARY)
            chip.grid(row=0, column=col,
                      padx=(0 if col == 0 else 8, 0), sticky="ew")
            tk.Frame(chip, bg=color, height=3).pack(fill="x")
            tk.Label(chip, text=lbl, font=("Arial", 10),
                     fg=LBL_SECONDARY, bg=BG_SECONDARY).pack(pady=(8, 0))
            tk.Label(chip, text=f"{val:.1f}",
                     font=("Arial", 24, "bold"), fg=color, bg=BG_SECONDARY).pack()
            tk.Label(chip, text=unit, font=("Arial", 10),
                     fg=LBL_SECONDARY, bg=BG_SECONDARY).pack(pady=(0, 10))

    def _enemy_card(self, parent: tk.Widget, stats: dict) -> tk.Frame:
        card = tk.Frame(parent, bg=BG_SECONDARY)
        tk.Frame(card, bg=IOS_RED, height=3).pack(fill="x")
        tk.Label(card, text="☠  Enemies Defeated",
                 font=("Arial", 11, "bold"), fg=IOS_RED, bg=BG_SECONDARY
                 ).pack(pady=(12, 0))
        tk.Label(card, text=str(stats["enemy_defeat"]["total"]),
                 font=("Arial", 40, "bold"), fg=LBL_PRIMARY, bg=BG_SECONDARY
                 ).pack()
        tk.Label(card, text="total kills", font=("Arial", 10),
                 fg=LBL_SECONDARY, bg=BG_SECONDARY).pack(pady=(0, 14))
        return card

    def _dist_card(self, parent: tk.Widget, title: str, dist: dict,
                   label_map: dict | None = None,
                   color_map: dict | None = None) -> tk.Frame:
        label_map = label_map or {}
        color_map = color_map or {}
        total     = sum(dist.values())

        card = tk.Frame(parent, bg=BG_SECONDARY)
        tk.Frame(card, bg=IOS_INDIGO, height=3).pack(fill="x")
        tk.Label(card, text=title, font=("Arial", 11, "bold"),
                 fg=LBL_SECONDARY, bg=BG_SECONDARY, anchor="w"
                 ).pack(fill="x", padx=14, pady=(10, 6))
        tk.Frame(card, bg=SEP, height=1).pack(fill="x", padx=14)

        for i, (key, count) in enumerate(sorted(dist.items(), key=lambda x: -x[1])):
            pct   = count / total * 100 if total else 0
            color = color_map.get(key, IOS_INDIGO)
            label = label_map.get(key, key.replace("_", " ").title())

            if i > 0:
                tk.Frame(card, bg=SEP, height=1).pack(fill="x", padx=14)

            row = tk.Frame(card, bg=BG_SECONDARY)
            row.pack(fill="x", padx=14, pady=7)
            tk.Label(row, text="●", font=("Arial", 10),
                     fg=color, bg=BG_SECONDARY).pack(side="left", padx=(0, 6))
            tk.Label(row, text=label, font=("Arial", 10),
                     fg=LBL_PRIMARY, bg=BG_SECONDARY).pack(side="left")
            tk.Label(row, text=f"{count} ({pct:.0f}%)",
                     font=("Arial", 10), fg=LBL_SECONDARY,
                     bg=BG_SECONDARY).pack(side="right")

            bar_cv = tk.Canvas(card, bg=BG_TERTIARY, height=3,
                               highlightthickness=0, bd=0)
            bar_cv.pack(fill="x", padx=14, pady=(0, 2))

            def _draw(e, pct=pct, color=color):
                bar_cv.delete("all")
                filled = max(2, int(e.width * pct / 100))
                bar_cv.create_rectangle(0, 0, filled, 3, fill=color, outline="")

            bar_cv.bind("<Configure>", _draw)

        tk.Frame(card, bg=BG_SECONDARY, height=8).pack()
        return card

    # ── Graphs tab ────────────────────────────────────────────────────────────

    def _build_graphs_tab(self, parent: tk.Frame) -> None:
        hdr = tk.Frame(parent, bg=BG_SECONDARY, height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="Graphs", font=("Arial", 17, "bold"),
                 fg=LBL_PRIMARY, bg=BG_SECONDARY).pack(side="left", padx=20, pady=14)
        tk.Frame(parent, bg=SEP, height=1).pack(fill="x")

        body = tk.Frame(parent, bg=BG_PRIMARY)
        body.pack(fill="both", expand=True)

        # ── Left: session sidebar (same widget style as Summary tab) ──────────
        sidebar = tk.Frame(body, bg=BG_SECONDARY, width=230)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="SESSIONS",
                 font=("Arial", 10), fg=LBL_SECONDARY, bg=BG_SECONDARY,
                 anchor="w").pack(fill="x", padx=14, pady=(14, 6))

        lb_frame = tk.Frame(sidebar, bg=BG_SECONDARY)
        lb_frame.pack(fill="both", expand=True)

        self._graph_session_lb = tk.Listbox(
            lb_frame,
            bg=BG_SECONDARY, fg=LBL_PRIMARY,
            selectbackground=SEL_BG, selectforeground=LBL_PRIMARY,
            activestyle="none",
            font=("Arial", 12),
            borderwidth=0, highlightthickness=0,
            relief="flat",
        )
        lb_sb = tk.Scrollbar(lb_frame, orient="vertical",
                             command=self._graph_session_lb.yview,
                             bg=BG_TERTIARY, troughcolor=BG_SECONDARY,
                             activebackground=BG_ELEVATED,
                             highlightthickness=0, bd=0, relief="flat", width=6)
        self._graph_session_lb.configure(yscrollcommand=lb_sb.set)
        lb_sb.pack(side="right", fill="y")
        self._graph_session_lb.pack(side="left", fill="both", expand=True)

        sorted_sids = sorted(self._sessions.keys(), reverse=True)
        self._graph_sidebar_ids: list[int | None] = [None] + sorted_sids

        self._graph_session_lb.insert("end", "  All Sessions")
        for idx, sid in enumerate(sorted_sids):
            label = self._session_label(sid, len(sorted_sids) - idx)
            self._graph_session_lb.insert("end", label)

        self._graph_session_lb.select_set(0)
        self._graph_session_lb.bind("<<ListboxSelect>>", self._on_graph_session_select)

        tk.Frame(body, bg=SEP, width=1).pack(side="left", fill="y")

        # ── Right: graph grid ─────────────────────────────────────────────────
        self._graphs_body = tk.Frame(body, bg=BG_PRIMARY)
        self._graphs_body.pack(side="left", fill="both", expand=True,
                               padx=10, pady=10)

        self._build_graph_grid(self._all_data)

    def _on_graph_session_select(self, _event: tk.Event | None = None) -> None:
        sel = self._graph_session_lb.curselection()
        if not sel:
            return
        idx  = sel[0]
        sid  = self._graph_sidebar_ids[idx]
        self._selected_sid = sid
        data = self._data_for_sid(sid)
        self._rebuild_graphs(data)

        # Sync Summary tab listbox to the same session
        try:
            summary_idx = self._sidebar_ids.index(sid)
            self._session_lb.select_clear(0, "end")
            self._session_lb.select_set(summary_idx)
            self._session_lb.see(summary_idx)
            self._render_stats(data)
        except (ValueError, AttributeError):
            pass

    def _sync_graphs_to_selection(self) -> None:
        """Called when switching to Graphs tab — syncs sidebar + rebuilds graphs."""
        try:
            graph_idx = self._graph_sidebar_ids.index(self._selected_sid)
            self._graph_session_lb.select_clear(0, "end")
            self._graph_session_lb.select_set(graph_idx)
            self._graph_session_lb.see(graph_idx)
        except (ValueError, AttributeError):
            pass
        self._rebuild_graphs(self._data_for_sid(self._selected_sid))

    def _build_graph_grid(self, data: dict) -> None:
        """Builds the 2×2 graph grid inside _graphs_body."""
        # Clear existing graph widgets
        for w in self._graphs_body.winfo_children():
            w.destroy()

        pairs = [
            [("Graph 1  —  Attack Type Distribution",    lambda c, d=data: self._draw_pie(c, d)),
             ("Graph 2  —  Hover Duration Distribution", lambda c, d=data: self._draw_hist(c, d))],
            [("Graph 3  —  Cumulative Enemy Defeats",    lambda c, d=data: self._draw_line(c, d)),
             ("Graph 4  —  Ability Loss Cause",          lambda c, d=data: self._draw_bar(c, d))],
        ]
        for pair in pairs:
            row = tk.Frame(self._graphs_body, bg=BG_PRIMARY)
            row.pack(fill="both", expand=True, pady=(0, 8))
            for i, (title, fn) in enumerate(pair):
                card = tk.Frame(row, bg=BG_SECONDARY)
                card.pack(side="left", fill="both", expand=True,
                          padx=(0, 8) if i == 0 else 0)
                tk.Label(card, text=f"  {title}",
                         font=("Arial", 10), fg=LBL_SECONDARY,
                         bg=BG_SECONDARY, anchor="w"
                         ).pack(fill="x", pady=(8, 0))
                tk.Frame(card, bg=SEP, height=1).pack(fill="x")
                c = tk.Canvas(card, bg=BG_SECONDARY, highlightthickness=0)
                c.pack(fill="both", expand=True)
                fn(c)

    def _rebuild_graphs(self, data: dict) -> None:
        """Rebuilds graph grid with the given data (used on session switch)."""
        self._build_graph_grid(data)

    # ── Graph drawing helpers ─────────────────────────────────────────────────

    def _fig(self):
        fig, ax = plt.subplots(figsize=(4, 3.6))
        fig.patch.set_facecolor(BG_SECONDARY)
        ax.set_facecolor(BG_SECONDARY)
        ax.tick_params(colors=LBL_SECONDARY, labelsize=9)
        ax.xaxis.label.set_color(LBL_SECONDARY)
        ax.yaxis.label.set_color(LBL_SECONDARY)
        ax.title.set_color(LBL_PRIMARY)
        for spine in ax.spines.values():
            spine.set_edgecolor(BG_TERTIARY)
        fig.tight_layout(pad=1.8)
        return fig, ax

    def _draw_pie(self, canvas: tk.Canvas, data: dict) -> None:
        fig, ax = self._fig()
        d = self._distribution(data["attack_type"])
        if not d:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                    color=LBL_SECONDARY); ax.axis("off")
        else:
            clrs = [IOS_PINK, IOS_BLUE, IOS_GREEN, IOS_ORANGE, IOS_PURPLE, IOS_TEAL]
            _, texts, autos = ax.pie(list(d.values()), labels=list(d.keys()),
                                     autopct="%1.1f%%", startangle=90,
                                     colors=clrs[:len(d)],
                                     wedgeprops={"edgecolor": BG_PRIMARY, "linewidth":2})
            for t in texts:  t.set_color(LBL_SECONDARY); t.set_fontsize(9)
            for a in autos:  a.set_color(LBL_PRIMARY);   a.set_fontsize(9)
        self._embed(fig, canvas)

    def _draw_hist(self, canvas: tk.Canvas, data: dict) -> None:
        fig, ax = self._fig()
        vals = [v for v in data["hover_duration"]
                if isinstance(v, (int, float)) and v > 0]
        if not vals:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                    color=LBL_SECONDARY); ax.axis("off")
        else:
            ax.hist(vals, bins=20, color=IOS_TEAL, edgecolor=BG_PRIMARY, alpha=0.9)
            ax.set_xlabel("Duration (ms)"); ax.set_ylabel("Frequency")
            ax.grid(axis="y", alpha=0.15, color=LBL_SECONDARY)
        self._embed(fig, canvas)

    def _draw_line(self, canvas: tk.Canvas, data: dict) -> None:
        fig, ax = self._fig()
        xs = sorted(v for v in data["survival_time"]
                    if isinstance(v, (int, float)))
        n  = min(len(xs), len(data["enemy_defeat"]))
        if not xs or n == 0:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                    color=LBL_SECONDARY); ax.axis("off")
        else:
            ys = list(range(1, n+1))
            ax.plot(xs[:n], ys, color=IOS_GREEN, linewidth=2)
            ax.fill_between(xs[:n], ys, alpha=0.15, color=IOS_GREEN)
            ax.set_xlabel("Survival Time (s)"); ax.set_ylabel("Cumulative Enemies")
            ax.grid(alpha=0.15, color=LBL_SECONDARY)
        self._embed(fig, canvas)

    def _draw_bar(self, canvas: tk.Canvas, data: dict) -> None:
        fig, ax = self._fig()
        d = self._distribution(data["ability_loss"])
        if not d:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                    color=LBL_SECONDARY); ax.axis("off")
        else:
            causes = list(d.keys())
            clr    = {"discard": IOS_BLUE, "hit": IOS_RED}
            bars   = ax.bar(causes, [d[c] for c in causes],
                            color=[clr.get(c, IOS_PURPLE) for c in causes],
                            edgecolor=BG_PRIMARY, linewidth=1.5, alpha=0.9, width=0.5)
            ax.bar_label(bars, padding=4, color=LBL_PRIMARY, fontsize=11)
            ax.set_xlabel("Cause"); ax.set_ylabel("Count")
            ax.set_xticklabels([c.title() for c in causes])
            ax.grid(axis="y", alpha=0.15, color=LBL_SECONDARY)
        self._embed(fig, canvas)

    def _embed(self, fig: plt.Figure, canvas: tk.Canvas) -> None:
        agg = tkagg.FigureCanvasTkAgg(fig, master=canvas)
        agg.draw()
        agg.get_tk_widget().pack(fill="both", expand=True)
        plt.close(fig)