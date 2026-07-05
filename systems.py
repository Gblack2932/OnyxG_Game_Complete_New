from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

import pygame


@dataclass
class GameState:
    """Runtime state container used by systems to reduce mega-loop sprawl."""

    sprite_rect: pygame.Rect
    fireballs: List[pygame.Rect] = field(default_factory=list)
    side_bullets: List[dict] = field(default_factory=list)
    enemies: List = field(default_factory=list)
    enemy_bullets: List[pygame.Rect] = field(default_factory=list)
    aimed_bullets: List[dict] = field(default_factory=list)
    boss_bullets: List[pygame.Rect] = field(default_factory=list)
    boss_minions: List = field(default_factory=list)
    health_pickups: List[pygame.Rect] = field(default_factory=list)
    sativa_pickups: List[pygame.Rect] = field(default_factory=list)
    data_souls: List[pygame.Rect] = field(default_factory=list)
    score_popups: List = field(default_factory=list)

    score: int = 0
    health: int = 0
    signal_meter: int = 0
    signal_max: int = 100
    block_signal: int = 0
    block_signal_max: int = 100
    sativa_active: bool = False
    sativa_timer: int = 0
    iframe_timer: int = 0

    boss_active: bool = False
    boss_rect: Optional[pygame.Rect] = None


def handle_player_bullets_vs_enemies(
    state: GameState,
    perk_power_shot: bool,
    on_enemy_destroyed: Callable,
    on_minion_destroyed: Callable,
    on_damage_boss: Callable[[int], None],
) -> None:
    """Handle player projectile collisions with enemies, minions, and boss."""

    for f in state.fireballs[:]:
        for e in state.enemies[:]:
            if f.colliderect(e[0]):
                state.fireballs.remove(f)
                state.enemies.remove(e)
                on_enemy_destroyed(
                    e,
                    (255, 80, 255),
                    [(255, 200, 0), (255, 100, 0), (255, 50, 0)],
                    10,
                )
                break

    for f in state.fireballs[:]:
        for bm in state.boss_minions[:]:
            if f.colliderect(bm['rect']):
                if f in state.fireballs:
                    state.fireballs.remove(f)
                state.boss_minions.remove(bm)
                on_minion_destroyed(
                    bm,
                    (255, 120, 0),
                    [(255, 180, 0), (255, 80, 0), (200, 200, 255)],
                )
                break

    if state.boss_active and state.boss_rect is not None:
        for f in state.fireballs[:]:
            if state.boss_rect.colliderect(f):
                if f not in state.fireballs:
                    continue
                state.fireballs.remove(f)
                on_damage_boss(2 if perk_power_shot else 1)


def handle_side_bullets_vs_enemies(
    state: GameState,
    on_enemy_destroyed: Callable,
) -> None:
    """Handle side-bullet collisions with standard enemies."""

    for sb in state.side_bullets[:]:
        sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
        for e in state.enemies[:]:
            if sbr.colliderect(e[0]):
                if sb in state.side_bullets:
                    state.side_bullets.remove(sb)
                if e in state.enemies:
                    state.enemies.remove(e)
                on_enemy_destroyed(
                    e,
                    (0, 220, 255),
                    [(0, 200, 255), (0, 150, 255), (100, 230, 255)],
                    8,
                )
                break


def handle_boss_damage(
    state: GameState,
    perk_power_shot: bool,
    on_minion_destroyed: Callable,
    on_damage_boss: Callable[[int], None],
) -> None:
    """Handle side-bullet collisions with minions and boss."""

    for sb in state.side_bullets[:]:
        sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
        for bm in state.boss_minions[:]:
            if sbr.colliderect(bm['rect']):
                if sb in state.side_bullets:
                    state.side_bullets.remove(sb)
                state.boss_minions.remove(bm)
                on_minion_destroyed(
                    bm,
                    (0, 220, 255),
                    [(0, 200, 255), (0, 150, 255), (255, 180, 0)],
                )
                break

    if state.boss_active and state.boss_rect is not None:
        for sb in state.side_bullets[:]:
            sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
            if state.boss_rect.colliderect(sbr):
                if sb not in state.side_bullets:
                    continue
                state.side_bullets.remove(sb)
                on_damage_boss(2 if perk_power_shot else 1)


def handle_enemy_bullets_vs_player(state: GameState, on_damage_player: Callable[[], None]) -> None:
    """Handle all enemy projectile/body collisions against player."""

    for e in state.enemies[:]:
        if e[0].colliderect(state.sprite_rect):
            state.enemies.remove(e)
            on_damage_player()

    for b in state.enemy_bullets[:]:
        if b.colliderect(state.sprite_rect):
            state.enemy_bullets.remove(b)
            on_damage_player()

    for ab in state.aimed_bullets[:]:
        abr = pygame.Rect(int(ab['x']) - 4, int(ab['y']) - 6, 8, 12)
        if abr.colliderect(state.sprite_rect):
            state.aimed_bullets.remove(ab)
            on_damage_player()

    for bm in state.boss_minions[:]:
        if bm['rect'].colliderect(state.sprite_rect):
            state.boss_minions.remove(bm)
            on_damage_player()

    for b in state.boss_bullets[:]:
        if b.colliderect(state.sprite_rect):
            state.boss_bullets.remove(b)
            on_damage_player()


def handle_pickups(
    state: GameState,
    powerup_sound: Optional[pygame.mixer.Sound],
    sativa_sound: Optional[pygame.mixer.Sound],
    add_popup: Callable[[int, int, int, int, str, tuple], None],
) -> None:
    """Handle health, sativa, and data-soul pickup collection."""

    for p in state.health_pickups[:]:
        if p.colliderect(state.sprite_rect):
            state.health_pickups.remove(p)
            state.health = min(state.health + 1, 8)
            add_popup(state.sprite_rect.centerx, state.sprite_rect.top, 45, 45, '+1 HP', (0, 255, 80))
            if powerup_sound:
                pygame.mixer.find_channel(True).play(powerup_sound)

    for p in state.sativa_pickups[:]:
        if p.colliderect(state.sprite_rect):
            state.sativa_pickups.remove(p)
            state.health = 8
            state.sativa_active = True
            state.sativa_timer = 600
            state.iframe_timer = 300
            add_popup(state.sprite_rect.centerx, state.sprite_rect.top - 20, 75, 75, '★ SATIVA MODE ★', (0, 255, 120))
            if sativa_sound:
                sativa_sound.play()

    for ds in state.data_souls[:]:
        if ds.colliderect(state.sprite_rect):
            state.data_souls.remove(ds)
            state.score += 250
            state.signal_meter = min(state.signal_max, state.signal_meter + 8)
            state.block_signal = min(state.block_signal_max, state.block_signal + 2)
            add_popup(state.sprite_rect.centerx, state.sprite_rect.top, 45, 45, 'DATA SOUL +250', (180, 80, 255))
            if powerup_sound:
                pygame.mixer.find_channel(True).play(powerup_sound)
