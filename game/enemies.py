from __future__ import annotations

import math
from pathlib import Path
import random
import pygame

from .entities import Entity
from .settings import (
    COLOR_BY_ENEMY,
    ENEMY_AIR_SPEED_MULTIPLIER,
    ENEMY_BASE_SPEED,
    ENEMY_JUMP_FORWARD_BOOST,
    ENEMY_JUMP_VELOCITY,
    GRAVITY,
    GROUND_HEIGHT,
    WINDOW_HEIGHT,
    WORLD_WIDTH,
)


class InsectEnemy(Entity):
    _sprite_cache: dict[str, list[pygame.Surface]] = {}

    def __init__(self, enemy_type: str, x: int, y: int, speed_multiplier: float = 1.0) -> None:
        super().__init__(rect=pygame.Rect(x, y, 34, 34))
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.enemy_type = enemy_type
        self.is_alive = True
        self.is_grounded = False
        self.facing = -1
        self.animation_frame = 0
        self.animation_timer_ms = 0
        self.sprite_size = (46, 46)
        self.speed_multiplier = speed_multiplier

        if not InsectEnemy._sprite_cache:
            InsectEnemy._sprite_cache = self._load_sprite_cache()

    def ai_behavior(
        self,
        player_rect: pygame.Rect,
        solid_rects: list[pygame.Rect],
        pit_rects: list[pygame.Rect],
        world_width: int,
    ) -> None:
        direction = -1 if player_rect.centerx < self.rect.centerx else 1
        self.facing = direction
        base = ENEMY_BASE_SPEED * self.speed_multiplier
        speed = base * (ENEMY_AIR_SPEED_MULTIPLIER if not self.is_grounded else 1.0)
        self.velocity_x = direction * speed

        if self.is_grounded:
            should_jump = self._should_jump(pit_rects)
            # Also jump to reach player on platforms above
            if player_rect.bottom < self.rect.top - 20:
                should_jump = True
            if should_jump:
                self.velocity_y = ENEMY_JUMP_VELOCITY
                self.velocity_x = direction * (base * ENEMY_JUMP_FORWARD_BOOST)
                self.is_grounded = False

        self.velocity_y += GRAVITY

        hit_wall = False
        self.rect.x += int(self.velocity_x)
        for block in solid_rects:
            if self.rect.colliderect(block):
                hit_wall = True
                if self.velocity_x > 0:
                    self.rect.right = block.left
                elif self.velocity_x < 0:
                    self.rect.left = block.right

        if hit_wall and self.is_grounded:
            self.velocity_y = ENEMY_JUMP_VELOCITY
            self.velocity_x = direction * (ENEMY_BASE_SPEED * self.speed_multiplier * ENEMY_JUMP_FORWARD_BOOST)
            self.is_grounded = False

        self.rect.y += int(self.velocity_y)
        self.is_grounded = False
        for block in solid_rects:
            if self.rect.colliderect(block):
                if self.velocity_y > 0:
                    self.rect.bottom = block.top
                    self.velocity_y = 0
                    self.is_grounded = True
                elif self.velocity_y < 0:
                    self.rect.top = block.bottom
                    self.velocity_y = 0

        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.right > world_width:
            self.rect.right = world_width

        self._update_animation()

    def spawn_logic(self) -> None:
        # Spawn logic is handled by GameManager; this method remains for OOP completeness.
        return

    def _should_jump(self, pit_rects: list[pygame.Rect]) -> bool:
        lookahead = 32
        foot_probe_x = self.rect.centerx + (lookahead if self.velocity_x > 0 else -lookahead)
        foot_probe_y = self.rect.bottom + 2
        for pit in pit_rects:
            if pit.left <= foot_probe_x <= pit.right and foot_probe_y >= pit.top:
                return True
        return False

    @classmethod
    def _load_sprite_cache(cls) -> dict[str, list[pygame.Surface]]:
        asset_root = Path(__file__).resolve().parent.parent / "assets"
        folder_by_enemy = {
            "fire_wasp": "fire",
            "ice_beetle": "ice",
            "sword_mantis": "sword",
        }

        sprite_cache: dict[str, list[pygame.Surface]] = {}
        for enemy_type, folder_name in folder_by_enemy.items():
            frames: list[pygame.Surface] = []
            folder_path = asset_root / folder_name
            for frame_index in range(1, 5):
                frame_path = folder_path / f"{frame_index}.png"
                if not frame_path.exists():
                    continue
                image = pygame.image.load(str(frame_path)).convert_alpha()
                frames.append(pygame.transform.scale(image, (46, 46)))
            sprite_cache[enemy_type] = frames
        return sprite_cache

    def _update_animation(self) -> None:
        if not InsectEnemy._sprite_cache.get(self.enemy_type):
            return

        now = pygame.time.get_ticks()
        if now - self.animation_timer_ms < 120:
            return

        self.animation_timer_ms = now
        self.animation_frame = (self.animation_frame + 1) % len(InsectEnemy._sprite_cache[self.enemy_type])

    def _get_current_sprite(self) -> pygame.Surface | None:
        frames = InsectEnemy._sprite_cache.get(self.enemy_type, [])
        if not frames:
            return None

        sprite = frames[self.animation_frame]
        source_faces_left = self.enemy_type in {"fire_wasp", "ice_beetle"}
        should_face_left = self.facing < 0
        if source_faces_left != should_face_left:
            return pygame.transform.flip(sprite, True, False)
        return sprite

    def draw(self, surface: pygame.Surface, camera_x: int = 0) -> None:
        draw_rect = self.rect.move(-camera_x, 0)
        sprite = self._get_current_sprite()
        if sprite is None:
            pygame.draw.rect(surface, COLOR_BY_ENEMY[self.enemy_type], draw_rect, border_radius=6)
            return

        bottom_offset = 4 if self.enemy_type == "sword_mantis" else 2
        sprite_rect = sprite.get_rect(midbottom=(draw_rect.centerx, draw_rect.bottom + bottom_offset))
        surface.blit(sprite, sprite_rect)


def spawn_enemy_for_time(survival_time_s: float, player_x: int, world_width: int, speed_multiplier: float = 1.0) -> InsectEnemy:
    offset = random.randint(450, 760)
    x = player_x - offset if random.random() < 0.5 else player_x + offset
    x = max(30, min(world_width - 64, x))
    y = WINDOW_HEIGHT - GROUND_HEIGHT - 34

    weights = {
        "fire_wasp": max(10, 55 - int(survival_time_s * 1.1)),
        "ice_beetle": min(45, 20 + int(survival_time_s * 0.8)),
        "sword_mantis": min(35, 10 + int(survival_time_s * 0.6)),
    }
    enemy_type = random.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]
    return InsectEnemy(enemy_type=enemy_type, x=x, y=y, speed_multiplier=speed_multiplier)

# ══════════════════════════════════════════════════════════════════════════════
#  BOSS — Queen Bee
# ══════════════════════════════════════════════════════════════════════════════

class QueenBeeBoss:
    """Giant Queen Bee boss. Spawns when 40 enemies have been defeated.

    - Very large (90×90 px) and floats freely in the air
    - Fires 3 aimed stingers (cooldown scales with difficulty)
    - Has 10 HP (hearts)
    - While alive, max 5 regular insects spawn alongside it
    - Each time defeated, difficulty_level increases speed and attack rate
    """

    BOSS_WIDTH  = 90
    BOSS_HEIGHT = 90

    def __init__(self, x: int, y: int, difficulty_level: int = 0) -> None:
        self.rect = pygame.Rect(x, y, self.BOSS_WIDTH, self.BOSS_HEIGHT)
        self.max_hp = 10
        self.hp = 10
        self.is_alive = True
        self.facing = -1
        self._last_attack_ms: int = -5000   # allow first attack quickly
        # Attack gets faster each difficulty level (min 2.5s)
        self.attack_cooldown_ms = max(2500, 5000 - difficulty_level * 400)
        self._hover_timer = 0.0
        self._hover_offset = 0.0
        self._hit_flash_until_ms: int = 0
        # Horizontal float speed increases with difficulty
        self.float_speed = 0.8 + difficulty_level * 0.3
        # Target Y: stay in upper half of screen, bob up and down
        self._target_y = y
        self._vy = 0.0

    # ── update ────────────────────────────────────────────────────────────────

    def update(
        self,
        player_rect: pygame.Rect,
        solid_rects: list[pygame.Rect],
        now: int,
    ) -> bool:
        """Float towards player (no gravity), sinusoidal vertical bobbing.
        Returns True when the boss should fire stingers this frame.
        """
        direction = -1 if player_rect.centerx < self.rect.centerx else 1
        self.facing = direction

        # Horizontal float — moves at float_speed, ignores solid_rects (flies over them)
        self.rect.x += int(direction * self.float_speed)

        # World bounds
        self.rect.x = max(0, min(WORLD_WIDTH - self.rect.width, self.rect.x))

        # Vertical: sinusoidal hover — target is ~150px above player
        self._hover_timer += 0.035
        desired_y = player_rect.centery - 180 + math.sin(self._hover_timer) * 55
        # Clamp to top of screen so boss doesn't go off-screen
        desired_y = max(30, min(WINDOW_HEIGHT - 200, desired_y))
        # Smoothly interpolate toward desired_y
        self.rect.y += int((desired_y - self.rect.y) * 0.04)

        # Hover offset for draw (visual bob only)
        self._hover_offset = math.sin(self._hover_timer * 1.5) * 5.0

        # Attack timing
        if now - self._last_attack_ms >= self.attack_cooldown_ms:
            self._last_attack_ms = now
            return True
        return False

    def take_damage(self, damage: int, now: int) -> None:
        """Reduce HP and trigger hit flash."""
        self.hp = max(0, self.hp - damage)
        self._hit_flash_until_ms = now + 220
        if self.hp <= 0:
            self.is_alive = False

    # ── draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, camera_x: int = 0) -> None:
        draw_rect = self.rect.move(-camera_x, int(self._hover_offset))
        cx, cy_center = draw_rect.center
        now = pygame.time.get_ticks()
        hit = now < self._hit_flash_until_ms

        # Wing flap angle
        flap = math.sin(now * 0.015)

        # ── Wings (behind body) ───────────────────────────────────────────────
        wing_w, wing_h = 72, 32
        for side in (-1, 1):
            wing_surf = pygame.Surface((wing_w, wing_h), pygame.SRCALPHA)
            if hit:
                pygame.draw.ellipse(wing_surf, (255, 255, 255, 210), (0, 0, wing_w, wing_h))
            else:
                pygame.draw.ellipse(wing_surf, (185, 235, 255, 155), (0, 0, wing_w, wing_h))
                pygame.draw.ellipse(wing_surf, (220, 248, 255, 70),  (5, 5, wing_w - 10, wing_h - 10))
                # Vein lines
                for v in range(3):
                    vx = wing_w // 4 + v * wing_w // 6
                    pygame.draw.line(wing_surf, (140, 200, 240, 80),
                                     (wing_w // 2, wing_h // 2), (vx, 2), 1)
            flip_y_off = int(flap * 9) * side
            if side == -1:
                surface.blit(wing_surf,
                             (cx - draw_rect.width // 2 - wing_w + 12,
                              cy_center - 26 + flip_y_off))
            else:
                flipped = pygame.transform.flip(wing_surf, True, False)
                surface.blit(flipped,
                             (cx + draw_rect.width // 2 - 12,
                              cy_center - 26 - flip_y_off))

        # ── Body ──────────────────────────────────────────────────────────────
        body_col   = (255, 255, 255) if hit else (255, 200, 22)
        stripe_col = (255, 200, 200) if hit else (28, 14, 4)
        pygame.draw.ellipse(surface, body_col, draw_rect)

        # Yellow-black stripes
        for i in range(3):
            sy = draw_rect.top + 16 + i * 22
            sh = 13
            s_surf = pygame.Surface((draw_rect.width, sh), pygame.SRCALPHA)
            pygame.draw.ellipse(s_surf, (*stripe_col, 200), (5, 0, draw_rect.width - 10, sh))
            surface.blit(s_surf, (draw_rect.left, sy))

        # Body highlight
        hl = pygame.Surface((draw_rect.width - 18, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(hl, (255, 242, 160, 90), (0, 0, draw_rect.width - 18, 16))
        surface.blit(hl, (draw_rect.left + 9, draw_rect.top + 7))

        # Body outline
        outline_col = (255, 255, 255) if hit else (160, 105, 0)
        pygame.draw.ellipse(surface, outline_col, draw_rect, 3)

        # ── Angry eyebrows ────────────────────────────────────────────────────
        brow_col = (255, 255, 255) if hit else (20, 10, 4)
        pygame.draw.line(surface, brow_col,
                         (cx - 24, draw_rect.top + 12), (cx - 9, draw_rect.top + 20), 3)
        pygame.draw.line(surface, brow_col,
                         (cx + 9,  draw_rect.top + 20), (cx + 24, draw_rect.top + 12), 3)

        # ── Eyes ─────────────────────────────────────────────────────────────
        eye_col = (255, 100, 100) if hit else (220, 35, 35)
        for ex in (cx - 17, cx + 17):
            pygame.draw.circle(surface, eye_col,       (ex, draw_rect.top + 28), 10)
            pygame.draw.circle(surface, (8, 4, 0),     (ex, draw_rect.top + 28),  6)
            pygame.draw.circle(surface, (255, 255, 255),(ex - 3, draw_rect.top + 24), 3)

        # ── Crown ─────────────────────────────────────────────────────────────
        crown_col = (255, 255, 210) if hit else (255, 215, 0)
        crown_pts = [
            (cx - 24, draw_rect.top +  2),
            (cx - 24, draw_rect.top - 18),
            (cx - 14, draw_rect.top -  5),
            (cx,      draw_rect.top - 24),
            (cx + 14, draw_rect.top -  5),
            (cx + 24, draw_rect.top - 18),
            (cx + 24, draw_rect.top +  2),
        ]
        pygame.draw.polygon(surface, crown_col, crown_pts)
        pygame.draw.polygon(surface, (185, 135, 0) if not hit else (255, 255, 200), crown_pts, 2)
        # Crown gems
        for gem_x, gem_y in [
            (cx - 24, draw_rect.top - 16),
            (cx,      draw_rect.top - 22),
            (cx + 24, draw_rect.top - 16),
        ]:
            pygame.draw.circle(surface, (255, 50, 50), (gem_x, gem_y), 4)
            pygame.draw.circle(surface, (255, 200, 200), (gem_x - 1, gem_y - 1), 2)

        # ── Stinger ───────────────────────────────────────────────────────────
        stinger_col = (200, 160, 180) if hit else (80, 48, 6)
        pygame.draw.polygon(surface, stinger_col, [
            (cx - 7, draw_rect.bottom - 8),
            (cx + 7, draw_rect.bottom - 8),
            (cx,     draw_rect.bottom + 20),
        ])