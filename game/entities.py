from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pygame

from .settings import (
    FLAMETHROWER_SPEED_MULTIPLIER,
    GRAVITY,
    PLAYER_ATTACK_COOLDOWN_MS,
    PLAYER_HOVER_GRAVITY_SCALE,
    PLAYER_JUMP_VELOCITY,
    PLAYER_JUMP_DECAY_PER_JUMP,
    PLAYER_MAX_JUMPS,
    PLAYER_MAX_HEALTH,
    PLAYER_MIN_JUMP_VELOCITY,
    PLAYER_SPEED,
    SNOWFALL_COOLDOWN_MS,
)


@dataclass
class Entity:
    rect: pygame.Rect
    velocity_x: float = 0.0
    velocity_y: float = 0.0

    def apply_gravity(self, gravity_scale: float = 1.0) -> None:
        self.velocity_y += GRAVITY * gravity_scale

    def move(self) -> None:
        self.rect.x += int(self.velocity_x)
        self.rect.y += int(self.velocity_y)


class Player(Entity):
    _ability_icon_cache: dict[str, pygame.Surface] = {}
    _movement_sprites: list[pygame.Surface] = []
    _attack_sprite: pygame.Surface | None = None
    _snatch_sprite: pygame.Surface | None = None

    def __init__(self, x: int, y: int) -> None:
        super().__init__(rect=pygame.Rect(x, y, 26, 26))
        self.health = PLAYER_MAX_HEALTH
        self.current_ability = "star_spit"
        self.held_enemy_type: str | None = None   # Enemy captured in mouth (not yet swallowed)
        self.is_grounded = False
        self.is_hovering = False
        self.max_jumps = PLAYER_MAX_JUMPS
        self.jump_count = 0
        self.facing = 1
        self._hover_start_ms = 0
        self._last_attack_ms = -max(PLAYER_ATTACK_COOLDOWN_MS, SNOWFALL_COOLDOWN_MS)
        self.aura_color: tuple[int, int, int] | None = None
        
        # Animation state
        self.animation_frame = 0
        self.animation_timer_ms = 0
        self.animation_state = "idle"  # idle, moving, attacking, snatching
        self.snatch_animation_end_ms = 0

        if not Player._ability_icon_cache:
            Player._ability_icon_cache = self._load_ability_icons()
        if not Player._movement_sprites:
            Player._movement_sprites, Player._attack_sprite, Player._snatch_sprite = self._load_frog_sprites()

    @classmethod
    def _load_ability_icons(cls) -> dict[str, pygame.Surface]:
        icon_by_ability = {
            "flamethrower": "fire_element.png",
            "snowfall": "ice_element.png",
            "sword_swing": "sword_element.png",
        }
        icon_root = Path(__file__).resolve().parent.parent / "assets" / "icons"

        icons: dict[str, pygame.Surface] = {}
        for ability, filename in icon_by_ability.items():
            icon_path = icon_root / filename
            if not icon_path.exists():
                continue
            icon = pygame.image.load(str(icon_path)).convert_alpha()
            icons[ability] = pygame.transform.scale(icon, (28, 28))
        return icons

    @classmethod
    def _load_frog_sprites(cls) -> tuple[list[pygame.Surface], pygame.Surface | None, pygame.Surface | None]:
        frog_root = Path(__file__).resolve().parent.parent / "assets" / "frog"
        
        # Load 4 movement sprites
        movement_sprites: list[pygame.Surface] = []
        for i in range(1, 5):
            sprite_path = frog_root / f"{i}.png"
            if sprite_path.exists():
                sprite = pygame.image.load(str(sprite_path)).convert_alpha()
                movement_sprites.append(sprite)
        
        # Load attack sprite
        attack_sprite = None
        attack_path = frog_root / "attack.png"
        if attack_path.exists():
            attack_sprite = pygame.image.load(str(attack_path)).convert_alpha()
        
        # Load snatch sprite
        snatch_sprite = None
        snatch_path = frog_root / "snatch.png"
        if snatch_path.exists():
            snatch_sprite = pygame.image.load(str(snatch_path)).convert_alpha()
        
        return movement_sprites, attack_sprite, snatch_sprite


    def update(
        self,
        pressed: pygame.key.ScancodeWrapper,
        world_width: int,
        solid_rects: list[pygame.Rect],
        is_flamethrower_active: bool = False,
    ) -> int:
        move_speed = PLAYER_SPEED * FLAMETHROWER_SPEED_MULTIPLIER if is_flamethrower_active else PLAYER_SPEED
        self.velocity_x = 0
        if pressed[pygame.K_a] or pressed[pygame.K_LEFT]:
            self.velocity_x = -move_speed
            self.facing = -1
        if pressed[pygame.K_d] or pressed[pygame.K_RIGHT]:
            self.velocity_x = move_speed
            self.facing = 1

        self.is_hovering = bool(pressed[pygame.K_SPACE] and self.velocity_y > 0)
        gravity_scale = PLAYER_HOVER_GRAVITY_SCALE if self.is_hovering else 1.0
        self.apply_gravity(gravity_scale=gravity_scale)

        hover_duration = 0
        self.is_grounded = False

        self.rect.x += int(self.velocity_x)
        for block in solid_rects:
            if self.rect.colliderect(block):
                if self.velocity_x > 0:
                    self.rect.right = block.left
                elif self.velocity_x < 0:
                    self.rect.left = block.right

        self.rect.y += int(self.velocity_y)
        for block in solid_rects:
            if self.rect.colliderect(block):
                if self.velocity_y > 0:
                    self.rect.bottom = block.top
                    self.velocity_y = 0
                    self.is_grounded = True
                    self.jump_count = 0
                    if self._hover_start_ms:
                        hover_duration = pygame.time.get_ticks() - self._hover_start_ms
                        self._hover_start_ms = 0
                elif self.velocity_y < 0:
                    self.rect.top = block.bottom
                    self.velocity_y = 0

        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.right > world_width:
            self.rect.right = world_width
        
        # Update animation state based on movement
        if self.animation_state not in ("attacking", "snatching"):
            if self.velocity_x != 0:
                self.animation_state = "moving"
            else:
                self.animation_state = "idle"

        return hover_duration

    def jump(self, is_flamethrower_active: bool = False) -> None:
        if is_flamethrower_active:
            return

        if self.jump_count >= self.max_jumps:
            return

        jump_velocity = PLAYER_JUMP_VELOCITY + (self.jump_count * PLAYER_JUMP_DECAY_PER_JUMP)
        # Keep first jump at full strength; clamp later flaps so they don't get weaker than the minimum.
        self.velocity_y = min(jump_velocity, PLAYER_MIN_JUMP_VELOCITY)

        self.jump_count += 1
        self.is_grounded = False
        self.animation_state = "jumping"
        self.animation_frame = 2  # Frame 3 (0-indexed)

    def on_ground(self) -> bool:
        return self.is_grounded

    def snatch_tongue(self) -> pygame.Rect:
        width = 64
        height = 16
        y = self.rect.centery - height // 2
        if self.facing > 0:
            return pygame.Rect(self.rect.right, y, width, height)
        return pygame.Rect(self.rect.left - width, y, width, height)

    def discard_ability(self) -> str:
        old = self.current_ability
        self.current_ability = "star_spit"
        self.aura_color = None
        return old

    def on_hit(self, damage: int = 1) -> None:
        self.health -= damage
        self.current_ability = "star_spit"
        self.held_enemy_type = None
        self.aura_color = None

    def start_hover(self, now_ms: int) -> None:
        if self._hover_start_ms == 0:
            self._hover_start_ms = now_ms

    def stop_hover(self, now_ms: int) -> int:
        if self._hover_start_ms == 0:
            return 0
        duration = now_ms - self._hover_start_ms
        self._hover_start_ms = 0
        return max(duration, 0)

    def trigger_attack(self, now_ms: int) -> None:
        """Trigger attack animation."""
        self.animation_state = "attacking"
        self.animation_timer_ms = 0
        self.animation_frame = 0

    def trigger_snatch(self, now_ms: int) -> None:
        """Trigger snatch animation."""
        self.animation_state = "snatching"
        self.animation_timer_ms = 0
        self.animation_frame = 0
        self.snatch_animation_end_ms = now_ms + 150  # 150ms snatch animation

    def update_animation(self, now_ms: int, dt_ms: int) -> None:
        """Update animation frames and states."""
        self.animation_timer_ms += dt_ms
        
        if self.animation_state == "attacking":
            # Attack animation plays once then returns to idle/moving
            if self.animation_timer_ms > 150:  # 150ms per attack frame
                self.animation_state = "idle" if self.velocity_x == 0 else "moving"
                self.animation_timer_ms = 0
                self.animation_frame = 0
        
        elif self.animation_state == "snatching":
            # Snatch animation plays once then returns to idle/moving
            if now_ms >= self.snatch_animation_end_ms:
                self.animation_state = "idle" if self.velocity_x == 0 else "moving"
                self.animation_timer_ms = 0
                self.animation_frame = 0
        
        elif self.animation_state == "jumping":
            # Jumping state shows frame 3 and returns to moving/idle when grounded
            if self.is_grounded:
                self.animation_state = "idle" if self.velocity_x == 0 else "moving"
                self.animation_timer_ms = 0
                self.animation_frame = 0
        
        elif self.animation_state == "moving":
            # Cycle through 4 movement frames at 150ms each
            if self.animation_timer_ms > 150:
                self.animation_timer_ms = 0
                self.animation_frame = (self.animation_frame + 1) % 4
        
        elif self.animation_state == "idle":
            # Reset frame for idle
            self.animation_frame = 0
            self.animation_timer_ms = 0

    def _get_current_sprite(self) -> pygame.Surface | None:
        """Get the current sprite based on animation state."""
        if self.animation_state == "attacking" and Player._attack_sprite:
            return Player._attack_sprite
        elif self.animation_state == "snatching" and Player._snatch_sprite:
            return Player._snatch_sprite
        elif self.animation_state in ("moving", "idle") and Player._movement_sprites:
            if Player._movement_sprites:
                sprite = Player._movement_sprites[self.animation_frame]
                return sprite
        return None


    def draw(self, surface: pygame.Surface, camera_x: int = 0) -> None:
        draw_rect = self.rect.move(-camera_x, 0)
        
        # Draw ability icon
        icon = Player._ability_icon_cache.get(self.current_ability)
        if icon is not None:
            icon_rect = icon.get_rect(midbottom=(draw_rect.centerx, draw_rect.top - 4))
            surface.blit(icon, icon_rect)
        
        # Draw frog sprite
        sprite = self._get_current_sprite()
        if sprite is not None:
            # Flip sprite if facing left
            if self.facing < 0:
                flipped_sprite = pygame.transform.flip(sprite, True, False)
            else:
                flipped_sprite = sprite
            
            # Scale sprite to fit hitbox better
            scaled_size = (
                int(flipped_sprite.get_width() * 1.0),
                int(flipped_sprite.get_height() * 1.0)
            )
            scaled_sprite = pygame.transform.scale(flipped_sprite, scaled_size)
            
            # Align sprite to hitbox bottom
            sprite_pos = (draw_rect.centerx, draw_rect.bottom + 10)
            sprite_rect = scaled_sprite.get_rect(midbottom=sprite_pos)
            surface.blit(scaled_sprite, sprite_rect)
        else:
            # ── Procedural frog fallback (used when sprite assets not found) ──
            self._draw_frog_procedural(surface, draw_rect)

    def _draw_frog_procedural(self, surface: pygame.Surface, draw_rect: pygame.Rect) -> None:
        """Draw a Kirby-style rounded frog: puffs cheeks + floats when hovering."""
        import math as _math
        now = pygame.time.get_ticks()
        cx = draw_rect.centerx
        by = draw_rect.bottom + 8

        state = self.animation_state
        facing = self.facing  # 1=right, -1=left
        frame = self.animation_frame
        hovering = self.is_hovering

        # ── colour palette ───────────────────────────────────────────────────
        body_green   = (88, 195, 108)
        body_dark    = (62, 155, 80)
        belly_col    = (185, 240, 175)
        leg_col      = (62, 155, 80)
        foot_col     = (44, 120, 58)
        toe_col      = (30, 88, 40)
        cheek_col    = (255, 175, 110)   # warm peachy cheeks when puffed
        eye_white    = (235, 252, 225)
        pupil_col    = (22, 30, 22)
        shine_col    = (255, 255, 255)

        # ── hover bob & puff amount ──────────────────────────────────────────
        if hovering:
            # gentle float bob
            bob = int(2.5 * _math.sin(now * 0.005))
            # puff grows over time (0→1 over 400 ms)
            if self._hover_start_ms:
                puff_t = min(1.0, (now - self._hover_start_ms) / 400.0)
            else:
                puff_t = 1.0
        else:
            bob = 0
            puff_t = 0.0

        # ── pose offsets ────────────────────────────────────────────────────
        if hovering:
            body_ox, body_oy = 0, bob - 4   # float up slightly
            leg_spread = 22 + int(puff_t * 8)  # legs splay out
            arm_raise  = -25 - int(puff_t * 10)
        elif state == "jumping":
            body_ox, body_oy = 0, -8
            leg_spread = 10
            arm_raise  = -35
        elif state in ("moving", "idle") and frame % 2 == 1:
            body_ox, body_oy = 2 * facing, 0
            leg_spread = 20
            arm_raise  = 8
        elif state in ("moving", "idle") and frame % 2 == 0:
            body_ox, body_oy = -2 * facing, 0
            leg_spread = -16
            arm_raise  = -8
        elif state == "attacking":
            body_ox, body_oy = 4 * facing, -2
            leg_spread = 0
            arm_raise  = -5
        elif state == "snatching":
            body_ox, body_oy = 0, 0
            leg_spread = 0
            arm_raise  = 20
        else:
            body_ox, body_oy = 0, 0
            leg_spread = 0
            arm_raise  = 0

        bx = cx + body_ox
        gy = by + body_oy

        # ── body size: puffs rounder when hovering ───────────────────────────
        body_w = 44 + int(puff_t * 10)
        body_h = 36 + int(puff_t * 10)

        # ── shadow (shrinks when floating) ───────────────────────────────────
        shadow_alpha = max(30, 80 - int(puff_t * 50))
        shadow_w = max(20, 42 - int(puff_t * 14))
        shadow_s = pygame.Surface((shadow_w, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_s, (0, 0, 0, shadow_alpha), (0, 0, shadow_w, 8))
        surface.blit(shadow_s, (cx - shadow_w // 2, by - 4))

        # ── back legs ────────────────────────────────────────────────────────
        for side in (-1, 1):
            lx = bx + side * (body_w // 2 - 4)
            ly = gy - 12
            swing = leg_spread * side
            knee_x = lx + side * 10 + int(_math.sin(_math.radians(swing)) * 10)
            knee_y = ly + 14 + int(_math.cos(_math.radians(swing)) * 4)
            foot_x = knee_x + side * 4
            foot_y = gy + (2 if not hovering else 6 + int(puff_t * 6))
            pygame.draw.line(surface, leg_col, (lx, ly), (knee_x, knee_y), 6)
            pygame.draw.line(surface, leg_col, (knee_x, knee_y), (foot_x, foot_y), 5)
            pygame.draw.ellipse(surface, foot_col, (foot_x - 9, foot_y - 3, 18, 6))
            for t in range(3):
                tx = foot_x - 7 + t * 7
                pygame.draw.line(surface, toe_col, (tx, foot_y), (tx + side, foot_y + 4), 1)

        # ── arms ─────────────────────────────────────────────────────────────
        for side in (-1, 1):
            ax = bx + side * (body_w // 2 - 2)
            ay = gy - 22
            a_rad = _math.radians(arm_raise * side)
            end_x = int(ax + _math.cos(a_rad) * 10 * side)
            end_y = int(ay + _math.sin(a_rad) * 8 + 8)
            pygame.draw.line(surface, leg_col, (ax, ay), (end_x, end_y), 6)
            pygame.draw.circle(surface, leg_col, (end_x, end_y), 5)

        # ── body (big round Kirby blob) ───────────────────────────────────────
        body_surf = pygame.Surface((body_w + 4, body_h + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(body_surf, body_green,   (2, 4, body_w, body_h))
        pygame.draw.ellipse(body_surf, belly_col,    (body_w//4, body_h//3, body_w//2, body_h//2))
        surface.blit(body_surf, (bx - body_w // 2 - 2, gy - body_h - 2))

        # ── head (merged into body like Kirby) ────────────────────────────────
        head_r = 20 + int(puff_t * 5)
        hx = bx
        hy = gy - body_h + 2

        # puffed cheeks — two big circles on the sides
        if puff_t > 0.05:
            cheek_r = int(10 * puff_t)
            cheek_alpha = int(200 * puff_t)
            for side in (-1, 1):
                chk = pygame.Surface((cheek_r * 2 + 2, cheek_r * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(chk, (*cheek_col, cheek_alpha), (cheek_r + 1, cheek_r + 1), cheek_r)
                surface.blit(chk, (hx + side * (head_r - 4) - cheek_r - 1, hy - cheek_r - 1))

        # ── eyes (big round, shift toward facing direction) ───────────────────
        eye_offset_x = 4 * facing  # eyes shift slightly toward facing side
        for side in (-1, 1):
            ex = hx + side * 9 + eye_offset_x
            ey = hy - 8
            pygame.draw.circle(surface, eye_white, (ex, ey), 7)
            # pupil slides toward facing
            px_off = 2 * facing
            if state == "attacking":
                p_r = 4
            elif state == "snatching":
                p_r = 5
            elif hovering:
                p_r = 3  # squint slightly when puffed
            else:
                p_r = 4
            pygame.draw.circle(surface, pupil_col, (ex + px_off, ey), p_r)
            pygame.draw.circle(surface, shine_col, (ex + px_off + 2, ey - 2), 2)

        # ── expression ───────────────────────────────────────────────────────
        if hovering and puff_t > 0.3:
            # puffed "O" mouth — holding breath!
            mouth_r = max(3, int(6 * puff_t))
            pygame.draw.circle(surface, (180, 60, 100), (hx, hy), mouth_r)
            pygame.draw.circle(surface, (255, 140, 180), (hx, hy), max(1, mouth_r - 2))
        elif state == "attacking":
            pygame.draw.ellipse(surface, (180, 60, 110), (hx - 6 + facing * 4, hy - 2, 12, 9))
            pygame.draw.ellipse(surface, (255, 140, 185), (hx - 4 + facing * 4, hy - 1, 8, 6))
        elif state == "snatching":
            tongue_end_x = hx + facing * 36
            tongue_end_y = hy - 4
            tongue_pts = [
                (hx + facing * 5, hy),
                (hx + facing * 20, hy - 8),
                (tongue_end_x, tongue_end_y),
            ]
            pygame.draw.lines(surface, (220, 60, 130), False, tongue_pts, 5)
            pygame.draw.circle(surface, (255, 80, 150), (tongue_end_x, tongue_end_y), 5)
        elif state == "jumping":
            pygame.draw.ellipse(surface, (160, 50, 90), (hx - 4, hy - 2, 8, 6))
        else:
            smile_surf = pygame.Surface((16, 8), pygame.SRCALPHA)
            pygame.draw.arc(smile_surf, (44, 120, 60), (0, 0, 16, 8),
                            _math.radians(200), _math.radians(340), 2)
            surface.blit(smile_surf, (hx - 8, hy))

        # ── angry brows on attack ─────────────────────────────────────────────
        if state == "attacking":
            for side in (-1, 1):
                ex = hx + side * 9 + eye_offset_x
                ey = hy - 8
                brow_start = (ex - 5, ey - 9)
                brow_end   = (ex + 3, ey - 12 if side * facing > 0 else ey - 6)
                pygame.draw.line(surface, body_dark, brow_start, brow_end, 2)

        # ── hover air puff particles ──────────────────────────────────────────
        if hovering and puff_t > 0.1:
            for i in range(6):
                a = now * 0.003 + i * (_math.pi / 3)
                dist = 28 + int(puff_t * 8)
                sx = int(cx + _math.cos(a) * dist)
                sy = int(gy - body_h // 2 + _math.sin(a) * (dist * 0.45))
                r = max(2, int(4 * puff_t))
                alpha = int(180 * puff_t)
                sp = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(sp, (160, 230, 255, alpha), (r + 1, r + 1), r)
                surface.blit(sp, (sx - r - 1, sy - r - 1))

        # ── breath puff lines (exhale effect) ─────────────────────────────────
        if hovering and puff_t > 0.5:
            puff_alpha = int(120 * puff_t)
            for i in range(3):
                a = _math.pi + i * 0.3 - 0.3
                px1 = int(hx + _math.cos(a) * 14)
                py1 = int(hy + 4 + _math.sin(a) * 6)
                px2 = int(hx + _math.cos(a) * 22)
                py2 = int(hy + 4 + _math.sin(a) * 10)
                pline = pygame.Surface((4, 4), pygame.SRCALPHA)
                pygame.draw.circle(pline, (200, 245, 255, puff_alpha), (2, 2), 2)
                surface.blit(pline, (px2 - 2, py2 - 2))


    def can_attack(self, now_ms: int, cooldown_ms: int = PLAYER_ATTACK_COOLDOWN_MS) -> bool:
        return now_ms - self._last_attack_ms >= cooldown_ms

    def record_attack(self, now_ms: int) -> None:
        self._last_attack_ms = now_ms