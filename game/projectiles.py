from __future__ import annotations

import math
import pygame

from .settings import (
    COLOR_BY_ABILITY,
    GRAVITY,
    PROJECTILE_LIFETIME_MS,
    PROJECTILE_SPEED,
    SNOW_WALL_HEIGHT,
    SNOW_WALL_WIDTH,
    WINDOW_HEIGHT,
    WORLD_WIDTH,
)


class Projectile:
    def __init__(
        self,
        x: int,
        y: int,
        direction: int,
        ability: str = "none",
        is_discarded: bool = False,
        color_override: tuple[int, int, int] | None = None,
    ) -> None:
        self.direction = direction
        self.ability = ability
        self.is_discarded = is_discarded
        self.color_override = color_override
        self.spawn_time_ms = pygame.time.get_ticks()

        if ability == "star_spit":
            self.rect = pygame.Rect(x, y, 44, 44)
            self.speed = 4.6
            self.damage = 1
            self.lifetime_ms = PROJECTILE_LIFETIME_MS + 900
        elif ability == "flamethrower":
            self.rect = pygame.Rect(x, y, 14, 14)
            self.speed = PROJECTILE_SPEED + 1
            self.damage = 2
            self.lifetime_ms = PROJECTILE_LIFETIME_MS
        elif ability == "sword_swing":
            self.rect = pygame.Rect(x, y, 40, 40)
            self.speed = 0
            self.damage = 3
            self.lifetime_ms = PROJECTILE_LIFETIME_MS
        else:
            self.rect = pygame.Rect(x, y, 14, 14)
            self.speed = PROJECTILE_SPEED
            self.damage = 1
            self.lifetime_ms = PROJECTILE_LIFETIME_MS

        self.angle = 0.0
        self.spin_speed = 12.0 if is_discarded else 0.0

    def update(self) -> None:
        if self.ability != "sword_swing":
            self.rect.x += self.speed * self.direction
        if self.is_discarded:
            self.angle = (self.angle + self.spin_speed) % 360

    def check_impact(self, enemy_rect: pygame.Rect) -> bool:
        return self.rect.colliderect(enemy_rect)

    def destroy(self) -> bool:
        out_of_bounds = self.rect.right < 0 or self.rect.left > WORLD_WIDTH
        expired = pygame.time.get_ticks() - self.spawn_time_ms > self.lifetime_ms
        return out_of_bounds or expired

    def draw(self, surface: pygame.Surface, camera_x: int = 0) -> None:
        draw_rect = self.rect.move(-camera_x, 0)
        color = self.color_override if self.color_override is not None else COLOR_BY_ABILITY.get(self.ability, (230, 230, 230))

        if self.is_discarded:
            center = draw_rect.center
            half = max(draw_rect.width, draw_rect.height) // 2
            points = [(-half, -half), (half, -half), (half, half), (-half, half)]
            rad = math.radians(self.angle)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            rotated = [
                (
                    center[0] + px * cos_a - py * sin_a,
                    center[1] + px * sin_a + py * cos_a,
                )
                for px, py in points
            ]
            pygame.draw.polygon(surface, color, rotated)
            pygame.draw.polygon(surface, (30, 30, 30), rotated, width=2)
            return

        if self.ability == "sword_swing":
            pygame.draw.polygon(surface, color, [
                (draw_rect.centerx, draw_rect.top),
                (draw_rect.right, draw_rect.centery),
                (draw_rect.centerx, draw_rect.bottom),
                (draw_rect.left, draw_rect.centery),
            ])
        elif self.ability == "star_spit":
            # ── 8-bit pixel star — 7×7 art-px grid, S=5 ──────────────────────
            S   = 5
            now = pygame.time.get_ticks()
            cx, cy = draw_rect.center
            # spin: rotate pixel grid each 120ms (4 frames = 480ms full)
            frame = (now // 120) % 4

            # 4-frame rotation: 0=normal, 1=45°, 2=horiz, 3=45° other
            STAR_FRAMES = [
                # frame 0 — standard 5-pt star shape
                ["..X..",
                 ".XXX.",
                 "XXXXX",
                 ".XXX.",
                 "..X.."],
                # frame 1 — rotated ~22°
                ["..XX.",
                 ".XXX.",
                 "XXXXX",
                 ".XXX.",
                 ".XX.."],
                # frame 2 — horizontal diamond
                ["..X..",
                 ".XXX.",
                 "XXXXX",
                 ".XXX.",
                 "..X.."],
                # frame 3 — squished
                [".XXX.",
                 "XXXXX",
                 "XXXXX",
                 "XXXXX",
                 ".XXX."],
            ]
            grid = STAR_FRAMES[frame]
            rows = len(grid)
            cols = len(grid[0])
            ox   = cx - cols * S // 2
            oy   = cy - rows * S // 2

            # colour: bright yellow core → gold → dark outline
            STAR_COLS = [
                (255, 255, 120),  # row 0 top
                (255, 235,  60),  # row 1
                (255, 210,  20),  # row 2 centre
                (235, 175,  10),  # row 3
                (200, 130,   5),  # row 4 bottom
            ]
            SHINE = (255, 255, 200)
            OUTL  = (80, 50, 0)

            for ry, row in enumerate(grid):
                for rx, ch in enumerate(row):
                    if ch == 'X':
                        col = STAR_COLS[ry]
                        pygame.draw.rect(surface, col, (ox+rx*S, oy+ry*S, S, S))
                        # 1-px dark outline (left and top edges of each block)
                        if rx == 0 or grid[ry][rx-1] != 'X':
                            pygame.draw.rect(surface, OUTL, (ox+rx*S, oy+ry*S, 1, S))
                        if ry == 0 or grid[ry-1][rx] != 'X':
                            pygame.draw.rect(surface, OUTL, (ox+rx*S, oy+ry*S, S, 1))

            # shine pixel (top-left of centre mass)
            if frame in (0,2):
                pygame.draw.rect(surface, SHINE, (cx-S//2, cy-S, S, S))

            # trailing pixel trail (4 dots behind based on direction)
            trail_col = (255, 200, 40)
            for ti in range(1, 4):
                tx = cx - self.direction * ti * S * 2
                ty = cy
                alpha = 180 - ti * 50
                ts = pygame.Surface((S, S), pygame.SRCALPHA)
                ts.fill((*trail_col, alpha))
                surface.blit(ts, (tx - S//2, ty - S//2))
        else:
            pygame.draw.rect(surface, color, draw_rect, border_radius=4)


class SnowWall:
    def __init__(self, x: int, y: int) -> None:
        self.rect = pygame.Rect(x, y, SNOW_WALL_WIDTH, SNOW_WALL_HEIGHT)
        self.velocity_y = -2.0
        self.hp = 2
        self.is_grounded = False
        self.state = "normal"

    def update(self, solid_rects: list[pygame.Rect]) -> None:
        self.velocity_y += GRAVITY
        self.rect.y += int(self.velocity_y)

        for block in solid_rects:
            if self.rect.colliderect(block) and self.velocity_y > 0:
                self.rect.bottom = block.top
                self.velocity_y = 0
                self.is_grounded = True
                break

    def on_hit_enemy(self) -> None:
        self.hp -= 1
        if self.hp == 1:
            self.state = "damaged"

    def is_destroyed(self) -> bool:
        return self.hp <= 0

    def draw(self, surface: pygame.Surface, camera_x: int = 0) -> None:
        draw_rect = self.rect.move(-camera_x, 0)
        outer = (155, 232, 255) if self.state == "normal" else (104, 170, 198)
        inner = (215, 248, 255) if self.state == "normal" else (150, 205, 225)
        rim = (200, 245, 255) if self.state == "normal" else (170, 220, 240)

        # Main body
        pygame.draw.rect(surface, outer, draw_rect, border_radius=5)
        pygame.draw.rect(surface, inner, draw_rect.inflate(-8, -8), border_radius=4)

        # Frost rim highlight (top-left glow)
        rim_surf = pygame.Surface((draw_rect.width, draw_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(rim_surf, (*rim, 90), (0, 0, draw_rect.width, 4), border_radius=3)
        pygame.draw.rect(rim_surf, (*rim, 60), (0, 0, 4, draw_rect.height), border_radius=3)
        surface.blit(rim_surf, draw_rect.topleft)

        # Crystal spike accents
        cx, cy = draw_rect.centerx, draw_rect.top
        spike_color = (230, 250, 255) if self.state == "normal" else (180, 220, 235)
        for offset in (-9, 0, 9):
            tip_x = cx + offset
            pygame.draw.polygon(surface, spike_color, [
                (tip_x, cy - 10),
                (tip_x - 4, cy + 1),
                (tip_x + 4, cy + 1),
            ])

        # Crack lines on damaged state
        if self.state == "damaged":
            crack_color = (100, 160, 190)
            pygame.draw.line(surface, crack_color,
                             (draw_rect.left + 6, draw_rect.top + 8),
                             (draw_rect.centerx + 3, draw_rect.bottom - 10), 1)
            pygame.draw.line(surface, crack_color,
                             (draw_rect.centerx + 3, draw_rect.bottom - 10),
                             (draw_rect.right - 5, draw_rect.centery + 4), 1)

# ══════════════════════════════════════════════════════════════════════════════
#  Boss Stinger — aimed projectile fired by the Queen Bee boss
# ══════════════════════════════════════════════════════════════════════════════

class BossStinger:
    """A stinger fired by the Queen Bee boss, aimed directly at the player."""

    def __init__(self, x: int, y: int, target_x: int, target_y: int) -> None:
        self.rect = pygame.Rect(x - 9, y - 5, 18, 10)
        dx = target_x - x
        dy = target_y - y
        dist = max(1.0, math.hypot(dx, dy))
        speed = 5.0
        self.vx = dx / dist * speed
        self.vy = dy / dist * speed
        self.spawn_time_ms = pygame.time.get_ticks()
        self.damage = 1
        self.angle = math.degrees(math.atan2(dy, dx))

    def update(self) -> None:
        self.rect.x += int(self.vx)
        self.rect.y += int(self.vy)

    def check_impact(self, rect: pygame.Rect) -> bool:
        return self.rect.colliderect(rect)

    def destroy(self) -> bool:
        out = (
            self.rect.right < 0
            or self.rect.left > WORLD_WIDTH
            or self.rect.top > WINDOW_HEIGHT + 100
        )
        expired = pygame.time.get_ticks() - self.spawn_time_ms > 4000
        return out or expired

    def draw(self, surface: pygame.Surface, camera_x: int = 0) -> None:
        draw_rect = self.rect.move(-camera_x, 0)
        cx, cy = draw_rect.center
        rad = math.radians(self.angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        l, w = 11, 4
        # Diamond / dart shape oriented along flight path
        points = [
            (cx + cos_a * l,       cy + sin_a * l),
            (cx - sin_a * w,       cy + cos_a * w),
            (cx - cos_a * l * 0.5, cy - sin_a * l * 0.5),
            (cx + sin_a * w,       cy - cos_a * w),
        ]
        pygame.draw.polygon(surface, (255, 185, 20), points)
        pygame.draw.polygon(surface, (180, 80, 0), points, 1)
        # Sharp tip glow
        tip_x = int(cx + cos_a * l)
        tip_y = int(cy + sin_a * l)
        pygame.draw.circle(surface, (255, 90, 10), (tip_x, tip_y), 3)