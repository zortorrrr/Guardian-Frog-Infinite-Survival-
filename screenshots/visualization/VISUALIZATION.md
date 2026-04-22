# VISUALIZATION — Guardian Frog Statistics Dashboard

The statistics dashboard is launched from the main menu (Stats button) or by running `python show_stats.py` directly.  
It is a Tkinter window with two tabs: **Summary** and **Graphs**. Both tabs share a session-selector sidebar that filters all data to a single game run or shows aggregate data across all sessions.

---

## Dashboard Overview

**File:** `overview.png`

The overview screenshot shows the full dashboard window. The left sidebar lists all recorded sessions by timestamp; clicking a session filters every panel to that run. The right area shows either the summary statistics table (Summary tab) or the four graph panels (Graphs tab).

> *(Add `overview.png` screenshot here — capture the full window with data loaded.)*

---

## Summary Tab

**File:** `summary_table.png`

The Summary tab contains a statistics table with one row per data category. Columns show the **mean**, **median**, **standard deviation**, **minimum**, **maximum**, and **total count** for numeric fields (`hover_duration`, `damage_taken`, `survival_time`). The `enemy_defeat` row shows total enemies defeated in the selected session.

This table is useful for comparing how aggressively a player hovered (longer hover durations indicate strategic use of the hover mechanic) versus how much damage they took, which reflects overall survival skill.

> *(Add `summary_table.png` screenshot here — show the table with visible numbers.)*

---

## Graph 1 — Attack Type Distribution (Pie Chart)

**File:** `graph1_attack_type.png`

This pie chart shows the proportion of each ability used during the selected session. Slices represent `star_spit`, `flamethrower`, `sword_swing`, and `snowfall`. This visualisation reveals the player's preferred combat style — a dominant `flamethrower` slice indicates an aggressive playstyle, while an even distribution suggests the player adapts their ability to each enemy type.

> *(Add `graph1_attack_type.png` screenshot here.)*

---

## Graph 2 — Hover Duration Distribution (Histogram)

**File:** `graph2_hover_duration.png`

This histogram plots the frequency of hover durations (in milliseconds) across all hover events in the session. Each bar represents a 50 ms bin. Short bars concentrated near zero indicate the player uses hovering primarily as a quick direction change, while a rightward spread shows that the player sustains flight to avoid projectiles or cross gaps deliberately.

> *(Add `graph2_hover_duration.png` screenshot here.)*

---

## Graph 3 — Cumulative Enemy Defeats Over Time (Line Chart)

**File:** `graph3_cumulative_defeats.png`

This line chart plots cumulative enemy kills on the Y-axis against survival time (seconds) on the X-axis. A steep slope indicates a high kill rate at that moment (likely during a boss fight or ability use), while a flat region indicates the player was spending time dodging rather than attacking. The shaded fill under the line makes rate changes easy to spot visually.

> *(Add `graph3_cumulative_defeats.png` screenshot here.)*

---

## Graph 4 — Ability Loss Cause (Bar Chart)

**File:** `graph4_ability_loss.png`

This bar chart compares how many times the player lost their current ability due to **Discard** (pressed `Q`) versus **Hit** (took contact damage while holding an ability). A high `hit` count suggests the player is struggling to maintain distance from enemies. A high `discard` count indicates deliberate tactical play — launching the ability as a spinning discarded projectile.

> *(Add `graph4_ability_loss.png` screenshot here.)*
