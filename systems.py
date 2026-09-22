from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import pygame

ScoreRow = List[Any]
ScoreTable = List[ScoreRow]
SideBulletMap = Dict[str, float]
AimedBulletMap = Dict[str, float]
EnemyDestroyedCallback = Callable[[Any, Tuple[int, int, int], List[Tuple[int, int, int]], int], None]
MinionDestroyedCallback = Callable[[Any, Tuple[int, int, int], List[Tuple[int, int, int]]], None]
PopupCallback = Callable[[int, int, int, int, str, Tuple[int, int, int]], None]


@dataclass
class GameState:
    """Runtime state container used by systems to reduce mega-loop sprawl."""

    sprite_rect: pygame.Rect
    fireballs: List[pygame.Rect] = field(default_factory=list)
    side_bullets: List[SideBulletMap] = field(default_factory=list)
    enemies: List[Any] = field(default_factory=list)
    enemy_bullets: List[pygame.Rect] = field(default_factory=list)
    aimed_bullets: List[AimedBulletMap] = field(default_factory=list)
    boss_bullets: List[pygame.Rect] = field(default_factory=list)
    boss_minions: List[Any] = field(default_factory=list)
    health_pickups: List[pygame.Rect] = field(default_factory=list)
    sativa_pickups: List[pygame.Rect] = field(default_factory=list)
    data_souls: List[pygame.Rect] = field(default_factory=list)
    score_popups: List[Any] = field(default_factory=list)

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
    on_enemy_destroyed: EnemyDestroyedCallback,
    on_minion_destroyed: MinionDestroyedCallback,
    on_damage_boss: Callable[[int], None],
) -> None:
    """Handle player projectile collisions with enemies, minions, and boss.

    Index-set marking: each phase marks dead indices; a single filter pass
    at the end removes them — no O(n) list.remove() scans inside loops.
    """
    dead_fb: set = set()
    dead_en: set = set()
    dead_bm: set = set()

    # Phase 1 — fireballs vs standard enemies
    for i, f in enumerate(state.fireballs):
        if i in dead_fb:
            continue
        for j, e in enumerate(state.enemies):
            if j in dead_en:
                continue
            if f.colliderect(e[0]):
                dead_fb.add(i)
                dead_en.add(j)
                on_enemy_destroyed(e, (255, 80, 255), [(255, 200, 0), (255, 100, 0), (255, 50, 0)], 10)
                break

    # Phase 2 — fireballs vs boss minions
    for i, f in enumerate(state.fireballs):
        if i in dead_fb:
            continue
        for j, bm in enumerate(state.boss_minions):
            if j in dead_bm:
                continue
            if f.colliderect(bm['rect']):
                dead_fb.add(i)
                dead_bm.add(j)
                on_minion_destroyed(bm, (255, 120, 0), [(255, 180, 0), (255, 80, 0), (200, 200, 255)])
                break

    # Phase 3 — fireballs vs boss
    if state.boss_active and state.boss_rect is not None:
        for i, f in enumerate(state.fireballs):
            if i in dead_fb:
                continue
            if state.boss_rect.colliderect(f):
                dead_fb.add(i)
                on_damage_boss(2 if perk_power_shot else 1)

    # Single-pass filter — O(n), no scanning
    state.fireballs    = [f  for i, f  in enumerate(state.fireballs)    if i not in dead_fb]
    state.enemies      = [e  for j, e  in enumerate(state.enemies)      if j not in dead_en]
    state.boss_minions = [bm for j, bm in enumerate(state.boss_minions) if j not in dead_bm]


def handle_side_bullets_vs_enemies(
    state: GameState,
    on_enemy_destroyed: EnemyDestroyedCallback,
) -> None:
    """Handle side-bullet collisions with standard enemies."""
    dead_sb: set = set()
    dead_en: set = set()

    for i, sb in enumerate(state.side_bullets):
        if i in dead_sb:
            continue
        sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
        for j, e in enumerate(state.enemies):
            if j in dead_en:
                continue
            if sbr.colliderect(e[0]):
                dead_sb.add(i)
                dead_en.add(j)
                on_enemy_destroyed(e, (0, 220, 255), [(0, 200, 255), (0, 150, 255), (100, 230, 255)], 8)
                break

    state.side_bullets = [sb for i, sb in enumerate(state.side_bullets) if i not in dead_sb]
    state.enemies      = [e  for j, e  in enumerate(state.enemies)      if j not in dead_en]


def handle_boss_damage(
    state: GameState,
    perk_power_shot: bool,
    on_minion_destroyed: MinionDestroyedCallback,
    on_damage_boss: Callable[[int], None],
) -> None:
    """Handle side-bullet collisions with minions and boss."""
    dead_sb: set = set()
    dead_bm: set = set()

    # Side bullets vs boss minions
    for i, sb in enumerate(state.side_bullets):
        if i in dead_sb:
            continue
        sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
        for j, bm in enumerate(state.boss_minions):
            if j in dead_bm:
                continue
            if sbr.colliderect(bm['rect']):
                dead_sb.add(i)
                dead_bm.add(j)
                on_minion_destroyed(bm, (0, 220, 255), [(0, 200, 255), (0, 150, 255), (255, 180, 0)])
                break

    # Side bullets vs boss
    if state.boss_active and state.boss_rect is not None:
        for i, sb in enumerate(state.side_bullets):
            if i in dead_sb:
                continue
            sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
            if state.boss_rect.colliderect(sbr):
                dead_sb.add(i)
                on_damage_boss(2 if perk_power_shot else 1)

    state.side_bullets = [sb for i, sb in enumerate(state.side_bullets) if i not in dead_sb]
    state.boss_minions = [bm for j, bm in enumerate(state.boss_minions) if j not in dead_bm]


def handle_enemy_bullets_vs_player(state: GameState, on_damage_player: Callable[[], None]) -> None:
    """Handle all enemy projectile/body collisions against player.

    Single O(n) pass per list — no list.remove() scans, no [:]  copies.
    """
    new_enemies: list = []
    for e in state.enemies:
        if e[0].colliderect(state.sprite_rect):
            on_damage_player()
        else:
            new_enemies.append(e)
    state.enemies = new_enemies

    new_eb: list = []
    for b in state.enemy_bullets:
        if b.colliderect(state.sprite_rect):
            on_damage_player()
        else:
            new_eb.append(b)
    state.enemy_bullets = new_eb

    new_ab: list = []
    for ab in state.aimed_bullets:
        abr = pygame.Rect(int(ab['x']) - 4, int(ab['y']) - 6, 8, 12)
        if abr.colliderect(state.sprite_rect):
            on_damage_player()
        else:
            new_ab.append(ab)
    state.aimed_bullets = new_ab

    new_bm: list = []
    for bm in state.boss_minions:
        if bm['rect'].colliderect(state.sprite_rect):
            on_damage_player()
        else:
            new_bm.append(bm)
    state.boss_minions = new_bm

    new_bb: list = []
    for b in state.boss_bullets:
        if b.colliderect(state.sprite_rect):
            on_damage_player()
        else:
            new_bb.append(b)
    state.boss_bullets = new_bb


def handle_pickups(
    state: GameState,
    powerup_sound: Optional[pygame.mixer.Sound],
    sativa_sound: Optional[pygame.mixer.Sound],
    add_popup: PopupCallback,
) -> None:
    """Handle health, sativa, and data-soul pickup collection."""
    new_hp: list = []
    for p in state.health_pickups:
        if p.colliderect(state.sprite_rect):
            state.health = min(state.health + 1, 8)
            add_popup(state.sprite_rect.centerx, state.sprite_rect.top, 45, 45, '+1 HP', (0, 255, 80))
            if powerup_sound:
                pygame.mixer.find_channel(True).play(powerup_sound)
        else:
            new_hp.append(p)
    state.health_pickups = new_hp

    new_sv: list = []
    for p in state.sativa_pickups:
        if p.colliderect(state.sprite_rect):
            state.health = 8
            state.sativa_active = True
            state.sativa_timer = 600
            state.iframe_timer = 300
            add_popup(state.sprite_rect.centerx, state.sprite_rect.top - 20, 75, 75, '★ HYDRATED ★', (0, 255, 120))
            if sativa_sound:
                sativa_sound.play()
        else:
            new_sv.append(p)
    state.sativa_pickups = new_sv

    new_ds: list = []
    for ds in state.data_souls:
        if ds.colliderect(state.sprite_rect):
            state.score += 250
            state.signal_meter = min(state.signal_max, state.signal_meter + 8)
            state.block_signal = min(state.block_signal_max, state.block_signal + 2)
            add_popup(state.sprite_rect.centerx, state.sprite_rect.top, 45, 45, 'DATA SOUL +250', (180, 80, 255))
            if powerup_sound:
                pygame.mixer.find_channel(True).play(powerup_sound)
        else:
            new_ds.append(ds)
    state.data_souls = new_ds


def resolve_score_file(
    base_dir: str,
    ladder_choice: str,
    legacy_file: str,
    v2_file: str,
) -> Tuple[str, str]:
    """Return selected leaderboard file path and display label."""
    if str(ladder_choice).lower() == 'legacy':
        return os.path.join(base_dir, legacy_file), 'LEGACY'
    return os.path.join(base_dir, v2_file), 'V2'


def normalize_scores(raw_scores: ScoreTable, entries: int, default_name: str) -> ScoreTable:
    """Return canonical top-score rows in [score, initials, timestamp] format."""
    normalized: ScoreTable = []
    for row in raw_scores:
        try:
            score = max(0, int(row[0]))
        except (TypeError, ValueError, IndexError):
            score = 0

        try:
            name = str(row[1]).strip().upper()[:3]
        except (TypeError, ValueError, IndexError):
            name = ''

        try:
            timestamp = str(row[2]).strip()
        except (TypeError, ValueError, IndexError):
            timestamp = ''

        if not name:
            name = default_name

        normalized.append([score, name, timestamp])

    normalized.sort(key=lambda row: row[0], reverse=True)
    normalized = normalized[:entries]
    while len(normalized) < entries:
        normalized.append([0, default_name, ''])
    return normalized


def load_scores(hs_file: str, entries: int, default_name: str) -> ScoreTable:
    """Load leaderboard rows from file, tolerating old 2-column format."""
    scores = [[0, default_name, ''] for _ in range(entries)]

    try:
        with open(hs_file) as handle:
            loaded: ScoreTable = []
            for line in handle.read().strip().splitlines()[:entries]:
                parts = line.strip().split()
                if not parts:
                    continue
                try:
                    score = int(parts[0])
                    name = parts[1][:3].upper() if len(parts) > 1 else default_name
                    timestamp = parts[2] if len(parts) > 2 else ''
                    loaded.append([score, name, timestamp])
                except ValueError:
                    print(f"Warning: skipping malformed high score row: {line!r}")
        return normalize_scores(loaded, entries, default_name)
    except Exception as err:
        print(f"Warning: high score load failed: {err}")
        return normalize_scores(scores, entries, default_name)


def save_scores(hs_file: str, scores: ScoreTable) -> None:
    """Persist leaderboard rows as score/initials/timestamp."""
    with open(hs_file, 'w') as handle:
        handle.write('\n'.join(f'{row[0]} {row[1]} {row[2]}' for row in scores))


def current_score_timestamp() -> str:
    """Return local timestamp for leaderboard persistence (ISO-like, no spaces)."""
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def display_score_timestamp(value: str) -> str:
    """Convert persisted timestamp into compact UI-safe text."""
    if not value:
        return ''
    return value.replace('T', ' ')[:16]


def build_replay_log_path(base_dir: str) -> str:
    """Build a unique file path for the current run replay action log."""
    replay_dir = os.path.join(base_dir, 'replays')
    os.makedirs(replay_dir, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(replay_dir, f'replay_{stamp}.log')


def append_replay_event(events: List[str], frame: int, event_type: str, payload: str = '') -> None:
    """Append a compact replay event line: frame|event|payload."""
    safe_payload = payload.replace('\n', ' ').strip()
    events.append(f"{frame}|{event_type}|{safe_payload}")


def save_replay_log(path: str, events: List[str]) -> None:
    """Persist replay events to disk as a readable action log."""
    with open(path, 'w') as handle:
        handle.write('# OnyxG Replay Action Log\n')
        handle.write('# frame|event|payload\n')
        handle.write('\n'.join(events))
