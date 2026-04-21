from __future__ import annotations

import math
from pathlib import Path
import random

import pygame

from .data_logger import DataLogger
from .enemies import InsectEnemy, QueenBeeBoss, spawn_enemy_for_time
from .entities import Player
from .projectiles import BossStinger, Projectile, SnowWall
import subprocess
import sys
from .settings import (
    ABILITY_BY_ENEMY,
    BG_COLOR,
    BOSS_SPAWN_THRESHOLD,
    COLOR_BY_ENEMY,
    ENEMY_MAX_COUNT,
    ENEMY_SPAWN_INTERVAL_MS,
    FLAMETHROWER_CONE_HEIGHT,
    FLAMETHROWER_CONE_LENGTH,
    FLAMETHROWER_COOLDOWN_MS,
    FLAMETHROWER_DAMAGE_TICK_MS,
    FPS,
    GROUND_COLOR,
    GROUND_HEIGHT,
    PIT_COLOR,
    PIT_RESPAWN_X,
    PLATFORM_COLOR,
    PLAYER_ATTACK_COOLDOWN_MS,
    SNOWFALL_COOLDOWN_MS,
    SWORD_WHIRLWIND_COOLDOWN_MS,
    SWORD_WHIRLWIND_EFFECT_MS,
    SWORD_WHIRLWIND_RADIUS,
    SWORD_SLASH_LENGTH,
    SWORD_SLASH_HEIGHT,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    WORLD_WIDTH,
)

# ── VFX colour palettes ────────────────────────────────────────────────────────
_DEFEAT_COLORS: dict[str, list[tuple[int, int, int]]] = {
    "fire_wasp":    [(255, 90, 20),  (255, 160, 50), (255, 220, 110)],
    "ice_beetle":   [(80,  190, 255), (160, 225, 255), (220, 245, 255)],
    "sword_mantis": [(200, 200, 240), (225, 225, 255), (255, 255, 255)],
}

_ABILITY_AURA: dict[str, tuple[int, int, int]] = {
    "flamethrower": (255, 120, 50),
    "snowfall":     (100, 200, 255),
    "sword_swing":  (200, 200, 255),
}

_ABILITY_HUD_COLOR: dict[str, tuple[int, int, int]] = {
    "flamethrower": (255, 155, 75),
    "snowfall":     (120, 210, 255),
    "sword_swing":  (205, 205, 255),
    "star_spit":    (200, 200, 220),
}


class GameManager:
    # ══════════════════════════════════════════════════════════════════════════
    #  Init
    # ══════════════════════════════════════════════════════════════════════════

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 24)
        self.small_font = pygame.font.SysFont("consolas", 18)
        self.camera_x = 0
        self.state = "menu"
        self._create_menu_buttons()

        # ── Asset loading ──────────────────────────────────────────────────────
        self.menu_background = None
        self.menu_logo = None
        self.lose_screen = None
        assets_dir = Path(__file__).resolve().parent.parent / "assets" / "menu"
        background_path = assets_dir / "menu_back.png"
        logo_path = assets_dir / "logo.png"
        lose_path = assets_dir / "lose.png"
        if background_path.exists():
            self.menu_background = pygame.image.load(str(background_path)).convert()
            self.menu_background = pygame.transform.scale(self.menu_background, (WINDOW_WIDTH, WINDOW_HEIGHT))
        if logo_path.exists():
            logo_image = pygame.image.load(str(logo_path)).convert_alpha()
            logo_width = min(440, logo_image.get_width())
            scale = logo_width / logo_image.get_width()
            logo_height = int(logo_image.get_height() * scale)
            self.menu_logo = pygame.transform.smoothscale(logo_image, (logo_width, logo_height))
        if lose_path.exists():
            self.lose_screen = pygame.image.load(str(lose_path)).convert_alpha()
            self.lose_screen = pygame.transform.scale(self.lose_screen, (WINDOW_WIDTH, WINDOW_HEIGHT))

        # ── Menu animation state ───────────────────────────────────────────────
        rng_menu = random.Random(77)
        self._menu_fireflies: list[dict] = [
            {
                "x": rng_menu.uniform(30, WINDOW_WIDTH - 30),
                "y": rng_menu.uniform(WINDOW_HEIGHT * 0.15, WINDOW_HEIGHT - 90),
                "vx": rng_menu.uniform(-0.35, 0.35),
                "vy": rng_menu.uniform(-0.20, 0.20),
                "phase": rng_menu.uniform(0, math.pi * 2),
                "speed": rng_menu.uniform(0.0025, 0.0055),
                "radius": rng_menu.randint(2, 4),
                "color": rng_menu.choice([
                    (60, 255, 80), (80, 255, 100), (40, 220, 60),
                    (100, 255, 120), (30, 200, 50),
                ]),
            }
            for _ in range(60)
        ]
        self._menu_particles: list[dict] = []
        self._menu_mist_offset: float = 0.0
        self._menu_star_phases: list[tuple] = [
            (rng_menu.randint(0, WINDOW_WIDTH),
             rng_menu.randint(0, int(WINDOW_HEIGHT * 0.65)),
             rng_menu.uniform(0, math.pi * 2),
             rng_menu.uniform(0.0018, 0.0040),
             rng_menu.randint(1, 2))
            for _ in range(160)
        ]

        self.heart_icons = self._load_heart_icons()
        self.sounds = self._load_sounds()
        self._last_footstep_sound_ms = 0
        self._last_flamethrower_sound_ms = 0

        # ── Level ─────────────────────────────────────────────────────────────
        self.platforms, self.ground_segments, self.pits = self._build_level()
        self._platform_styles = self._assign_platform_styles()
        self._ground_styles   = self._assign_ground_styles()

        start_ground_top = self._ground_top_at(PIT_RESPAWN_X)
        self.player = Player(PIT_RESPAWN_X, start_ground_top - 44)
        self.enemies: list[InsectEnemy] = []
        self.projectiles: list[Projectile] = []
        self.snow_walls: list[SnowWall] = []

        # ── Boss state ────────────────────────────────────────────────────────
        self.boss: QueenBeeBoss | None = None
        self._boss_spawned: bool = False
        self._next_boss_threshold: int = BOSS_SPAWN_THRESHOLD  # recurring every 50 kills
        self._boss_stingers: list[BossStinger] = []
        self._boss_announce_until_ms: int = 0

        # ── Game state ────────────────────────────────────────────────────────
        self.enemy_count = 0
        self.session_time = 0.0
        self.running = True
        self.game_over = False
        self._spawn_timer_ms = 0
        self._next_survival_log_sec = 2
        self._min_spawn_interval_ms = max(1, ENEMY_SPAWN_INTERVAL_MS // 2)
        self._difficulty_cap_seconds = max(
            1,
            (ENEMY_SPAWN_INTERVAL_MS - self._min_spawn_interval_ms) * 5,
        )

        self.is_flamethrower_active = False
        self._last_flamethrower_tick_ms = -FLAMETHROWER_DAMAGE_TICK_MS
        self._flamethrower_released_ms = -FLAMETHROWER_COOLDOWN_MS  # cooldown after release
        self._whirlwind_until_ms = 0
        self._whirlwind_center = (0, 0)
        self._slash_until_ms = 0      # directional slash VFX timer
        self._slash_facing = 1        # direction of last slash

        # ── Logging ───────────────────────────────────────────────────────────
        self.logger = DataLogger()
        self.stats_window = None

        # ── VFX state ─────────────────────────────────────────────────────────
        self.particles: list[dict] = []
        self._pending_defeat_fx: list[tuple[int, int, str]] = []
        self._damage_flash_until_ms: int = 0
        self._snatch_flash_until_ms: int = 0
        self._score_pops: list[dict] = []
        self._lose_fade_alpha: int = 0
        self._game_over_start_ms: int = 0
        self._death_particles: list[dict] = []
        self._heart_bounce: list[float] = [0.0] * 5   # per-heart bounce offset
        self._heart_bounce_timer: list[int] = [0] * 5
        self._last_player_health: int = 5              # track HP changes for bounce

        # ── Screen shake ──────────────────────────────────────────────────────
        self._shake_until_ms: int = 0
        self._shake_mag: int = 0

        # ── Snatch tongue beam ────────────────────────────────────────────────
        self._snatch_beam_until_ms: int = 0
        self._snatch_beam_end: tuple[int, int] = (0, 0)

        # ── Combo tracker ─────────────────────────────────────────────────────
        self._combo_count: int = 0
        self._combo_deadline_ms: int = 0

        # ── HUD hint system ───────────────────────────────────────────────────
        self._hud_hint: tuple[str, int, tuple] | None = None  # (text, expire_ms, color)

        # ── Precomputed surfaces ──────────────────────────────────────────────
        self._vignette = self._create_vignette()
        self._hover_glow_surf = self._create_hover_glow()

        # ── Procedural background data ────────────────────────────────────────
        self._bg_data = self._generate_bg_data()

        # ใน __init__
        pygame.mixer.init()
        pygame.mixer.music.load("bg_music.wav")
        pygame.mixer.music.set_volume(0.01)   # ปรับความดัง 0.0–1.0
        pygame.mixer.music.play(-1)          # -1 = loop ไม่หยุด

    # ══════════════════════════════════════════════════════════════════════════
    #  Main loop
    # ══════════════════════════════════════════════════════════════════════════

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS)
            now = pygame.time.get_ticks()
            if not self.game_over:
                self.session_time = now / 1000.0

            self._handle_events(now)
            if self.state == "playing" and not self.game_over:
                self._update_game(now, dt)
            self._draw()

        self.logger.save_to_csv()

    # ══════════════════════════════════════════════════════════════════════════
    #  Event handling
    # ══════════════════════════════════════════════════════════════════════════

    def _handle_events(self, now: int) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if self.state == "menu":
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._start_game()
                elif self.state == "stats":
                    if event.key == pygame.K_ESCAPE:
                        self._close_stats_window()
                        self.state = "menu"
                elif self.state == "playing":
                    if self.game_over:
                        if event.key == pygame.K_r:
                            self._restart_game()
                        elif event.key == pygame.K_ESCAPE:
                            self.__init__(self.screen)
                    elif event.key in (pygame.K_w, pygame.K_UP):
                        self.player.jump(is_flamethrower_active=self.is_flamethrower_active)
                    elif event.key == pygame.K_j:
                        self._snatch_or_spit(now)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self._swallow_enemy(now)
                    elif event.key == pygame.K_k and self.player.current_ability != "flamethrower":
                        self._shoot_projectile(now)
                    elif event.key == pygame.K_k and self.player.current_ability == "flamethrower":
                        # Show cooldown hint if still cooling down
                        remaining = FLAMETHROWER_COOLDOWN_MS - (now - self._flamethrower_released_ms)
                        if remaining > 0:
                            self._hud_hint = (f"Flamethrower cooling… {remaining // 1000 + 1}s", now + 1200, (255, 140, 60))
                    elif event.key == pygame.K_q:
                        discarded_color = self.player.aura_color
                        old = self.player.discard_ability()
                        if old != "star_spit":
                            self._spit_discarded_ability(old, discarded_color)
                            self.logger.record_event("ability_loss", "discard", now)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.state == "menu":
                    if self._play_button_rect.collidepoint(event.pos):
                        self._start_game()
                    elif self._stats_button_rect.collidepoint(event.pos):
                        self._open_stats_window()
                        self.state = "stats"
                elif self.state == "stats":
                    if self._back_button_rect.collidepoint(event.pos):
                        self._close_stats_window()
                        self.state = "menu"

    # ══════════════════════════════════════════════════════════════════════════
    #  Game update
    # ══════════════════════════════════════════════════════════════════════════

    def _update_game(self, now: int, dt_ms: int) -> None:
        pressed = pygame.key.get_pressed()
        was_flamethrower = self.is_flamethrower_active
        self.is_flamethrower_active = bool(
            pressed[pygame.K_k]
            and self.player.current_ability == "flamethrower"
            and not self.game_over
            and (pygame.time.get_ticks() - self._flamethrower_released_ms) >= FLAMETHROWER_COOLDOWN_MS
        )
        # Track when flamethrower is released to start cooldown
        if was_flamethrower and not self.is_flamethrower_active:
            self._flamethrower_released_ms = pygame.time.get_ticks()

        was_hovering = self.player.is_hovering
        hover_duration = self.player.update(
            pressed,
            world_width=WORLD_WIDTH,
            solid_rects=self.platforms,
            is_flamethrower_active=self.is_flamethrower_active,
        )

        self.player.update_animation(now, dt_ms)

        # Footstep dust particles
        if self.player.on_ground() and abs(self.player.velocity_x) > 0 and self.player.animation_frame in (1, 3):
            if now - self._last_footstep_sound_ms >= 220:
                self._play_sound("footstep", volume=0.24)
                self._last_footstep_sound_ms = now
                self._spawn_particles(
                    self.player.rect.centerx, self.player.rect.bottom,
                    count=4,
                    colors=[(110, 100, 75), (140, 125, 95), (80, 75, 60)],
                    speed=1.4, size=3.2, gravity=0.07, lifetime_ms=260,
                    spread=70, base_angle=90,
                )

        # Flamethrower stream particles
        # Flamethrower stream particles — layered fire + ember sparks
        if self.is_flamethrower_active:
            self._apply_flamethrower(now)
            fx = self.player.rect.right + 4 if self.player.facing > 0 else self.player.rect.left - 4
            fy = self.player.rect.centery - 4
            fire_angle = 0.0 if self.player.facing > 0 else 180.0
            if now % 2 == 0:
                # Core flame — wide, hot
                self._spawn_particles(
                    fx, fy, count=4,
                    colors=[(255, 60, 10), (255, 130, 30), (255, 200, 80)],
                    speed=5.5, size=7.0, gravity=-0.06, lifetime_ms=320,
                    spread=28, base_angle=fire_angle,
                )
                # Outer glow — larger, cooler orange
                self._spawn_particles(
                    fx, fy, count=2,
                    colors=[(255, 100, 20), (255, 170, 60)],
                    speed=3.5, size=10.0, gravity=-0.02, lifetime_ms=260,
                    spread=35, base_angle=fire_angle,
                )
            # Ember sparks every 3 frames
            if now % 3 == 0:
                self._spawn_particles(
                    fx + (random.randint(10, 50) * self.player.facing),
                    fy + random.randint(-18, 18),
                    count=2,
                    colors=[(255, 220, 50), (255, 255, 160), (255, 180, 20)],
                    speed=2.5, size=2.5, gravity=-0.10, lifetime_ms=480,
                    spread=80, base_angle=-90.0,
                )

        if self.player.is_hovering and not was_hovering:
            self.player.start_hover(now)
        elif not self.player.is_hovering and was_hovering:
            duration = self.player.stop_hover(now)
            if duration:
                self.logger.record_event("hover_duration", duration, now)
        if hover_duration:
            self.logger.record_event("hover_duration", hover_duration, now)

        if self.player.rect.top > WINDOW_HEIGHT + 100:
            self._handle_pit_fall(now)

        self._spawn_timer_ms += dt_ms
        dynamic_spawn_interval_ms = max(
            self._min_spawn_interval_ms,
            ENEMY_SPAWN_INTERVAL_MS - int(self.session_time // 5),
        )
        dynamic_enemy_cap = ENEMY_MAX_COUNT + int(self.session_time // 30)
        boss_alive = self.boss is not None and self.boss.is_alive
        # Spawn boss when threshold reached (recurring every 50 kills)
        if not self._boss_spawned and self.enemy_count >= self._next_boss_threshold:
            self._spawn_boss()
        # Regular enemy spawning — capped at 5 while boss is alive, normal otherwise
        _boss_enemy_cap = 5
        if not boss_alive and not self._boss_spawned:
            if self._spawn_timer_ms >= dynamic_spawn_interval_ms and len(self.enemies) < dynamic_enemy_cap:
                self._spawn_enemy()
                self._spawn_timer_ms = 0
        elif boss_alive:
            if self._spawn_timer_ms >= dynamic_spawn_interval_ms * 2 and len(self.enemies) < _boss_enemy_cap:
                self._spawn_enemy()
                self._spawn_timer_ms = 0

        self._update_enemies(now)
        self._update_projectiles(now)
        self._update_snow_walls(now)
        if self.boss is not None and self.boss.is_alive:
            self._update_boss(now)

        # VFX updates
        self._process_defeat_fx()
        self._update_particles(dt_ms)
        self._update_score_pops(dt_ms)

        if self.session_time >= self._next_survival_log_sec:
            self.logger.record_event("survival_time", round(self.session_time, 2), now)
            self._next_survival_log_sec += 2

        if sum(len(buf) for buf in self.logger.buffers.values()) >= 25:
            self.logger.save_to_csv()

        if self.player.health <= 0:
            if not self.game_over:
                self._game_over_start_ms = now
                self._trigger_game_over_fx(now)
            self.game_over = True
            self.logger.record_event("game_over", round(self.session_time, 2), now)

        self.camera_x = max(
            0,
            min(WORLD_WIDTH - WINDOW_WIDTH, self.player.rect.centerx - WINDOW_WIDTH // 2),
        )
        # Screen shake
        if now < self._shake_until_ms:
            progress = (self._shake_until_ms - now) / 380.0
            mag = int(self._shake_mag * progress)
            self.camera_x += random.randint(-mag, mag)

    def _update_enemies(self, now: int) -> None:
        for enemy in self.enemies:
            enemy.ai_behavior(
                self.player.rect,
                solid_rects=self.platforms,
                pit_rects=self.pits,
                world_width=WORLD_WIDTH,
            )
            if enemy.rect.colliderect(self.player.rect):
                self.player.on_hit(1)
                self._play_sound("hurt")
                self._on_player_damaged(now)
                self.logger.record_event("damage_taken", 1, now)
                self.logger.record_event("ability_loss", "hit", now)
                enemy.is_alive = False
            if enemy.rect.top > WINDOW_HEIGHT + 120:
                enemy.is_alive = False
            if abs(enemy.rect.centerx - self.player.rect.centerx) > 1200:
                enemy.is_alive = False

        self.enemies = [e for e in self.enemies if e.is_alive]

    def _update_projectiles(self, now: int) -> None:
        for projectile in self.projectiles:
            projectile.update()
            # Star-spit particle trail
            if projectile.ability == "star_spit" and not projectile.is_discarded:
                self._spawn_particles(
                    projectile.rect.centerx, projectile.rect.centery,
                    count=2,
                    colors=[(255, 235, 80), (255, 180, 40), (255, 255, 160)],
                    speed=1.0, size=3.0, gravity=0.05, lifetime_ms=180,
                    spread=50, base_angle=180.0 if projectile.direction > 0 else 0.0,
                )
            # Flamethrower trail
            elif projectile.ability == "flamethrower" and not projectile.is_discarded:
                self._spawn_particles(
                    projectile.rect.centerx, projectile.rect.centery,
                    count=1,
                    colors=[(255, 90, 20), (255, 160, 50)],
                    speed=0.8, size=2.5, gravity=-0.03, lifetime_ms=140,
                    spread=30, base_angle=180.0 if projectile.direction > 0 else 0.0,
                )
            for enemy in self.enemies:
                if enemy.is_alive and projectile.check_impact(enemy.rect):
                    enemy.is_alive = False
                    self.enemy_count += 1
                    self._pending_defeat_fx.append((enemy.rect.centerx, enemy.rect.centery, enemy.enemy_type))
                    self.logger.record_event("enemy_defeat", enemy.enemy_type, now)

            # Projectiles also hit the boss
            if self.boss is not None and self.boss.is_alive:
                if projectile.check_impact(self.boss.rect):
                    self.boss.take_damage(projectile.damage, now)
                    projectile.rect.x = -9999
                    if not self.boss.is_alive:
                        self._on_boss_defeated(now)

        self.enemies = [e for e in self.enemies if e.is_alive]
        self.projectiles = [p for p in self.projectiles if not p.destroy()]

    def _update_snow_walls(self, now: int) -> None:
        for wall in self.snow_walls:
            wall.update(self.platforms)
            # Falling frost trail
            if not wall.is_grounded and now % 3 == 0:
                self._spawn_particles(
                    wall.rect.centerx + random.randint(-10, 10),
                    wall.rect.bottom,
                    count=2,
                    colors=[(180, 235, 255), (220, 248, 255), (140, 210, 245)],
                    speed=1.0, size=2.2, gravity=0.04, lifetime_ms=380,
                    spread=60, base_angle=90.0,
                )
            for enemy in self.enemies:
                if enemy.is_alive and wall.rect.colliderect(enemy.rect):
                    enemy.is_alive = False
                    wall.on_hit_enemy()
                    self.enemy_count += 1
                    self._pending_defeat_fx.append((enemy.rect.centerx, enemy.rect.centery, enemy.enemy_type))
                    self.logger.record_event("enemy_defeat", enemy.enemy_type, now)
                    break

        self.enemies = [e for e in self.enemies if e.is_alive]
        self.snow_walls = [w for w in self.snow_walls if not w.is_destroyed()]

        # Snow walls also damage the boss
        if self.boss is not None and self.boss.is_alive:
            now_sw = pygame.time.get_ticks()
            for wall in self.snow_walls:
                if wall.rect.colliderect(self.boss.rect):
                    self.boss.take_damage(1, now_sw)
                    wall.on_hit_enemy()
                    if not self.boss.is_alive:
                        self._on_boss_defeated(now_sw)

    def _snatch_or_spit(self, now: int) -> None:
        """J key: capture an enemy if free, or spit the held one as a star."""
        # ── Already holding an enemy → spit it as a star ──────────────────────
        if self.player.held_enemy_type is not None:
            x = self.player.rect.centerx + (20 * self.player.facing)
            y = self.player.rect.centery - 24
            star = Projectile(x=x, y=y, direction=self.player.facing, ability="star_spit")
            self.projectiles.append(star)
            self._play_sound("star")
            self.player.trigger_attack(now)
            self.logger.record_event("attack_type", "star_spit", now)
            self._spawn_particles(
                x, y, count=8,
                colors=[(255, 235, 80), (255, 180, 40), (255, 255, 160)],
                speed=3.0, size=4.5, gravity=-0.04, lifetime_ms=280, spread=60,
            )
            self.player.held_enemy_type = None
            self._hud_hint = (" Star fired!", now + 1200, (255, 235, 80))
            return

        # ── Nothing held → attempt snatch ─────────────────────────────────────
        self.player.trigger_snatch(now)
        tongue_hitbox = self.player.snatch_tongue()
        for enemy in self.enemies:
            if tongue_hitbox.colliderect(enemy.rect):
                enemy.is_alive = False
                self.enemy_count += 1
                self.player.held_enemy_type = enemy.enemy_type
                self._play_sound("snatch", volume=0.32)
                self._snatch_flash_until_ms = now + 320
                # Record tongue beam for visual
                self._snatch_beam_until_ms = now + 160
                self._snatch_beam_end = (enemy.rect.centerx, enemy.rect.centery)
                self._pending_defeat_fx.append((enemy.rect.centerx, enemy.rect.centery, enemy.enemy_type))
                self.logger.record_event("attack_type", "snatch", now)
                self.logger.record_event("enemy_defeat", enemy.enemy_type, now)
                self._hud_hint = ("J = Spit      down = Swallow (gain power)", now + 3000, (200, 240, 160))
                return
        # Miss — still show a short tongue beam in facing direction
        self._snatch_beam_until_ms = now + 100
        tip = tongue_hitbox.center
        self._snatch_beam_end = tip
        self.logger.record_event("attack_type", "snatch_miss", now)

    def _swallow_enemy(self, now: int) -> None:
        """Down key: swallow the held enemy and gain its ability."""
        if self.player.held_enemy_type is None:
            return
        ability = ABILITY_BY_ENEMY.get(self.player.held_enemy_type, "none")
        self.player.current_ability = ability
        self.player.aura_color = COLOR_BY_ENEMY.get(self.player.held_enemy_type)
        self.player.held_enemy_type = None
        self._snatch_flash_until_ms = now + 200
        self._play_sound("snatch", volume=0.22)
        self.logger.record_event("ability_gain", ability, now)
        self._hud_hint = (f"Power: {ability.replace('_', ' ').title()} acquired!", now + 2400,
                          _ABILITY_HUD_COLOR.get(ability, (200, 240, 160)))
        # Burst particles on swallow
        self._spawn_particles(
            self.player.rect.centerx, self.player.rect.centery,
            count=16, colors=list(_DEFEAT_COLORS.get(
                next((k for k, v in ABILITY_BY_ENEMY.items() if v == ability), "sword_mantis"),
                [(200, 200, 255)])),
            speed=4.0, size=5.0, gravity=0.08, lifetime_ms=480,
        )

    def _shoot_projectile(self, now: int) -> None:
        ability = self.player.current_ability
        if ability == "snowfall":
            cooldown_ms = SNOWFALL_COOLDOWN_MS
        elif ability == "sword_swing":
            cooldown_ms = SWORD_WHIRLWIND_COOLDOWN_MS
        else:
            cooldown_ms = PLAYER_ATTACK_COOLDOWN_MS

        if not self.player.can_attack(now, cooldown_ms=cooldown_ms):
            return

        # Can't use K-attacks while an enemy is held in mouth
        if self.player.held_enemy_type is not None:
            self._hud_hint = ("J = Spit      down = Swallow (gain power)", now + 2000, (200, 240, 160))
            return

        # star_spit has no K-attack — player must snatch an enemy first
        if ability == "star_spit":
            self._hud_hint = ("Press J to snatch an enemy!", now + 2000, (255, 230, 80))
            return

        self.player.trigger_attack(now)

        if ability == "snowfall":
            spawn_x = self.player.rect.centerx + (42 * self.player.facing) - 17
            spawn_y = self.player.rect.top - 70
            self.snow_walls.append(SnowWall(spawn_x, spawn_y))
            self._play_sound("ice")
            self.player.record_attack(now)
            self.logger.record_event("attack_type", "snowfall", now)
            # Ice burst particles — shards + shimmer
            self._spawn_particles(
                spawn_x + 17, spawn_y + 29, count=16,
                colors=[(160, 230, 255), (200, 245, 255), (100, 200, 245), (255, 255, 255)],
                speed=4.5, size=4.0, gravity=0.06, lifetime_ms=500,
            )
            self._spawn_particles(
                spawn_x + 17, spawn_y + 29, count=8,
                colors=[(220, 248, 255), (255, 255, 255)],
                speed=2.0, size=2.0, gravity=-0.04, lifetime_ms=700,
                spread=360, base_angle=-90.0,
            )
            return

        if ability == "sword_swing":
            self._apply_whirlwind(now)
            self._play_sound("sword")
            self.player.record_attack(now)
            self.logger.record_event("attack_type", "whirlwind", now)
            return

        x = self.player.rect.centerx + (20 * self.player.facing)
        y = self.player.rect.centery - 24 if ability == "star_spit" else self.player.rect.centery - 6
        projectile = Projectile(x=x, y=y, direction=self.player.facing, ability=ability)
        self.projectiles.append(projectile)
        self._play_sound("star")
        self.player.record_attack(now)
        self.logger.record_event("attack_type", f"spit_{ability}", now)

    def _spit_discarded_ability(self, ability: str, color: tuple[int, int, int] | None) -> None:
        if ability in ("star_spit", "none"):
            return

        if color is None:
            from .settings import COLOR_BY_ABILITY
            color = COLOR_BY_ABILITY.get(ability, (230, 230, 230))

        x = self.player.rect.centerx + (20 * self.player.facing)
        y = self.player.rect.centery - 10
        projectile = Projectile(
            x=x, y=y, direction=self.player.facing,
            ability=ability, is_discarded=True, color_override=color,
        )
        projectile.speed += 2
        self.projectiles.append(projectile)

        if ability == "flamethrower":
            self._play_sound("fire")
        elif ability == "snowfall":
            self._play_sound("ice")
        elif ability == "sword_swing":
            self._play_sound("sword")

    def _apply_flamethrower(self, now: int) -> None:
        if now - self._last_flamethrower_tick_ms < FLAMETHROWER_DAMAGE_TICK_MS:
            return

        if now - self._last_flamethrower_sound_ms >= 800:
            self._play_sound("fire", volume=0.45)
            self._last_flamethrower_sound_ms = now

        hitbox = self._get_flamethrower_rect()
        defeated = 0
        for enemy in self.enemies:
            if enemy.is_alive and hitbox.colliderect(enemy.rect):
                enemy.is_alive = False
                self.enemy_count += 1
                defeated += 1
                self._pending_defeat_fx.append((enemy.rect.centerx, enemy.rect.centery, enemy.enemy_type))
                self.logger.record_event("enemy_defeat", enemy.enemy_type, now)

        self._last_flamethrower_tick_ms = now
        if defeated > 0:
            self.logger.record_event("attack_type", "flamethrower", now)

        # Flamethrower also damages the boss
        if self.boss is not None and self.boss.is_alive:
            if hitbox.colliderect(self.boss.rect):
                self.boss.take_damage(2, now)
                if not self.boss.is_alive:
                    self._on_boss_defeated(now)

    def _apply_whirlwind(self, now: int) -> None:
        """Directional sword slash — hits enemies in a forward arc."""
        facing = self.player.facing
        px, py = self.player.rect.centerx, self.player.rect.centery

        # Build slash hitbox as a forward rectangle
        slash_w = SWORD_SLASH_LENGTH
        slash_h = SWORD_SLASH_HEIGHT * 2
        if facing > 0:
            slash_rect = pygame.Rect(px - 10, py - SWORD_SLASH_HEIGHT, slash_w, slash_h)
        else:
            slash_rect = pygame.Rect(px - slash_w + 10, py - SWORD_SLASH_HEIGHT, slash_w, slash_h)

        self._whirlwind_center = (px, py)
        self._whirlwind_until_ms = now + SWORD_WHIRLWIND_EFFECT_MS
        self._slash_until_ms = now + 160
        self._slash_facing = facing

        # Slash arc particles — sweeping forward
        base_angle = -30.0 if facing > 0 else 210.0
        self._spawn_particles(
            px + facing * 40, py - 10, count=20,
            colors=[(220, 220, 255), (180, 180, 255), (255, 255, 255), (140, 200, 255)],
            speed=7.0, size=4.5, gravity=0.0, lifetime_ms=220,
            spread=70, base_angle=base_angle,
        )
        # Trailing shimmer
        self._spawn_particles(
            px + facing * 70, py, count=10,
            colors=[(255, 255, 255), (200, 200, 255)],
            speed=3.0, size=2.5, gravity=0.08, lifetime_ms=340,
            spread=50, base_angle=base_angle,
        )

        defeated = 0
        for enemy in self.enemies:
            if not enemy.is_alive:
                continue
            if slash_rect.colliderect(enemy.rect):
                enemy.is_alive = False
                self.enemy_count += 1
                defeated += 1
                self._pending_defeat_fx.append((enemy.rect.centerx, enemy.rect.centery, enemy.enemy_type))
                self.logger.record_event("enemy_defeat", enemy.enemy_type, now)

        self.enemies = [e for e in self.enemies if e.is_alive]

        # Boss can also be hit by the sword slash
        if self.boss is not None and self.boss.is_alive:
            if slash_rect.colliderect(self.boss.rect):
                self.boss.take_damage(3, now)
                if not self.boss.is_alive:
                    self._on_boss_defeated(now)

    # ══════════════════════════════════════════════════════════════════════════
    #  VFX helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_player_damaged(self, now: int) -> None:
        """Triggers damage screen flash + hurt sparks + screen shake + heart bounce."""
        self._damage_flash_until_ms = now + 320
        self._shake_until_ms = now + 380
        self._shake_mag = 7
        # Bounce the heart that was just lost
        lost_idx = self.player.health  # 0-based index of the heart that just broke
        if 0 <= lost_idx < 5:
            self._heart_bounce[lost_idx] = -8.0
            self._heart_bounce_timer[lost_idx] = now
        self._spawn_particles(
            self.player.rect.centerx, self.player.rect.centery,
            count=10,
            colors=[(255, 70, 70), (255, 150, 100), (255, 210, 160)],
            speed=3.2, size=5.0, gravity=0.1, lifetime_ms=400,
        )

    def _generate_bg_data(self) -> dict:
        rng = random.Random(42)
        ground_y = WINDOW_HEIGHT - GROUND_HEIGHT

        clouds = []
        x = rng.randint(200, 500)
        while x < WORLD_WIDTH + 500:
            clouds.append((x, rng.randint(30, 160), rng.randint(70, 190), rng.randint(18, 46)))
            x += rng.randint(250, 620)

        mountains = []
        x = -100
        while x < WORLD_WIDTH + 400:
            h = rng.randint(85, 210)
            w = rng.randint(200, 390)
            mountains.append((x, h, w))
            x += w - rng.randint(60, 130)

        hills = []
        x = -60
        while x < WORLD_WIDTH + 220:
            h = rng.randint(45, 115)
            w = rng.randint(130, 270)
            hills.append((x, h, w))
            x += w - rng.randint(25, 80)

        trees = []
        x = rng.randint(60, 160)
        while x < WORLD_WIDTH:
            trees.append((x, rng.randint(50, 125)))
            x += rng.randint(85, 210)

        # Background decorative structures (non-collidable, parallax 0.35x)
        bg_structures = []
        # Zone 0 (grass 0-799) — dead trees
        for wx in range(150, 780, 220):
            bg_structures.append((wx, "dead_tree", rng.randint(20, 36), rng.randint(90, 160)))
        # Zone 1 (mossy 800-1749) — arches
        for wx in range(880, 1720, 290):
            bg_structures.append((wx, "arch", rng.randint(60, 90), rng.randint(100, 150)))
        # Zone 2 (ancient 1750-2619) — towers + obelisks
        for wx in range(1820, 2600, 240):
            stype = rng.choice(["tower", "tower", "obelisk"])
            bg_structures.append((wx, stype, rng.randint(28, 44), rng.randint(110, 180)))
        # Zone 3 (volcanic 2620-3519) — dead trees
        for wx in range(2700, 3500, 220):
            bg_structures.append((wx, "dead_tree", rng.randint(16, 28), rng.randint(80, 140)))
        # Zone 4 (crystal 3520-5000) — stalactites
        for wx in range(3600, WORLD_WIDTH - 100, 260):
            bg_structures.append((wx, "stalactite_bg", rng.randint(60, 120), rng.randint(80, 200)))

        return {"clouds": clouds, "mountains": mountains, "hills": hills,
                "trees": trees, "bg_structures": bg_structures}

    def _create_vignette(self) -> pygame.Surface:
        """Precompute a screen-edge darkening vignette."""
        surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        depth = 78
        for i in range(depth):
            alpha = int(((1.0 - i / depth) ** 2.0) * 130)
            c = (0, 0, 12, alpha)
            pygame.draw.rect(surf, c, (i, i, WINDOW_WIDTH - i * 2, 1))
            pygame.draw.rect(surf, c, (i, WINDOW_HEIGHT - 1 - i, WINDOW_WIDTH - i * 2, 1))
            pygame.draw.rect(surf, c, (i, i, 1, WINDOW_HEIGHT - i * 2))
            pygame.draw.rect(surf, c, (WINDOW_WIDTH - 1 - i, i, 1, WINDOW_HEIGHT - i * 2))
        return surf

    def _create_hover_glow(self) -> pygame.Surface:
        """Precompute soft ellipse glow drawn under the player while hovering."""
        w, h = 92, 24
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (140, 210, 255, 65), (0, 0, w, h))
        pygame.draw.ellipse(surf, (190, 235, 255, 35), (10, 5, w - 20, h - 10))
        return surf

    def _spawn_particles(
        self,
        x: float,
        y: float,
        count: int,
        colors: list[tuple[int, int, int]],
        speed: float = 2.5,
        size: float = 4.0,
        gravity: float = 0.12,
        lifetime_ms: int = 450,
        spread: float = 360.0,
        base_angle: float = -90.0,
    ) -> None:
        for _ in range(count):
            a = math.radians(base_angle + random.uniform(-spread / 2, spread / 2))
            spd = random.uniform(speed * 0.4, speed * 1.55)
            lt = int(random.uniform(lifetime_ms * 0.6, lifetime_ms * 1.2))
            self.particles.append({
                "x": x, "y": y,
                "vx": math.cos(a) * spd,
                "vy": math.sin(a) * spd,
                "gravity": gravity,
                "life": lt, "max_life": lt,
                "color": random.choice(colors),
                "size": random.uniform(size * 0.45, size),
            })

    def _update_particles(self, dt_ms: int) -> None:
        keep = []
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += p["gravity"]
            p["vx"] *= 0.965
            p["life"] -= dt_ms
            if p["life"] > 0:
                keep.append(p)
        self.particles = keep

    def _draw_particles(self) -> None:
        for p in self.particles:
            alpha = max(0.0, p["life"] / p["max_life"])
            size = max(1, int(p["size"] * alpha))
            sx = int(p["x"] - self.camera_x)
            sy = int(p["y"])
            if -10 <= sx <= WINDOW_WIDTH + 10 and -10 <= sy <= WINDOW_HEIGHT + 10:
                r, g, b = p["color"]
                draw_color = (
                    min(255, int(r * alpha + 18)),
                    min(255, int(g * alpha + 8)),
                    min(255, int(b * alpha + 4)),
                )
                pygame.draw.circle(self.screen, draw_color, (sx, sy), size)

    def _process_defeat_fx(self) -> None:
        if self._pending_defeat_fx:
            now = pygame.time.get_ticks()
            count = len(self._pending_defeat_fx)
            if now <= self._combo_deadline_ms:
                self._combo_count += count
            else:
                self._combo_count = count
            self._combo_deadline_ms = now + 3000

        for (wx, wy, etype) in self._pending_defeat_fx:
            colors = _DEFEAT_COLORS.get(etype, [(210, 210, 210)])
            self._spawn_particles(
                wx, wy, count=14, colors=colors,
                speed=3.2, size=5.5, gravity=0.13, lifetime_ms=520,
            )
            pop_text = f"x{self._combo_count}  +1" if self._combo_count >= 3 else "+1"
            pop_color = (255, 100, 60) if self._combo_count >= 5 else (255, 220, 60) if self._combo_count >= 3 else (255, 235, 80)
            self._score_pops.append({
                "text": pop_text,
                "color": pop_color,
                "x": float(wx), "y": float(wy - 12),
                "life": 720, "max_life": 720,
            })
        self._pending_defeat_fx.clear()

    def _update_score_pops(self, dt_ms: int) -> None:
        keep = []
        for pop in self._score_pops:
            pop["y"] -= dt_ms * 0.042
            pop["life"] -= dt_ms
            if pop["life"] > 0:
                keep.append(pop)
        self._score_pops = keep

    def _draw_score_pops(self) -> None:
        for pop in self._score_pops:
            alpha = max(0.0, pop["life"] / pop["max_life"])
            sx = int(pop["x"] - self.camera_x)
            sy = int(pop["y"])
            if -30 <= sx <= WINDOW_WIDTH + 30 and -30 <= sy <= WINDOW_HEIGHT + 30:
                color = pop.get("color", (255, 235, 80))
                surf = self.small_font.render(pop["text"], True, color)
                surf.set_alpha(int(alpha * 255))
                self.screen.blit(surf, (sx - surf.get_width() // 2, sy))

    def _draw_damage_flash(self, now: int) -> None:
        if now >= self._damage_flash_until_ms:
            return
        progress = (self._damage_flash_until_ms - now) / 320.0
        alpha = int(90 * progress)
        flash = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 18, 18, alpha))
        self.screen.blit(flash, (0, 0))

    def _draw_snatch_flash(self, now: int) -> None:
        if now >= self._snatch_flash_until_ms:
            return
        progress = (self._snatch_flash_until_ms - now) / 320.0
        alpha = int(70 * progress)
        flash = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        flash.fill((80, 255, 120, alpha))
        self.screen.blit(flash, (0, 0))

    def _draw_hud_hints(self, now: int) -> None:
        if self._hud_hint is None:
            return
        text, expire_ms, color = self._hud_hint
        if now >= expire_ms:
            self._hud_hint = None
            return
        progress = min(1.0, (expire_ms - now) / 600.0)
        alpha = int(255 * progress)
        # Pulsing scale
        pulse = 1.0 + 0.05 * math.sin(now * 0.012)
        hint_surf = self.font.render(text, True, color)
        w = int(hint_surf.get_width() * pulse)
        h = int(hint_surf.get_height() * pulse)
        scaled = pygame.transform.smoothscale(hint_surf, (w, h))
        scaled.set_alpha(alpha)
        self.screen.blit(scaled, (WINDOW_WIDTH // 2 - w // 2, WINDOW_HEIGHT // 2 - 80))

    # ══════════════════════════════════════════════════════════════════════════
    #  Background drawing
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_background(self) -> None:
        ground_y = WINDOW_HEIGHT - GROUND_HEIGHT
        now = pygame.time.get_ticks()

        # ── Zone detection from camera_x ──────────────────────────────────────
        # Zones: 0=grass(0-799), 1=mossy(800-1749), 2=ancient(1750-2619),
        #        3=volcanic(2620-3519), 4=crystal(3520+)
        zone_edges = [0, 800, 1750, 2620, 3520, WORLD_WIDTH]
        zone_skies = [
            # (top, mid, bot) sky colors
            ((14, 20, 50),  (22, 36, 68),  (32, 52, 80)),   # grass — blue night
            ((10, 22, 18),  (16, 38, 28),  (24, 54, 38)),   # mossy — dark green
            ((26, 20, 12),  (40, 30, 16),  (52, 42, 22)),   # ancient — amber dusk
            ((22, 8,  4),   (34, 12, 6),   (46, 18, 8)),    # volcanic — blood red
            ((6,  12, 28),  (10, 20, 44),  (16, 30, 62)),   # crystal cave — deep blue
        ]
        # find current zone + blend ratio
        cx = self.camera_x + WINDOW_WIDTH // 2
        zone_idx = 0
        blend_t = 0.0
        for z in range(len(zone_edges) - 1):
            if zone_edges[z] <= cx < zone_edges[z + 1]:
                zone_idx = min(z, len(zone_skies) - 1)
                span = zone_edges[z + 1] - zone_edges[z]
                # blend starts 200px before zone end
                blend_start = zone_edges[z + 1] - 200
                if cx > blend_start and z + 1 < len(zone_skies):
                    blend_t = min(1.0, (cx - blend_start) / 200.0)
                break

        def lerp_col(a, b, t):
            return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

        next_idx = min(zone_idx + 1, len(zone_skies) - 1)
        sky_top = lerp_col(zone_skies[zone_idx][0], zone_skies[next_idx][0], blend_t)
        sky_mid = lerp_col(zone_skies[zone_idx][1], zone_skies[next_idx][1], blend_t)
        sky_bot = lerp_col(zone_skies[zone_idx][2], zone_skies[next_idx][2], blend_t)

        # ── Sky gradient ──────────────────────────────────────────────────────
        band = ground_y // 3
        pygame.draw.rect(self.screen, sky_top, (0, 0,        WINDOW_WIDTH, band))
        pygame.draw.rect(self.screen, sky_mid, (0, band,     WINDOW_WIDTH, band))
        pygame.draw.rect(self.screen, sky_bot, (0, band * 2, WINDOW_WIDTH, ground_y - band * 2))

        # ── Zone-specific sky details ──────────────────────────────────────────
        if zone_idx == 0:  # grass — stars + moon
            rng_s = random.Random(77)
            for _ in range(40):
                sx = rng_s.randint(0, WINDOW_WIDTH)
                sy = rng_s.randint(0, ground_y - 60)
                twinkle = int(80 + 60 * abs(math.sin(now * 0.002 + sx * 0.1)))
                pygame.draw.circle(self.screen, (twinkle, twinkle, twinkle + 40), (sx, sy), 1)
            # moon
            moon_x = int(WINDOW_WIDTH * 0.78)
            moon_y = 55
            pygame.draw.circle(self.screen, (240, 240, 210), (moon_x, moon_y), 28)
            pygame.draw.circle(self.screen, sky_top,          (moon_x + 10, moon_y - 6), 22)
            # moon glow
            mg = pygame.Surface((90, 90), pygame.SRCALPHA)
            pygame.draw.circle(mg, (200, 200, 160, 25), (45, 45), 45)
            self.screen.blit(mg, (moon_x - 45, moon_y - 45))

        elif zone_idx == 1:  # mossy — fireflies
            rng_f = random.Random(88)
            for i in range(18):
                fx = int((rng_f.randint(0, WORLD_WIDTH) - self.camera_x * 0.3) % WINDOW_WIDTH)
                fy = rng_f.randint(ground_y - 200, ground_y - 20)
                phase = math.sin(now * 0.003 + i * 1.7)
                if phase > 0:
                    alpha = int(phase * 180)
                    ff = pygame.Surface((8, 8), pygame.SRCALPHA)
                    pygame.draw.circle(ff, (100, 255, 120, alpha), (4, 4), 4)
                    self.screen.blit(ff, (fx - 4, fy - 4))
            # fog wisps near ground
            for i in range(5):
                wx = int((i * 240 - self.camera_x * 0.15) % (WINDOW_WIDTH + 200)) - 100
                wy = ground_y - 30 + int(6 * math.sin(now * 0.0008 + i * 2.1))
                wsurf = pygame.Surface((180, 28), pygame.SRCALPHA)
                pygame.draw.ellipse(wsurf, (60, 90, 60, 28), (0, 4, 180, 20))
                self.screen.blit(wsurf, (wx, wy))

        elif zone_idx == 2:  # ancient — dusk sun + ruin silhouettes
            sun_x = WINDOW_WIDTH // 2
            sun_y = ground_y - 120
            # sun glow rings
            for r, a in [(70, 18), (50, 30), (34, 55)]:
                sg = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(sg, (220, 140, 40, a), (r, r), r)
                self.screen.blit(sg, (sun_x - r, sun_y - r))
            pygame.draw.circle(self.screen, (255, 200, 80), (sun_x, sun_y), 24)
            pygame.draw.circle(self.screen, (255, 240, 180), (sun_x, sun_y), 14)
            # horizon glow
            for i in range(20):
                alpha = int((1 - i / 20) * 40)
                gs = pygame.Surface((WINDOW_WIDTH, 1), pygame.SRCALPHA)
                gs.fill((200, 120, 30, alpha))
                self.screen.blit(gs, (0, ground_y - i - 1))
            # bg ruin columns silhouette
            rng_r = random.Random(99)
            for ci in range(6):
                rx = int((rng_r.randint(100, WORLD_WIDTH - 100) - self.camera_x * 0.18) % (WINDOW_WIDTH + 80)) - 40
                col_h = rng_r.randint(80, 170)
                col_w = rng_r.randint(18, 32)
                pygame.draw.rect(self.screen, (38, 28, 12),
                                 (rx - col_w // 2, ground_y - col_h, col_w, col_h))
                # column capital
                pygame.draw.rect(self.screen, (44, 34, 14),
                                 (rx - col_w // 2 - 5, ground_y - col_h, col_w + 10, 8))

        elif zone_idx == 3:  # volcanic — ember sky + ash clouds
            # red/orange sky tint
            for i in range(15):
                alpha = int((1 - i / 15) * 35)
                gs = pygame.Surface((WINDOW_WIDTH, 1), pygame.SRCALPHA)
                gs.fill((180, 40, 10, alpha))
                self.screen.blit(gs, (0, ground_y - i - 1))
            # ash cloud puffs
            rng_v = random.Random(55)
            for ci in range(8):
                ax = int((rng_v.randint(0, WORLD_WIDTH) - self.camera_x * 0.08) % (WINDOW_WIDTH + 300)) - 150
                ay = rng_v.randint(20, ground_y - 80)
                aw = rng_v.randint(80, 200)
                ah = rng_v.randint(20, 50)
                asurf = pygame.Surface((aw, ah), pygame.SRCALPHA)
                pygame.draw.ellipse(asurf, (28, 16, 12, 60), (0, 0, aw, ah))
                self.screen.blit(asurf, (ax, ay))
            # distant lava glow on horizon
            lg = pygame.Surface((WINDOW_WIDTH, 18), pygame.SRCALPHA)
            for i in range(18):
                alpha = int((1 - i / 18) * 70)
                pygame.draw.rect(lg, (220, 80, 10, alpha), (0, i, WINDOW_WIDTH, 1))
            self.screen.blit(lg, (0, ground_y - 20))
            # falling ash particles
            rng_a = random.Random(33)
            for i in range(25):
                ax = int((rng_a.randint(0, WINDOW_WIDTH) + now // 20 + i * 37) % WINDOW_WIDTH)
                ay = int((rng_a.randint(0, ground_y) + now // 8 + i * 53) % ground_y)
                pygame.draw.circle(self.screen, (50, 35, 28), (ax, ay), 1)

        else:  # crystal cave — aurora + falling crystals
            # aurora bands
            for i, (col, oy) in enumerate([
                ((20, 180, 140, 22), 0),
                ((40, 120, 200, 18), 40),
                ((80, 60,  220, 14), 80),
            ]):
                wave_off = int(20 * math.sin(now * 0.0006 + i * 2.0))
                asurf = pygame.Surface((WINDOW_WIDTH, 60), pygame.SRCALPHA)
                pygame.draw.ellipse(asurf, col, (0, 0, WINDOW_WIDTH, 60))
                self.screen.blit(asurf, (0, oy + wave_off))
            # falling crystal shards
            rng_c = random.Random(44)
            for i in range(20):
                fx = int((rng_c.randint(0, WINDOW_WIDTH) - self.camera_x * 0.02) % WINDOW_WIDTH)
                fy = int((rng_c.randint(0, ground_y) + now // 6 + i * 77) % ground_y)
                alpha = int(60 + 40 * abs(math.sin(now * 0.002 + i)))
                cf = pygame.Surface((4, 10), pygame.SRCALPHA)
                pygame.draw.polygon(cf, (100, 200, 255, alpha), [(2, 0), (4, 5), (2, 10), (0, 5)])
                self.screen.blit(cf, (fx, fy))

        # ── Far mountains / structures (0.13x parallax) ───────────────────────
        for (mx, mh, mw) in self._bg_data["mountains"]:
            dx = int(mx - self.camera_x * 0.13)
            if dx + mw < 0 or dx > WINDOW_WIDTH:
                continue
            peak_x = dx + mw // 2
            base_y = ground_y + 5
            peak_y = base_y - mh
            # mountain color by zone
            if zone_idx == 3:
                mcol = (30, 14, 8)
                cap_col = (60, 25, 12)
            elif zone_idx == 4:
                mcol = (14, 28, 52)
                cap_col = (28, 70, 110)
            elif zone_idx == 2:
                mcol = (32, 24, 10)
                cap_col = (60, 46, 18)
            else:
                mcol = (20, 28, 56)
                cap_col = (42, 52, 84)
            pygame.draw.polygon(self.screen, mcol,
                                [(dx, base_y), (peak_x, peak_y), (dx + mw, base_y)])
            cap = mh // 5
            pygame.draw.polygon(self.screen, cap_col, [
                (peak_x, peak_y),
                (peak_x - cap, peak_y + cap),
                (peak_x + cap, peak_y + cap),
            ])

        # ── Mid hills (0.27x parallax) ─────────────────────────────────────────
        for (hx, hh, hw) in self._bg_data["hills"]:
            dx = int(hx - self.camera_x * 0.27)
            if dx + hw < 0 or dx > WINDOW_WIDTH:
                continue
            if zone_idx == 3:
                hcol = (20, 10, 6)
            elif zone_idx == 4:
                hcol = (10, 22, 42)
            elif zone_idx == 2:
                hcol = (28, 22, 10)
            else:
                hcol = (25, 44, 30)
            pygame.draw.ellipse(self.screen, hcol, (dx, ground_y - hh, hw, hh + 16))

        # ── Background structures (0.35x parallax) ────────────────────────────
        for item in self._bg_data.get("bg_structures", []):
            wx, stype, sw, sh = item
            dx = int(wx - self.camera_x * 0.35)
            if dx + sw < 0 or dx > WINDOW_WIDTH:
                continue
            base_y = ground_y
            if stype == "tower":
                col = (28, 22, 10) if zone_idx == 2 else (22, 28, 18)
                pygame.draw.rect(self.screen, col, (dx, base_y - sh, sw, sh))
                # battlements
                for bi in range(sw // 14):
                    pygame.draw.rect(self.screen, col,
                                     (dx + bi * 14, base_y - sh - 10, 8, 10))
                # window
                pygame.draw.rect(self.screen, (40, 60, 90),
                                 (dx + sw // 2 - 4, base_y - sh + sh // 3, 8, 12))
            elif stype == "arch":
                col = (32, 26, 12)
                # two pillars
                pygame.draw.rect(self.screen, col, (dx, base_y - sh, 18, sh))
                pygame.draw.rect(self.screen, col, (dx + sw - 18, base_y - sh, 18, sh))
                # arch top
                pygame.draw.rect(self.screen, col, (dx, base_y - sh, sw, 18))
            elif stype == "obelisk":
                col = (36, 28, 14)
                pygame.draw.polygon(self.screen, col, [
                    (dx + sw // 2, base_y - sh),
                    (dx, base_y - sh // 4),
                    (dx + sw, base_y - sh // 4),
                ])
                pygame.draw.rect(self.screen, col, (dx, base_y - sh // 4, sw, sh // 4))
            elif stype == "dead_tree":
                col = (16, 20, 14)
                trunk_w = max(4, sw // 4)
                pygame.draw.rect(self.screen, col,
                                 (dx + sw // 2 - trunk_w // 2, base_y - sh, trunk_w, sh))
                # branches
                for blen, bangle in [(sw // 2, -40), (sw // 2, 40), (sw // 3, -60)]:
                    brad = math.radians(bangle - 90)
                    bx2 = dx + sw // 2 + int(math.cos(brad) * blen)
                    by2 = base_y - sh // 2 + int(math.sin(brad) * blen)
                    pygame.draw.line(self.screen, col,
                                     (dx + sw // 2, base_y - sh // 2),
                                     (bx2, by2), max(2, trunk_w // 2))
            elif stype == "stalactite_bg":
                # giant bg stalactite hanging from top (crystal zone)
                col = (12, 35, 65)
                pygame.draw.polygon(self.screen, col, [
                    (dx, 0), (dx + sw, 0), (dx + sw // 2, sh)
                ])
                # glow edge
                pg = pygame.Surface((sw, sh), pygame.SRCALPHA)
                pygame.draw.polygon(pg, (40, 100, 180, 30), [
                    (0, 0), (sw, 0), (sw // 2, sh)
                ])
                self.screen.blit(pg, (dx, 0))

        # ── Silhouette trees (0.44x parallax) ────────────────────────────────
        for (tx, th) in self._bg_data["trees"]:
            dx = int(tx - self.camera_x * 0.44)
            if dx < -th - 10 or dx > WINDOW_WIDTH + th:
                continue
            if zone_idx == 3:  # volcanic — dead/burnt trees
                trunk_h = int(th * 0.7)
                pygame.draw.rect(self.screen, (16, 10, 6),
                                 (dx - 4, ground_y - trunk_h, 8, trunk_h))
                # charred bare branches
                for blen, bang in [(th // 3, -50), (th // 3, 40), (th // 4, -70)]:
                    brad = math.radians(bang - 90)
                    pygame.draw.line(self.screen, (16, 10, 6),
                                     (dx, ground_y - trunk_h // 2),
                                     (dx + int(math.cos(brad) * blen),
                                      ground_y - trunk_h // 2 + int(math.sin(brad) * blen)), 2)
            elif zone_idx == 4:  # crystal — crystal pillars
                trunk_h = th
                pw = max(6, th // 8)
                pygame.draw.rect(self.screen, (14, 38, 68),
                                 (dx - pw // 2, ground_y - trunk_h, pw, trunk_h))
                pygame.draw.polygon(self.screen, (20, 60, 100), [
                    (dx - pw // 2, ground_y - trunk_h),
                    (dx + pw // 2, ground_y - trunk_h),
                    (dx, ground_y - trunk_h - th // 4),
                ])
            else:
                trunk_h = th // 3
                trunk_w = 7
                pygame.draw.rect(self.screen, (18, 28, 16),
                                 (dx - trunk_w // 2, ground_y - trunk_h, trunk_w, trunk_h))
                r = th // 4
                for off_x, off_y in [(0, -r), (-r * 3 // 4, -r * 5 // 8), (r * 3 // 4, -r * 5 // 8)]:
                    pygame.draw.circle(self.screen, (22, 50, 24),
                                       (dx + off_x, ground_y - trunk_h + off_y), r)

        # ── Horizon glow line ──────────────────────────────────────────────────
        if zone_idx == 3:
            hcol = (180, 60, 10, 28)
        elif zone_idx == 4:
            hcol = (30, 80, 160, 22)
        elif zone_idx == 2:
            hcol = (180, 110, 20, 25)
        else:
            hcol = (60, 90, 110, 22)
        for i in range(12):
            alpha = int((1 - i / 12) * hcol[3])
            hs = pygame.Surface((WINDOW_WIDTH, 1), pygame.SRCALPHA)
            hs.fill((*hcol[:3], alpha))
            self.screen.blit(hs, (0, ground_y - i - 1))

    # ══════════════════════════════════════════════════════════════════════════
    #  World drawing
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_world(self) -> None:
        now = pygame.time.get_ticks()

        # ── Pits ──────────────────────────────────────────────────────────────
        for pit in self.pits:
            dp = pit.move(-self.camera_x, 0)
            if dp.right < 0 or dp.left > WINDOW_WIDTH:
                continue
            # Void abyss fill
            pygame.draw.rect(self.screen, (5, 6, 14), dp)
            # Depth lines fading into darkness
            for d in range(5):
                alpha_val = max(0, 50 - d * 10)
                depth_surf = pygame.Surface((dp.width, 1), pygame.SRCALPHA)
                depth_surf.fill((12, 18, 50, alpha_val))
                self.screen.blit(depth_surf, (dp.left, dp.top + 6 + d * 6))
            # Danger rim glow (blue-purple)
            rim = pygame.Surface((dp.width, 3), pygame.SRCALPHA)
            rim.fill((40, 60, 200, 90))
            self.screen.blit(rim, (dp.left, dp.top))
            rim2 = pygame.Surface((dp.width, 1), pygame.SRCALPHA)
            rim2.fill((80, 120, 255, 50))
            self.screen.blit(rim2, (dp.left, dp.top + 3))
            # Animated falling sparkles inside pit
            rng_seed = pit.left
            for s in range(4):
                sx = dp.left + ((rng_seed * 37 + s * 83) % max(1, dp.width))
                fall_period = 1800 + s * 400
                sy = dp.top + 5 + ((now // 4 + s * 300) % max(1, dp.height - 5))
                spark_surf = pygame.Surface((3, 3), pygame.SRCALPHA)
                spark_surf.fill((50, 80, 220, 80))
                self.screen.blit(spark_surf, (sx, sy))
            # Side wall lines
            wall_surf = pygame.Surface((2, dp.height), pygame.SRCALPHA)
            wall_surf.fill((25, 40, 140, 70))
            self.screen.blit(wall_surf, (dp.left, dp.top))
            self.screen.blit(wall_surf, (dp.right - 2, dp.top))

        # ── Ground segments ───────────────────────────────────────────────────
        for seg_idx, block in enumerate(self.ground_segments):
            db = block.move(-self.camera_x, 0)
            if db.right < 0 or db.left > WINDOW_WIDTH:
                continue
            style = self._ground_styles[seg_idx] if seg_idx < len(self._ground_styles) else "grass"
            self._draw_ground_segment(db, style, now, block.left)

        # ── Floating platforms ────────────────────────────────────────────────
        plat_style_idx = 0
        for i, block in enumerate(self.platforms):
            if block.height >= GROUND_HEIGHT:
                continue
            db = block.move(-self.camera_x, 0)
            if db.right < 0 or db.left > WINDOW_WIDTH:
                plat_style_idx += 1
                continue
            style = self._platform_styles.get(i, "log")
            self._draw_platform(db, style, now, block.left)
            plat_style_idx += 1

        # ── Foreground obstacles ───────────────────────────────────────────────
        for idx, obs in enumerate(getattr(self, "_obstacle_rects", [])):
            dob = obs.move(-self.camera_x, 0)
            if dob.right < 0 or dob.left > WINDOW_WIDTH:
                continue
            style = getattr(self, "_obstacle_styles", {}).get(idx, "wall")
            self._draw_obstacle(dob, style, now, obs.left)

    def _draw_ground_segment(self, db: pygame.Rect, style: str, now: int, world_x: int) -> None:
        """Draw a ground segment with a specific visual style."""
        rng = random.Random(world_x + 9999)  # stable seed based on world position

        if style == "grass":
            # ── Rich grass ground ──────────────────────────────────────────
            pygame.draw.rect(self.screen, (24, 40, 14), db, border_radius=2)
            # Sub layers
            sub = pygame.Rect(db.left, db.top + 14, db.width, db.height - 14)
            pygame.draw.rect(self.screen, (18, 30, 10), sub)
            # Stone pebble texture
            for _ in range(db.width // 28):
                px = db.left + rng.randint(8, max(9, db.width - 8))
                py = db.top + rng.randint(20, db.height - 6)
                pr = rng.randint(3, 7)
                pebble_surf = pygame.Surface((pr * 2, pr), pygame.SRCALPHA)
                pygame.draw.ellipse(pebble_surf, (30, 48, 18, 120), (0, 0, pr * 2, pr))
                self.screen.blit(pebble_surf, (px - pr, py - pr // 2))
            # Root lines
            for _ in range(db.width // 45):
                rx1 = db.left + rng.randint(10, max(11, db.width - 10))
                ry1 = db.top + 18
                rx2 = rx1 + rng.randint(-12, 12)
                ry2 = db.top + rng.randint(32, db.height - 4)
                root_surf = pygame.Surface((abs(rx2 - rx1) + 2, abs(ry2 - ry1) + 2), pygame.SRCALPHA)
                pygame.draw.line(root_surf, (20, 36, 10, 100), (0, 0), (root_surf.get_width() - 1, root_surf.get_height() - 1), 1)
                self.screen.blit(root_surf, (min(rx1, rx2), min(ry1, ry2)))
            # Grass top strip
            pygame.draw.rect(self.screen, (52, 100, 36), pygame.Rect(db.left, db.top, db.width, 13))
            # Bright rim
            rim_surf = pygame.Surface((db.width, 3), pygame.SRCALPHA)
            rim_surf.fill((100, 185, 60, 200))
            self.screen.blit(rim_surf, (db.left, db.top))
            # Grass blades
            blade_count = db.width // 9
            for b in range(blade_count):
                bx = db.left + b * 9 + rng.randint(-2, 2)
                lean = rng.randint(-3, 3)
                blade_h = rng.randint(5, 10)
                col = rng.choice([(110, 200, 60), (85, 170, 45), (130, 220, 70)])
                bsurf = pygame.Surface((4, blade_h + 2), pygame.SRCALPHA)
                pygame.draw.line(bsurf, (*col, 220), (2, blade_h), (2 + lean, 0), 1)
                self.screen.blit(bsurf, (bx, db.top - blade_h + 1))
            # Sub-surface dark band
            band = pygame.Surface((db.width, 2), pygame.SRCALPHA)
            band.fill((35, 55, 20, 180))
            self.screen.blit(band, (db.left, db.top + 13))
            # Left edge shadow
            edge = pygame.Surface((2, db.height), pygame.SRCALPHA)
            edge.fill((10, 18, 6, 140))
            self.screen.blit(edge, (db.left, db.top + 14))

        elif style == "mossy":
            # ── Mossy stone blocks ─────────────────────────────────────────
            pygame.draw.rect(self.screen, (26, 36, 18), db, border_radius=2)
            # Draw stone block grid
            block_h = 30
            for row_y in range(db.top, db.bottom, block_h):
                offset = block_h if (row_y // block_h) % 2 else 0
                block_w = rng.randint(55, 85)
                bx = db.left - offset
                while bx < db.right:
                    bw = min(block_w, db.right - bx)
                    bh = min(block_h, db.bottom - row_y)
                    if bw > 4 and bh > 4:
                        shade = rng.randint(-6, 6)
                        col = (42 + shade, 56 + shade, 32 + shade)
                        pygame.draw.rect(self.screen, col, (bx + 1, row_y + 1, bw - 2, bh - 2))
                        # crack lines inside block
                        if rng.random() < 0.4:
                            cx1 = bx + rng.randint(4, max(5, bw - 4))
                            crack_surf = pygame.Surface((2, bh - 4), pygame.SRCALPHA)
                            crack_surf.fill((18, 26, 10, 80))
                            self.screen.blit(crack_surf, (cx1, row_y + 2))
                    bx += block_w
                    block_w = rng.randint(55, 85)
            # Mortar grid overlay
            for row_y in range(db.top, db.bottom, block_h):
                mortar = pygame.Surface((db.width, 1), pygame.SRCALPHA)
                mortar.fill((14, 20, 8, 160))
                self.screen.blit(mortar, (db.left, row_y))
            # Moss patches on top
            moss_count = db.width // 18
            for m in range(moss_count):
                mx = db.left + m * 18 + rng.randint(0, 12)
                mw = rng.randint(10, 22)
                mh = rng.randint(3, 6)
                mcol = rng.choice([(68, 120, 45), (55, 100, 35), (80, 140, 50)])
                mp_surf = pygame.Surface((mw, mh), pygame.SRCALPHA)
                pygame.draw.ellipse(mp_surf, (*mcol, 200), (0, 0, mw, mh))
                self.screen.blit(mp_surf, (mx, db.top - mh // 2))
            # Bright moss rim
            rim = pygame.Surface((db.width, 2), pygame.SRCALPHA)
            rim.fill((95, 175, 55, 180))
            self.screen.blit(rim, (db.left, db.top))
            # Blade tips from moss
            for m in range(db.width // 14):
                bx = db.left + m * 14 + rng.randint(-3, 3)
                bh = rng.randint(3, 7)
                lean = rng.randint(-2, 2)
                bsurf = pygame.Surface((3, bh + 1), pygame.SRCALPHA)
                pygame.draw.line(bsurf, (90, 170, 50, 180), (1, bh), (1 + lean, 0), 1)
                self.screen.blit(bsurf, (bx, db.top - bh))

        elif style == "ancient":
            # ── Ancient carved stone ruins ─────────────────────────────────
            pygame.draw.rect(self.screen, (48, 32, 18), db, border_radius=2)
            block_h = 28
            for row_y in range(db.top, db.bottom, block_h):
                offset = 40 if (row_y // block_h) % 2 else 0
                block_w = rng.randint(60, 90)
                bx = db.left - offset
                while bx < db.right:
                    bw = min(block_w, db.right - bx)
                    bh = min(block_h, db.bottom - row_y)
                    if bw > 4 and bh > 4:
                        shade = rng.randint(-5, 5)
                        col = (75 + shade, 52 + shade, 28 + shade)
                        pygame.draw.rect(self.screen, col, (bx + 1, row_y + 1, bw - 2, bh - 2))
                        # Carved symbol (rare)
                        if rng.random() < 0.15 and bw > 24 and bh > 16:
                            sym_surf = pygame.Surface((8, 8), pygame.SRCALPHA)
                            pygame.draw.line(sym_surf, (130, 95, 50, 130), (4, 0), (4, 7), 1)
                            pygame.draw.line(sym_surf, (130, 95, 50, 130), (0, 4), (7, 4), 1)
                            self.screen.blit(sym_surf, (bx + bw // 2 - 4, row_y + bh // 2 - 4))
                    bx += block_w
                    block_w = rng.randint(60, 90)
            for row_y in range(db.top, db.bottom, block_h):
                m = pygame.Surface((db.width, 1), pygame.SRCALPHA)
                m.fill((28, 18, 8, 160))
                self.screen.blit(m, (db.left, row_y))
            # Golden top edge
            gold = pygame.Surface((db.width, 4), pygame.SRCALPHA)
            gold.fill((130, 90, 40, 220))
            self.screen.blit(gold, (db.left, db.top))
            bright_gold = pygame.Surface((db.width, 2), pygame.SRCALPHA)
            bright_gold.fill((200, 155, 70, 200))
            self.screen.blit(bright_gold, (db.left, db.top))
            # Vine creep on right edge
            for v in range(3):
                vx = db.right - 4 - v * 14
                if vx < db.left:
                    break
                vine_len = rng.randint(20, 45)
                for vy in range(vine_len):
                    vs = pygame.Surface((2, 2), pygame.SRCALPHA)
                    vs.fill((60, 130, 35, 180 - vy * 3))
                    self.screen.blit(vs, (vx + (1 if vy % 4 > 1 else 0), db.top + vy))

        elif style == "volcanic":
            # ── Dark volcanic obsidian ─────────────────────────────────────
            pygame.draw.rect(self.screen, (14, 8, 6), db, border_radius=2)
            # Obsidian block grid
            block_h = 26
            for row_y in range(db.top, db.bottom, block_h):
                block_w = rng.randint(50, 80)
                bx = db.left
                while bx < db.right:
                    bw = min(block_w, db.right - bx)
                    bh = min(block_h, db.bottom - row_y)
                    if bw > 4 and bh > 4:
                        shade = rng.randint(-4, 4)
                        col = (22 + shade, 14 + shade, 10 + shade)
                        pygame.draw.rect(self.screen, col, (bx + 1, row_y + 1, bw - 2, bh - 2))
                        # Lava crack inside block (rare)
                        if rng.random() < 0.25:
                            cx1 = bx + rng.randint(3, max(4, bw - 3))
                            cy1 = row_y + 3
                            cy2 = row_y + bh - 3
                            crack = pygame.Surface((2, cy2 - cy1), pygame.SRCALPHA)
                            crack.fill((180, 60, 10, 80))
                            self.screen.blit(crack, (cx1, cy1))
                    bx += block_w
                    block_w = rng.randint(50, 80)
            for row_y in range(db.top, db.bottom, block_h):
                m = pygame.Surface((db.width, 1), pygame.SRCALPHA)
                m.fill((6, 4, 3, 200))
                self.screen.blit(m, (db.left, row_y))
            # Lava top glow line
            lava_rim = pygame.Surface((db.width, 3), pygame.SRCALPHA)
            lava_rim.fill((200, 70, 10, 200))
            self.screen.blit(lava_rim, (db.left, db.top))
            lava_bright = pygame.Surface((db.width, 1), pygame.SRCALPHA)
            lava_bright.fill((255, 140, 40, 160))
            self.screen.blit(lava_bright, (db.left, db.top))
            # Lava crack paths on surface
            for _ in range(db.width // 80):
                cx = db.left + rng.randint(10, max(11, db.width - 10))
                cy = db.top + 5
                for step in range(rng.randint(8, 16)):
                    nx = cx + rng.randint(-3, 3)
                    ny = cy + rng.randint(3, 8)
                    lc = pygame.Surface((abs(nx - cx) + 2, abs(ny - cy) + 2), pygame.SRCALPHA)
                    alpha = max(0, 140 - step * 8)
                    pygame.draw.line(lc, (180, 60, 10, alpha), (0, 0), (lc.get_width() - 1, lc.get_height() - 1), 1)
                    self.screen.blit(lc, (min(cx, nx), min(cy, ny)))
                    cx, cy = nx, ny
            # Ember glow dots on rim
            for e in range(db.width // 30):
                ex = db.left + e * 30 + rng.randint(-8, 8)
                flicker = math.sin(now * 0.007 + e * 1.3)
                ea = int(100 + 60 * flicker)
                ember = pygame.Surface((3, 3), pygame.SRCALPHA)
                ember.fill((255, 120, 20, max(0, ea)))
                self.screen.blit(ember, (ex, db.top - 1))

        else:  # crystal cave — zone 5
            # ── Deep crystal cavern ground ─────────────────────────────────
            pygame.draw.rect(self.screen, (8, 18, 34), db, border_radius=2)
            # Ice-blue sub-layers
            sub1 = pygame.Rect(db.left, db.top + 16, db.width, db.height - 16)
            pygame.draw.rect(self.screen, (6, 14, 26), sub1)
            # Crystal vein patterns (glowing lines)
            for _ in range(db.width // 50):
                cx = db.left + rng.randint(10, max(11, db.width - 10))
                pts = [(cx, db.top + 12)]
                y = db.top + 12
                while y < db.bottom - 4:
                    cx += rng.randint(-8, 8)
                    y += rng.randint(10, 20)
                    pts.append((cx, min(y, db.bottom - 4)))
                if len(pts) > 1:
                    pulse = 0.4 + 0.6 * abs(math.sin(now * 0.0015 + db.left * 0.002))
                    vein_col = (
                        int(30 + 30 * pulse),
                        int(100 + 80 * pulse),
                        int(180 + 50 * pulse),
                    )
                    pygame.draw.lines(self.screen, vein_col, False, pts, 1)
            # Glowing crystal surface
            pygame.draw.rect(self.screen, (18, 52, 90),
                             pygame.Rect(db.left, db.top, db.width, 10))
            pygame.draw.rect(self.screen, (34, 100, 165),
                             pygame.Rect(db.left, db.top, db.width, 3))
            # Crystal spikes along top
            spike_rng = random.Random(db.left + 99)
            kx = db.left + spike_rng.randint(6, 16)
            while kx < db.right - 8:
                kh = spike_rng.randint(8, 22)
                kw = spike_rng.randint(5, 10)
                col = spike_rng.choice([(30, 90, 155), (45, 120, 185), (22, 75, 135)])
                pygame.draw.polygon(self.screen, col, [
                    (kx - kw // 2, db.top),
                    (kx + kw // 2, db.top),
                    (kx, db.top - kh),
                ])
                # Spike highlight
                pygame.draw.line(self.screen, (110, 205, 255),
                                 (kx, db.top - kh), (kx + 1, db.top - kh + 4), 1)
                kx += spike_rng.randint(20, 38)
            # Animated glow pools on surface
            glow_rng = random.Random(db.left + 123)
            for gx in range(db.left + 24, db.right - 24, glow_rng.randint(55, 90)):
                pulse = 0.35 + 0.65 * abs(math.sin(now * 0.0018 + gx * 0.025))
                gs = pygame.Surface((28, 10), pygame.SRCALPHA)
                pygame.draw.ellipse(gs, (38, 130, 220, int(100 * pulse)), (0, 0, 28, 10))
                self.screen.blit(gs, (gx - 14, db.top + 2))
            # Stalactite drips from ceiling (bottom edge of ground)
            drip_rng = random.Random(db.left + 55)
            for dx in range(db.left + 18, db.right - 18, drip_rng.randint(30, 52)):
                dh = drip_rng.randint(14, 32)
                dw = drip_rng.randint(4, 8)
                pygame.draw.polygon(self.screen, (10, 32, 60), [
                    (dx - dw // 2, db.bottom - 4),
                    (dx + dw // 2, db.bottom - 4),
                    (dx, db.bottom - 4 + dh),
                ])

    def _draw_obstacle(self, db: pygame.Rect, style: str, now: int, world_x: int) -> None:
        """Draw a foreground collidable obstacle."""
        rng = random.Random(world_x + 3333)
        ground_y = WINDOW_HEIGHT - GROUND_HEIGHT

        if style == "wall":
            # Mossy stone wall
            pygame.draw.rect(self.screen, (55, 72, 42), db, border_radius=3)
            # brick rows
            bh = 14
            for row_y in range(db.top, db.bottom, bh):
                offset = 10 if (row_y // bh) % 2 else 0
                bw = rng.randint(24, 36)
                bx = db.left - offset
                while bx < db.right:
                    bw2 = min(bw, db.right - bx)
                    bh2 = min(bh, db.bottom - row_y)
                    if bw2 > 3 and bh2 > 3:
                        shade = rng.randint(-8, 8)
                        pygame.draw.rect(self.screen,
                                         (62 + shade, 80 + shade, 48 + shade),
                                         (bx + 1, row_y + 1, bw2 - 2, bh2 - 2))
                    bx += bw
                    bw = rng.randint(24, 36)
            # moss cap
            pygame.draw.rect(self.screen, (50, 100, 35),
                             (db.left, db.top, db.width, 5), border_radius=2)
            pygame.draw.rect(self.screen, (70, 140, 48),
                             (db.left, db.top, db.width, 2), border_radius=2)
            # top crumble detail
            for ci in range(db.width // 10):
                cx = db.left + ci * 10 + rng.randint(0, 6)
                ch = rng.randint(2, 6)
                pygame.draw.rect(self.screen, (62, 80, 48), (cx, db.top - ch, 6, ch))
            # shadow
            pygame.draw.rect(self.screen, (20, 26, 14),
                             (db.left + 3, db.bottom, db.width - 3, 4), border_radius=2)

        elif style == "pillar":
            # Mossy stone pillar (taller, narrower)
            pygame.draw.rect(self.screen, (58, 74, 50), db, border_radius=4)
            # vertical stone rings
            for ry in range(db.top + 6, db.bottom, 18):
                rh = min(14, db.bottom - ry)
                pygame.draw.rect(self.screen, (66, 84, 56),
                                 (db.left + 1, ry, db.width - 2, rh), border_radius=2)
            # carved line down center
            pygame.draw.rect(self.screen, (42, 56, 36),
                             (db.centerx - 1, db.top + 4, 2, db.height - 8))
            # capital (top block)
            cap_h = 10
            pygame.draw.rect(self.screen, (72, 90, 58),
                             (db.left - 4, db.top, db.width + 8, cap_h), border_radius=3)
            # base
            pygame.draw.rect(self.screen, (72, 90, 58),
                             (db.left - 4, db.bottom - cap_h, db.width + 8, cap_h), border_radius=3)
            # moss drip
            pygame.draw.rect(self.screen, (55, 110, 40),
                             (db.left, db.top, db.width, 4), border_radius=2)
            # shadow
            shadow_s = pygame.Surface((db.width + 8, 5), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow_s, (0, 0, 0, 50), (0, 0, db.width + 8, 5))
            self.screen.blit(shadow_s, (db.left - 4, db.bottom + 1))

        elif style == "ancient":
            # Ancient stone gate pillar / monolith
            pygame.draw.rect(self.screen, (56, 46, 22), db, border_radius=3)
            # worn stone blocks
            bh = 20
            for row_y in range(db.top, db.bottom, bh):
                bh2 = min(bh, db.bottom - row_y)
                shade = rng.randint(-6, 6)
                pygame.draw.rect(self.screen, (64 + shade, 52 + shade, 24 + shade),
                                 (db.left + 1, row_y + 1, db.width - 2, bh2 - 2))
            # gold trim lines
            pygame.draw.rect(self.screen, (150, 120, 38),
                             (db.left, db.top, db.width, 3), border_radius=2)
            pygame.draw.rect(self.screen, (130, 100, 30),
                             (db.left, db.bottom - 6, db.width, 6), border_radius=2)
            # rune mark center
            rune = rng.choice(["ᚱ", "ᚠ", "✦", "ᛉ"])
            pulse = 0.6 + 0.4 * math.sin(now * 0.003 + world_x * 0.01)
            try:
                rs = self.small_font.render(rune, True, (180, 148, 48))
                rs.set_alpha(int(180 * pulse))
                self.screen.blit(rs, (db.centerx - rs.get_width() // 2,
                                      db.centery - rs.get_height() // 2))
            except Exception:
                pass
            # edge carvings
            for side_x in (db.left + 2, db.right - 5):
                pygame.draw.rect(self.screen, (150, 120, 38),
                                 (side_x, db.top + db.height // 3, 3, db.height // 8))
            # shadow
            pygame.draw.rect(self.screen, (24, 18, 6),
                             (db.left + 3, db.bottom, db.width - 3, 5), border_radius=2)

        elif style == "volcanic":
            # Volcanic obsidian rubble block
            pygame.draw.rect(self.screen, (26, 14, 8), db, border_radius=2)
            # rough facets
            for ri in range(3):
                ry = db.top + ri * (db.height // 3)
                rh = db.height // 3
                shade = rng.randint(-5, 5)
                pygame.draw.rect(self.screen, (30 + shade, 16 + shade, 10 + shade),
                                 (db.left + 1, ry + 1, db.width - 2, rh - 2))
            # lava crack
            pts = [(db.left + rng.randint(3, db.width - 3), db.top + 4)]
            y = db.top + 4
            while y < db.bottom - 4:
                pts.append((db.left + rng.randint(2, db.width - 2), y))
                y += rng.randint(10, 20)
            if len(pts) > 1:
                pulse = 0.5 + 0.5 * math.sin(now * 0.005 + world_x * 0.008)
                lava_col = (min(255, int(180 + 60 * pulse)), int(40 + 20 * pulse), 8)
                pygame.draw.lines(self.screen, lava_col, False, pts, 1)
            # ember on top
            ec = pygame.Surface((db.width, 4), pygame.SRCALPHA)
            ep = 0.4 + 0.6 * abs(math.sin(now * 0.006 + world_x * 0.01))
            pygame.draw.rect(ec, (220, 70, 10, int(80 * ep)), (0, 0, db.width, 4), border_radius=2)
            self.screen.blit(ec, (db.left, db.top))

        else:  # crystal
            # Crystal spire / pillar
            pygame.draw.rect(self.screen, (22, 72, 120), db, border_radius=4)
            # inner glow
            pygame.draw.rect(self.screen, (30, 100, 165),
                             (db.left + 2, db.top + 4, db.width - 4, db.height - 8),
                             border_radius=3)
            # shimmer line
            shimmer_y = int((now // 6) % db.height) + db.top
            if db.top < shimmer_y < db.bottom:
                sl = pygame.Surface((db.width - 4, 3), pygame.SRCALPHA)
                sl.fill((160, 230, 255, 60))
                self.screen.blit(sl, (db.left + 2, shimmer_y))
            # crystal tip (spike at top)
            tip_w = db.width + 8
            tip_h = 20
            pygame.draw.polygon(self.screen, (28, 90, 150), [
                (db.left - 4, db.top),
                (db.right + 4, db.top),
                (db.centerx, db.top - tip_h),
            ])
            pygame.draw.line(self.screen, (140, 220, 255),
                             (db.centerx, db.top - tip_h),
                             (db.centerx + 1, db.top - tip_h + 6), 1)
            # glow aura
            pulse = 0.4 + 0.6 * abs(math.sin(now * 0.002 + world_x * 0.01))
            ga = pygame.Surface((db.width + 16, db.height + 16), pygame.SRCALPHA)
            pygame.draw.rect(ga, (30, 100, 200, int(30 * pulse)),
                             (0, 0, db.width + 16, db.height + 16), border_radius=6)
            self.screen.blit(ga, (db.left - 8, db.top - 8))

    def _draw_platform(self, db: pygame.Rect, style: str, now: int, world_x: int) -> None:
        """Draw a floating platform with a specific visual style."""
        rng = random.Random(world_x + 7777)
        # Drop shadow
        shadow = pygame.Surface((db.width + 4, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 55), (0, 0, db.width + 4, 6))
        self.screen.blit(shadow, (db.left - 2, db.bottom + 3))

        if style == "log":
            # ── Mossy log ──────────────────────────────────────────────────
            pygame.draw.rect(self.screen, (60, 38, 18), db, border_radius=7)
            # Wood grain ellipses (cross-section hint on sides)
            end_r = db.height // 2 - 1
            if end_r > 2:
                for ex, flip in [(db.left + end_r + 1, 1), (db.right - end_r - 1, -1)]:
                    ring = pygame.Surface((end_r * 2, db.height - 2), pygame.SRCALPHA)
                    pygame.draw.ellipse(ring, (50, 32, 14, 100), (0, 0, end_r * 2, db.height - 2), 1)
                    pygame.draw.ellipse(ring, (45, 28, 12, 60), (3, 2, end_r * 2 - 6, db.height - 6), 1)
                    self.screen.blit(ring, (ex - end_r, db.top + 1))
            # Bark grain lines
            for g in range(4):
                gx = db.left + db.width * (g + 1) // 5
                gline = pygame.Surface((1, db.height - 4), pygame.SRCALPHA)
                gline.fill((42, 26, 10, 70))
                self.screen.blit(gline, (gx, db.top + 2))
            # Moss top
            pygame.draw.rect(self.screen, (52, 95, 35), pygame.Rect(db.left + 3, db.top, db.width - 6, 7), border_radius=4)
            # Bright rim
            rim = pygame.Surface((db.width, 2), pygame.SRCALPHA)
            rim.fill((105, 200, 55, 220))
            self.screen.blit(rim, (db.left, db.top))
            # Moss tufts
            tuft_count = db.width // 16
            for t in range(tuft_count):
                tx = db.left + t * 16 + rng.randint(0, 10)
                tw = rng.randint(8, 16)
                th = rng.randint(3, 6)
                tc = rng.choice([(72, 145, 42), (58, 118, 32), (88, 165, 50)])
                tf = pygame.Surface((tw, th), pygame.SRCALPHA)
                pygame.draw.ellipse(tf, (*tc, 200), (0, 0, tw, th))
                self.screen.blit(tf, (tx, db.top - th // 2 - 1))
            # Dangling root tendrils
            for r in range(3):
                rx = db.left + (r + 1) * db.width // 4
                rl = rng.randint(6, 14)
                root = pygame.Surface((3, rl), pygame.SRCALPHA)
                for ry in range(rl):
                    root.set_at((1, ry), (50, 30, 12, max(0, 180 - ry * 12)))
                self.screen.blit(root, (rx, db.bottom))

        elif style == "stone":
            # ── Carved rune stone ──────────────────────────────────────────
            pygame.draw.rect(self.screen, (58, 68, 48), db, border_radius=3)
            # Top lighter face
            pygame.draw.rect(self.screen, (72, 84, 58), pygame.Rect(db.left, db.top, db.width, db.height // 2 + 2), border_radius=3)
            # Chiseled side shadow
            side = pygame.Surface((3, db.height), pygame.SRCALPHA)
            side.fill((30, 36, 22, 140))
            self.screen.blit(side, (db.right - 3, db.top))
            # Top shine
            shine = pygame.Surface((db.width - 6, 2), pygame.SRCALPHA)
            shine.fill((110, 130, 82, 200))
            self.screen.blit(shine, (db.left + 3, db.top + 1))
            # Rune glyphs
            rune_chars = ["ᚱ", "ᚢ", "ᚾ", "ᛖ", "ᛊ", "ᚦ", "ᚨ"]
            glyph_surf = pygame.font.SysFont("monospace", 10).render(
                "  ".join(rng.choice(rune_chars) for _ in range(min(5, db.width // 18))),
                True, (145, 165, 100)
            )
            glyph_surf.set_alpha(140)
            gx = db.left + db.width // 2 - glyph_surf.get_width() // 2
            gy = db.top + db.height // 2 - glyph_surf.get_height() // 2
            self.screen.blit(glyph_surf, (gx, gy))
            # Moss corners
            for mx_off, my_off in [(db.left + 3, db.top), (db.right - 12, db.top)]:
                msurf = pygame.Surface((12, 5), pygame.SRCALPHA)
                pygame.draw.ellipse(msurf, (65, 115, 40, 180), (0, 0, 12, 5))
                self.screen.blit(msurf, (mx_off, my_off - 2))

        elif style == "crystal":
            # ── Ice crystal platform ───────────────────────────────────────
            pygame.draw.rect(self.screen, (32, 90, 175), db, border_radius=4)
            # Inner shine layer
            inner = pygame.Surface((db.width - 4, db.height - 4), pygame.SRCALPHA)
            pygame.draw.rect(inner, (55, 130, 210, 180), (0, 0, db.width - 4, db.height - 4), border_radius=3)
            self.screen.blit(inner, (db.left + 2, db.top + 2))
            # Highlight strip
            hl = pygame.Surface((db.width - 8, 3), pygame.SRCALPHA)
            hl.fill((180, 230, 255, 120))
            self.screen.blit(hl, (db.left + 4, db.top + 2))
            # Frost top rim
            frost = pygame.Surface((db.width, 2), pygame.SRCALPHA)
            frost.fill((200, 240, 255, 230))
            self.screen.blit(frost, (db.left, db.top))
            # Crystal spikes
            spike_count = db.width // 18
            for s in range(spike_count):
                sx = db.left + s * 18 + 6
                sh = rng.randint(8, 16)
                sw = rng.randint(5, 8)
                col = rng.choice([(65, 150, 225), (80, 170, 240), (55, 130, 200)])
                pts = [(sx, db.top), (sx - sw // 2, db.top + sh), (sx + sw // 2, db.top + sh)]
                # shift spike up from top
                pts_shifted = [(px, py - sh) for px, py in pts]
                pygame.draw.polygon(self.screen, col, pts_shifted)
                # spike highlight
                hl2 = pygame.Surface((2, sh - 3), pygame.SRCALPHA)
                hl2.fill((200, 240, 255, 100))
                self.screen.blit(hl2, (sx - 1, db.top - sh + 1))
            # Drip drops underneath
            for d in range(db.width // 22):
                dx = db.left + d * 22 + rng.randint(4, 12)
                dl = rng.randint(4, 9)
                drip = pygame.Surface((3, dl), pygame.SRCALPHA)
                for dy in range(dl):
                    drip.set_at((1, dy), (80, 170, 240, max(0, 180 - dy * 22)))
                self.screen.blit(drip, (dx, db.bottom))

        elif style == "mushroom":
            # ── Mushroom cap platform ──────────────────────────────────────
            cap_w = db.width + 14
            cap_h = db.height + 10
            cap_surf = pygame.Surface((cap_w, cap_h), pygame.SRCALPHA)
            # Cap body (ellipse)
            pygame.draw.ellipse(cap_surf, (185, 55, 80), (0, cap_h // 3, cap_w, cap_h * 2 // 3))
            pygame.draw.ellipse(cap_surf, (210, 70, 95), (0, 0, cap_w, cap_h * 3 // 4))
            # Spots
            spot_positions = [(cap_w // 5, cap_h // 3), (cap_w * 2 // 5, cap_h // 5),
                              (cap_w * 3 // 5, cap_h // 3), (cap_w * 4 // 5, cap_h // 4)]
            for spx, spy in spot_positions:
                sr = rng.randint(4, 7)
                pygame.draw.ellipse(cap_surf, (240, 210, 215, 200), (spx - sr, spy - sr // 2, sr * 2, int(sr * 1.3)))
            # Gill shadow underside
            pygame.draw.ellipse(cap_surf, (110, 28, 50, 130), (3, cap_h // 2, cap_w - 6, cap_h // 2))
            # Walkable top rim glow
            pygame.draw.ellipse(cap_surf, (240, 90, 130, 80), (2, 1, cap_w - 4, cap_h // 3))
            self.screen.blit(cap_surf, (db.left - 7, db.top - 8))
            # Top walk line
            walk = pygame.Surface((db.width + 2, 2), pygame.SRCALPHA)
            walk.fill((240, 100, 150, 160))
            self.screen.blit(walk, (db.left - 1, db.top))
            # Falling spore drops
            for s in range(3):
                sx = db.left + (s + 1) * db.width // 4
                sf = (now // 600 + s) % 3
                sy = db.bottom + sf * 5
                spore = pygame.Surface((3, 3), pygame.SRCALPHA)
                spore.fill((200, 60, 100, 120))
                self.screen.blit(spore, (sx, sy))

        elif style == "ancient":
            # ── Ancient carved slab ────────────────────────────────────────
            pygame.draw.rect(self.screen, (85, 62, 38), db, border_radius=2)
            # Top face lighter
            pygame.draw.rect(self.screen, (105, 78, 48), pygame.Rect(db.left, db.top, db.width, db.height // 2 + 1), border_radius=2)
            # Chiseled lines
            for cx in range(db.left + 12, db.right - 8, 20):
                cl = pygame.Surface((1, db.height - 4), pygame.SRCALPHA)
                cl.fill((55, 38, 22, 80))
                self.screen.blit(cl, (cx, db.top + 2))
            # Golden top edge
            gold = pygame.Surface((db.width, 3), pygame.SRCALPHA)
            gold.fill((170, 120, 50, 220))
            self.screen.blit(gold, (db.left, db.top))
            gold_bright = pygame.Surface((db.width, 1), pygame.SRCALPHA)
            gold_bright.fill((220, 175, 80, 200))
            self.screen.blit(gold_bright, (db.left, db.top))
            # Worn edge underside
            worn = pygame.Surface((db.width - 4, 2), pygame.SRCALPHA)
            worn.fill((40, 28, 14, 150))
            self.screen.blit(worn, (db.left + 2, db.bottom - 2))

    # ══════════════════════════════════════════════════════════════════════════
    #  Ability VFX drawing
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_flamethrower_cone(self) -> None:
        cone_rect = self._get_flamethrower_rect().move(-self.camera_x, 0)
        now = pygame.time.get_ticks()

        # Animated wave offsets for organic flame shape
        wave  = math.sin(now * 0.018) * 9
        wave2 = math.sin(now * 0.027 + 1.2) * 6
        wave3 = math.sin(now * 0.041 + 2.5) * 4

        # ── Outermost halo ────────────────────────────────────────────────────
        gw, gh = cone_rect.width + 52, cone_rect.height + 52
        halo = pygame.Surface((gw, gh), pygame.SRCALPHA)
        pygame.draw.ellipse(halo, (255, 50, 0, 22), (0, 0, gw, gh))
        self.screen.blit(halo, (cone_rect.left - 26, cone_rect.top - 26))

        # ── Flame body (3 animated layers) ────────────────────────────────────
        r1 = cone_rect.inflate(int(wave), int(wave2))
        pygame.draw.ellipse(self.screen, (230, 70, 10), r1)

        r2 = cone_rect.inflate(-18 + int(wave2), -14 + int(wave3))
        if r2.width > 4 and r2.height > 4:
            pygame.draw.ellipse(self.screen, (255, 110, 20), r2)

        r3 = cone_rect.inflate(-32 + int(wave3), -24)
        if r3.width > 4 and r3.height > 4:
            pygame.draw.ellipse(self.screen, (255, 175, 50), r3)

        # ── Hot inner glow ────────────────────────────────────────────────────
        core = cone_rect.inflate(-50, -38).move(int(wave * 0.4), 0)
        if core.width > 4 and core.height > 4:
            pygame.draw.ellipse(self.screen, (255, 235, 140), core)

        # ── White-hot tip ─────────────────────────────────────────────────────
        tip = cone_rect.inflate(-68, -52).move(int(wave * 0.7), int(wave2 * 0.3))
        if tip.width > 2 and tip.height > 2:
            pygame.draw.ellipse(self.screen, (255, 255, 230), tip)

        # ── Emissive glow rim on player side ──────────────────────────────────
        rim_x = cone_rect.left if self.player.facing > 0 else cone_rect.right
        rim_surf = pygame.Surface((28, 28), pygame.SRCALPHA)
        pygame.draw.circle(rim_surf, (255, 130, 20, 80), (14, 14), 14)
        self.screen.blit(rim_surf, (rim_x - 14, cone_rect.centery - 14))

    def _draw_whirlwind_effect(self) -> None:
        now = pygame.time.get_ticks()
        if now > self._slash_until_ms:
            return

        progress = (self._slash_until_ms - now) / 160.0
        cx = self.player.rect.centerx - self.camera_x
        cy = self.player.rect.centery
        facing = self._slash_facing

        # ── Slash arc — sweeping forward in facing direction ───────────────────
        slash_w = int(SWORD_SLASH_LENGTH * (0.5 + 0.5 * progress))
        slash_h = SWORD_SLASH_HEIGHT

        # Draw 3 arc lines at different radii for depth
        for layer, (radius, color, width) in enumerate([
            (slash_h + 12, (255, 255, 255), 3),
            (slash_h,      (210, 220, 255), 2),
            (slash_h - 16, (170, 180, 255), 1),
        ]):
            if radius <= 0:
                continue
            # Arc sweeps from -50° to +50° around forward direction
            center_angle = 0.0 if facing > 0 else math.pi
            arc_surf_size = radius * 2 + 20
            arc_surf = pygame.Surface((arc_surf_size, arc_surf_size), pygame.SRCALPHA)
            arc_alpha = int(255 * progress)
            arc_color = (*color, arc_alpha)
            arc_rect = pygame.Rect(10, 10, (arc_surf_size - 20), (arc_surf_size - 20))
            span = math.radians(110)
            pygame.draw.arc(arc_surf, arc_color, arc_rect,
                            center_angle - span / 2, center_angle + span / 2, width)
            arc_blit_x = cx - arc_surf_size // 2 + int(facing * slash_w * 0.45)
            arc_blit_y = cy - arc_surf_size // 2
            self.screen.blit(arc_surf, (arc_blit_x, arc_blit_y))

        # ── Slash streak lines (3 bold lines forward) ─────────────────────────
        for offset_y in (-22, 0, 22):
            x1 = cx + facing * 12
            y1 = cy + offset_y
            x2 = cx + facing * int(slash_w * progress * 1.1)
            y2 = cy + offset_y + int(offset_y * 0.3)
            alpha_val = int(220 * progress)
            line_surf = pygame.Surface((abs(x2 - x1) + 4, abs(y2 - y1) + 4), pygame.SRCALPHA)
            color_line = (240, 245, 255, alpha_val)
            pygame.draw.line(line_surf, color_line,
                             (0 if facing > 0 else line_surf.get_width(), line_surf.get_height() // 2),
                             (line_surf.get_width() if facing > 0 else 0, line_surf.get_height() // 2),
                             2)
            self.screen.blit(line_surf, (min(x1, x2) - 2, y1 - 2))

        # ── Center flash at player ─────────────────────────────────────────────
        cf_r = int(18 * progress)
        if cf_r > 1:
            cf = pygame.Surface((cf_r * 2 + 4, cf_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(cf, (255, 255, 255, int(180 * progress)), (cf_r + 2, cf_r + 2), cf_r)
            self.screen.blit(cf, (cx - cf_r - 2, cy - cf_r - 2))

    def _draw_hover_glow(self) -> None:
        if not self.player.is_hovering:
            return
        now = pygame.time.get_ticks()
        pulse = 0.75 + 0.25 * math.sin(now * 0.008)
        w = int(self._hover_glow_surf.get_width() * pulse)
        h = self._hover_glow_surf.get_height()
        scaled = pygame.transform.scale(self._hover_glow_surf, (w, h))
        draw_x = self.player.rect.centerx - self.camera_x - w // 2
        draw_y = self.player.rect.bottom + 3
        self.screen.blit(scaled, (draw_x, draw_y))

    def _draw_ability_aura(self) -> None:
        ability = self.player.current_ability
        aura_color = _ABILITY_AURA.get(ability)
        if aura_color is None:
            return
        now = pygame.time.get_ticks()
        pulse = 0.65 + 0.35 * math.sin(now * 0.0045)
        cx = self.player.rect.centerx - self.camera_x
        cy = self.player.rect.centery + 4

        # ── Base pulsing ring ─────────────────────────────────────────────────
        r = int(22 * pulse)
        diam = r * 2 + 10
        surf = pygame.Surface((diam, diam), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*aura_color, int(55 * pulse)), (diam // 2, diam // 2), r)
        pygame.draw.circle(surf, (*aura_color, int(90 * pulse)), (diam // 2, diam // 2), r, width=2)
        self.screen.blit(surf, (cx - diam // 2, cy - diam // 2))

        # ── Per-ability orbital effects ────────────────────────────────────────
        if ability == "flamethrower":
            # 4 orbiting flame orbs with bright cores
            for i in range(4):
                a = now * 0.005 + i * (math.pi / 2)
                ox = int(cx + math.cos(a) * 26)
                oy = int(cy + math.sin(a) * 16)
                pygame.draw.circle(self.screen, (255, 100, 15), (ox, oy), 5)
                pygame.draw.circle(self.screen, (255, 210, 80), (ox, oy), 2)
                # Trailing spark
                ta = a - 0.45
                tx = int(cx + math.cos(ta) * 26)
                ty = int(cy + math.sin(ta) * 16)
                pygame.draw.line(self.screen, (255, 80, 10), (tx, ty), (ox, oy), 2)

        elif ability == "snowfall":
            # 6 slowly orbiting ice crystals (cross shape)
            for i in range(6):
                a = now * 0.0018 + i * (math.pi / 3)
                ox = int(cx + math.cos(a) * 28)
                oy = int(cy + math.sin(a) * 18)
                cr = (140, 220, 255)
                pygame.draw.line(self.screen, cr, (ox - 4, oy), (ox + 4, oy), 1)
                pygame.draw.line(self.screen, cr, (ox, oy - 4), (ox, oy + 4), 1)
                pygame.draw.line(self.screen, cr, (ox - 3, oy - 3), (ox + 3, oy + 3), 1)
                pygame.draw.line(self.screen, cr, (ox + 3, oy - 3), (ox - 3, oy + 3), 1)
                pygame.draw.circle(self.screen, (210, 245, 255), (ox, oy), 2)

        elif ability == "sword_swing":
            # 6 fast silver sparks with motion trails
            for i in range(6):
                a = now * 0.013 + i * (math.pi / 3)
                ox = int(cx + math.cos(a) * 30)
                oy = int(cy + math.sin(a) * 20)
                pygame.draw.circle(self.screen, (230, 230, 255), (ox, oy), 3)
                # Trail (two fading steps)
                for step, alpha_frac in [(0.25, 160), (0.50, 80)]:
                    ta = a - step
                    tx = int(cx + math.cos(ta) * 30)
                    ty = int(cy + math.sin(ta) * 20)
                    tr_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
                    pygame.draw.circle(tr_surf, (200, 200, 240, alpha_frac), (3, 3), 2)
                    self.screen.blit(tr_surf, (tx - 3, ty - 3))

    def _draw_snatch_beam(self, now: int) -> None:
        """Pink tongue beam drawn while snatch animation is live."""
        if now >= self._snatch_beam_until_ms:
            return
        progress = (self._snatch_beam_until_ms - now) / 160.0
        alpha = int(255 * progress)
        start = (self.player.rect.centerx - self.camera_x,
                 self.player.rect.centery + 2)
        end   = (self._snatch_beam_end[0] - self.camera_x,
                 self._snatch_beam_end[1])
        width = max(1, int(5 * progress))

        # Outer soft glow
        glow_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.line(glow_surf, (255, 80, 140, int(60 * progress)), start, end, width + 6)
        self.screen.blit(glow_surf, (0, 0))
        # Core beam
        pygame.draw.line(self.screen, (255, 60, 120), start, end, width)
        pygame.draw.line(self.screen, (255, 200, 220), start, end, max(1, width - 2))
        # Tip circle
        pygame.draw.circle(self.screen, (255, 150, 190), end, width + 2)
        pygame.draw.circle(self.screen, (255, 255, 255), end, max(1, width - 1))

    def _draw_held_enemy_glow(self, now: int) -> None:
        """Pulsing colored glow around frog mouth while holding an enemy."""
        if self.player.held_enemy_type is None:
            return
        color = COLOR_BY_ENEMY.get(self.player.held_enemy_type, (200, 240, 160))
        pulse = 0.6 + 0.4 * abs(math.sin(now * 0.007))
        cx = self.player.rect.centerx - self.camera_x
        cy = self.player.rect.centery
        r = int(18 * pulse)
        s = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, int(80 * pulse)), (r + 4, r + 4), r)
        pygame.draw.circle(s, (*color, int(140 * pulse)), (r + 4, r + 4), r, width=2)
        self.screen.blit(s, (cx - r - 4, cy - r - 4))
        # Small bouncing dot above head
        dot_y = self.player.rect.top - 10 - int(4 * math.sin(now * 0.010))
        pygame.draw.circle(self.screen, color, (cx, dot_y), 4)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx, dot_y), 2)

    # ══════════════════════════════════════════════════════════════════════════
    #  UI drawing
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_ui(self) -> None:
        now = pygame.time.get_ticks()

        # ── Health panel (top-left) ───────────────────────────────────────────
        self._draw_heart_hud(now)

        # ── Score + ability panel (top-center, redesigned) ───────────────────
        ability      = self.player.current_ability
        ability_name = self._ability_display_name(ability)
        ability_color = _ABILITY_HUD_COLOR.get(ability, (200, 200, 220))

        panel_w  = 294
        panel_h  = 60
        panel_x  = WINDOW_WIDTH // 2 - panel_w // 2
        panel_y  = 5
        half_w   = panel_w // 2

        # Frosted glass background
        sc_panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        sc_panel.fill((8, 10, 22, 180))
        # Ability-tinted border rim
        pygame.draw.rect(sc_panel, (*ability_color, 38), (0, 0, panel_w, panel_h),
                         border_radius=11, width=1)
        # Top highlight streak
        hl = pygame.Surface((panel_w - 20, 1), pygame.SRCALPHA)
        hl.fill((255, 255, 255, 32))
        sc_panel.blit(hl, (10, 1))
        self.screen.blit(sc_panel, (panel_x, panel_y))

        # Vertical divider
        dv = pygame.Surface((1, panel_h - 14), pygame.SRCALPHA)
        dv.fill((255, 255, 255, 22))
        self.screen.blit(dv, (panel_x + half_w, panel_y + 7))

        # ── LEFT HALF — Kill / Score ─────────────────────────────────────────
        left_cx = panel_x + half_w // 2

        sc_lbl = self.small_font.render("SCORE", True, (88, 98, 148))
        self.screen.blit(sc_lbl, sc_lbl.get_rect(midtop=(left_cx, panel_y + 6)))

        sc_num_font = pygame.font.SysFont("consolas", 26, bold=True)
        sc_num = sc_num_font.render(str(self.enemy_count), True, (235, 240, 255))
        self.screen.blit(sc_num, sc_num.get_rect(midtop=(left_cx, panel_y + 22)))

        # ── RIGHT HALF — Ability Power Badge ─────────────────────────────────
        right_cx = panel_x + half_w + half_w // 2

        logo_size = 36
        logo_cx   = panel_x + half_w + 8 + logo_size // 2
        logo_cy   = panel_y + panel_h // 2

        # Pulsing glow behind the logo circle
        glow_r = logo_size // 2 + 5
        pulse_t = 0.5 + 0.5 * abs(math.sin(now * 0.004))
        glow_s = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_s, (*ability_color, int(45 * pulse_t)),
                           (glow_r, glow_r), glow_r)
        self.screen.blit(glow_s, (logo_cx - glow_r, logo_cy - glow_r))

        # Dark disc + tinted ring
        pygame.draw.circle(self.screen, (10, 12, 26), (logo_cx, logo_cy), logo_size // 2)
        pygame.draw.circle(self.screen, (*ability_color, 90), (logo_cx, logo_cy),
                           logo_size // 2, 2)

        # Procedural ability logo drawn inside the disc
        self._draw_ability_logo(self.screen, logo_cx, logo_cy, ability, logo_size - 8, now)

        # "POWER" micro-label + ability name stacked to the right of the disc
        text_x = logo_cx + logo_size // 2 + 5
        pw_lbl = self.small_font.render("POWER", True, (88, 98, 148))
        self.screen.blit(pw_lbl, (text_x, panel_y + 8))
        ab_surf = self.small_font.render(ability_name, True, ability_color)
        self.screen.blit(ab_surf, (text_x, panel_y + 24))

        # ── Held-enemy indicator (bottom-center) ──────────────────────────────
        if self.player.held_enemy_type is not None:
            pulse = 0.7 + 0.3 * abs(math.sin(now * 0.006))
            enemy_col = COLOR_BY_ENEMY.get(self.player.held_enemy_type, (200, 240, 160))
            ec = tuple(int(c * pulse) for c in enemy_col)
            held_text = self.small_font.render(
                f"Holding: {self.player.held_enemy_type.replace('_', ' ').title()}   "
                f"J=Spit ★   ↓=Swallow",
                True, ec,
            )
            held_rect = held_text.get_rect(midbottom=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 10))
            bg = pygame.Surface((held_rect.width + 20, held_rect.height + 8), pygame.SRCALPHA)
            bg.fill((0, 0, 0, int(160 * pulse)))
            self.screen.blit(bg, (held_rect.left - 10, held_rect.top - 4))
            self.screen.blit(held_text, held_rect)
        elif self.player.current_ability == "star_spit":
            # No ability and nothing held — guide player to snatch
            pulse = 0.55 + 0.45 * abs(math.sin(now * 0.004))
            lock_color = (int(255 * pulse), int(210 * pulse), int(60 * pulse))
            lock_text = self.small_font.render("Press J to snatch an enemy!", True, lock_color)
            lock_rect = lock_text.get_rect(midbottom=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 14))
            bg = pygame.Surface((lock_rect.width + 16, lock_rect.height + 8), pygame.SRCALPHA)
            bg.fill((0, 0, 0, int(140 * pulse)))
            self.screen.blit(bg, (lock_rect.left - 8, lock_rect.top - 4))
            self.screen.blit(lock_text, lock_rect)

        # ── Combo display (bottom-left area) ─────────────────────────────────
        if self._combo_count >= 3 and now <= self._combo_deadline_ms:
            combo_progress = max(0.0, (self._combo_deadline_ms - now) / 3000.0)
            combo_alpha = int(min(255, combo_progress * 600))
            combo_scale = 1.0 + 0.08 * math.sin(now * 0.015)
            if self._combo_count >= 8:
                c_col = (255, 80, 50)
                label = f"🔥 COMBO x{self._combo_count}!"
            elif self._combo_count >= 5:
                c_col = (255, 160, 40)
                label = f"COMBO x{self._combo_count}!"
            else:
                c_col = (255, 230, 70)
                label = f"COMBO x{self._combo_count}"
            combo_surf = self.font.render(label, True, c_col)
            w = int(combo_surf.get_width() * combo_scale)
            h = int(combo_surf.get_height() * combo_scale)
            scaled = pygame.transform.smoothscale(combo_surf, (w, h))
            scaled.set_alpha(combo_alpha)
            self.screen.blit(scaled, (14, WINDOW_HEIGHT - 90 - h))

        # ══ TOP-RIGHT PANEL — time / difficulty / enemy count ════════════════
        self._draw_top_right_panel(now)

        # ── Boss health bar + announcement ────────────────────────────────────
        if self.boss is not None and self.boss.is_alive:
            self._draw_boss_health_bar(now)
        if now < self._boss_announce_until_ms:
            self._draw_boss_announce(now)

        self._draw_score_pops()

        # ── Game over overlay ─────────────────────────────────────────────────
        if self.game_over:
            self._draw_game_over_screen(now)

    def _draw_single_heart(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        size: int,
        filled: bool,
        alpha: int = 255,
        bounce_offset: float = 0.0,
    ) -> None:
        """Draw a single heart shape at (cx, cy)."""
        cy_draw = int(cy + bounce_offset)
        r = max(1, size // 4)

        if filled:
            body_col   = (220, 55,  75)
            shine_col  = (255, 130, 145, 140)
            outline_col = (255, 100, 120)
        else:
            body_col   = (38, 28, 40)
            shine_col  = (0, 0, 0, 0)
            outline_col = (80, 55, 68)

        s = pygame.Surface((size, size), pygame.SRCALPHA)

        # Two circles for the top bumps
        lc = (size // 4,     size // 3)
        rc = (3 * size // 4, size // 3)
        pygame.draw.circle(s, body_col, lc, r)
        pygame.draw.circle(s, body_col, rc, r)

        # Diamond polygon for the bottom V
        pts = [
            (0,          size // 3),
            (size,       size // 3),
            (size // 2,  size - 2),
        ]
        pygame.draw.polygon(s, body_col, pts)

        # Thin outline pass
        pygame.draw.circle(s, outline_col, lc, r, 1)
        pygame.draw.circle(s, outline_col, rc, r, 1)
        pygame.draw.polygon(s, outline_col, pts, 1)

        # Shine dot (filled hearts only)
        if filled:
            sh = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(sh, shine_col, (size // 4 - 1, size // 3 - 2), max(1, r - 2))
            s.blit(sh, (0, 0))

        s.set_alpha(alpha)
        surface.blit(s, (cx - size // 2, cy_draw - size // 2))

    def _draw_heart_hud(self, now: int) -> None:
        """Draw individual heart icons for each HP slot (top-left corner)."""
        from .settings import PLAYER_MAX_HEALTH
        heart_size  = 22
        gap         = 6
        total_w     = PLAYER_MAX_HEALTH * heart_size + (PLAYER_MAX_HEALTH - 1) * gap
        panel_pad_x = 10
        panel_pad_y = 8
        panel_w     = total_w + panel_pad_x * 2
        panel_h     = heart_size + panel_pad_y * 2 + 4   # +4 for bounce room

        # Background pill
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((8, 10, 22, 170))
        pygame.draw.rect(panel, (255, 255, 255, 22), (0, 0, panel_w, panel_h), border_radius=10, width=1)
        self.screen.blit(panel, (4, 4))

        for i in range(PLAYER_MAX_HEALTH):
            filled = i < self.player.health
            cx = 4 + panel_pad_x + i * (heart_size + gap) + heart_size // 2
            cy = 4 + panel_pad_y + heart_size // 2

            # Animate bounce offset (spring-back)
            bounce = self._heart_bounce[i]
            if abs(bounce) > 0.3:
                # Simple spring: decay toward 0
                elapsed = now - self._heart_bounce_timer[i]
                decay = math.exp(-elapsed * 0.010)
                self._heart_bounce[i] = bounce * decay
            else:
                self._heart_bounce[i] = 0.0

            # Pulse glow on the last remaining heart when low on HP
            alpha = 255
            if filled and self.player.health == 1:
                pulse = 0.55 + 0.45 * abs(math.sin(now * 0.006))
                alpha = int(180 + 75 * pulse)

            self._draw_single_heart(
                self.screen, cx, cy,
                size=heart_size,
                filled=filled,
                alpha=alpha,
                bounce_offset=self._heart_bounce[i],
            )

    def _trigger_game_over_fx(self, now: int) -> None:
        """Spawn heart-break particles when game over begins."""
        cx, cy = WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 60
        # Burst of red heart-tinted particles
        for _ in range(40):
            a = math.radians(random.uniform(0, 360))
            spd = random.uniform(1.5, 6.0)
            lt  = random.randint(900, 2200)
            self._death_particles.append({
                "x": float(cx + random.randint(-20, 20)),
                "y": float(cy + random.randint(-10, 10)),
                "vx": math.cos(a) * spd,
                "vy": math.sin(a) * spd - random.uniform(0, 2),
                "gravity": 0.09,
                "life": lt, "max_life": lt,
                "color": random.choice([
                    (220, 50, 70), (255, 90, 110), (180, 30, 50),
                    (255, 200, 210), (255, 60, 90),
                ]),
                "size": random.uniform(3.0, 7.5),
                "is_heart": random.random() < 0.30,
            })

    def _update_death_particles(self, dt_ms: int) -> None:
        keep = []
        for p in self._death_particles:
            p["x"]  += p["vx"]
            p["y"]  += p["vy"]
            p["vy"] += p["gravity"]
            p["vx"] *= 0.97
            p["life"] -= dt_ms
            if p["life"] > 0:
                keep.append(p)
        self._death_particles = keep

    def _draw_death_particles(self) -> None:
        for p in self._death_particles:
            alpha = max(0.0, p["life"] / p["max_life"])
            size  = max(1, int(p["size"] * (0.4 + 0.6 * alpha)))
            sx, sy = int(p["x"]), int(p["y"])
            if not (-20 <= sx <= WINDOW_WIDTH + 20 and -20 <= sy <= WINDOW_HEIGHT + 20):
                continue
            r, g, b = p["color"]
            col = (min(255, int(r * alpha)), min(255, int(g * alpha)), min(255, int(b * alpha)))
            if p.get("is_heart"):
                self._draw_single_heart(self.screen, sx, sy, size * 2 + 4, filled=True, alpha=int(alpha * 200))
            else:
                pygame.draw.circle(self.screen, col, (sx, sy), size)

    def _draw_game_over_screen(self, now: int) -> None:
        """Beautiful animated game over overlay."""
        elapsed = now - self._game_over_start_ms

        # ── 1. Darkening overlay (fades in over 600ms) ────────────────────────
        overlay_alpha = min(200, int(200 * elapsed / 600))
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 4, 14, overlay_alpha))
        self.screen.blit(overlay, (0, 0))

        # ── 2. Optional lose-screen image underneath text ─────────────────────
        if self.lose_screen is not None:
            img_alpha = min(180, int(180 * elapsed / 700))
            fc = self.lose_screen.copy()
            fc.set_alpha(img_alpha)
            self.screen.blit(fc, (0, 0))

        if elapsed < 300:
            return   # Let the fade-in play before showing text

        text_alpha = min(255, int(255 * (elapsed - 300) / 400))

        cx = WINDOW_WIDTH // 2
        cy = WINDOW_HEIGHT // 2

        # ── 3. Glowing backdrop panel ─────────────────────────────────────────
        panel_w, panel_h = 520, 230
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((12, 8, 22, int(200 * text_alpha / 255)))
        pygame.draw.rect(panel, (200, 50, 80, int(60 * text_alpha / 255)),
                         (0, 0, panel_w, panel_h), border_radius=18, width=2)
        # Inner rim glow
        pulse = 0.6 + 0.4 * math.sin(now * 0.004)
        glow_col = (int(180 * pulse), int(40 * pulse), int(60 * pulse), int(30 * text_alpha / 255))
        pygame.draw.rect(panel, glow_col, (3, 3, panel_w - 6, panel_h - 6), border_radius=16, width=1)
        self.screen.blit(panel, (cx - panel_w // 2, cy - panel_h // 2))

        # ── 4. "GAME OVER" title ──────────────────────────────────────────────
        title_font = pygame.font.SysFont("consolas", 52, bold=True)
        title_scale = 1.0 + 0.025 * math.sin(now * 0.003)

        # Shadow pass
        shadow_surf = title_font.render("GAME  OVER", True, (90, 10, 20))
        shadow_surf.set_alpha(int(140 * text_alpha / 255))
        sw = int(shadow_surf.get_width() * title_scale)
        sh = int(shadow_surf.get_height() * title_scale)
        shadow_scaled = pygame.transform.smoothscale(shadow_surf, (sw, sh))
        self.screen.blit(shadow_scaled, (cx - sw // 2 + 3, cy - panel_h // 2 + 26 + 3))

        # Main title
        title_surf = title_font.render("GAME  OVER", True, (245, 70, 95))
        tw = int(title_surf.get_width() * title_scale)
        th = int(title_surf.get_height() * title_scale)
        title_scaled = pygame.transform.smoothscale(title_surf, (tw, th))
        title_scaled.set_alpha(text_alpha)
        self.screen.blit(title_scaled, (cx - tw // 2, cy - panel_h // 2 + 26))

        # ── 5. Decorative broken hearts row ───────────────────────────────────
        heart_y = cy - panel_h // 2 + 26 + th + 14
        for hi in range(5):
            hx = cx + (hi - 2) * 36
            self._draw_single_heart(self.screen, hx, heart_y + 10,
                                    size=18, filled=False, alpha=int(180 * text_alpha / 255))

        # ── 6. Stats block ────────────────────────────────────────────────────
        stats_y = heart_y + 30
        t_sec   = max(0, int(self.session_time))
        time_str  = f"{t_sec // 60:02d}:{t_sec % 60:02d}"
        stats_lines = [
            (f"Score:   {self.enemy_count}  enemies defeated", (220, 220, 240)),
            (f"Time:    {time_str}  survived",                  (180, 205, 230)),
        ]
        for i, (line, col) in enumerate(stats_lines):
            s = self.font.render(line, True, col)
            s.set_alpha(text_alpha)
            self.screen.blit(s, (cx - s.get_width() // 2, stats_y + i * 30))

        # ── 7. Divider ────────────────────────────────────────────────────────
        divider_y = stats_y + len(stats_lines) * 30 + 8
        div = pygame.Surface((360, 1), pygame.SRCALPHA)
        div.fill((200, 80, 100, int(100 * text_alpha / 255)))
        self.screen.blit(div, (cx - 180, divider_y))

        # ── 8. Prompt (blink after 1.2 s) ────────────────────────────────────
        if elapsed > 1200:
            blink = abs(math.sin(now * 0.0025))
            prompt_alpha = int(text_alpha * (0.55 + 0.45 * blink))
            r_surf = self.small_font.render("[R]  Restart", True, (255, 210, 80))
            e_surf = self.small_font.render("[ESC]  Menu", True, (180, 195, 220))
            r_surf.set_alpha(prompt_alpha)
            e_surf.set_alpha(prompt_alpha)
            prompt_y = divider_y + 14
            self.screen.blit(r_surf, (cx - 120 - r_surf.get_width() // 2, prompt_y))
            self.screen.blit(e_surf, (cx + 120 - e_surf.get_width() // 2, prompt_y))

    
    def _draw_ability_logo(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        ability: str,
        size: int = 28,
        now: int = 0,
    ) -> None:
        """Draw a procedural ability power logo centered at (cx, cy).

        Each ability gets a distinctive symbolic icon:
          flamethrower → animated teardrop flame
          snowfall     → 6-arm snowflake with branch ticks
          sword_swing  → vertical sword with crossguard
          star_spit    → spinning 8-point star (default)
        """
        import math as _m
        half = max(4, size // 2)

        if ability == "flamethrower":
            # ── Flame: layered teardrop, flickers ───────────────────────────
            flicker = 0.86 + 0.14 * _m.sin(now * 0.013)
            # outer (orange)
            pts_o = [
                (cx,                     cy - int(half * flicker)),
                (cx + half * 55 // 100,  cy - half * 18 // 100),
                (cx + half * 40 // 100,  cy + half * 35 // 100),
                (cx,                     cy + half * 55 // 100),
                (cx - half * 40 // 100,  cy + half * 35 // 100),
                (cx - half * 55 // 100,  cy - half * 18 // 100),
            ]
            pygame.draw.polygon(surface, (255, 95, 18), pts_o)
            # mid (amber)
            pts_m = [
                (cx,                     cy - int(half * 0.68 * flicker)),
                (cx + half * 33 // 100,  cy - half * 6  // 100),
                (cx + half * 24 // 100,  cy + half * 28 // 100),
                (cx,                     cy + half * 40 // 100),
                (cx - half * 24 // 100,  cy + half * 28 // 100),
                (cx - half * 33 // 100,  cy - half * 6  // 100),
            ]
            pygame.draw.polygon(surface, (255, 190, 30), pts_m)
            # inner (pale yellow core)
            core_r = max(2, half * 14 // 100)
            pygame.draw.circle(surface, (255, 252, 200), (cx, cy + half * 22 // 100), core_r)

        elif ability == "snowfall":
            # ── Snowflake: 6 arms + barbs + tip dots ────────────────────────
            arm_col  = (160, 228, 255)
            barb_col = (200, 244, 255)
            tip_col  = (240, 252, 255)
            for i in range(6):
                angle = _m.radians(i * 60)
                ex = int(cx + _m.cos(angle) * half)
                ey = int(cy + _m.sin(angle) * half)
                pygame.draw.line(surface, arm_col, (cx, cy), (ex, ey), 2)
                # two barbs along each arm
                for frac in (0.45, 0.72):
                    mx = int(cx + _m.cos(angle) * half * frac)
                    my = int(cy + _m.sin(angle) * half * frac)
                    perp = angle + _m.pi * 0.5
                    bl = half * 0.22
                    pygame.draw.line(
                        surface, barb_col,
                        (int(mx + _m.cos(perp) * bl), int(my + _m.sin(perp) * bl)),
                        (int(mx - _m.cos(perp) * bl), int(my - _m.sin(perp) * bl)),
                        1,
                    )
                pygame.draw.circle(surface, tip_col, (ex, ey), max(1, half * 12 // 100))
            pygame.draw.circle(surface, (255, 255, 255), (cx, cy), max(2, half * 18 // 100))

        elif ability == "sword_swing":
            # ── Sword: blade + crossguard + handle + pommel ─────────────────
            blade_w = max(3, size * 14 // 100)
            tip_h   = max(4, half * 38 // 100)
            # blade rect
            pygame.draw.rect(
                surface, (185, 195, 225),
                (cx - blade_w // 2, cy - half + tip_h, blade_w, int(half * 1.30)),
                border_radius=1,
            )
            # blade shine (left edge highlight)
            pygame.draw.rect(
                surface, (230, 238, 255),
                (cx - blade_w // 2, cy - half + tip_h + 2, max(1, blade_w // 3), int(half * 0.9)),
            )
            # pointed tip
            pygame.draw.polygon(surface, (215, 225, 255), [
                (cx,               cy - half),
                (cx - blade_w // 2, cy - half + tip_h),
                (cx + blade_w // 2, cy - half + tip_h),
            ])
            # crossguard
            guard_w = max(8, size * 54 // 100)
            guard_h = max(3, blade_w)
            pygame.draw.rect(
                surface, (130, 145, 200),
                (cx - guard_w // 2, cy - guard_h // 2, guard_w, guard_h),
                border_radius=2,
            )
            # handle
            handle_h = max(5, half * 40 // 100)
            pygame.draw.rect(
                surface, (150, 110, 65),
                (cx - blade_w // 2 + 1, cy + guard_h // 2, blade_w - 2, handle_h),
                border_radius=1,
            )
            # grip wrap lines
            for gi in range(2):
                gy = cy + guard_h // 2 + 3 + gi * (handle_h // 3)
                pygame.draw.line(surface, (110, 80, 40),
                                 (cx - blade_w // 2 + 1, gy), (cx + blade_w // 2 - 2, gy), 1)
            # pommel
            pommel_r = max(2, blade_w)
            pygame.draw.circle(
                surface, (190, 165, 90),
                (cx, cy + guard_h // 2 + handle_h + pommel_r - 1),
                pommel_r,
            )

        else:
            # ── Star spit (default): spinning 8-point star ───────────────────
            spin    = (_m.fmod(now * 0.003, _m.pi * 2))
            r_out   = half
            r_in    = max(2, int(half * 0.42))
            pts = []
            for i in range(8):
                a_o = spin + i * (_m.pi / 4)
                a_i = a_o + _m.pi / 8
                pts.append((int(cx + _m.cos(a_o) * r_out), int(cy + _m.sin(a_o) * r_out)))
                pts.append((int(cx + _m.cos(a_i) * r_in),  int(cy + _m.sin(a_i) * r_in)))
            pygame.draw.polygon(surface, (255, 125, 200), pts)
            pygame.draw.polygon(surface, (255, 252, 200), pts, 1)
            pygame.draw.circle(surface, (255, 230, 90),
                                (cx, cy), max(2, half * 22 // 100))

    def _ability_display_name(self, ability: str) -> str:
        return {
            "star_spit":    "None",
            "none":         "None",
            "flamethrower": "Flamethrower",
            "snowfall":     "Snowfall",
            "sword_swing":  "Whirlwind",
        }.get(ability, "None")

    def _draw_top_right_panel(self, now: int) -> None:
        """Top-right HUD panel — modern 8-bit pixel-art style."""
        import math as _m

        ability      = self.player.current_ability
        has_flame    = ability == "flamethrower"
        has_snow     = ability == "snowfall"
        has_sword    = ability == "sword_swing"
        has_cd       = has_flame or has_snow or has_sword
        combo_active = self._combo_count >= 3 and now <= self._combo_deadline_ms

        # ── Panel dimensions ──────────────────────────────────────────────────
        panel_w = 216
        panel_x = WINDOW_WIDTH - panel_w - 8
        panel_y = 8
        pad_x   = 12
        label_x = panel_x + pad_x

        ROW_TIME  = 30
        ROW_SEP   = 7
        ROW_DIFF  = 38
        ROW_KILLS = 48
        ROW_CD    = 38
        ROW_COMBO = 28

        panel_h = (8
                   + ROW_TIME + ROW_SEP
                   + ROW_DIFF + ROW_SEP
                   + ROW_KILLS
                   + (ROW_SEP + ROW_CD    if has_cd       else 0)
                   + (ROW_SEP + ROW_COMBO if combo_active else 0)
                   + 8)

        # ── Ability accent color ──────────────────────────────────────────────
        ACCENT: dict[str, tuple[int, int, int]] = {
            "flamethrower": (255, 110, 40),
            "snowfall":     (70,  205, 255),
            "sword_swing":  (185, 185, 255),
            "star_spit":    (255, 110, 195),
            "none":         (60,  95,  200),
        }
        accent_col = ACCENT.get(ability, ACCENT["none"])

        # ══════════════════════════════════════════════════════════════════════
        #  8-bit panel background
        # ══════════════════════════════════════════════════════════════════════
        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill((6, 7, 18, 218))

        # Subtle scanlines (every 2 px — classic CRT feel)
        scan = pygame.Surface((panel_w, 1), pygame.SRCALPHA)
        scan.fill((0, 0, 0, 16))
        for sy in range(0, panel_h, 2):
            bg.blit(scan, (0, sy))

        # Very faint ability tint wash
        tint = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        tint.fill((*accent_col, 8))
        bg.blit(tint, (0, 0))

        # Pixel-art border: 1-px bright rim
        pygame.draw.rect(bg, (*accent_col, 55), (0, 0, panel_w, panel_h), width=1)

        # Corner L-shapes (4 px each) — hallmark of 8-bit UI frames
        c_bright = (*accent_col, 200)
        for cx_o, cy_o, xd, yd in [
            (0,         0,          1,  1),
            (panel_w-1, 0,         -1,  1),
            (0,         panel_h-1,  1, -1),
            (panel_w-1, panel_h-1, -1, -1),
        ]:
            for i in range(5):
                if 0 <= cx_o + xd*i < panel_w:
                    bg.fill(c_bright, (cx_o + xd*i, cy_o, 1, 1))
                if 0 <= cy_o + yd*i < panel_h:
                    bg.fill(c_bright, (cx_o, cy_o + yd*i, 1, 1))

        self.screen.blit(bg, (panel_x, panel_y))

        # Pixel left accent stripe (3-px, dashed every 2 rows for 8-bit look)
        for sy in range(0, panel_h - 8, 2):
            t_pos  = sy / max(1, panel_h - 8)
            alpha  = int(210 * (1.0 - abs(t_pos - 0.5) * 1.8))
            alpha  = max(0, min(210, alpha))
            stripe_dot = pygame.Surface((3, 2), pygame.SRCALPHA)
            stripe_dot.fill((*accent_col, alpha))
            self.screen.blit(stripe_dot, (panel_x + 4, panel_y + 4 + sy))

        row_y = panel_y + 8

        # ══ ROW 1 — TIMER (digital display) ══════════════════════════════════
        t     = max(0, int(self.session_time))
        mins, secs = t // 60, t % 60
        colon = ":" if (now // 500) % 2 == 0 else " "  # blinking colon
        time_str = f"{mins:02d}{colon}{secs:02d}"

        # Pixel clock icon (14×14, sharp-cornered)
        ic_x, ic_y = label_x, row_y + 2
        pygame.draw.rect(self.screen, (38, 55, 110), (ic_x, ic_y, 14, 14))
        pygame.draw.rect(self.screen, (75, 105, 190), (ic_x, ic_y, 14, 14), width=1)
        # Clock hands (pixel lines)
        hour_ang = _m.radians(t / 60.0 * 360 - 90)
        sec_ang  = _m.radians(secs * 6 - 90)
        pygame.draw.line(self.screen, (195, 215, 255),
                         (ic_x + 7, ic_y + 7),
                         (ic_x + 7 + int(_m.cos(hour_ang) * 3),
                          ic_y + 7 + int(_m.sin(hour_ang) * 3)), 2)
        pygame.draw.line(self.screen, (90, 175, 255),
                         (ic_x + 7, ic_y + 7),
                         (ic_x + 7 + int(_m.cos(sec_ang) * 5),
                          ic_y + 7 + int(_m.sin(sec_ang) * 5)), 1)
        pygame.draw.rect(self.screen, (210, 228, 255), (ic_x + 6, ic_y + 6, 2, 2))

        # Time digits
        time_surf = self.font.render(time_str, True, (175, 210, 255))
        self.screen.blit(time_surf, (label_x + 18, row_y + 2))

        lbl = self.small_font.render("TIME", True, (55, 75, 125))
        self.screen.blit(lbl, (panel_x + panel_w - pad_x - lbl.get_width(), row_y + 8))

        row_y += ROW_TIME
        self._hud_sep_pixel(panel_x + 8, row_y, panel_w - 16)
        row_y += ROW_SEP

        # ══ ROW 2 — DIFFICULTY (8-bit segmented block bar) ════════════════════
        progress  = min(self.session_time / max(1, self._difficulty_cap_seconds), 1.0)
        r_c       = min(255, int(55  + 200 * progress))
        g_c       = max(20,  int(220 - 185 * progress))
        fill_col  = (r_c, g_c, 45)

        # 3-tower signal icon (pixel-sharp, no border_radius)
        sb_x, sb_y = label_x, row_y + 2
        for bi, bh in enumerate((4, 7, 10)):
            bfilled = bi < max(1, int(progress * 3 + 0.5))
            bc = fill_col if bfilled else (22, 25, 44)
            pygame.draw.rect(self.screen, bc, (sb_x + bi * 6, sb_y + (10 - bh), 4, bh))
            pygame.draw.rect(self.screen, (38, 42, 68),
                             (sb_x + bi * 6, sb_y + (10 - bh), 4, bh), width=1)

        diff_lbl = self.small_font.render("DIFFICULTY", True, (88, 98, 152))
        pct_col  = (min(255, int(100 + 155 * progress)), max(50, int(220 - 165 * progress)), 70)
        pct_surf = self.small_font.render(f"{int(progress * 100)}%", True, pct_col)
        self.screen.blit(diff_lbl, (label_x + 22, row_y))
        self.screen.blit(pct_surf, (panel_x + panel_w - pad_x - pct_surf.get_width(), row_y))
        row_y += 14

        # ── 8-bit segmented block bar ─────────────────────────────────────────
        bar_w  = panel_w - pad_x * 2
        N_SEGS = 16
        seg_w  = (bar_w - (N_SEGS - 1)) // N_SEGS
        seg_h  = 8
        n_fill = int(N_SEGS * progress)
        for si in range(N_SEGS):
            sx    = label_x + si * (seg_w + 1)
            t_seg = si / max(1, N_SEGS - 1)
            if si < n_fill:
                seg_r = min(255, int(55 + 200 * t_seg))
                seg_g = max(20,  int(220 - 185 * t_seg))
                seg_col = (seg_r, seg_g, 45)
            else:
                seg_col = (16, 18, 34)
            pygame.draw.rect(self.screen, seg_col, (sx, row_y, seg_w, seg_h))
            if si >= n_fill:
                pygame.draw.rect(self.screen, (28, 30, 52), (sx, row_y, seg_w, seg_h), width=1)

        if progress >= 0.85:
            pulse   = 0.45 + 0.55 * abs(math.sin(now * 0.005))
            danger  = pygame.Surface((bar_w, seg_h), pygame.SRCALPHA)
            danger.fill((255, 30, 20, int(38 * pulse)))
            self.screen.blit(danger, (label_x, row_y))

        row_y += seg_h + 12
        self._hud_sep_pixel(panel_x + 8, row_y, panel_w - 16)
        row_y += ROW_SEP

        # ══ ROW 3 — KILL COUNTER + BOSS PROGRESS ══════════════════════════════
        # Pixel skull icon
        sk_cx, sk_cy = label_x + 9, row_y + 10
        pygame.draw.circle(self.screen, (160, 165, 202), (sk_cx, sk_cy - 1), 9)
        pygame.draw.rect(self.screen,   (145, 150, 188), (sk_cx - 6, sk_cy + 5, 12, 6), border_radius=2)
        pygame.draw.circle(self.screen, (16, 18, 36),    (sk_cx - 3, sk_cy - 1), 2)
        pygame.draw.circle(self.screen, (16, 18, 36),    (sk_cx + 3, sk_cy - 1), 2)
        pygame.draw.polygon(self.screen, (16, 18, 36),
                            [(sk_cx, sk_cy + 2), (sk_cx - 1, sk_cy + 4), (sk_cx + 1, sk_cy + 4)])
        for tx in (sk_cx - 4, sk_cx - 1, sk_cx + 2, sk_cx + 5):
            pygame.draw.rect(self.screen, (16, 18, 36), (tx, sk_cy + 6, 2, 4))

        kill_font = pygame.font.SysFont("consolas", 26, bold=True)
        kill_surf = kill_font.render(str(self.enemy_count), True, (220, 225, 255))
        self.screen.blit(kill_surf, (label_x + 22, row_y))

        def_lbl = self.small_font.render("DEFEATED", True, (62, 72, 125))
        self.screen.blit(def_lbl,
                         (panel_x + panel_w - pad_x - def_lbl.get_width(),
                          row_y + kill_surf.get_height() - def_lbl.get_height()))

        # Boss threshold — 8-bit segmented mini-bar
        bbar_y = row_y + kill_surf.get_height() + 3
        bbar_w = panel_w - pad_x * 2
        B_SEGS  = 12
        bseg_w  = (bbar_w - (B_SEGS - 1)) // B_SEGS
        bseg_h  = 6

        if not self._boss_spawned:
            prev_thresh   = self._next_boss_threshold - BOSS_SPAWN_THRESHOLD
            kills_since   = self.enemy_count - prev_thresh
            boss_progress = max(0.0, min(1.0, kills_since / BOSS_SPAWN_THRESHOLD))
            n_boss_fill   = int(B_SEGS * boss_progress)

            bpulse = 1.0
            if boss_progress >= 0.8:
                bpulse = 0.7 + 0.3 * abs(math.sin(now * 0.007))

            for si in range(B_SEGS):
                bsx    = label_x + si * (bseg_w + 1)
                t_bseg = si / max(1, B_SEGS - 1)
                if si < n_boss_fill:
                    bp_r = min(255, int((150 + 105 * t_bseg) * bpulse))
                    bp_g = max(20,  int(140 * (1 - t_bseg) * bpulse))
                    bseg_col = (bp_r, bp_g, int(15 * bpulse))
                else:
                    bseg_col = (18, 12, 34)
                pygame.draw.rect(self.screen, bseg_col, (bsx, bbar_y, bseg_w, bseg_h))
                if si >= n_boss_fill:
                    pygame.draw.rect(self.screen, (30, 20, 50),
                                     (bsx, bbar_y, bseg_w, bseg_h), width=1)

            boss_lbl_col = (200, 150, 255) if boss_progress < 0.8 else (
                255, int(200 * (0.5 + 0.5 * abs(math.sin(now * 0.007)))), 50)
            boss_lbl = self.small_font.render(
                f"{self.enemy_count}/{self._next_boss_threshold}", True, boss_lbl_col)
            self.screen.blit(boss_lbl, (panel_x + panel_w - pad_x - boss_lbl.get_width(),
                                        bbar_y + bseg_h + 1))

        row_y += ROW_KILLS

        # ══ ROW 4 — ABILITY COOLDOWN (8-bit segmented) ════════════════════════
        if has_cd:
            self._hud_sep_pixel(panel_x + 8, row_y, panel_w - 16)
            row_y += ROW_SEP

            if has_flame:
                elapsed_cd      = now - self._flamethrower_released_ms
                cooldown_ms_val = FLAMETHROWER_COOLDOWN_MS
                cd_lbl_ready    = "[K] FLAME"
                cd_fill_ready   = (255, 145, 35)
                cd_fill_wait    = (90,  40,  10)
                cd_col_ready    = (255, 190, 60)
                cd_col_wait     = (135, 75,  25)
            elif has_snow:
                elapsed_cd      = now - self.player._last_attack_ms
                cooldown_ms_val = SNOWFALL_COOLDOWN_MS
                cd_lbl_ready    = "[K] SNOWFALL"
                cd_fill_ready   = (70,  200, 255)
                cd_fill_wait    = (25,  75,  110)
                cd_col_ready    = (130, 220, 255)
                cd_col_wait     = (55,  115, 160)
            else:
                elapsed_cd      = now - self.player._last_attack_ms
                cooldown_ms_val = SWORD_WHIRLWIND_COOLDOWN_MS
                cd_lbl_ready    = "[K] SWORD"
                cd_fill_ready   = (195, 195, 255)
                cd_fill_wait    = (65,  65,  125)
                cd_col_ready    = (215, 215, 255)
                cd_col_wait     = (100, 100, 170)

            cd_ready = elapsed_cd >= cooldown_ms_val
            cd_frac  = min(1.0, elapsed_cd / max(1, cooldown_ms_val))
            lbl_text = cd_lbl_ready   if cd_ready else "   COOLING"
            lbl_col  = cd_col_ready   if cd_ready else cd_col_wait
            fill_col = cd_fill_ready  if cd_ready else cd_fill_wait

            # Glow behind label when ready
            if cd_ready:
                pulse = 0.5 + 0.5 * abs(math.sin(now * 0.006))
                gw    = self.small_font.size(lbl_text)[0] + 14
                glow  = pygame.Surface((gw, 16), pygame.SRCALPHA)
                glow.fill((*accent_col, int(28 * pulse)))
                self.screen.blit(glow, (label_x - 5, row_y - 2))

            cd_surf = self.small_font.render(lbl_text, True, lbl_col)
            self.screen.blit(cd_surf, (label_x, row_y))

            # "READY" chip badge (right-aligned)
            if cd_ready:
                rw, rh = 42, 14
                ready_bg = pygame.Surface((rw, rh), pygame.SRCALPHA)
                ready_bg.fill((*fill_col, 45))
                pygame.draw.rect(ready_bg, (*fill_col, 160), (0, 0, rw, rh), width=1)
                ready_txt = self.small_font.render("READY", True, fill_col)
                ready_bg.blit(ready_txt,
                              (rw // 2 - ready_txt.get_width() // 2,
                               rh // 2 - ready_txt.get_height() // 2 + 1))
                self.screen.blit(ready_bg, (panel_x + panel_w - pad_x - rw, row_y - 1))

            row_y += 14

            # 8-bit segmented cooldown bar
            CD_SEGS    = 14
            cbar_w     = panel_w - pad_x * 2
            cseg_w     = (cbar_w - (CD_SEGS - 1)) // CD_SEGS
            cseg_h     = 7
            n_cd_fill  = int(CD_SEGS * cd_frac)

            for si in range(CD_SEGS):
                csx = label_x + si * (cseg_w + 1)
                if si < n_cd_fill:
                    t_s  = si / max(1, CD_SEGS - 1)
                    fr, fg, fb = fill_col
                    seg_col = (min(255, int(fr * (0.65 + 0.35 * t_s))),
                               min(255, int(fg * (0.65 + 0.35 * t_s))),
                               min(255, int(fb * (0.65 + 0.35 * t_s))))
                else:
                    seg_col = (12, 10, 24)
                pygame.draw.rect(self.screen, seg_col, (csx, row_y, cseg_w, cseg_h))
                if si >= n_cd_fill:
                    pygame.draw.rect(self.screen, (24, 22, 44),
                                     (csx, row_y, cseg_w, cseg_h), width=1)

            # Pulsing glow on full bar
            if cd_ready and n_cd_fill == CD_SEGS:
                pulse2   = 0.4 + 0.6 * abs(math.sin(now * 0.007))
                glow_end = pygame.Surface((10, cseg_h), pygame.SRCALPHA)
                glow_end.fill((*fill_col, int(110 * pulse2)))
                self.screen.blit(glow_end, (label_x + cbar_w - 10, row_y))

        # ══ ROW 5 — COMBO COUNTER (when active) ═══════════════════════════════
        if combo_active:
            self._hud_sep_pixel(panel_x + 8, row_y + (14 if has_cd else 0), panel_w - 16)
            row_y += (14 if has_cd else 0) + ROW_SEP

            combo_progress = max(0.0, (self._combo_deadline_ms - now) / 3000.0)

            if self._combo_count >= 8:
                c_col  = (255, int(80 + 80 * abs(math.sin(now * 0.008))), 20)
                c_text = f"x{self._combo_count} COMBO!"
            elif self._combo_count >= 5:
                c_col  = (255, 210, 40)
                c_text = f"x{self._combo_count} COMBO!"
            else:
                c_col  = (195, 255, 100)
                c_text = f"x{self._combo_count} COMBO"

            cs = self.small_font.render(c_text, True, c_col)
            # Glow behind text
            cg = pygame.Surface((cs.get_width() + 14, cs.get_height() + 4), pygame.SRCALPHA)
            cg.fill((*c_col, int(20 * (0.4 + 0.6 * abs(math.sin(now * 0.006))))))
            self.screen.blit(cg, (label_x - 4, row_y - 2))
            self.screen.blit(cs, (label_x, row_y))

            # Decay bar — 8-bit segmented
            cdb_w      = panel_w - pad_x * 2
            cdb_y      = row_y + cs.get_height() + 1
            N_CDEC     = 10
            cdec_seg_w = (cdb_w - (N_CDEC - 1)) // N_CDEC
            n_cdec     = int(N_CDEC * combo_progress)
            for si in range(N_CDEC):
                cdsx    = label_x + si * (cdec_seg_w + 1)
                seg_col = c_col if si < n_cdec else (18, 16, 8)
                pygame.draw.rect(self.screen, seg_col, (cdsx, cdb_y, cdec_seg_w, 4))

    def _hud_sep(self, x: int, y: int, w: int) -> None:
        """Draw a faint horizontal separator line."""
        sep = pygame.Surface((w, 1), pygame.SRCALPHA)
        sep.fill((255, 255, 255, 20))
        self.screen.blit(sep, (x, y))

    def _hud_sep_pixel(self, x: int, y: int, w: int) -> None:
        """Draw a dotted 8-bit style separator (2px dot every 4px)."""
        dot = pygame.Surface((2, 1), pygame.SRCALPHA)
        dot.fill((255, 255, 255, 22))
        for dx in range(0, w, 4):
            self.screen.blit(dot, (x + dx, y))

    def _draw_boss_health_bar(self, now: int) -> None:
        """Draw the Queen Bee health bar at the top-center of the screen."""
        bar_w, bar_h = 320, 20
        bx = WINDOW_WIDTH // 2 - bar_w // 2
        by = 70

        # Panel background
        bg = pygame.Surface((bar_w + 16, bar_h + 30), pygame.SRCALPHA)
        bg.fill((10, 5, 2, 185))
        pygame.draw.rect(bg, (255, 200, 0, 28), (0, 0, bar_w + 16, bar_h + 30),
                         border_radius=8, width=1)
        self.screen.blit(bg, (bx - 8, by - 14))

        # Label
        label = self.small_font.render("♛  QUEEN BEE", True, (255, 215, 0))
        self.screen.blit(label, (WINDOW_WIDTH // 2 - label.get_width() // 2, by - 12))

        # Bar background
        pygame.draw.rect(self.screen, (40, 20, 5),
                         (bx, by + 10, bar_w, bar_h), border_radius=5)

        # Fill
        fill = int(bar_w * self.boss.hp / self.boss.max_hp)
        pulse = 0.7 + 0.3 * math.sin(now * 0.008)
        fill_col = (int(255 * pulse), int(175 * pulse), 0)
        if fill > 0:
            pygame.draw.rect(self.screen, fill_col,
                             (bx, by + 10, fill, bar_h), border_radius=5)
            # Shine
            sh = pygame.Surface((fill, bar_h // 2), pygame.SRCALPHA)
            sh.fill((255, 240, 180, 40))
            self.screen.blit(sh, (bx, by + 10))

        pygame.draw.rect(self.screen, (255, 255, 255, 18),
                         (bx, by + 10, bar_w, bar_h), border_radius=5, width=1)

        # HP numbers
        hp_text = self.small_font.render(
            f"{self.boss.hp} / {self.boss.max_hp}", True, (255, 240, 200))
        self.screen.blit(hp_text, (WINDOW_WIDTH // 2 - hp_text.get_width() // 2, by + 12))

    def _draw_boss_announce(self, now: int) -> None:
        """Full-screen banner when the boss first appears."""
        progress = max(0.0, (self._boss_announce_until_ms - now) / 3500.0)
        alpha = int(min(255, progress * 700))
        pulse = 1.0 + 0.07 * math.sin(now * 0.014)
        wave_num = self._next_boss_threshold // BOSS_SPAWN_THRESHOLD

        for text_str, color, y_off in [
            ("⚠  BOSS APPEARED!  ⚠", (255, 70, 70),   -36),
            ("♛   QUEEN BEE   ♛",    (255, 215, 0),     10),
            (f"— WAVE {wave_num} —",  (255, 180, 80),    52),
        ]:
            surf = self.font.render(text_str, True, color)
            w = int(surf.get_width() * pulse)
            h = int(surf.get_height() * pulse)
            scaled = pygame.transform.smoothscale(surf, (w, h))
            scaled.set_alpha(alpha)
            self.screen.blit(scaled,
                             (WINDOW_WIDTH // 2 - w // 2,
                              WINDOW_HEIGHT // 2 + y_off - h // 2))

    # ══════════════════════════════════════════════════════════════════════════
    #  Main draw
    # ══════════════════════════════════════════════════════════════════════════

    def _draw(self) -> None:
        self.screen.fill(BG_COLOR)
        now = pygame.time.get_ticks()

        if self.state == "menu":
            self._draw_menu()
            pygame.display.flip()
            return
        if self.state == "stats":
            self._draw_stats()
            pygame.display.flip()
            return

        # 1 – Parallax background
        self._draw_background()

        # 2 – Terrain
        self._draw_world()

        # 3 – Sub-player VFX (hover glow, ability aura, held-enemy glow)
        self._draw_hover_glow()
        self._draw_ability_aura()
        self._draw_held_enemy_glow(now)

        # 4 – Ability cone/whirlwind
        if self.is_flamethrower_active:
            self._draw_flamethrower_cone()
        self._draw_whirlwind_effect()

        # 5 – Entities
        self.player.draw(self.screen, camera_x=self.camera_x)
        for enemy in self.enemies:
            enemy.draw(self.screen, camera_x=self.camera_x)
        if self.boss is not None and self.boss.is_alive:
            self.boss.draw(self.screen, camera_x=self.camera_x)
        for st in self._boss_stingers:
            st.draw(self.screen, camera_x=self.camera_x)
        for projectile in self.projectiles:
            projectile.draw(self.screen, camera_x=self.camera_x)
        for wall in self.snow_walls:
            wall.draw(self.screen, camera_x=self.camera_x)

        # 5b – Tongue beam (on top of entities)
        self._draw_snatch_beam(now)

        # 6 – Particles (on top of entities)
        self._draw_particles()
        # Also update+draw death particles (active even when game is paused on game over)
        if self.game_over:
            self._update_death_particles(self.clock.get_time())
            self._draw_death_particles()

        # 7 – Screen-space overlays
        self._draw_damage_flash(now)
        self._draw_snatch_flash(now)
        self.screen.blit(self._vignette, (0, 0))

        # 8 – HUD (always topmost)
        self._draw_ui()
        self._draw_hud_hints(now)

        pygame.display.flip()

    # ══════════════════════════════════════════════════════════════════════════
    #  Menu drawing
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_menu(self) -> None:
        now = pygame.time.get_ticks()

        # ── Static background ──────────────────────────────────────────────────
        if self.menu_background is not None:
            self.screen.blit(self.menu_background, (0, 0))
        else:
            self.screen.fill((8, 14, 8))

        # ── Animated twinkling stars ───────────────────────────────────────────
        for (sx, sy, phase, spd, sr) in self._menu_star_phases:
            brightness = 0.35 + 0.65 * abs(math.sin(now * spd + phase))
            a = int(brightness * 200)
            star_s = pygame.Surface((sr * 2 + 2, sr * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(star_s, (int(180 * brightness), int(210 * brightness), int(140 * brightness), a),
                               (sr + 1, sr + 1), sr)
            self.screen.blit(star_s, (sx - sr - 1, sy - sr - 1))

        # ── Scrolling mist wisps ───────────────────────────────────────────────
        self._menu_mist_offset = (self._menu_mist_offset + 0.18) % (WINDOW_WIDTH + 400)
        mist_positions = [
            (int((160  + self._menu_mist_offset) % (WINDOW_WIDTH + 420)) - 210, WINDOW_HEIGHT - 105, 340, 32),
            (int((500  + self._menu_mist_offset * 0.65) % (WINDOW_WIDTH + 420)) - 210, WINDOW_HEIGHT - 88,  280, 24),
            (int((820  + self._menu_mist_offset * 0.40) % (WINDOW_WIDTH + 420)) - 210, WINDOW_HEIGHT - 98,  380, 28),
            (int((1100 + self._menu_mist_offset * 0.80) % (WINDOW_WIDTH + 420)) - 210, WINDOW_HEIGHT - 80,  260, 20),
        ]
        for mx_m, my_m, mw, mh in mist_positions:
            mist_s = pygame.Surface((mw, mh), pygame.SRCALPHA)
            pygame.draw.ellipse(mist_s, (18, 55, 18, 28), (0, 0, mw, mh))
            self.screen.blit(mist_s, (mx_m, my_m))

        # ── Animated fireflies ─────────────────────────────────────────────────
        for ff in self._menu_fireflies:
            # Move
            ff["x"] = (ff["x"] + ff["vx"]) % WINDOW_WIDTH
            ff["y"] = max(30.0, min(float(WINDOW_HEIGHT - 90), ff["y"] + ff["vy"]))
            if ff["y"] <= 30 or ff["y"] >= WINDOW_HEIGHT - 90:
                ff["vy"] *= -1
            # Gentle random drift
            ff["vx"] += random.uniform(-0.012, 0.012)
            ff["vy"] += random.uniform(-0.008, 0.008)
            ff["vx"] = max(-0.55, min(0.55, ff["vx"]))
            ff["vy"] = max(-0.35, min(0.35, ff["vy"]))

            # Flicker with individual phase + speed
            brightness = 0.15 + 0.85 * abs(math.sin(now * ff["speed"] + ff["phase"]))
            # Some frames — fully dark (off state)
            if brightness < 0.18:
                continue

            r, g, b = ff["color"]
            a = int(brightness * 220)
            rad = ff["radius"]
            fx, fy = int(ff["x"]), int(ff["y"])

            # Outer soft glow
            glow_r = rad + 5
            glow_s = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_s, (r, g, b, int(a * 0.25)), (glow_r, glow_r), glow_r)
            self.screen.blit(glow_s, (fx - glow_r, fy - glow_r))
            # Inner bright core
            core_s = pygame.Surface((rad * 2 + 2, rad * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(core_s, (r, g, b, a), (rad + 1, rad + 1), rad)
            # White hot centre
            if rad >= 3:
                pygame.draw.circle(core_s, (220, 255, 220, int(a * 0.7)), (rad + 1, rad + 1), max(1, rad - 1))
            self.screen.blit(core_s, (fx - rad - 1, fy - rad - 1))

        # ── Pulsing ambient glow behind logo ──────────────────────────────────
        pulse_glow = 0.55 + 0.45 * math.sin(now * 0.0018)
        glow_w, glow_h = 520, 200
        glow_surf = pygame.Surface((glow_w, glow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(glow_surf, (0, int(80 * pulse_glow), 0, int(38 * pulse_glow)),
                            (0, 0, glow_w, glow_h))
        self.screen.blit(glow_surf, (WINDOW_WIDTH // 2 - glow_w // 2, 60))

        # ── Logo ──────────────────────────────────────────────────────────────
        if self.menu_logo is not None:
            logo_rect = self.menu_logo.get_rect(center=(WINDOW_WIDTH // 2 + 24, 160))
            # Subtle logo pulse
            logo_scale = 1.0 + 0.012 * math.sin(now * 0.0022)
            if abs(logo_scale - 1.0) > 0.001:
                lw = int(self.menu_logo.get_width() * logo_scale)
                lh = int(self.menu_logo.get_height() * logo_scale)
                scaled_logo = pygame.transform.smoothscale(self.menu_logo, (lw, lh))
                logo_rect = scaled_logo.get_rect(center=(WINDOW_WIDTH // 2 + 24, 160))
                self.screen.blit(scaled_logo, logo_rect)
            else:
                self.screen.blit(self.menu_logo, logo_rect)

        # ── Buttons ───────────────────────────────────────────────────────────
        mx, my = pygame.mouse.get_pos()

        for btn_rect, label in [
            (self._play_button_rect, "Play"),
            (self._stats_button_rect, "Statistics"),
        ]:
            hovered = btn_rect.collidepoint(mx, my)
            pulse = 1.0 + 0.04 * math.sin(now * 0.005) if hovered else 1.0
            inflated = btn_rect.inflate(int((pulse - 1) * btn_rect.width), int((pulse - 1) * btn_rect.height))

            # Green-tinted button when hovered
            btn_surf = pygame.Surface((inflated.width, inflated.height), pygame.SRCALPHA)
            if hovered:
                btn_color = (220, 255, 220, 240)
                pygame.draw.rect(btn_surf, btn_color, (0, 0, inflated.width, inflated.height), border_radius=12)
                # Green glow rim
                pygame.draw.rect(btn_surf, (80, 255, 100, 80),
                                 (0, 0, inflated.width, inflated.height), border_radius=12, width=2)
            else:
                pygame.draw.rect(btn_surf, (255, 255, 255, 200),
                                 (0, 0, inflated.width, inflated.height), border_radius=12)
            self.screen.blit(btn_surf, inflated.topleft)

            text_color = (10, 45, 10) if hovered else (35, 35, 50)
            text = self.font.render(label, True, text_color)
            text_rect = text.get_rect(center=inflated.center)
            self.screen.blit(text, text_rect)

    def _draw_stats(self) -> None:
        heading = self.font.render("Statistics", True, (245, 245, 245))
        heading_rect = heading.get_rect(center=(WINDOW_WIDTH // 2, 140))
        self.screen.blit(heading, heading_rect)

        placeholder = self.small_font.render("This page is empty for now.", True, (200, 200, 220))
        placeholder_rect = placeholder.get_rect(center=(WINDOW_WIDTH // 2, 210))
        self.screen.blit(placeholder, placeholder_rect)

        note = self.small_font.render("Press Esc or Back to return.", True, (170, 170, 190))
        note_rect = note.get_rect(center=(WINDOW_WIDTH // 2, 250))
        self.screen.blit(note, note_rect)

        pygame.draw.rect(self.screen, (255, 255, 255), self._back_button_rect, border_radius=10)
        back_text = self.small_font.render("Back", True, (30, 30, 30))
        back_rect = back_text.get_rect(center=self._back_button_rect.center)
        self.screen.blit(back_text, back_rect)

    # ══════════════════════════════════════════════════════════════════════════
    #  Level geometry helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _assign_platform_styles(self) -> dict:
        """Assign a visual style to each floating platform based on its zone (x position)."""
        def style_for_x(x: int) -> str:
            if x < 1050:    return "log"        # Zone 0 — grass
            if x < 2050:    return "mushroom"   # Zone 1 — mossy
            if x < 3050:    return "ancient"    # Zone 2 — ancient
            if x < 4050:    return "stone"      # Zone 3 — volcanic
            return "crystal"                    # Zone 4 — crystal

        result = {}
        for i, block in enumerate(self.platforms):
            if block.height < GROUND_HEIGHT:
                result[i] = style_for_x(block.x)
        return result

    def _assign_ground_styles(self) -> list[str]:
        """Assign visual style to each ground segment — matches 7-segment layout."""
        # Segments: grass(0), mossy-low(1050), mossy-high(1320), mossy-high(1620),
        #           ancient(2050), volcanic(3050), crystal(4050)
        return ["grass", "mossy", "mossy", "mossy", "ancient", "volcanic", "crystal"]

    def _build_level(self) -> tuple[list[pygame.Rect], list[pygame.Rect], list[pygame.Rect]]:
        ground_y   = WINDOW_HEIGHT - GROUND_HEIGHT        # base ground Y (540)
        raised_y   = ground_y - 60                        # raised terrain
        high_y     = ground_y - 110                       # high raised terrain
        low_y      = ground_y + 28                        # sunken terrain (still on screen)

        # ══ GROUND SEGMENTS ══════════════════════════════════════════════════
        # Zone 0 — Grass      (x:    0 –  900)  flat start, wide and welcoming
        # Zone 1 — Mossy      (x: 1050 – 1900)  terraced: low chunk + two raised chunks
        #   1a lower terrace  (x: 1050 – 1270)
        #   1b mid terrace    (x: 1320 – 1570)  +60 up
        #   1c high terrace   (x: 1620 – 1900)  +110 up
        # Zone 2 — Ancient    (x: 2050 – 2820)  back to base, ruins/pillars
        # Zone 3 — Volcanic   (x: 3050 – 3820)  sunken, hot tone
        # Zone 4 — Crystal    (x: 4050 – 5000)  raised, long endgame stretch
        ground_segments = [
            # Zone 0 — wide flat grass start
            pygame.Rect(0,       ground_y, 900,  GROUND_HEIGHT),
            # Zone 1a — mossy low terrace
            pygame.Rect(1050,    raised_y, 220,  GROUND_HEIGHT),
            # Zone 1b — mossy mid terrace (step up)
            pygame.Rect(1320,    raised_y - 50, 250, GROUND_HEIGHT),
            # Zone 1c — mossy high terrace (step up again)
            pygame.Rect(1620,    high_y,  280,  GROUND_HEIGHT),
            # Zone 2 — ancient ruins, baseline
            pygame.Rect(2050,    ground_y, 770,  GROUND_HEIGHT),
            # Zone 3 — volcanic, slightly sunken
            pygame.Rect(3050,    low_y,   770,  GROUND_HEIGHT),
            # Zone 4 — crystal cave, raised
            pygame.Rect(4050,    raised_y, 950, GROUND_HEIGHT),
        ]

        # ══ FLOATING PLATFORMS ════════════════════════════════════════════════
        # Design principles:
        #  - Every pit has at least 2 stepping-stone platforms to cross it
        #  - Within each zone, platforms form a clear "high route" and "low route"
        #  - No platform is more than 130px higher than the previous reachable one
        #  - Platforms are wider (100–140px) for easier landing, spaced 140–200px apart
        #  - Zone heights are respected: platforms sit above their local ground
        jump_platforms = [
            # ── Zone 0: warm-up area, gentle climb ───────────────────────────
            # Left tower — easy warm-up
            pygame.Rect(120,  ground_y - 110, 130, 18),
            pygame.Rect(290,  ground_y - 190, 120, 18),
            pygame.Rect(450,  ground_y - 110, 130, 18),

            # Centre tower — optional taller challenge
            pygame.Rect(230,  ground_y - 270, 110, 18),
            pygame.Rect(370,  ground_y - 340, 120, 18),

            # Right-side low bridge leading toward pit 1
            pygame.Rect(640,  ground_y - 80,  120, 18),
            pygame.Rect(790,  ground_y - 140, 110, 18),  # extra bridge before pit

            # ── Pit 1 crossings (x: 900–1050) — two stepping stones ─────────
            pygame.Rect(900,  ground_y - 60,  110, 18),
            pygame.Rect(1000, raised_y - 30,  100, 18),

            # ── Zone 1a: stepping stones from low to mid terrace ─────────────
            pygame.Rect(1090, raised_y - 80,  120, 18),
            pygame.Rect(1200, raised_y - 170, 110, 18),

            # ── Zone 1b: mid terrace platforms ───────────────────────────────
            pygame.Rect(1340, raised_y - 100, 120, 18),
            pygame.Rect(1470, raised_y - 250, 110, 18),

            # ── Zone 1c: high terrace platforms ──────────────────────────────
            pygame.Rect(1645, high_y - 200,  120, 18),
            pygame.Rect(1790, high_y - 180,  110, 18),
            pygame.Rect(1900, high_y - 90,   120, 18),

            # ── Pit 2 crossings (x: 1900–2050) — two stepping stones ─────────
            pygame.Rect(1930, high_y - 50,   100, 18),
            pygame.Rect(2010, ground_y - 80, 100, 18),

            # ── Zone 2: ancient staircase, symmetric up-down ─────────────────
            pygame.Rect(2080, ground_y - 120, 130, 18),
            pygame.Rect(2250, ground_y - 230, 120, 18),
            pygame.Rect(2400, ground_y - 320, 130, 18),  # peak (widened)
            pygame.Rect(2560, ground_y - 230, 120, 18),
            pygame.Rect(2710, ground_y - 120, 130, 18),

            # ── Pit 3 crossings (x: 2820–3050) — two wide stepping stones ────
            pygame.Rect(2840, ground_y - 90,  120, 18),
            pygame.Rect(2970, low_y   - 60,   110, 18),

            # ── Zone 3: volcanic lower ground, irregular heights ──────────────
            pygame.Rect(3070, low_y - 130,   120, 18),
            pygame.Rect(3220, low_y - 210,   110, 18),
            pygame.Rect(3370, low_y - 140,   120, 18),
            pygame.Rect(3520, low_y - 230,   110, 18),
            pygame.Rect(3670, low_y - 150,   120, 18),

            # ── Pit 4 crossings (x: 3820–4050) — two stepping stones ─────────
            pygame.Rect(3840, low_y   - 80,   120, 18),
            pygame.Rect(3960, raised_y - 40,  110, 18),

            # ── Zone 4: crystal towers — dense vertical challenge ─────────────
            pygame.Rect(4080, raised_y - 200,  130, 18),
            pygame.Rect(4250, raised_y - 220, 120, 18),
            pygame.Rect(4410, raised_y - 330, 130, 18),  # peak 1 (widened)
            pygame.Rect(4560, raised_y - 220, 120, 18),
            pygame.Rect(4700, raised_y - 140, 130, 18),
            pygame.Rect(4840, raised_y - 270, 120, 18),  # peak 2
        ]

        # ══ OBSTACLES ════════════════════════════════════════════════════════
        # Wider, more varied, placed to force interesting movement choices
        obstacle_defs = [
            # Zone 0 — single wall, with breathing room between each
            (300,  28, 44, "wall"),
            (620,  24, 36, "wall"),

            # Zone 1a — single mossy pillar, not blocking full width
            # (1130, 20, 80, "pillar"),

            # Zone 1b — one column only
            (1500, 20, 95, "pillar"),

            # Zone 1c — single tall gate, off-centre
            (1720, 20, 120, "pillar"),

            # Zone 2 — ancient gate pair at entrance (spaced apart) + altar
            (2100, 22, 110, "ancient"),
            (2480, 20, 70,  "ancient"),

            # Zone 3 — volcanic rubble, widely spaced
            (3150, 26, 50, "volcanic"),
            (3480, 26, 60, "volcanic"),
            (3720, 24, 50, "volcanic"),

            # Zone 4 — crystal spires with clear gaps between each
            (4160, 18, 130, "crystal"),
            (4460, 18, 150, "crystal"),
            (4760, 18, 60, "crystal"),
        ]
        obstacles = []
        self._obstacle_styles: dict[int, str] = {}
        for idx, (ox, ow, oh, ost) in enumerate(obstacle_defs):
            ground_base = ground_y
            for seg in ground_segments:
                if seg.left <= ox <= seg.right:
                    ground_base = seg.top
                    break
            obstacles.append(pygame.Rect(ox, ground_base - oh, ow, oh))
            self._obstacle_styles[idx] = ost
        self._obstacle_rects = obstacles

        # ══ PITS ═════════════════════════════════════════════════════════════
        pits: list[pygame.Rect] = []
        segs_sorted = sorted(ground_segments, key=lambda r: r.left)
        for left_seg, right_seg in zip(segs_sorted, segs_sorted[1:]):
            pit_left  = left_seg.right
            pit_right = right_seg.left
            if pit_right > pit_left:
                pit_y = max(left_seg.top, right_seg.top)
                pit_h = WINDOW_HEIGHT - pit_y + 100
                pits.append(pygame.Rect(pit_left, pit_y, pit_right - pit_left, pit_h))

        return ground_segments + jump_platforms + obstacles, ground_segments, pits

    def _ground_top_at(self, x: int) -> int:
        for segment in self.ground_segments:
            if segment.left <= x <= segment.right:
                return segment.top
        return WINDOW_HEIGHT

    def _surface_tops_at(self, x: int) -> list[int]:
        return [block.top for block in self.platforms if block.left <= x <= block.right]

    def _get_flamethrower_rect(self) -> pygame.Rect:
        width = FLAMETHROWER_CONE_LENGTH
        height = FLAMETHROWER_CONE_HEIGHT
        y = self.player.rect.centery - height // 2
        if self.player.facing > 0:
            return pygame.Rect(self.player.rect.right - 6, y, width, height)
        return pygame.Rect(self.player.rect.left - width + 6, y, width, height)

    # ══════════════════════════════════════════════════════════════════════════
    #  Spawning helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _spawn_enemy(self) -> None:
        candidate = spawn_enemy_for_time(self.session_time, self.player.rect.centerx, WORLD_WIDTH)
        spawn_tops = self._surface_tops_at(candidate.rect.centerx)
        if not spawn_tops:
            nearest = min(
                self.platforms,
                key=lambda seg: abs(seg.centerx - candidate.rect.centerx),
            )
            candidate.rect.centerx = nearest.centerx
            spawn_tops = self._surface_tops_at(candidate.rect.centerx)

        candidate.rect.bottom = (
            random.choice(spawn_tops) if spawn_tops else self._ground_top_at(candidate.rect.centerx)
        )
        self.enemies.append(candidate)

    # ── Boss helpers ──────────────────────────────────────────────────────────

    def _spawn_boss(self) -> None:
        """Create the Queen Bee boss with escort insects (up to 5 total), recurring every 50 kills."""
        self._boss_spawned = True
        self._next_boss_threshold += BOSS_SPAWN_THRESHOLD  # schedule next wave
        ox = self.player.rect.centerx + random.choice([-1, 1]) * 600
        ox = max(100, min(WORLD_WIDTH - 200, ox))
        oy = self._ground_top_at(ox) - QueenBeeBoss.BOSS_HEIGHT
        self.boss = QueenBeeBoss(ox, oy)
        self._boss_announce_until_ms = pygame.time.get_ticks() + 3500
        # Keep at most 2 existing enemies, then fill up to 5 with fresh escort insects
        self.enemies = self.enemies[:2]
        escort_count = random.randint(3, 5) - len(self.enemies)
        for _ in range(escort_count):
            self._spawn_enemy()

    def _update_boss(self, now: int) -> None:
        """Update the boss, its stingers, and handle all damage interactions."""
        boss = self.boss
        fire = boss.update(self.player.rect, self.platforms, now)

        # Fire 3 spread stingers aimed at the player
        if fire:
            cx, cy = boss.rect.centerx, boss.rect.centery
            px, py = self.player.rect.centerx, self.player.rect.centery
            for angle_offset in (-18, 0, 18):
                rad = math.radians(angle_offset)
                dx = px - cx
                dy = py - cy
                dist = max(1.0, math.hypot(dx, dy))
                tx = int(cx + (dx / dist * math.cos(rad) - dy / dist * math.sin(rad)) * 200)
                ty = int(cy + (dx / dist * math.sin(rad) + dy / dist * math.cos(rad)) * 200)
                self._boss_stingers.append(BossStinger(cx, cy, tx, ty))
            # Shake screen slightly on attack
            self._shake_until_ms = now + 200
            self._shake_mag = 4

        # Update stingers and check player collision
        for st in self._boss_stingers:
            st.update()
            if st.check_impact(self.player.rect):
                self.player.on_hit(1)
                self._play_sound("hurt")
                self._on_player_damaged(now)
                self.logger.record_event("damage_taken", 1, now)
                st.rect.x = -99999   # mark for removal
        self._boss_stingers = [s for s in self._boss_stingers if not s.destroy()]

    def _on_boss_defeated(self, now: int) -> None:
        """VFX and state cleanup when the boss dies."""
        cx, cy = self.boss.rect.centerx, self.boss.rect.centery
        self._spawn_particles(
            cx, cy, count=80,
            colors=[(255, 200, 20), (255, 150, 0), (255, 255, 100),
                    (255, 80, 80), (255, 230, 60), (200, 255, 80)],
            speed=8.0, size=9.0, gravity=0.18, lifetime_ms=1100,
        )
        self._shake_until_ms = now + 700
        self._shake_mag = 14
        self._hud_hint = ("♛ QUEEN BEE DEFEATED! ♛", now + 4000, (255, 215, 0))
        self._boss_stingers.clear()
        # Resume normal enemy spawning after boss is dead
        self._boss_spawned = False

    def _handle_pit_fall(self, now: int) -> None:
        self.player.on_hit(1)
        self._play_sound("hurt")
        self._on_player_damaged(now)
        self.logger.record_event("damage_taken", 1, now)
        self.logger.record_event("ability_loss", "hit", now)
        self.logger.record_event("pit_fall", 1, now)
        respawn_top = self._ground_top_at(PIT_RESPAWN_X)
        self.player.rect.x = PIT_RESPAWN_X
        self.player.rect.bottom = respawn_top
        self.player.velocity_x = 0
        self.player.velocity_y = 0

    # ══════════════════════════════════════════════════════════════════════════
    #  Menu / stats management
    # ══════════════════════════════════════════════════════════════════════════

    def _create_menu_buttons(self) -> None:
        button_width = 260
        button_height = 64
        center_x = WINDOW_WIDTH // 2
        self._play_button_rect = pygame.Rect(center_x - button_width // 2, 320, button_width, button_height)
        self._stats_button_rect = pygame.Rect(center_x - button_width // 2, 400, button_width, button_height)
        self._back_button_rect = pygame.Rect(24, WINDOW_HEIGHT - 78, 140, 48)

    def _start_game(self) -> None:
        self._close_stats_window()
        self.__init__(self.screen)
        self.state = "playing"
        self._print_controls_tutorial()

    def _restart_game(self) -> None:
        self.__init__(self.screen)
        self.state = "playing"

    def _open_stats_window(self) -> None:
        self._close_stats_window()
        script = Path(__file__).resolve().parent.parent / "show_stats.py"
        self.stats_window = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _close_stats_window(self) -> None:
        if self.stats_window is not None:
            try:
                self.stats_window.terminate()
            except Exception:
                pass
            self.stats_window = None

    # ══════════════════════════════════════════════════════════════════════════
    #  Asset loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_heart_icons(self) -> dict[int, pygame.Surface]:
        icons: dict[int, pygame.Surface] = {}
        icon_dir = Path(__file__).resolve().parent.parent / "assets" / "icons"
        for idx in range(1, 6):
            icon_path = icon_dir / f"heart{idx}.png"
            if not icon_path.exists():
                continue
            image = pygame.image.load(str(icon_path)).convert_alpha()
            icons[idx] = pygame.transform.scale(image, (64, 64))
        return icons

    def _load_sounds(self) -> dict[str, pygame.mixer.Sound]:
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except pygame.error:
                return {}

        sound_dir = Path(__file__).resolve().parent.parent / "assets" / "sounds"
        files = {
            "star":      "star.mp3",
            "fire":      "fire.mp3",
            "ice":       "ice.mp3",
            "sword":     "sword.mp3",
            "snatch":    "snatch.mp3",
            "hurt":      "hurt.mp3",
            "footstep":  "footstep.mp3",
        }

        loaded: dict[str, pygame.mixer.Sound] = {}
        for key, filename in files.items():
            path = sound_dir / filename
            if not path.exists():
                continue
            try:
                loaded[key] = pygame.mixer.Sound(str(path))
            except pygame.error:
                continue
        return loaded

    def _play_sound(self, name: str, volume: float = 0.5) -> None:
        sound = self.sounds.get(name)
        if sound is None:
            return
        sound.set_volume(max(0.0, min(1.0, volume)))
        sound.play()

    def _print_controls_tutorial(self) -> None:
        print("Controls:")
        print("  Move:           A/D or Left/Right")
        print("  Jump:           W/Up  (multi-jump)")
        print("  Hover:          Hold Space")
        print("  Snatch enemy:   J  (no enemy held)")
        print("  Spit star ★:    J  (enemy held in mouth)")
        print("  Swallow power:  ↓ Down  (enemy held in mouth)")
        print("  Use ability:    K  (after swallowing)")
        print("  Hold K:         Flamethrower (if fire ability)")
        print("  Discard:        Q")