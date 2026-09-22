#!/usr/bin/env python3
"""
Onyx G vs Space Drones — Main Game Loop
A retro-arcade shmup with procedural boss AI, combo scoring, and roguelike progression.

Architecture:
  - constants.py      All game config, difficulty scaling, tuning
  - entities.py       Typed entity classes (Enemy, Bullet, Particle, etc.)
  - systems.py        Collision resolution, scoring, replay, leaderboard I/O
  - score.py          Rank calculation

Animation system (PlayerSpriteAnimator):
  Uses LeftAnimatons.png (left-facing) + RightAnimations.png (right-facing) as
  the primary source.  Falls back to FlyLeftAndRight.png, then pygame transforms.
  9 animation rows: idle, run, run+shoot, stand+shoot, shoot-up, hover,
  jetpack-fly, jetpack+shoot, jetpack+shoot-up.

Audio channels:
  0 — impact (enemy/player hits)    1 — signal burst
  2 — run footsteps (looping)       3 — jetpack thrust (looping)
  music — pygame.mixer.music (background track per level)
"""

from __future__ import annotations
import array
from collections import deque
import math
import os
import random
import sys
import traceback
from typing import List, Dict, Tuple, Optional, Any

import pygame


import constants as cfg
from entities import (
    Enemy, BossMinionEnemy, Bullet, SideBullet, AimedBullet, BossBullet,
    Particle, ScorePopup, HealthPickup, SativaPickup, DataSoul, Boss
)
from score import calculate_rank
from systems import (
    append_replay_event,
    build_replay_log_path,
    GameState,
    current_score_timestamp,
    display_score_timestamp,
    handle_boss_damage,
    handle_enemy_bullets_vs_player,
    load_scores,
    normalize_scores,
    handle_pickups,
    handle_player_bullets_vs_enemies,
    resolve_score_file,
    save_replay_log,
    save_scores,
    handle_side_bullets_vs_enemies,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Accessibility: reduce flash intensity/frequency for photosensitive players.
PHOTOSENSITIVE_SAFE_MODE = True

# Alias constants for backward compatibility
_COL_FIREBALL = cfg.COL_FIREBALL
_COL_EBULLET = cfg.COL_EBULLET
_COL_BBULLET = cfg.COL_BBULLET
_COL_BAR_BG = cfg.COL_BAR_BG
_COL_BAR_FG = cfg.COL_BAR_FG
_COL_WHITE = cfg.COL_WHITE
_COL_RED = cfg.COL_RED
_COL_PICKUP = cfg.COL_PICKUP


def _build_dir_map() -> Dict[str, str]:
    """Build case-insensitive directory map for cross-platform asset loading."""
    return {e.lower(): e for e in os.listdir(BASE_DIR)}


def load_image(dir_map: Dict[str, str], filename: str, size: Tuple[int, int]) -> pygame.Surface:
    entry = dir_map.get(filename.lower())
    if entry:
        try:
            img = pygame.image.load(os.path.join(BASE_DIR, entry)).convert_alpha()
            return pygame.transform.scale(img, size)
        except pygame.error as err:
            print(f"⚠️ Failed to load {filename}: {err}")
    print(f"⚠️ Missing asset: {filename}. Using placeholder.")
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((255, 0, 255, 255))
    return surf


def load_image_cover(dir_map: Dict[str, str], filename: str, size: Tuple[int, int]) -> pygame.Surface:
    """Load an image scaled to cover the target rect without distorting aspect ratio."""
    entry = dir_map.get(filename.lower())
    if entry:
        try:
            img = pygame.image.load(os.path.join(BASE_DIR, entry)).convert_alpha()
            src_w, src_h = img.get_size()
            dst_w, dst_h = size
            scale = max(dst_w / max(1, src_w), dst_h / max(1, src_h))
            scaled_size = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
            scaled = pygame.transform.smoothscale(img, scaled_size)
            x_off = (scaled_size[0] - dst_w) // 2
            y_off = (scaled_size[1] - dst_h) // 2
            surf = pygame.Surface(size, pygame.SRCALPHA)
            surf.blit(scaled, (-x_off, -y_off))
            return surf
        except pygame.error as err:
            print(f"⚠️ Failed to load {filename}: {err}")
    print(f"⚠️ Missing asset: {filename}. Using placeholder.")
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((255, 0, 255, 255))
    return surf


def load_image_tight(dir_map: Dict[str, str], filename: str, size: Tuple[int, int],
                     bg_tol: int = 42) -> pygame.Surface:
    """Load an image, remove edge-connected background, and tightly crop before scaling."""
    entry = dir_map.get(filename.lower())
    if entry:
        try:
            img = pygame.image.load(os.path.join(BASE_DIR, entry)).convert_alpha()

            width, height = img.get_size()

            # Use corner samples as background references (works for white/checkerboard exports).
            bg_refs = [
                img.get_at((0, 0))[:3],
                img.get_at((width - 1, 0))[:3],
                img.get_at((0, height - 1))[:3],
                img.get_at((width - 1, height - 1))[:3],
            ]

            def _is_bg(px: int, py: int) -> bool:
                r, g, b, a = img.get_at((px, py))
                if a <= 8:
                    return True
                # Treat low-saturation gray gradients as removable background.
                cmax = max(r, g, b)
                cmin = min(r, g, b)
                if (cmax - cmin) <= 30 and 10 <= cmax <= 245:
                    return True
                # Treat near-corner colors as background so only the bottle remains.
                for br, bg, bb in bg_refs:
                    if abs(r - br) + abs(g - bg) + abs(b - bb) <= bg_tol:
                        return True
                return False

            # Remove only edge-connected background pixels so interior highlights stay intact.
            q = deque()
            seen = set()
            for x in range(width):
                q.append((x, 0))
                q.append((x, height - 1))
            for y in range(height):
                q.append((0, y))
                q.append((width - 1, y))

            while q:
                px, py = q.popleft()
                if (px, py) in seen:
                    continue
                seen.add((px, py))
                if not _is_bg(px, py):
                    continue
                img.set_at((px, py), (255, 255, 255, 0))

                if px > 0:
                    q.append((px - 1, py))
                if px + 1 < width:
                    q.append((px + 1, py))
                if py > 0:
                    q.append((px, py - 1))
                if py + 1 < height:
                    q.append((px, py + 1))

            trim_rect = img.get_bounding_rect(min_alpha=1)
            if trim_rect.width > 0 and trim_rect.height > 0:
                img = img.subsurface(trim_rect).copy()

            return pygame.transform.smoothscale(img, size)
        except pygame.error as err:
            print(f"⚠️ Failed to load {filename}: {err}")
    print(f"⚠️ Missing asset: {filename}. Using placeholder.")
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((255, 0, 255, 255))
    return surf


def load_drone_sheet_sprites(dir_map: Dict[str, str], filename: str,
                              size: Tuple[int, int] = (44, 44)) -> list:
    """Crop 3 drone sprites from the Level 2 sheet and strip the blue background."""
    # Approximate crop rects for each drone in the 1448x1086 sheet
    CROPS = [
        (20,  15, 490, 510),   # top-left  — red spike drone
        (385, 490, 540, 560),  # bottom-center — tank drone
        (760, 15,  660, 690),  # right         — green gem drone
    ]
    entry = dir_map.get(filename.lower())
    results = []
    if entry:
        try:
            sheet = pygame.image.load(os.path.join(BASE_DIR, entry)).convert()
            for (cx, cy, cw, ch) in CROPS:
                crop_surf = pygame.Surface((cw, ch))
                crop_surf.blit(sheet, (0, 0), (cx, cy, cw, ch))
                small = pygame.transform.smoothscale(crop_surf, size)
                # Per-pixel background removal on the small surface (only 44×44 = 1936 px)
                out = small.convert_alpha()
                bg_r, bg_g, bg_b = small.get_at((0, 0))[:3]
                for py in range(size[1]):
                    for px in range(size[0]):
                        r, g, b = out.get_at((px, py))[:3]
                        diff = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)
                        if diff < 90:
                            out.set_at((px, py), (0, 0, 0, 0))
                results.append(out)
        except pygame.error as err:
            print(f"⚠️ Failed to load drone sheet {filename}: {err}")
    # Fallback: return placeholders so the list always has 3 entries
    while len(results) < 3:
        ph = pygame.Surface(size, pygame.SRCALPHA)
        ph.fill((180, 60, 60, 200))
        results.append(ph)
    return results


def load_level4_enemy_sprites(dir_map: Dict[str, str],
                              filenames: List[str],
                              size: Tuple[int, int] = (44, 44)) -> list:
    """Load Level 4 enemy variants from a two-character promo image.

    The provided art has two enemy units on a shared background. This loader
    slices left/right halves and removes edge-connected background so each unit
    can be reused as an in-game sprite.
    """
    path = None
    for name in filenames:
        path = find_file(dir_map, name)
        if path:
            break

    if not path:
        return []

    try:
        src = pygame.image.load(path).convert_alpha()
    except pygame.error as err:
        print(f"⚠️ Failed to load Level 4 enemies: {err}")
        return []

    w, h = src.get_size()
    halves = [
        src.subsurface(pygame.Rect(0, 0, w // 2, h)).copy(),
        src.subsurface(pygame.Rect(w // 2, 0, w - (w // 2), h)).copy(),
    ]

    out = []
    for half in halves:
        hw, hh = half.get_size()
        corner_refs = [
            half.get_at((0, 0))[:3],
            half.get_at((hw - 1, 0))[:3],
            half.get_at((0, hh - 1))[:3],
            half.get_at((hw - 1, hh - 1))[:3],
        ]

        def _is_bg(px: int, py: int) -> bool:
            r, g, b, a = half.get_at((px, py))
            if a <= 8:
                return True
            for br, bg, bb in corner_refs:
                if abs(r - br) + abs(g - bg) + abs(b - bb) <= 72:
                    return True
            return False

        q = deque()
        seen = set()
        for x in range(hw):
            q.append((x, 0))
            q.append((x, hh - 1))
        for y in range(hh):
            q.append((0, y))
            q.append((hw - 1, y))

        while q:
            px, py = q.popleft()
            if (px, py) in seen:
                continue
            seen.add((px, py))
            if not _is_bg(px, py):
                continue

            half.set_at((px, py), (0, 0, 0, 0))
            if px > 0:
                q.append((px - 1, py))
            if px + 1 < hw:
                q.append((px + 1, py))
            if py > 0:
                q.append((px, py - 1))
            if py + 1 < hh:
                q.append((px, py + 1))

        trim = half.get_bounding_rect(min_alpha=1)
        if trim.width > 0 and trim.height > 0:
            half = half.subsurface(trim).copy()

        out.append(pygame.transform.smoothscale(half, size))

    return out


def load_player_pose_image(dir_map: Dict[str, str], filename: str, size: Tuple[int, int]) -> pygame.Surface:
    """
    Load and process a full-body player sprite pose.
    
    - Removes edge-connected background pixels (baked black/white)
    - Crops transparent padding
    - Fills interior holes to maintain silhouette
    
    Args:
        dir_map: Case-insensitive asset directory map
        filename: Asset filename to load
        size: Target (width, height) to scale to
        
    Returns:
        Processed pygame.Surface ready for gameplay
    """
    entry = dir_map.get(filename.lower())

    if entry:
        try:
            img = pygame.image.load(os.path.join(BASE_DIR, entry)).convert_alpha()

            width, height = img.get_size()

            def _is_edge_background(px, py):
                r, g, b, a = img.get_at((px, py))
                is_dark = r <= 1 and g <= 1 and b <= 1
                is_light = r >= 245 and g >= 245 and b >= 245
                return a and (is_dark or is_light)

            # Remove only edge-connected background pixels so interior details survive.
            edge_stack = []
            visited = set()

            for x in range(width):
                edge_stack.append((x, 0))
                edge_stack.append((x, height - 1))
            for y in range(height):
                edge_stack.append((0, y))
                edge_stack.append((width - 1, y))

            while edge_stack:
                px, py = edge_stack.pop()
                if (px, py) in visited:
                    continue
                visited.add((px, py))

                if not _is_edge_background(px, py):
                    continue

                img.set_at((px, py), (0, 0, 0, 0))

                if px > 0:
                    edge_stack.append((px - 1, py))
                if px + 1 < width:
                    edge_stack.append((px + 1, py))
                if py > 0:
                    edge_stack.append((px, py - 1))
                if py + 1 < height:
                    edge_stack.append((px, py + 1))

            # Crop away transparent padding around the character.
            trim_rect = img.get_bounding_rect(min_alpha=1)

            if trim_rect.width > 0 and trim_rect.height > 0:
                img = img.subsurface(trim_rect).copy()

            # Preserve outer transparency, but fill transparent holes trapped
            # inside the player silhouette so they don't read as see-through.
            fill_w, fill_h = img.get_size()
            transparent_stack = []
            outer_transparent = set()

            for x in range(fill_w):
                transparent_stack.append((x, 0))
                transparent_stack.append((x, fill_h - 1))
            for y in range(fill_h):
                transparent_stack.append((0, y))
                transparent_stack.append((fill_w - 1, y))

            while transparent_stack:
                px, py = transparent_stack.pop()
                if (px, py) in outer_transparent:
                    continue
                if img.get_at((px, py))[3] != 0:
                    continue

                outer_transparent.add((px, py))

                if px > 0:
                    transparent_stack.append((px - 1, py))
                if px + 1 < fill_w:
                    transparent_stack.append((px + 1, py))
                if py > 0:
                    transparent_stack.append((px, py - 1))
                if py + 1 < fill_h:
                    transparent_stack.append((px, py + 1))

            for y in range(fill_h):
                for x in range(fill_w):
                    if img.get_at((x, y))[3] == 0 and (x, y) not in outer_transparent:
                        img.set_at((x, y), (0, 0, 0, 255))

            darken_amount = 18
            dark_w, dark_h = img.get_size()
            for y in range(dark_h):
                for x in range(dark_w):
                    r, g, b, a = img.get_at((x, y))
                    if a:
                        img.set_at(
                            (x, y),
                            (max(0, r - darken_amount), max(0, g - darken_amount), max(0, b - darken_amount), a)
                        )

            return pygame.transform.scale(img, size)

        except pygame.error as err:
            print(f"⚠️ Failed to load {filename}: {err}")

    print(f"⚠️ Missing asset: {filename}. Using placeholder.")
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((255, 0, 255, 255))
    return surf


def _cut_sheet_frames(
    sheet: pygame.Surface,
    rects: List[Tuple[int, int, int, int]],
    target_size: Tuple[int, int],
) -> Tuple[pygame.Surface, ...]:
    """
    Slice frames from an RGBA sprite sheet, clean up, and scale.

    Steps per rect:
      1. Subsurface copy — isolates the frame region.
      2. Edge flood-fill — removes opaque near-black label-box borders.
         Safe on transparent-bg sheets (alpha=0 pixels are skipped).
      3. Content crop — trims fully-transparent rows/cols from all sides.
      4. Aspect-ratio-preserving scale — fits within target_size without distortion.

    Used for both FlyLeftAndRight.png (dark label boxes) and the newer
    LeftAnimatons.png / RightAnimations.png (transparent backgrounds).
    """
    tw, th = target_size
    result = []
    for (fx, fy, fw, fh) in rects:
        frame = sheet.subsurface(pygame.Rect(fx, fy, fw, fh)).copy()
        fw2, fh2 = frame.get_size()

        # Edge-flood-fill: remove opaque near-black label-box backgrounds.
        # True background has alpha ≈ 0; character clothing is never edge-connected.
        stack = (
            [(x, 0) for x in range(fw2)]
            + [(x, fh2 - 1) for x in range(fw2)]
            + [(0, y) for y in range(fh2)]
            + [(fw2 - 1, y) for y in range(fh2)]
        )
        visited: set = set()
        while stack:
            px, py = stack.pop()
            if (px, py) in visited:
                continue
            visited.add((px, py))
            r, g, b, a = frame.get_at((px, py))
            if a < 150:
                continue        # transparent / semi-transparent → skip
            if r > 20 or g > 20 or b > 20:
                continue        # coloured character pixel → stop
            frame.set_at((px, py), (0, 0, 0, 0))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = px + dx, py + dy
                if 0 <= nx < fw2 and 0 <= ny < fh2 and (nx, ny) not in visited:
                    stack.append((nx, ny))

        # Crop transparent padding.
        trim = frame.get_bounding_rect(min_alpha=10)
        if trim.width > 0 and trim.height > 0:
            frame = frame.subsurface(trim).copy()

        # Scale to fit within target_size preserving aspect ratio.
        cw, ch = frame.get_size()
        if cw > 0 and ch > 0:
            scale = min(tw / cw, th / ch)
            nw = max(1, int(cw * scale))
            nh = max(1, int(ch * scale))
            frame = pygame.transform.smoothscale(frame, (nw, nh))

        result.append(frame)
    return tuple(result)


class PlayerSpriteAnimator:
    """
    Player sprite animation system.
    Priority: LeftAnimatons.png + RightAnimations.png > FlyLeftAndRight.png > transform fallback.
    """

    _RUN_CYCLE_FRAMES       = 4   # game frames per keyframe — run
    _RUN_SHOOT_CYCLE_FRAMES = 3   # faster during run + shoot
    _FLY_CYCLE_FRAMES       = 5   # hover cycle
    _FLY_SHOOT_CYCLE_FRAMES = 4   # fly + shoot
    _SHOOT_CYCLE_FRAMES     = 3   # upward / hit flash

    def __init__(
        self,
        idle_image: pygame.Surface,
        shoot_image: pygame.Surface,
        sheet: Optional[pygame.Surface] = None,
        lsheet: Optional[pygame.Surface] = None,
        rsheet: Optional[pygame.Surface] = None,
    ) -> None:
        """Bake every animation frame once at startup."""

        left_facing_idle = pygame.transform.flip(idle_image, True, False)
        shoot_right_base = pygame.transform.flip(shoot_image, True, False)

        def _rot(src: pygame.Surface, angle: float) -> pygame.Surface:
            return pygame.transform.rotate(src, angle)

        def _run_frame(src: pygame.Surface, angle: float, yscale: float) -> pygame.Surface:
            rotated = pygame.transform.rotate(src, angle)
            rw, rh = rotated.get_size()
            return pygame.transform.scale(rotated, (rw, max(1, int(rh * yscale))))

        # ── Target sizes ────────────────────────────────────────────────────
        STAND = cfg.PLAYER_SIZE                                      # (80, 160)
        FLY = (int(cfg.PLAYER_SIZE[0] * 2.0), int(cfg.PLAYER_SIZE[1] * 0.65))

        if lsheet is not None and rsheet is not None:
            # ── NEW SHEETS: LeftAnimatons.png + RightAnimations.png ──────────
            # Both sheets share identical row y-ranges (9 rows, transparent bg).
            # L = left-facing, R = right-facing.  All frames scaled to STAND.
            def _cl(rects, tgt=STAND): return _cut_sheet_frames(lsheet, rects, tgt)
            def _cr(rects, tgt=STAND): return _cut_sheet_frames(rsheet, rects, tgt)

            idle_f  = _cr([                       # Row 0 — idle right (5 f)
                (40,7,113,146),(153,7,113,146),(266,7,113,146),
                (379,7,113,146),(492,7,116,146),
            ])
            rr_f    = _cr([                       # Row 1 — run right (8 f)
                (17,153,129,152),(146,153,129,152),(275,153,129,152),(404,153,129,152),
                (533,153,129,152),(662,153,129,152),(791,153,129,152),(920,153,132,152),
            ])
            rl_f    = _cl([                       # Row 1 — run left (8 f)
                (69,153,129,152),(198,153,129,152),(327,153,129,152),(456,153,129,152),
                (585,153,129,152),(714,153,129,152),(843,153,129,152),(972,153,130,152),
            ])
            rsr_f   = _cr([                       # Row 2 — run+shoot right (8 f)
                (18,305,137,146),(155,305,137,146),(292,305,137,146),(429,305,137,146),
                (566,305,137,146),(703,305,137,146),(840,305,137,146),(977,305,144,146),
            ])
            rsl_f   = _cl([                       # Row 2 — run+shoot left (8 f)
                (11,305,136,146),(147,305,136,146),(283,305,136,146),(419,305,136,146),
                (555,305,136,146),(691,305,136,146),(827,305,136,146),(963,305,136,146),
            ])
            shu_f   = _cr([                       # Row 4 — shoot up RIGHT (6 f) — replaces C.png
                (22,602,127,171),(149,602,127,171),(276,602,127,171),
                (403,602,127,171),(530,602,127,171),(657,602,128,171),
            ])
            shu_l_f = _cl([                       # Row 4 — shoot up LEFT (6 f)
                (227,602,139,171),(366,602,139,171),(505,602,139,171),
                (644,602,139,171),(783,602,139,171),(922,602,142,171),
            ])
            fr_f    = _cr([                       # Row 6 — jetpack fly right (8 f)
                (22,913,112,133),(134,913,112,133),(246,913,112,133),(358,913,112,133),
                (470,913,112,133),(582,913,112,133),(694,913,112,133),(806,913,113,133),
            ])
            fl_f    = _cl([                       # Row 6 — jetpack fly left (8 f)
                (47,913,132,133),(179,913,132,133),(311,913,132,133),(443,913,132,133),
                (575,913,132,133),(707,913,132,133),(839,913,132,133),(971,913,132,133),
            ])
            fsr_f   = _cr([                       # Row 7 — jetpack+shoot right (8 f)
                (13,1046,134,134),(147,1046,134,134),(281,1046,134,134),(415,1046,134,134),
                (549,1046,134,134),(683,1046,134,134),(817,1046,134,134),(951,1046,136,134),
            ])
            fsl_f   = _cl([                       # Row 7 — jetpack+shoot left (8 f)
                (12,1046,135,134),(147,1046,135,134),(282,1046,135,134),(417,1046,135,134),
                (552,1046,135,134),(687,1046,135,134),(822,1046,135,134),(957,1046,142,134),
            ])
            fsu_r_f = _cr([                       # Row 8 — jetpack+shoot up-right (7 f) — replaces C.png
                (17,1180,152,175),(169,1180,152,175),(321,1180,152,175),(473,1180,152,175),
                (625,1180,152,175),(777,1180,152,175),(929,1180,152,175),
            ])
            fsu_l_f = _cl([                       # Row 8 — jetpack+shoot up-left (7 f)
                (80,1180,147,175),(227,1180,147,175),(374,1180,147,175),(521,1180,147,175),
                (668,1180,147,175),(815,1180,147,175),(962,1180,147,175),
            ])
            hit_f   = tuple(_cr([(22,451,159,151)]))  # Row 3 frame 0 — braced shot = hit pose

            # New sheets: use actual drawn fly+shoot-up frames for directional variants
            _fup_r  = fsu_r_f        # fly up + shoot right — actual art
            _fup_l  = fsu_l_f        # fly up + shoot left  — actual art
            _fdn_r  = fsr_f          # fly down + shoot right — reuse fly_shoot
            _fdn_l  = fsl_f          # fly down + shoot left  — reuse fly_shoot

        elif sheet is not None:
            # ── LEGACY SHEET: FlyLeftAndRight.png (1448×1086) ───────────────
            #   Row 0  y=3-159   IDLE | RUN RIGHT | RUN LEFT
            #   Row 3  y=314-451 SHOOT RIGHT (RUN) | SHOOT LEFT (RUN)
            #   Row 5a y=621-774  FLY RIGHT HOVER | FLY LEFT HOVER
            #   Row 5b y=775-908  FLY SHOOT RIGHT | FLY SHOOT LEFT
            def _c(rects, tgt=STAND): return _cut_sheet_frames(sheet, rects, tgt)

            idle_f = _c([(9, 3, 70, 156), (92, 3, 74, 156)])

            rr_f = _c([                          # RUN RIGHT — 6 frames
                (272, 3, 116, 156), (388, 3, 79, 156), (467, 3, 66, 156),
                (533, 3,  89, 156), (622, 3, 130, 156), (752, 3, 82, 156),
            ])
            rl_f = _c([                          # RUN LEFT — 6 frames
                (866,  3,  76, 156), (942,  3,  87, 156), (1029, 3, 111, 156),
                (1140, 3,  97, 156), (1237, 3,  82, 156), (1319, 3,  99, 156),
            ])
            rsr_f = _c([                         # RUN SHOOT RIGHT — 5 frames
                (9,   314, 139, 137), (148, 314, 151, 137), (299, 314,  87, 137),
                (386, 314, 124, 137), (510, 314, 167, 137),
            ])
            rsl_f = _c([                         # RUN SHOOT LEFT — 5 frames
                (700,  314, 136, 137), (836,  314, 174, 137), (1010, 314, 139, 137),
                (1149, 314, 125, 137), (1274, 314, 153, 137),
            ])
            fr_f = _c([                          # FLY RIGHT HOVER — 4 frames
                (435, 621,  99, 153), (534, 621, 156, 153),
                (690, 621, 131, 153), (821, 621, 112, 153),
            ], FLY)
            fl_f = _c([                          # FLY LEFT HOVER — 4 frames
                (948,  621,  98, 153), (1046, 621, 128, 153),
                (1174, 621, 126, 153), (1300, 621, 118, 153),
            ], FLY)
            fsr_f = _c([                         # FLY SHOOT RIGHT — 4 frames
                (9,   775, 172, 133), (181, 775, 223, 133),
                (404, 775, 101, 133), (505, 775, 219, 133),
            ], FLY)
            fsl_f = _c([                         # FLY SHOOT LEFT — 4 frames
                (733,  775, 134, 133), (867,  775, 189, 133),
                (1056, 775, 141, 133), (1197, 775, 189, 133),
            ], FLY)
            shu_f = (shoot_image, _rot(shoot_image, 2))
            shu_l_f = shu_f   # legacy fallback: no separate left sheet
            fsu_r_f = (_rot(shoot_image, -12), _rot(shoot_image, -7))
            fsu_l_f = fsu_r_f
            hit_f = (_rot(shoot_image, 9),)

            _fup_r  = tuple(_rot(f,  14) for f in fsr_f)
            _fup_l  = tuple(_rot(f, -14) for f in fsl_f)
            _fdn_r  = tuple(_rot(f, -12) for f in fsr_f)
            _fdn_l  = tuple(_rot(f,  12) for f in fsl_f)

        else:
            # ── Transform fallback when no sheets are available ──────────────
            idle_f = (idle_image,)
            rr_f   = (_run_frame(idle_image, -6, .96), _run_frame(idle_image, -2, 1.03),
                      _run_frame(idle_image, -5, .95), _run_frame(idle_image, -1, 1.02))
            rl_f   = (_run_frame(left_facing_idle, 6, .96), _run_frame(left_facing_idle, 2, 1.03),
                      _run_frame(left_facing_idle, 5, .95), _run_frame(left_facing_idle, 1, 1.02))
            rsr_f  = (_run_frame(idle_image, -8, .95), _run_frame(idle_image, -4, 1.03),
                      _run_frame(idle_image, -7, .94), _run_frame(idle_image, -3, 1.02))
            rsl_f  = (_run_frame(left_facing_idle, 8, .95), _run_frame(left_facing_idle, 4, 1.03),
                      _run_frame(left_facing_idle, 7, .94), _run_frame(left_facing_idle, 3, 1.02))
            fr_f   = (_rot(idle_image, -20), _rot(idle_image, -14),
                      _rot(idle_image, -18), _rot(idle_image, -12))
            fl_f   = (_rot(left_facing_idle, 20), _rot(left_facing_idle, 14),
                      _rot(left_facing_idle, 18), _rot(left_facing_idle, 12))
            fsr_f  = (_rot(shoot_right_base, -38), _rot(shoot_right_base, -32),
                      _rot(shoot_right_base, -36), _rot(shoot_right_base, -40))
            fsl_f  = (_rot(shoot_image, 38), _rot(shoot_image, 32),
                      _rot(shoot_image, 36), _rot(shoot_image, 40))
            shu_f  = (shoot_image, _rot(shoot_image, 2))
            shu_l_f = shu_f   # transform fallback: no left sheet
            fsu_r_f = (_rot(shoot_image, -12), _rot(shoot_image, -7))
            fsu_l_f = fsu_r_f
            hit_f  = (_rot(shoot_image, 9),)

            _fup_r  = tuple(_rot(f,  14) for f in fsr_f)
            _fup_l  = tuple(_rot(f, -14) for f in fsl_f)
            _fdn_r  = tuple(_rot(f, -12) for f in fsr_f)
            _fdn_l  = tuple(_rot(f,  12) for f in fsl_f)

        self._frames: Dict[str, Tuple[pygame.Surface, ...]] = {
            'idle':               idle_f,
            'run_right':          rr_f,
            'run_left':           rl_f,
            'run_shoot_right':    rsr_f,
            'run_shoot_left':     rsl_f,
            'shoot_up':           shu_f,
            'shoot_up_left':      shu_l_f,
            'fly_right':          fr_f,
            'fly_left':           fl_f,
            'fly_shoot_right':    fsr_f,
            'fly_shoot_left':     fsl_f,
            'fly_up_shoot_right': _fup_r,
            'fly_up_shoot_left':  _fup_l,
            'fly_dn_shoot_right': _fdn_r,
            'fly_dn_shoot_left':  _fdn_l,
            'fly_shoot_up':       fsu_r_f,
            'fly_shoot_up_left':  fsu_l_f,
            'hit':                hit_f,
        }

        # Per-frame visual-only (x, y) offsets — hitbox is never affected.
        if lsheet is not None and rsheet is not None:
            # New sheets: 5/8/8/6/8/8/7 frame counts
            self._frame_offsets: Dict[str, Tuple[Tuple[int, int], ...]] = {
                'idle':               ((0,0),(0,0),(0,0),(0,0),(0,0)),
                'run_right':          ((+1,+4),(0,-2),(+2,+5),(0,-3),(+1,+4),(0,-2),(+2,+5),(0,-3)),
                'run_left':           ((-1,+4),(0,-2),(-2,+5),(0,-3),(-1,+4),(0,-2),(-2,+5),(0,-3)),
                'run_shoot_right':    ((+1,+3),(0,-2),(+2,+4),(0,-2),(+1,+3),(0,-2),(+2,+4),(0,-2)),
                'run_shoot_left':     ((-1,+3),(0,-2),(-2,+4),(0,-2),(-1,+3),(0,-2),(-2,+4),(0,-2)),
                'shoot_up':           ((0,0),(0,-1),(0,-2),(0,-1),(0,0),(0,-1)),
                'shoot_up_left':      ((0,0),(0,-1),(0,-2),(0,-1),(0,0),(0,-1)),
                'fly_right':          ((0,0),(0,-2),(0,-3),(0,-2),(0,0),(0,-2),(0,-3),(0,-2)),
                'fly_left':           ((0,0),(0,-2),(0,-3),(0,-2),(0,0),(0,-2),(0,-3),(0,-2)),
                'fly_shoot_right':    ((0,0),(0,-2),(0,-3),(0,-2),(0,0),(0,-2),(0,-3),(0,-2)),
                'fly_shoot_left':     ((0,0),(0,-2),(0,-3),(0,-2),(0,0),(0,-2),(0,-3),(0,-2)),
                'fly_up_shoot_right': ((0,-2),(0,-4),(0,-5),(0,-4),(0,-2),(0,-4),(0,-5)),
                'fly_up_shoot_left':  ((0,-2),(0,-4),(0,-5),(0,-4),(0,-2),(0,-4),(0,-5)),
                'fly_dn_shoot_right': ((0,0),(0,-2),(0,-3),(0,-2),(0,0),(0,-2),(0,-3),(0,-2)),
                'fly_dn_shoot_left':  ((0,0),(0,-2),(0,-3),(0,-2),(0,0),(0,-2),(0,-3),(0,-2)),
                'fly_shoot_up':       ((0,-2),(0,-4),(0,-5),(0,-4),(0,-2),(0,-4),(0,-5)),
                'fly_shoot_up_left':  ((0,-2),(0,-4),(0,-5),(0,-4),(0,-2),(0,-4),(0,-5)),
                'hit':                ((0,0),),
            }
        else:
            self._frame_offsets = {
                'idle':               ((0,  0),(0,  0)),
                'run_right':          ((+1,+4),(+1,-3),(+2,+5),(+1,-2),(+1,+3),(+2,-2)),
                'run_left':           ((-1,+4),(-1,-3),(-2,+5),(-1,-2),(-1,+3),(-2,-2)),
                'run_shoot_right':    ((+1,+3),( 0,-3),(+2,+4),( 0,-2),(+1,+2)),
                'run_shoot_left':     ((-1,+3),( 0,-3),(-2,+4),( 0,-2),(-1,+2)),
                'shoot_up':           ((0, 0),(0,-2)),
                'shoot_up_left':      ((0, 0),(0,-2)),
                'fly_right':          ((+2,-2),(+3,-5),(+2,-3),(+3,-6)),
                'fly_left':           ((-2,-2),(-3,-5),(-2,-3),(-3,-6)),
                'fly_shoot_right':    ((-4,-2),(-3,-5),(-4,-3),(-3,-6)),
                'fly_shoot_left':     ((+4,-2),(+3,-5),(+4,-3),(+3,-6)),
                'fly_up_shoot_right': ((-4,-6),(-3,-9),(-4,-7),(-3,-10)),
                'fly_up_shoot_left':  ((+4,-6),(+3,-9),(+4,-7),(+3,-10)),
                'fly_dn_shoot_right': ((-4, 1),(-3,-2),(-4, 0),(-3,-3)),
                'fly_dn_shoot_left':  ((+4, 1),(+3,-2),(+4, 0),(+3,-3)),
                'fly_shoot_up':       ((0,-1),(0,-4)),
                'fly_shoot_up_left':  ((0,-1),(0,-4)),
                'hit':                ((0, 0),),
            }
        self._last_facing = 1

    def get_frame(
            self,
            velocity: pygame.Vector2,
            is_upward_shooting: bool,
            is_side_shooting: bool,
            side_shot_direction: int,
            is_hit: bool,
            frame_count: int,
    ) -> Tuple[pygame.Surface, str, Tuple[int, int]]:
        """Return the current frame surface, pose cache key, and visual-only offset."""
        if velocity.x > 0.45:
            self._last_facing = 1
        elif velocity.x < -0.45:
            self._last_facing = -1

        is_flying = abs(velocity.y) > 0.45
        if is_hit:
            state = 'hit'
        elif is_side_shooting:
            self._last_facing = 1 if side_shot_direction >= 0 else -1
            direction = 'right' if self._last_facing > 0 else 'left'
            if is_flying:
                if velocity.y < -0.45:       # moving upward
                    state = f'fly_up_shoot_{direction}'
                elif velocity.y > 0.45:      # moving downward
                    state = f'fly_dn_shoot_{direction}'
                else:
                    state = f'fly_shoot_{direction}'
            else:
                state = f'run_shoot_{direction}'
        elif is_upward_shooting:
            direction = 'right' if self._last_facing > 0 else 'left'
            if is_flying:
                state = 'fly_shoot_up' if direction == 'right' else 'fly_shoot_up_left'
            else:
                state = 'shoot_up' if direction == 'right' else 'shoot_up_left'
        elif is_flying:
            direction = 'right' if self._last_facing > 0 else 'left'
            state = f'fly_{direction}'
        elif velocity.x > 0.45:
            state = 'run_right'
        elif velocity.x < -0.45:
            state = 'run_left'
        else:
            state = 'idle'

        frames = self._frames[state]
        if len(frames) == 1:
            frame_index = 0
        elif state in ('run_shoot_right', 'run_shoot_left'):
            frame_index = (frame_count // self._RUN_SHOOT_CYCLE_FRAMES) % len(frames)
        elif state in ('fly_shoot_right', 'fly_shoot_left',
                        'fly_up_shoot_right', 'fly_up_shoot_left',
                        'fly_dn_shoot_right', 'fly_dn_shoot_left'):
            frame_index = (frame_count // self._FLY_SHOOT_CYCLE_FRAMES) % len(frames)
        elif 'shoot' in state:
            frame_index = (frame_count // self._SHOOT_CYCLE_FRAMES) % len(frames)
        elif state.startswith('fly_'):
            frame_index = (frame_count // self._FLY_CYCLE_FRAMES) % len(frames)
        else:
            frame_index = (frame_count // self._RUN_CYCLE_FRAMES) % len(frames)

        offset_x, offset_y = self._frame_offsets[state][
            frame_index % len(self._frame_offsets[state])
        ]
        if state.startswith('fly_'):
            offset_y += int(math.sin(frame_count * 0.32) * 4) - 3
        elif state == 'idle':
            offset_y += int(math.sin(frame_count * 0.12) * 2)

        return frames[frame_index], f'{state}:{frame_index}', (offset_x, offset_y)


def load_image_remove_dark_bg(dir_map: Dict[str, str], filename: str, size: Tuple[int, int], threshold: int = 8) -> pygame.Surface:
    """
    Loads a sprite and removes very dark background pixels.
    Use only for generated player pose sprites with black-box backgrounds.
    """
    entry = dir_map.get(filename.lower())

    if entry:
        try:
            img = pygame.image.load(os.path.join(BASE_DIR, entry)).convert_alpha()

            width, height = img.get_size()

            for y in range(height):
                for x in range(width):
                    r, g, b, a = img.get_at((x, y))

                    # Remove almost-black background pixels.
                    # Keep threshold low so shirt/hair/details survive.
                    if r <= threshold and g <= threshold and b <= threshold:
                        img.set_at((x, y), (0, 0, 0, 0))

            return pygame.transform.scale(img, size)

        except pygame.error as err:
            print(f"⚠️ Failed to load {filename}: {err}")

    print(f"⚠️ Missing asset: {filename}. Using placeholder.")
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((255, 0, 255, 255))
    return surf


def find_file(dir_map: Dict[str, str], filename: str) -> Optional[str]:
    """Locate a file in BASE_DIR using case-insensitive lookup."""
    entry = dir_map.get(filename.lower())
    return os.path.join(BASE_DIR, entry) if entry else None


def find_level2_music_file(dir_map: Dict[str, str], level1_music_file: Optional[str]) -> Optional[str]:
    """Find a Level 2 BGM file, preferring explicitly named or likely candidates."""
    # Explicit preferred filename(s) first.
    for _name in (
        "Level 2 music.ogg",
        "Level 2 Music.ogg",
        "Level 2 music .ogg",
        "Level 2 Music .ogg",
    ):
        explicit = find_file(dir_map, _name)
        if explicit:
            return explicit

    # Fallback: pick an .ogg that looks like level/boss gameplay music and isn't a known SFX/menu/result track.
    skip_tokens = (
        "start menu", "tutorial", "win", "lose", "impact", "shot", "power up", "power-up"
    )
    prefer_tokens = ("level 2", "level2", "boss")
    level1_name = os.path.basename(level1_music_file).lower() if level1_music_file else ""

    candidates = []
    for key, entry in dir_map.items():
        if not key.endswith('.ogg'):
            continue
        low = entry.lower()
        if low == level1_name:
            continue
        if any(tok in low for tok in skip_tokens):
            continue
        score = 0
        for tok in prefer_tokens:
            if tok in low:
                score += 2
        if score > 0:
            candidates.append((score, entry))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return os.path.join(BASE_DIR, candidates[0][1])


def _make_impact_sound() -> pygame.mixer.Sound:
    """Generate a procedural impact/hit sound using sine wave synthesis."""
    n = int(44100 * 0.32)
    samples = [
        max(-32768, min(32767, int(random.uniform(-1, 1) * (1.0 - i / n) * 28000)))
        for i in range(n)
    ]
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.6)
    return snd


def _make_siren_sound() -> pygame.mixer.Sound:
    """Generate a procedural siren/alarm sound."""
    sr, dur = 44100, 0.5
    n = int(sr * dur)
    f0, f1 = 440, 1100
    samples = [
        max(-32768, min(32767, int(
            math.sin(2 * math.pi * (f0 * (i/sr) + (f1 - f0) * (i/sr)**2 / (2 * dur))) * 26000
        )))
        for i in range(n)
    ]
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.65)
    return snd


def _make_powerup_sound() -> pygame.mixer.Sound:
    """Generate a procedural power-up/success sound."""
    sr, dur = 44100, 0.25
    n = int(sr * dur)
    f0, f1 = 350, 950
    fade = max(1, int(sr * 0.04))
    samples = [
        max(-32768, min(32767, int(
            math.sin(2 * math.pi * (f0 * (i/sr) + (f1 - f0) * (i/sr)**2 / (2 * dur)))
            * (min(i, n - i, fade) / fade) * 22000
        )))
        for i in range(n)
    ]
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.55)
    return snd


def _make_landing_sound() -> pygame.mixer.Sound:
    """Procedural low-frequency thud for jetpack landing."""
    sr, dur = 44100, 0.18
    n = int(sr * dur)
    samples = []
    for i in range(n):
        t = i / sr
        env = math.exp(-t * 28)          # fast exponential decay
        freq = 70 * math.exp(-t * 12)    # pitch falls from 70 Hz down
        sine  = math.sin(2 * math.pi * freq * t)
        noise = random.uniform(-0.35, 0.35)
        val = int((sine * 0.65 + noise * 0.35) * env * 30000)
        samples.append(max(-32768, min(32767, val)))
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.55)
    return snd


def _make_combo_sound(base_hz: float, peak_hz: float, dur: float) -> pygame.mixer.Sound:
    """Short ascending chirp for combo milestone feedback.
    Pitch sweeps from base_hz to peak_hz over dur seconds.
    Higher combos get higher base/peak and shorter duration for urgency.
    """
    sr = 44100
    n  = int(sr * dur)
    fade = max(1, int(sr * 0.015))   # 15 ms fade-in / fade-out
    samples = []
    for i in range(n):
        t   = i / sr
        env = (min(i, n - i, fade) / fade)  # linear fade in/out
        hz  = base_hz + (peak_hz - base_hz) * (t / dur) ** 0.6
        val = int(math.sin(2 * math.pi * hz * t) * env * 24000)
        samples.append(max(-32768, min(32767, val)))
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.55)
    return snd


def _make_signal_burst_sound() -> pygame.mixer.Sound:
    """Generate a layered low-boom + bright sweep for Signal Burst activation."""
    sr, dur = 44100, 0.42
    n = int(sr * dur)
    attack = max(1, int(sr * 0.012))
    samples = []
    for i in range(n):
        t = i / sr
        atk = min(1.0, i / attack)
        env = atk * math.exp(-4.2 * t)
        boom = math.sin(2 * math.pi * (62.0 - 18.0 * t) * t)
        sweep_freq = 1250.0 - (900.0 * min(1.0, t / dur))
        sweep = math.sin(2 * math.pi * sweep_freq * t)
        fizz = random.uniform(-1.0, 1.0) * math.exp(-11.0 * t)
        v = (0.66 * boom + 0.38 * sweep + 0.22 * fizz) * env
        samples.append(max(-32768, min(32767, int(v * 30000))))
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.7)
    return snd


def _make_near_miss_sound() -> pygame.mixer.Sound:
    """Descending whoosh (900→150 Hz) played when an enemy bullet just misses."""
    sr, dur = 44100, 0.13
    n = int(sr * dur)
    samples = []
    for i in range(n):
        t     = i / sr
        env   = max(0.0, 1.0 - (t / dur) ** 0.5)   # convex fast decay
        freq  = 900.0 - 750.0 * (t / dur)           # 900 → 150 Hz sweep
        sine  = math.sin(2 * math.pi * freq * t)
        noise = random.uniform(-1.0, 1.0)
        val   = int((sine * 0.5 + noise * 0.5) * env * 22000)
        samples.append(max(-32768, min(32767, val)))
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.32)
    return snd


def _make_countdown_tick_sound() -> pygame.mixer.Sound:
    """Short crisp descending beep — arcade-style countdown tick for last 3 seconds."""
    sr, dur = 44100, 0.10
    n = int(sr * dur)
    fade = max(1, int(sr * 0.008))
    samples = []
    for i in range(n):
        env = min(i, n - i, fade) / fade
        hz  = 1050.0 - 550.0 * (i / n)    # 1050 → 500 Hz descending sweep
        val = int(math.sin(2 * math.pi * hz * (i / sr)) * env * 26000)
        samples.append(max(-32768, min(32767, val)))
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.45)
    return snd


def _tutorial_screen(screen: pygame.Surface, clock: pygame.time.Clock, 
                    tutorial_img: List[pygame.Surface], 
                    tutorial_music_file: Optional[str] = None) -> None:
    """
    Display tutorial/instructions screen.
    
    Shows on first run before gameplay begins.
    """
    """Show one or more tutorial pages. Returns when the player dismisses it."""
    if tutorial_music_file:
        try:
            pygame.mixer.music.load(tutorial_music_file)
            pygame.mixer.music.set_volume(0.7)
            pygame.mixer.music.play(-1)
        except pygame.error:
            pass
    W, H = screen.get_size()
    font_hint = pygame.font.SysFont("Arial", 28, bold=True)
    pages = tutorial_img if isinstance(tutorial_img, (list, tuple)) else [tutorial_img]
    pages = [p for p in pages if p is not None]
    if not pages:
        return
    page_idx = 0

    def _hint_surface(idx):
        if len(pages) == 1:
            text = "Press  ESC  or  BACKSPACE  to return"
        elif idx < len(pages) - 1:
            text = "LEFT/RIGHT or CLICK to navigate   ESC/BACKSPACE to return"
        else:
            text = "LEFT/RIGHT to navigate   CLICK/ENTER to close"
        surf = font_hint.render(text, True, (220, 220, 220))
        surf.set_alpha(180)
        return surf

    while True:
        screen.blit(pages[page_idx], (0, 0))
        hint = _hint_surface(page_idx)
        hint_rect = hint.get_rect(center=(W // 2, H - 28))
        screen.blit(hint, hint_rect)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_RETURN):
                    if event.key in (pygame.K_RETURN,) and len(pages) > 1 and page_idx < len(pages) - 1:
                        page_idx += 1
                    else:
                        return
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    page_idx = min(len(pages) - 1, page_idx + 1)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    page_idx = max(0, page_idx - 1)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if len(pages) > 1 and page_idx < len(pages) - 1:
                    page_idx += 1
                else:
                    return

        pygame.display.flip()
        clock.tick(60)


def _credits_screen(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    """
    Display ending credits sequence.
    
    Shown after winning or significant completion.
    """
    """Scrolling arcade-style credits roll. Any key / click to skip."""
    W, H = screen.get_size()
    _ft  = _get_arcade_font(40)
    _fh  = _get_arcade_font(22)
    _fn  = _get_arcade_font(18)
    _fhi = _get_arcade_font(14)

    _GOLD  = ( 57, 255,  20)
    _CYAN  = (180,  80, 255)
    _WHITE = (230, 230, 230)
    _GREY  = (160, 160, 160)

    ENTRIES = [
        None, None, None,
        ('ONYX G',                  _ft, _GOLD),
        ('vs',                      _fh, _WHITE),
        ('SPACE DRONES',            _ft, _GOLD),
        None, None,
        ('\u2014  C R E D I T S  \u2014', _fh, _CYAN),
        None,
        ('CREATED BY',              _fh, _CYAN),
        ('Gary Black',              _fn, _WHITE),
        None,
        ('GAME DESIGN',             _fh, _CYAN),
        ('Gary Black',              _fn, _WHITE),
        None,
        ('ART & ASSETS',            _fh, _CYAN),
        ('Gary Black',              _fn, _WHITE),
        None,
        ('MUSIC',                   _fh, _CYAN),
        ('Gary Black',              _fn, _WHITE),
        None,
        ('AI PROGRAMMING ASSIST',   _fh, _CYAN),
        ('GitHub Copilot',          _fn, _WHITE),
        None, None,
        ('SPECIAL THANKS',          _fh, _CYAN),
        ('To everyone keeping',     _fn, _GREY),
        ('the arcade spirit alive', _fn, _GREY),
        None, None, None,
        ('\u2756  THANK YOU  \u2756', _ft, _GOLD),
        ('FOR PLAYING',             _fh, _WHITE),
        None, None, None, None, None,
    ]

    # Pre-render surfaces and compute cumulative y offsets
    _surfs, _ys, _y = [], [], 0
    for entry in ENTRIES:
        _ys.append(_y)
        if entry is None:
            _surfs.append(None)
            _y += 30
        else:
            text, font, col = entry
            surf = font.render(text, True, col)
            _surfs.append(surf)
            _y += surf.get_height() + 10
    total_h = _y

    scroll_y     = float(H)
    scroll_speed = 1.2
    hint = _fhi.render("press any key to skip", True, (65, 65, 65))
    hint_rect = hint.get_rect(center=(W // 2, H - 18))
    _stars = [(random.randint(0, W - 1), random.randint(0, H - 1)) for _ in range(70)]

    while True:
        screen.fill((0, 0, 5))
        for sx, sy in _stars:
            pygame.draw.rect(screen, (120, 120, 155), (sx, sy, 1, 1))

        for i, surf in enumerate(_surfs):
            y = int(_ys[i] + scroll_y)
            if surf is not None and -80 < y < H:
                screen.blit(surf, surf.get_rect(centerx=W // 2, y=y))

        screen.blit(hint, hint_rect)
        pygame.display.flip()
        clock.tick(60)

        scroll_y -= scroll_speed
        if scroll_y + total_h < 0:
            break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                return


def _get_arcade_font(size):
    """Returns a vintage arcade-style font at the given size, with graceful fallback."""
    _path = next(
        (pygame.font.match_font(f) for f in
         ["pressstart2p", "arcadeclassic", "impact", "couriernew"]
         if pygame.font.match_font(f)), None)
    return (pygame.font.Font(_path, size) if _path
            else pygame.font.SysFont("courier new", size, bold=True))


def _start_menu(screen, clock, menu_img, menu_music_file=None,
                tutorial_img=None, tutorial_music_file=None):
    if menu_music_file:
        try:
            pygame.mixer.music.load(menu_music_file)
            pygame.mixer.music.set_volume(0.7)
            pygame.mixer.music.play(-1)
        except pygame.error:
            pass
    W, H = screen.get_size()

    # Keep the menu UI inside the cabinet monitor area regardless of resolution.
    monitor_rect = pygame.Rect(int(W * 0.18), int(H * 0.285), int(W * 0.64), int(H * 0.35))
    monitor_safe = monitor_rect.inflate(-int(monitor_rect.width * 0.10), -int(monitor_rect.height * 0.10))

    btn_w = int(monitor_safe.width * 0.62)
    btn_h = max(34, min(56, int(monitor_safe.height * 0.135)))
    btn_gap = max(8, int(btn_h * 0.28))
    total_h = btn_h * 5 + btn_gap * 4
    start_y = monitor_safe.top + max(0, (monitor_safe.height - total_h) // 2)
    btn_x = monitor_safe.centerx - btn_w // 2

    buttons = [
        ("START GAME",      "start"),
        ("VS MODE",         "soon"),
        ("HOW TO PLAY",     "tutorial"),
        ("CREDITS",         "credits"),
        ("EXIT GAME",       "exit"),
    ]
    rects = [
        (pygame.Rect(btn_x, start_y + i * (btn_h + btn_gap), btn_w, btn_h), action)
        for i, (_, action) in enumerate(buttons)
    ]

    font_soon = _get_arcade_font(20)
    font_btn  = _get_arcade_font(16)
    soon_timer = 0
    highlight  = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 55))

    while True:
        screen.blit(menu_img, (0, 0))
        mx, my = pygame.mouse.get_pos()

        for (rect, _), (label, _) in zip(rects, buttons):
            pygame.draw.rect(screen, (15, 10, 35), rect, border_radius=6)
            pygame.draw.rect(screen, (100, 60, 180), rect, 2, border_radius=6)
            if rect.collidepoint(mx, my):
                screen.blit(highlight, rect.topleft)
            _lbl = font_btn.render(label, True, (220, 200, 255))
            screen.blit(_lbl, _lbl.get_rect(center=rect.center))

        if soon_timer > 0:
            t = font_soon.render("Coming Soon!", True, (255, 210, 0))
            _soon_y = max(monitor_safe.top + 14, rects[0][0].top - 20)
            screen.blit(t, t.get_rect(center=(monitor_safe.centerx, _soon_y)))
            soon_timer -= 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, action in rects:
                    if rect.collidepoint(event.pos):
                        if action == "start":
                            return
                        elif action == "exit":
                            pygame.quit()
                            sys.exit()
                        elif action == "tutorial" and tutorial_img is not None:
                            _tutorial_screen(screen, clock, tutorial_img, tutorial_music_file)
                            # Restore menu music after tutorial
                            if menu_music_file:
                                try:
                                    pygame.mixer.music.load(menu_music_file)
                                    pygame.mixer.music.set_volume(0.7)
                                    pygame.mixer.music.play(-1)
                                except pygame.error:
                                    pass
                        elif action == "credits":
                            _credits_screen(screen, clock)
                            if menu_music_file:
                                try:
                                    pygame.mixer.music.load(menu_music_file)
                                    pygame.mixer.music.set_volume(0.7)
                                    pygame.mixer.music.play(-1)
                                except pygame.error:
                                    pass
                        else:
                            soon_timer = 120

        pygame.display.flip()
        clock.tick(60)


def _boss_intro_cinematic(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    """
    Display dramatic boss entrance cinematic sequence.
    
    Triggered when player reaches wave 5 and clears all drones.
    Builds tension before boss fight begins.
    """
    """Black screen, ☠ CRANIUM COMMANDER ☠ slides in with flash + rumble."""
    W, H = screen.get_size()
    _ft = pygame.font.SysFont("Arial", 44, bold=True)
    _fs = pygame.font.SysFont("Arial", 22, bold=True)
    _TITLE = "☠  CRANIUM COMMANDER  ☠"
    _SUB   = "—  PREPARE FOR BATTLE  —"

    # Pre-render text surfaces
    _t_shadow = _ft.render(_TITLE, True, (80, 0, 0))
    _t_main   = _ft.render(_TITLE, True, (230, 55, 55))
    _s_surf   = _fs.render(_SUB,   True, (200, 140, 255))

    # ── Low rumble / impact sound ─────────────────────────────────────────
    _snd = None
    try:
        _n = int(44100 * 0.55)
        _buf = array.array('h', [
            max(-32768, min(32767, int((
                math.sin(2 * math.pi * 55 * i / 44100) * 0.5 +
                math.sin(2 * math.pi * 110 * i / 44100) * 0.3 +
                (random.random() * 2 - 1) * 0.2
            ) * 26000 * max(0.0, 1.0 - i / _n * 1.4))))
            for i in range(_n)
        ])
        _snd = pygame.mixer.Sound(buffer=array.array('h', [s for s in _buf for _ in range(2)]))
        _snd.set_volume(0.75)
    except Exception:
        pass

    # ── Phase lengths (frames @ 60 fps) ──────────────────────────────────
    _P     = [25, 38, 10, 55, 22]          # fade-in | slide | flash | hold | fade-out
    _ends  = [sum(_P[:i + 1]) for i in range(len(_P))]
    _TOTAL = _ends[-1]                      # 150 frames ≈ 2.5 s

    def _blit_title(cx, cy):
        screen.blit(_t_shadow, _t_shadow.get_rect(center=(cx + 4, cy + 4)))
        screen.blit(_t_main,   _t_main.get_rect(center=(cx, cy)))

    _hit = False
    _orig_vol = pygame.mixer.music.get_volume()
    pygame.mixer.music.set_volume(max(0.0, _orig_vol * 0.25))   # duck bgm

    for _f in range(_TOTAL):
        for _ev in pygame.event.get():
            if _ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if _ev.type == pygame.KEYDOWN and _ev.key == pygame.K_ESCAPE:
                pygame.mixer.music.set_volume(_orig_vol)
                return

        screen.fill((0, 0, 0))

        if _f < _ends[0]:
            # Phase 0 – black fade-in (screen already black)
            pass

        elif _f < _ends[1]:
            # Phase 1 – title slides in from left with ease-out cubic
            t  = (_f - _ends[0]) / _P[1]
            te = 1.0 - (1.0 - t) ** 3
            cx = int(-W * 0.6 + (W * 0.6 + W // 2) * te)
            _blit_title(cx, H // 2 - 15)

        elif _f < _ends[2]:
            # Phase 2 – warm flash + play impact sound
            if not _hit:
                if _snd:
                    _snd.play()
                _hit = True
            t = (_f - _ends[1]) / _P[2]
            _blit_title(W // 2, H // 2 - 15)
            if not PHOTOSENSITIVE_SAFE_MODE:
                _fl = pygame.Surface((W, H))
                _fl.fill((255, 240, 200))
                _fl.set_alpha(int(130 * (1.0 - t) ** 2))
                screen.blit(_fl, (0, 0))

        elif _f < _ends[3]:
            # Phase 3 – hold; subtitle fades in
            t_h = (_f - _ends[2]) / _P[3]
            _blit_title(W // 2, H // 2 - 30)
            if t_h > 0.18:
                _a = min(255, int((t_h - 0.18) / 0.25 * 255))
                _s2 = _s_surf.copy()
                _s2.set_alpha(_a)
                screen.blit(_s2, _s2.get_rect(center=(W // 2, H // 2 + 55)))

        else:
            # Phase 4 – fade to black
            t = (_f - _ends[3]) / _P[4]
            _blit_title(W // 2, H // 2 - 30)
            screen.blit(_s_surf, _s_surf.get_rect(center=(W // 2, H // 2 + 55)))
            _fds = pygame.Surface((W, H))
            _fds.fill((0, 0, 0))
            _fds.set_alpha(int(255 * t ** 2))
            screen.blit(_fds, (0, 0))

        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.music.set_volume(_orig_vol)


def _level_two_transition(screen: pygame.Surface, clock: pygame.time.Clock,
                          background_img: pygame.Surface) -> None:
    """Cinematic bridge between Level 1 clear and Level 2 start."""
    W, H = screen.get_size()
    _ft  = pygame.font.SysFont("Arial", 72, bold=True)
    _fm  = pygame.font.SysFont("Arial", 34, bold=True)
    _fs  = pygame.font.SysFont("Arial", 22, bold=True)

    _clear_surf  = _ft.render("LEVEL 1  CLEAR", True, (255, 220, 0))
    _l2_surf     = _ft.render("LEVEL 2", True, (255, 90, 90))
    _sub_surf    = _fm.render("FASTER DRONES  •  TRAUMA CONDITIONS", True, (255, 200, 200))
    _ready_surf  = _fs.render("—  PREPARE YOURSELF  —", True, (200, 200, 255))

    # Fit clear text if too wide
    if _clear_surf.get_width() > W - 80:
        _clear_surf = pygame.font.SysFont("Arial", 48, bold=True).render("LEVEL 1  CLEAR", True, (255, 220, 0))
    if _sub_surf.get_width() > W - 80:
        _sub_surf = pygame.font.SysFont("Arial", 24, bold=True).render("FASTER DRONES  •  TRAUMA CONDITIONS", True, (255, 200, 200))

    # Phases: fade-to-black | hold clear | crossfade to L2 bg | L2 reveal | fade out
    _P    = [22, 45, 30, 60, 30]
    _ends = [sum(_P[:i + 1]) for i in range(len(_P))]
    _TOTAL = _ends[-1]

    _orig_vol = pygame.mixer.music.get_volume()
    pygame.mixer.music.set_volume(max(0.0, _orig_vol * 0.3))

    _black = pygame.Surface((W, H))
    _black.fill((0, 0, 0))
    _overlay = pygame.Surface((W, H))

    for _f in range(_TOTAL):
        for _ev in pygame.event.get():
            if _ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()

        if _f < _ends[0]:
            # Fade to black
            t = _f / _P[0]
            _black.set_alpha(int(255 * t ** 1.8))
            screen.fill((0, 0, 0))
            screen.blit(_black, (0, 0))

        elif _f < _ends[1]:
            # Hold black, show LEVEL 1 CLEAR fading in then out
            t = (_f - _ends[0]) / _P[1]
            screen.fill((0, 0, 0))
            _a = int(255 * min(1.0, (1.0 - abs(t - 0.5) * 2) + 0.3))
            _clear_surf.set_alpha(max(0, min(255, _a)))
            screen.blit(_clear_surf, _clear_surf.get_rect(center=(W // 2, H // 2)))

        elif _f < _ends[2]:
            # Crossfade Level 2 background in
            t = (_f - _ends[1]) / _P[2]
            screen.blit(background_img, (0, 0))
            _black.set_alpha(int(255 * (1.0 - t) ** 2))
            screen.blit(_black, (0, 0))

        elif _f < _ends[3]:
            # Hold: show LEVEL 2 title + subtitle fading in
            t = (_f - _ends[2]) / _P[3]
            screen.blit(background_img, (0, 0))
            _pulse = 205 if PHOTOSENSITIVE_SAFE_MODE else int(220 + 35 * abs(math.sin(_f * 0.14)))
            _l2c = _ft.render("LEVEL 2", True, (255, _pulse // 2, _pulse // 2))
            screen.blit(_l2c, _l2c.get_rect(center=(W // 2, H // 2 - 50)))
            if t > 0.15:
                _sa = min(255, int((t - 0.15) / 0.3 * 255))
                _sub_surf.set_alpha(_sa)
                screen.blit(_sub_surf, _sub_surf.get_rect(center=(W // 2, H // 2 + 18)))
            if t > 0.45:
                _ra = min(255, int((t - 0.45) / 0.3 * 255))
                _ready_surf.set_alpha(_ra)
                screen.blit(_ready_surf, _ready_surf.get_rect(center=(W // 2, H // 2 + 62)))

        else:
            # Fade out overlays (background stays, gameplay starts)
            t = (_f - _ends[3]) / _P[4]
            screen.blit(background_img, (0, 0))
            _sub_surf.set_alpha(max(0, int(255 * (1.0 - t))))
            screen.blit(_sub_surf, _sub_surf.get_rect(center=(W // 2, H // 2 + 18)))

        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.music.set_volume(_orig_vol)


def _level_three_transition(screen: pygame.Surface, clock: pygame.time.Clock,
                            background_img: pygame.Surface) -> None:
    """Cinematic bridge between Level 2 clear and Level 3 start."""
    W, H = screen.get_size()
    _ft  = pygame.font.SysFont("Arial", 72, bold=True)
    _fs  = pygame.font.SysFont("Arial", 32, bold=True)
    _clear_surf  = _ft.render("LEVEL 2  CLEAR", True, (255, 180, 60))
    _l3_surf     = _ft.render("LEVEL 3", True, (255, 180, 0))

    # Fit clear text if too wide
    if _clear_surf.get_width() > W - 80:
        _clear_surf = pygame.font.SysFont("Arial", 48, bold=True).render("LEVEL 2  CLEAR", True, (255, 180, 60))

    _sub_surf    = _fs.render("APEX  MODE  ACTIVATED", True, (255, 220, 100))
    _black       = pygame.Surface((W, H))
    _black.fill((0, 0, 0))

    # Phases: fade-to-black | hold clear | crossfade to L3 bg | L3 reveal | fade out
    _P = [30, 40, 25, 50, 25]
    _ends = [sum(_P[:i + 1]) for i in range(len(_P))]
    _TOTAL = _ends[-1]

    _orig_vol = pygame.mixer.music.get_volume()
    pygame.mixer.music.set_volume(max(0.0, _orig_vol * 0.3))

    for _f in range(_TOTAL):
        for _ev in pygame.event.get():
            if _ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        if _f < _ends[0]:
            # Fade to black
            t = _f / _P[0]
            screen.blit(screen, (0, 0))
            _black.set_alpha(int(255 * t))
            screen.blit(_black, (0, 0))

        elif _f < _ends[1]:
            # Hold black, show LEVEL 2 CLEAR fading in then out
            t = (_f - _ends[0]) / _P[1]
            screen.blit(_black, (0, 0))
            _a = 255 * (1.0 - (t - 0.5) ** 2 * 4) if 0 <= t <= 1 else 0
            _clear_surf.set_alpha(max(0, min(255, _a)))
            screen.blit(_clear_surf, _clear_surf.get_rect(center=(W // 2, H // 2)))

        elif _f < _ends[2]:
            # Crossfade Level 3 background in
            t = (_f - _ends[1]) / _P[2]
            screen.blit(_black, (0, 0))
            screen.blit(background_img, (0, 0))
            _black.set_alpha(int(255 * (1.0 - t) ** 2))
            screen.blit(_black, (0, 0))

        elif _f < _ends[3]:
            # Hold: show LEVEL 3 title + subtitle fading in
            t = (_f - _ends[2]) / _P[3]
            screen.blit(background_img, (0, 0))
            _pulse = 220 if PHOTOSENSITIVE_SAFE_MODE else int(240 + 40 * abs(math.sin(_f * 0.12)))
            _l3c = _ft.render("LEVEL 3", True, (255, _pulse // 2, 0))
            screen.blit(_l3c, _l3c.get_rect(center=(W // 2, H // 2 - 50)))
            if t > 0.15:
                _sa = min(255, int((t - 0.15) / 0.3 * 255))
                _sub_surf.set_alpha(_sa)
                screen.blit(_sub_surf, _sub_surf.get_rect(center=(W // 2, H // 2 + 18)))

        else:
            # Fade out overlays (background stays, gameplay starts)
            t = (_f - _ends[3]) / _P[4]
            screen.blit(background_img, (0, 0))
            _sub_surf.set_alpha(max(0, int(255 * (1.0 - t))))
            screen.blit(_sub_surf, _sub_surf.get_rect(center=(W // 2, H // 2 + 18)))

        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.music.set_volume(_orig_vol)


def _level_four_transition(screen: pygame.Surface, clock: pygame.time.Clock,
                           background_img: pygame.Surface) -> None:
    """Cinematic bridge into Level 4 with title reveal only."""
    W, H = screen.get_size()
    _title_f = pygame.font.SysFont("Arial", 72, bold=True)
    _line_f = pygame.font.SysFont("Arial", 26, bold=True)

    _sub_surf = _line_f.render("FINAL ASCENT  •  MAX THREAT", True, (255, 245, 170))
    _hint_surf = _line_f.render("SURVIVE THE DRONE ONSLAUGHT", True, (210, 240, 255))

    _black = pygame.Surface((W, H), pygame.SRCALPHA)
    _dialog_ov = pygame.Surface((W, H), pygame.SRCALPHA)

    # Phases: darken -> title reveal -> hold -> fade out
    _P = [28, 56, 72, 26]
    _ends = [sum(_P[:i + 1]) for i in range(len(_P))]
    _TOTAL = _ends[-1]

    _orig_vol = pygame.mixer.music.get_volume()
    pygame.mixer.music.set_volume(max(0.0, _orig_vol * 0.35))

    for _f in range(_TOTAL):
        for _ev in pygame.event.get():
            if _ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()

        screen.blit(background_img, (0, 0))
        _dialog_ov.fill((0, 0, 0, 0))

        if _f < _ends[0]:
            t = _f / _P[0]
            _black.fill((0, 0, 0, int(190 * (1.0 - t))))
            screen.blit(_black, (0, 0))

        elif _f < _ends[1]:
            t = (_f - _ends[0]) / _P[1]
            _pulse = 210 if PHOTOSENSITIVE_SAFE_MODE else int(220 + 35 * abs(math.sin(_f * 0.18)))
            _l4c = _title_f.render("LEVEL 4", True, (160, _pulse, 255))
            _l4c.set_alpha(min(255, int(255 * (0.35 + t))))
            screen.blit(_l4c, _l4c.get_rect(center=(W // 2, H // 2 - 76)))
            if t > 0.24:
                _sa = min(255, int((t - 0.24) / 0.5 * 255))
                _sub_surf.set_alpha(_sa)
                screen.blit(_sub_surf, _sub_surf.get_rect(center=(W // 2, H // 2 - 24)))

        elif _f < _ends[2]:
            t = (_f - _ends[1]) / _P[2]
            _dialog_ov.fill((10, 6, 16, 175 if PHOTOSENSITIVE_SAFE_MODE else 200))
            screen.blit(_dialog_ov, (0, 0))
            _title_alpha = min(255, int((0.4 + 0.6 * t) * 255))
            _l4c = _title_f.render("LEVEL 4", True, (160, 230, 255))
            _l4c.set_alpha(_title_alpha)
            _sub_surf.set_alpha(_title_alpha)
            _hint_surf.set_alpha(_title_alpha)
            screen.blit(_l4c, _l4c.get_rect(center=(W // 2, H // 2 - 72)))
            screen.blit(_sub_surf, _sub_surf.get_rect(center=(W // 2, H // 2 - 22)))
            screen.blit(_hint_surf, _hint_surf.get_rect(center=(W // 2, H // 2 + 24)))

        else:
            t = (_f - _ends[2]) / _P[3]
            _black.fill((0, 0, 0, int(190 * t)))
            screen.blit(_black, (0, 0))

        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.music.set_volume(_orig_vol)


def _oracle_victory_message(screen: pygame.Surface, clock: pygame.time.Clock,
                            background_img: pygame.Surface,
                            oracle_img: pygame.Surface,
                            onyx_img: pygame.Surface) -> None:
    """Post-Level-4 Oracle-only message before final win screen."""
    W, H = screen.get_size()
    _name_f = pygame.font.SysFont("Arial", 30, bold=True)
    _line_f = pygame.font.SysFont("Arial", 24, bold=True)
    # High-contrast palette so dialogue remains legible over bright speech bubble fills.
    _oracle_tag = _name_f.render("ORACLE ALLIE", True, (132, 58, 180))
    _line1 = _line_f.render("Onyx G, your victory echoes through the realm.", True, (38, 28, 62))
    _line2 = _line_f.render("The ancestral gates are open to you.", True, (38, 28, 62))
    _oracle_tag_shadow = _name_f.render("ORACLE ALLIE", True, (12, 8, 26))
    _line1_shadow = _line_f.render("Onyx G, your victory echoes through the realm.", True, (12, 8, 26))
    _line2_shadow = _line_f.render("The ancestral gates are open to you.", True, (12, 8, 26))

    _ov = pygame.Surface((W, H), pygame.SRCALPHA)
    _bubble = pygame.Surface((560, 190), pygame.SRCALPHA)
    _P = [24, 84, 70, 28]
    _ends = [sum(_P[:i + 1]) for i in range(len(_P))]
    _TOTAL = _ends[-1]

    _orig_vol = pygame.mixer.music.get_volume()
    pygame.mixer.music.set_volume(max(0.0, _orig_vol * 0.42))

    for _f in range(_TOTAL):
        for _ev in pygame.event.get():
            if _ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()

        screen.blit(background_img, (0, 0))
        _ov.fill((8, 8, 18, 170 if PHOTOSENSITIVE_SAFE_MODE else 200))
        screen.blit(_ov, (0, 0))
        screen.blit(onyx_img, onyx_img.get_rect(midbottom=(W // 2 - 200, H - 18)))
        screen.blit(oracle_img, oracle_img.get_rect(midbottom=(W // 2 + 220, H - 18)))

        _bubble.fill((0, 0, 0, 0))
        _br = pygame.Rect(12, 12, 536, 160)
        pygame.draw.rect(_bubble, (252, 244, 255), _br, border_radius=34)
        pygame.draw.rect(_bubble, (255, 170, 255), _br, 4, border_radius=34)
        pygame.draw.rect(_bubble, (241, 229, 252), _br.inflate(-16, -16), border_radius=28)
        _tail = [(468, 166), (520, 186), (442, 160)]
        pygame.draw.polygon(_bubble, (252, 244, 255), _tail)
        pygame.draw.polygon(_bubble, (255, 170, 255), _tail, 4)

        _alpha = 255
        if _f < _ends[0]:
            _alpha = int(255 * (_f / max(1, _P[0])))
        elif _f > _ends[2]:
            _alpha = int(255 * max(0.0, 1.0 - ((_f - _ends[2]) / max(1, _P[3]))))
        _bubble.set_alpha(max(0, min(255, _alpha)))

        _pos = _bubble.get_rect(center=(W // 2 - 10, H // 2 - 70))
        screen.blit(_bubble, _pos)
        _oracle_tag.set_alpha(_bubble.get_alpha())
        _oracle_tag_shadow.set_alpha(_bubble.get_alpha())
        _line1.set_alpha(_bubble.get_alpha())
        _line1_shadow.set_alpha(_bubble.get_alpha())
        _line2.set_alpha(_bubble.get_alpha())
        _line2_shadow.set_alpha(_bubble.get_alpha())
        _tag_pos = _oracle_tag.get_rect(center=(_pos.centerx, _pos.top + 44))
        _line1_pos = _line1.get_rect(center=(_pos.centerx, _pos.top + 88))
        _line2_pos = _line2.get_rect(center=(_pos.centerx, _pos.top + 122))
        screen.blit(_oracle_tag_shadow, _tag_pos.move(2, 2))
        screen.blit(_oracle_tag, _tag_pos)
        screen.blit(_line1_shadow, _line1_pos.move(2, 2))
        screen.blit(_line1, _line1_pos)
        screen.blit(_line2_shadow, _line2_pos.move(2, 2))
        screen.blit(_line2, _line2_pos)

        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.music.set_volume(_orig_vol)


def _result_screen(screen, clock, img, music_file, score=0, scores=None, is_lose=False,
                   block_signal=0, continues_used=0, leaderboard_label='V2'):
    """Show win or lose image. Returns 'restart' or 'menu'."""
    W, H = screen.get_size()
    _sf_size = 30
    _sf2_size = 18 if is_lose else 20
    _btn_font_size = 22 if is_lose else 24
    _sf  = _get_arcade_font(_sf_size)
    _sf2 = _get_arcade_font(_sf2_size)
    _btn_font   = _get_arcade_font(_btn_font_size)
    _rank_letter, _rank_name = calculate_rank(score, block_signal, continues_used)
    _rank_cols = {
        'S': (255, 220, 60),
        'A': (57, 255, 20),
        'B': (180, 80, 255),
        'C': (230, 230, 230),
        'D': (255, 80, 80),
    }
    _rank_col = _rank_cols.get(_rank_letter, (230, 230, 230))
    lose_score_y = None
    lose_newbest_y = None
    lose_lby = None
    lose_row_gap = None
    _btn_gap = None
    _base_try_y = None
    if is_lose:
        monitor_rect = pygame.Rect(int(W * 0.352), int(H * 0.308), int(W * 0.296), int(H * 0.333))
    else:
        monitor_rect = pygame.Rect(int(W * 0.186), int(H * 0.296), int(W * 0.628), int(H * 0.338))
    monitor_safe = monitor_rect.inflate(-int(monitor_rect.width * 0.10), -int(monitor_rect.height * 0.12))
    win_score_y = None
    win_newbest_y = None
    win_rank_y = None
    win_board_header_y = None
    win_board_top_y = None
    if is_lose:
        lose_score_y = monitor_safe.top + int(monitor_safe.height * 0.14)
        lose_newbest_y = monitor_safe.top + int(monitor_safe.height * 0.22)
        btn_w   = int(monitor_safe.width * 0.56)
        btn_h   = max(30, int(monitor_safe.height * 0.16))
        btn_cx  = monitor_safe.centerx
        _btn_gap = max(6, int(H * 0.008))
        _base_try_y = monitor_safe.top + int(monitor_safe.height * 0.37)
        _try_y = _base_try_y
        _menu_y = _try_y + btn_h + _btn_gap

        lose_row_gap = max(22, int(H * 0.028))
        lose_lby = monitor_safe.bottom - (lose_row_gap * 3 + 20)
        _max_menu_bottom = lose_lby - 10
        if _menu_y + btn_h > _max_menu_bottom:
            _shift = (_menu_y + btn_h) - _max_menu_bottom
            _try_y -= _shift
            _menu_y -= _shift

        try_rect  = pygame.Rect(btn_cx - btn_w // 2, _try_y, btn_w, btn_h)
        menu_rect = pygame.Rect(btn_cx - btn_w // 2, _menu_y, btn_w, btn_h)
    else:
        btn_w   = int(monitor_safe.width * 0.40)
        btn_h   = max(30, int(monitor_safe.height * 0.16))
        _btn_gap = max(10, int(monitor_safe.width * 0.04))
        _btn_y = monitor_safe.bottom - btn_h
        _btn_total_w = btn_w * 2 + _btn_gap
        _btn_left = monitor_safe.centerx - _btn_total_w // 2
        try_rect  = pygame.Rect(_btn_left, _btn_y, btn_w, btn_h)
        menu_rect = pygame.Rect(_btn_left + btn_w + _btn_gap, _btn_y, btn_w, btn_h)
        win_score_y = monitor_safe.top + int(monitor_safe.height * 0.12)
        win_newbest_y = monitor_safe.top + int(monitor_safe.height * 0.24)
        win_rank_y = monitor_safe.top + int(monitor_safe.height * 0.36)
        win_board_header_y = monitor_safe.top + int(monitor_safe.height * 0.50)
        win_board_top_y = monitor_safe.top + int(monitor_safe.height * 0.62)

    highlight = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 60))

    _top_score  = scores[0][0] if scores else 0
    _RANK_COLS  = [( 57, 255,  20), (230, 230, 230), (180,  80, 255)]
    _RANK_LBLS  = ['1ST', '2ND', '3RD']

    _fit_cache = {}

    def _fit_render(text, color, base_size, max_width, min_size=14):
        _k = (text, color, base_size, max_width, min_size)
        _cached = _fit_cache.get(_k)
        if _cached is not None:
            return _cached
        _sz = base_size
        while _sz > min_size:
            _f = _get_arcade_font(_sz)
            _surf = _f.render(text, True, color)
            if _surf.get_width() <= max_width:
                _fit_cache[_k] = (_f, _surf)
                return _f, _surf
            _sz -= 1
        _f = _get_arcade_font(min_size)
        _surf = _f.render(text, True, color)
        _fit_cache[_k] = (_f, _surf)
        return _f, _surf

    def _fit_arcade_plain(text, base_size, max_width, color, min_size=12):
        _sz = base_size
        while _sz > min_size:
            _f = _get_arcade_font(_sz)
            _surf = _f.render(text, True, color)
            if _surf.get_width() <= max_width:
                return _f, _surf
            _sz -= 1
        _f = _get_arcade_font(min_size)
        return _f, _f.render(text, True, color)

    def _draw_arcade_text(text, font, color, center, glow_color=None):
        # Layered blits create an arcade-style outline + glow without extra assets.
        if glow_color:
            glow = font.render(text, True, glow_color)
            for ox, oy in ((-4, 0), (4, 0), (0, -4), (0, 4), (-3, -3), (3, -3), (-3, 3), (3, 3)):
                screen.blit(glow, glow.get_rect(center=(center[0] + ox, center[1] + oy)))
        shadow = font.render(text, True, (0, 0, 0))
        main = font.render(text, True, color)
        screen.blit(shadow, shadow.get_rect(center=(center[0] + 3, center[1] + 3)))
        screen.blit(main, main.get_rect(center=center))

    def _draw_lose_button(rect, label, hovered, primary=True):
        if primary:
            top_col = (255, 165, 30) if hovered else (245, 128, 0)
            bot_col = (195, 80, 0) if hovered else (145, 45, 0)
            border_col = (255, 215, 70) if hovered else (255, 140, 30)
            text_col = (255, 240, 205)
            glow_col = (90, 35, 0)
            inner_col = (30, 10, 0)
        else:
            top_col = (88, 88, 98) if hovered else (70, 70, 80)
            bot_col = (42, 42, 50) if hovered else (28, 28, 35)
            border_col = (168, 168, 188) if hovered else (120, 120, 138)
            text_col = (230, 230, 238)
            glow_col = (20, 20, 28)
            inner_col = (14, 14, 20)
        for i in range(rect.height):
            t = i / max(1, rect.height - 1)
            col = (
                int(top_col[0] + (bot_col[0] - top_col[0]) * t),
                int(top_col[1] + (bot_col[1] - top_col[1]) * t),
                int(top_col[2] + (bot_col[2] - top_col[2]) * t),
            )
            pygame.draw.line(screen, col, (rect.left, rect.top + i), (rect.right - 1, rect.top + i))
        pygame.draw.rect(screen, border_col, rect, 3, border_radius=10)
        pygame.draw.rect(screen, inner_col, rect.inflate(-8, -8), 2, border_radius=8)
        _label_font, _ = _fit_render(label, text_col, _btn_font_size, rect.width - 22, min_size=14)
        _draw_arcade_text(label, _label_font, text_col, rect.center, glow_col)

    # ── Score roll-up setup ──────────────────────────────────────────────
    _displayed  = 0
    _step       = max(1, score // 90)   # reaches final in ~1.5 s at 60 fps
    _tick_frame = 0
    _tick_snd   = None
    try:
        _tn = int(44100 * 0.025)
        _ta = array.array('h', [
            max(-32768, min(32767, int(
                math.sin(2 * math.pi * 1400 * i / 44100) * 7000 * (1 - i / _tn)
            ))) for i in range(_tn)
        ])
        _tick_snd = pygame.mixer.Sound(buffer=array.array('h', [s for s in _ta for _ in range(2)]))
        _tick_snd.set_volume(0.2)
    except Exception:
        pass

    while True:
        screen.blit(img, (0, 0))
        # Advance roll-up
        if _displayed < score:
            _displayed = min(score, _displayed + _step)
            _tick_frame += 1
            if _tick_snd and _tick_frame % 3 == 0:
                _tick_snd.play()
        _show_new_best = False
        if score > 0:
            _sc_text = f"Score:  {_displayed:,}"
            _, _sc = _fit_render(_sc_text, (57, 255, 20), _sf_size, monitor_safe.width - 12, min_size=16)
            if is_lose:
                _sc_c = (monitor_safe.centerx, lose_score_y)
            else:
                _sc_c = (monitor_safe.centerx, win_score_y)
            screen.blit(_sc, _sc.get_rect(center=_sc_c))
            _rk_text = f"RANK:  {_rank_letter}   {_rank_name}"
            _, _rk = _fit_render(_rk_text, _rank_col, _sf2_size if is_lose else 24,
                                 monitor_safe.width - 12, min_size=14)
            if is_lose:
                _rk_c = (monitor_safe.centerx, monitor_safe.top + int(monitor_safe.height * 0.28))
            else:
                _rk_c = (monitor_safe.centerx, win_rank_y)
            screen.blit(_rk, _rk.get_rect(center=_rk_c))
            if _displayed >= score and score >= _top_score:
                _show_new_best = True
                _, _nb = _fit_render("❖  NEW BEST  ❖", (180, 80, 255), _sf_size,
                                     monitor_safe.width - 10, min_size=16)
                if is_lose:
                    _nb_c = (monitor_safe.centerx, lose_newbest_y)
                else:
                    _nb_c = (monitor_safe.centerx, win_newbest_y)
                screen.blit(_nb, _nb.get_rect(center=_nb_c))

        if is_lose:
            # Keep vertical stacking collision-free inside the monitor.
            _anchor_y = lose_newbest_y if _show_new_best else lose_score_y
            _min_try_top = _anchor_y + (_sf.get_height() // 2) + _btn_gap
            _try_y = max(_base_try_y, _min_try_top)
            _menu_y = _try_y + btn_h + _btn_gap
            _max_menu_bottom = lose_lby - 10
            if _menu_y + btn_h > _max_menu_bottom:
                _shift = (_menu_y + btn_h) - _max_menu_bottom
                _try_y -= _shift
                _menu_y -= _shift
            try_rect.y = _try_y
            menu_rect.y = _menu_y

        # ── Mini leaderboard ────────────────────────────────────────────
        if scores:
            if is_lose:
                _lbx = monitor_safe.centerx
                _lby = lose_lby
            else:
                _win_row_gap = max(20, int(monitor_safe.height * 0.10))
                _win_first_offset = max(26, int(monitor_safe.height * 0.10))
                _lby = win_board_header_y
                _lbx = monitor_safe.centerx
            _, _hdr = _fit_render(f'TOP SCORES ({leaderboard_label})', (180, 80, 255), _sf2_size,
                                  monitor_safe.width - 12, min_size=13)
            screen.blit(_hdr, _hdr.get_rect(center=(_lbx, _lby)))
            for _ri, _row in enumerate(scores):
                _rs = int(_row[0]) if len(_row) > 0 else 0
                _rn = str(_row[1]) if len(_row) > 1 else cfg.HIGH_SCORE_DEFAULT_NAME
                _rt = display_score_timestamp(str(_row[2])) if len(_row) > 2 else ""
                _col = _RANK_COLS[_ri]
                _hl  = (score > 0 and _ri == 0 and score >= _top_score)
                _tc  = (255, 255, 255) if _hl else _col
                if is_lose:
                    _ry  = _lby + 22 + _ri * lose_row_gap
                    _name_max = monitor_safe.width - 170
                    pygame.draw.circle(screen, _col, (_lbx - 120, _ry), 10)
                    pygame.draw.circle(screen, (0, 0, 0), (_lbx - 120, _ry), 6)
                    _row_surf = _sf2.render(f"{_RANK_LBLS[_ri]}  {_rn}  {_rs:,}", True, _tc)
                    screen.blit(_row_surf, _row_surf.get_rect(midleft=(_lbx - 102, _ry - 10)))
                    if _rt:
                        _t_small = _get_arcade_font(11).render(_rt, True, (160, 160, 160))
                        screen.blit(_t_small, _t_small.get_rect(midleft=(_lbx + 8, _ry + 10)))
                else:
                    _ry  = win_board_top_y + _ri * _win_row_gap
                    _row_left = monitor_safe.left + 14
                    _row_right = monitor_safe.right - 14
                    _badge_x = _row_left + 12
                    _rank_cx = _row_left + 44
                    _score_anchor = _row_right
                    _name_left = _row_left + 76
                    _name_right = _row_right - 88
                    _name_max = max(40, _name_right - _name_left)
                    pygame.draw.circle(screen, _col, (_badge_x, _ry), 9)
                    pygame.draw.circle(screen, (0, 0, 0), (_badge_x, _ry), 5)
                    _, _rank_surf = _fit_arcade_plain(_RANK_LBLS[_ri], 14, 42, _col, min_size=11)
                    screen.blit(_rank_surf, _rank_surf.get_rect(center=(_rank_cx, _ry)))
                    _, _name_surf = _fit_arcade_plain(_rn, 16, _name_max, _tc, min_size=12)
                    _, _score_surf = _fit_arcade_plain(f"{_rs:,}", 16, 82, _col, min_size=11)
                    screen.blit(_name_surf, _name_surf.get_rect(midleft=(_name_left, _ry)))
                    screen.blit(_score_surf, _score_surf.get_rect(midright=(_score_anchor, _ry)))
                    if _rt:
                        _, _time_surf = _fit_arcade_plain(_rt, 11, 126, (150, 150, 150), min_size=9)
                        screen.blit(_time_surf, _time_surf.get_rect(midright=(_score_anchor - 92, _ry + 12)))
        mx, my = pygame.mouse.get_pos()
        _hover_try = try_rect.collidepoint(mx, my)
        _hover_menu = menu_rect.collidepoint(mx, my)
        _draw_lose_button(try_rect, "TRY AGAIN" if is_lose else "PLAY AGAIN",
                          _hover_try, primary=True)
        _draw_lose_button(menu_rect, "MAIN MENU", _hover_menu, primary=False)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if _displayed < score:
                    _displayed = score   # skip roll-up
                elif event.key in (pygame.K_RETURN, pygame.K_r):
                    return "restart"
                elif event.key in (pygame.K_ESCAPE, pygame.K_m):
                    return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if _displayed < score:
                    _displayed = score   # skip roll-up on click too
                elif try_rect.collidepoint(event.pos):
                    return "restart"
                elif menu_rect.collidepoint(event.pos):
                    return "menu"

        pygame.display.flip()
        clock.tick(60)


def _name_entry_screen(screen, clock, font_big, font_med, font,
                       place=1, scores=None, new_score=0, leaderboard_label='V2'):
    """Classic 3-letter initials entry on a new high score (top 3 aware)."""
    W, H   = screen.get_size()
    _af_big = _get_arcade_font(24)
    _af_med = _get_arcade_font(16)
    initials = ['A', 'A', 'A']
    cursor   = 0
    blink    = 0

    # ── Load arcade cabinet frame ─────────────────────────────────────────
    _cab_frame = None
    _cab_rect  = None
    _SCR_V_MID = 0.37
    _SCR_V_TOP = 0.32
    try:
        _cab_path = os.path.join(os.path.dirname(__file__), 'HIGH SCORE Frame 2 .png')
        _raw = pygame.image.load(_cab_path).convert_alpha()
        _iw, _ih = _raw.get_size()
        # Cover mode: scale to fill full screen width; crops top/bottom
        _scale = W / _iw
        _cw    = W
        _ch    = int(_ih * _scale)
        _cab_frame = pygame.transform.smoothscale(_raw, (_cw, _ch))
        _cab_rect  = _cab_frame.get_rect(midtop=(W // 2, 0))
    except Exception:
        pass

    if _cab_frame and _cab_rect:
        _scr_cx    = W // 2
        _scr_cy    = _cab_rect.top + int(_cab_rect.height * _SCR_V_MID)
        _scr_top_y = max(10, _cab_rect.top + int(_cab_rect.height * _SCR_V_TOP))
        _cab_screen = pygame.Rect(
            _cab_rect.left + int(_cab_rect.width * 0.18),
            _cab_rect.top + int(_cab_rect.height * 0.29),
            int(_cab_rect.width * 0.64),
            int(_cab_rect.height * 0.34),
        )
    else:
        _scr_cx, _scr_cy = W // 2, H // 2
        _scr_top_y = H // 2 - 130
        _cab_screen = pygame.Rect(int(W * 0.18), int(H * 0.28), int(W * 0.64), int(H * 0.36))

    _cab_safe = _cab_screen.inflate(-int(_cab_screen.width * 0.08), -int(_cab_screen.height * 0.08))
    _cab_max = _cab_safe.width

    def _fit_arcade_color(text: str, max_width: int, base_size: int, color, min_size: int = 14):
        size = base_size
        while size >= min_size:
            fnt = _get_arcade_font(size)
            surf = fnt.render(text, True, color)
            if surf.get_width() <= max_width:
                return fnt, surf
            size -= 1
        fnt = _get_arcade_font(min_size)
        return fnt, fnt.render(text, True, color)

    # ── Place-specific header ─────────────────────────────────────────────
    _PLACE_INFO = {
        1: ('1ST PLACE!', (255, 215,   0)),
        2: ('2ND PLACE!', (200, 200, 215)),
        3: ('3RD PLACE!', (205, 127,  50)),
    }
    _title_text, _title_col = _PLACE_INFO.get(place, ('NEW BEST!', (255, 220, 0)))

    def _fit_arcade(text: str, max_width: int, base_size: int, min_size: int = 14):
        size = base_size
        while size >= min_size:
            fnt = _get_arcade_font(size)
            surf = fnt.render(text, True, (255, 255, 255))
            if surf.get_width() <= max_width:
                return fnt, surf
            size -= 1
        fnt = _get_arcade_font(min_size)
        return fnt, fnt.render(text, True, (255, 255, 255))

    # ── Entry loop ────────────────────────────────────────────────────────
    confirmed_name = None
    while confirmed_name is None:
        screen.fill((0, 0, 0))
        if _cab_frame and _cab_rect:
            screen.blit(_cab_frame, _cab_rect)

        _panel = pygame.Surface((_cab_safe.width, _cab_safe.height), pygame.SRCALPHA)
        _panel.fill((6, 10, 18, 120))
        screen.blit(_panel, _cab_safe.topleft)

        t_font, t_surf = _fit_arcade_color(_title_text, _cab_max, 24, _title_col, min_size=16)
        lb_font, _lb_surf = _fit_arcade_color(f'LEADERBOARD: {leaderboard_label}', _cab_max, 15,
                                              (130, 220, 255), min_size=11)
        sub_font, sub_surf = _fit_arcade_color('ENTER YOUR INITIALS', _cab_max, 20,
                                               (245, 245, 255), min_size=14)
        _header_y = _cab_safe.top + 18
        screen.blit(t_surf, t_surf.get_rect(center=(_scr_cx, _header_y + t_surf.get_height() // 2)))
        screen.blit(_lb_surf, _lb_surf.get_rect(center=(_scr_cx, _header_y + 28 + _lb_surf.get_height() // 2)))
        screen.blit(sub_surf, sub_surf.get_rect(center=(_scr_cx, _cab_safe.top + int(_cab_safe.height * 0.34))))

        _init_font = _get_arcade_font(38)
        _initials_y = _cab_safe.top + int(_cab_safe.height * 0.56)
        for i, ch in enumerate(initials):
            col = (57, 255, 20) if i == cursor else (0, 200, 60)
            if i != cursor or (blink // 15) % 2 == 0:
                ls = _init_font.render(ch, True, col)
                screen.blit(ls, ls.get_rect(center=(_scr_cx - 70 + i * 70, _initials_y)))
            pygame.draw.line(screen, col,
                             (_scr_cx - 84 + i * 70, _initials_y + 36),
                             (_scr_cx - 36 + i * 70, _initials_y + 36), 3)
        hint_font = _get_arcade_font(15)
        hint = hint_font.render('\u2191\u2193: letter    \u2192: next    ENTER: confirm',
                                True, (0, 160, 50))
        _hint_rect = hint.get_rect(center=(_scr_cx, _cab_safe.bottom - 20))
        if _hint_rect.width > _cab_safe.width - 10:
            hint_font, hint = _fit_arcade_color('\u2191\u2193: letter    \u2192: next    ENTER: confirm',
                                                _cab_safe.width - 10, 14, (0, 160, 50), min_size=10)
            _hint_rect = hint.get_rect(center=(_scr_cx, _cab_safe.bottom - 18))
        screen.blit(hint, _hint_rect)
        blink += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    initials[cursor] = chr((ord(initials[cursor]) - ord('A') - 1) % 26 + ord('A'))
                elif event.key == pygame.K_DOWN:
                    initials[cursor] = chr((ord(initials[cursor]) - ord('A') + 1) % 26 + ord('A'))
                elif event.key in (pygame.K_RIGHT, pygame.K_TAB):
                    if cursor < 2:
                        cursor += 1
                    else:
                        confirmed_name = ''.join(initials)
                elif event.key == pygame.K_LEFT:
                    cursor = max(0, cursor - 1)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    confirmed_name = ''.join(initials)
        pygame.display.flip()
        clock.tick(60)

    # ── Hall of Fame display ──────────────────────────────────────────────
    if scores is not None:
        _RANK_COLS   = [( 57, 255,  20), (230, 230, 230), (180,  80, 255)]
        _RANK_LABELS = ['1ST', '2ND', '3RD']
        # Build preview with new entry inserted at the earned rank
        _preview = [list(s) for s in scores]
        _preview.insert(place - 1, [new_score, confirmed_name, current_score_timestamp()])
        _preview = _preview[:3]
        _hof_timer = 0
        while _hof_timer < 240:          # ~4 s; any key exits early
            screen.fill((0, 0, 0))
            if _cab_frame and _cab_rect:
                screen.blit(_cab_frame, _cab_rect)

            _panel = pygame.Surface((_cab_safe.width, _cab_safe.height), pygame.SRCALPHA)
            _panel.fill((6, 10, 18, 120))
            screen.blit(_panel, _cab_safe.topleft)

            hof_font, hof_surf = _fit_arcade_color(f'\u2605 HALL OF FAME ({leaderboard_label}) \u2605',
                                                   _cab_max, 20, (255, 235, 120), min_size=14)
            screen.blit(hof_surf, hof_surf.get_rect(center=(_scr_cx, _cab_safe.top + 20)))

            _rank_x = _cab_safe.left + 44
            _name_left = _cab_safe.left + 94
            _score_right = _cab_safe.right - 20
            _name_max = max(50, _score_right - _name_left - 82)
            _row_start_y = _cab_safe.top + int(_cab_safe.height * 0.34)
            _row_gap = max(36, int(_cab_safe.height * 0.17))

            for _ri, _row in enumerate(_preview):
                _rs = int(_row[0]) if len(_row) > 0 else 0
                _rn = str(_row[1]) if len(_row) > 1 else cfg.HIGH_SCORE_DEFAULT_NAME
                _rt = display_score_timestamp(str(_row[2])) if len(_row) > 2 else ""
                _ry  = _row_start_y + _ri * _row_gap
                _col = _RANK_COLS[_ri]
                _new = (_ri == place - 1)

                # Highlight row for the just-entered score
                if _new:
                    _bg = pygame.Surface((_cab_safe.width - 16, 42), pygame.SRCALPHA)
                    _bg.fill((255, 255, 0, 35))
                    screen.blit(_bg, _bg.get_rect(center=(_scr_cx, _ry)))

                # Filled circle medal + dark inner ring
                pygame.draw.circle(screen, _col, (_cab_safe.left + 20, _ry), 10)
                pygame.draw.circle(screen, (0, 0, 0), (_cab_safe.left + 20, _ry), 6)
                _, rank_s = _fit_arcade_color(_RANK_LABELS[_ri], 46, 14, _col, min_size=11)
                screen.blit(rank_s, rank_s.get_rect(center=(_rank_x, _ry)))
                _, name_s = _fit_arcade_color(_rn, _name_max, 16,
                                              (255, 255, 255) if _new else _col, min_size=12)
                screen.blit(name_s, name_s.get_rect(midleft=(_name_left, _ry)))
                _, sc_s = _fit_arcade_color(f'{_rs:,}', 92, 16, _col, min_size=11)
                screen.blit(sc_s, sc_s.get_rect(midright=(_score_right, _ry)))
                if _rt:
                    _, ts_s = _fit_arcade_color(_rt, 126, 11, (150, 150, 150), min_size=9)
                    screen.blit(ts_s, ts_s.get_rect(midright=(_score_right - 96, _ry + 12)))

            cont_font = _get_arcade_font(14)
            cont_s = cont_font.render('Press any key to continue\u2026', True, (110, 110, 110))
            if cont_s.get_width() > _cab_safe.width - 10:
                cont_font, cont_s = _fit_arcade_color('Press any key to continue\u2026',
                                                      _cab_safe.width - 10, 14, (110, 110, 110), min_size=10)
            screen.blit(cont_s, cont_s.get_rect(center=(_scr_cx, _cab_safe.bottom - 18)))
            pygame.display.flip()
            clock.tick(60)
            _hof_timer += 1
            for _ev in pygame.event.get():
                if _ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if _ev.type == pygame.KEYDOWN:
                    _hof_timer = 9999   # break out

    return confirmed_name


def build_rage_vignette(width: int, height: int, color: Tuple[int, int, int], base_alpha: int) -> pygame.Surface:
    """
    Build a reusable boss-rage screen-edge vignette surface.
    
    Creates a gradient fade overlay at screen edges to indicate boss critical state.
    """
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    depth = height // 3
    for y in range(0, depth, 12):
        alpha = int(base_alpha * (1.0 - y / depth))
        pygame.draw.rect(surf, (*color, alpha), (0, y, width, 12))
        pygame.draw.rect(surf, (*color, alpha), (0, height - y - 12, width, 12))
    return surf


def main() -> None:
    """
    Entry point — initializes everything and runs the outer restart loop.

    Startup sequence:
      1. pygame.mixer.pre_init + pygame.init
      2. Dedicated audio channels (0-3) reserved before any sound loads
      3. Asset loading: images, sprite sheets, sounds, fonts
      4. PlayerSpriteAnimator constructed with Left/Right sprite sheets
      5. Menu → Tutorial (optional) → Gameplay inner loop → Results screen
      6. Outer loop allows consecutive runs without relaunching the process
    """
    pygame.mixer.pre_init(cfg.AUDIO_INIT_FREQ, cfg.AUDIO_INIT_SIZE, 
                          cfg.AUDIO_INIT_CHANNELS, cfg.AUDIO_INIT_BUFFER)
    pygame.init()
    # ── Xbox / gamepad controller support ─────────────────────────────────────
    pygame.joystick.init()
    _joy = None   # connected Joystick object, or None if no controller
    if pygame.joystick.get_count() > 0:
        _joy = pygame.joystick.Joystick(0)
        _joy.init()
        print(f"🎮 Controller connected: {_joy.get_name()}")
    impact_channel   = pygame.mixer.Channel(0)  # ch 0: enemy/player hits — never dropped
    burst_channel    = pygame.mixer.Channel(1)  # ch 1: signal burst punch
    run_channel      = pygame.mixer.Channel(2)  # ch 2: run footsteps (looping)
    jetpack_channel  = pygame.mixer.Channel(3)  # ch 3: jetpack thrust (looping)

    WIDTH, HEIGHT = cfg.WIDTH, cfg.HEIGHT
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    screen_bounds = pygame.Rect(0, 0, WIDTH, HEIGHT)
    pygame.display.set_caption("Onyx G vs Space Drones")
    clock = pygame.time.Clock()

    dir_map = _build_dir_map()

    # ── One-time asset loads ──────────────────────────────────────────────────
    # Player pose sprites (full-body): idle and upward shooting pose.
    sprite_idle_image = load_player_pose_image(
        dir_map,
        "D.png",
        cfg.PLAYER_SIZE
    )

    sprite_shoot_image = load_player_pose_image(
        dir_map,
        "C.png",
        cfg.PLAYER_SIZE
    )
    _anim_sheet_path = find_file(dir_map, "FlyLeftAndRight.png")
    _anim_sheet = pygame.image.load(_anim_sheet_path).convert_alpha() if _anim_sheet_path else None
    _lsheet_path = find_file(dir_map, "LeftAnimatons.png")
    _rsheet_path = find_file(dir_map, "RightAnimations.png")
    _lsheet = pygame.image.load(_lsheet_path).convert_alpha() if _lsheet_path else None
    _rsheet = pygame.image.load(_rsheet_path).convert_alpha() if _rsheet_path else None
    player_animator = PlayerSpriteAnimator(
        sprite_idle_image, sprite_shoot_image,
        sheet=_anim_sheet, lsheet=_lsheet, rsheet=_rsheet,
    )
    # Keep this name for existing rect init and fallback paths.
    sprite_image       = sprite_idle_image
    drone_image    = load_image(dir_map, "drone_spaceship.png",   (40, 40))
    drone_images_level_2 = load_drone_sheet_sprites(dir_map, "Drones Level 2 .png", (44, 44))
    drone_images_level_4 = load_level4_enemy_sprites(
        dir_map,
        [
            "Level_4_enemies .png",
            "Level_4_enemies.png",
            "Level 4 enemies .png",
            "Level 4 enemies.png",
        ],
        (46, 46),
    )
    if not drone_images_level_4:
        drone_images_level_4 = drone_images_level_2
    minion_image   = load_image(dir_map, "tibbixel-dot-com-4947-wpng 2.png", (32, 32))
    boss_image_level_1 = load_image(dir_map, "cranium_commander 2.png", (100, 100))
    boss_image_level_2 = load_image(dir_map, "Agent boss Level 2.png", (124, 124))
    boss_image_level_3 = load_image(dir_map, "Level 3 Boss.png", (140, 140))
    _boss_level4_file = (
        find_file(dir_map, "Level_4_Boss.png")
        or find_file(dir_map, "Level 4 Boss.png")
        or find_file(dir_map, "Boss Level 4.png")
        or find_file(dir_map, "Ancestor Boss.png")
    )
    if _boss_level4_file:
        boss_image_level_4 = load_image(dir_map, os.path.basename(_boss_level4_file), (152, 152))
    else:
        boss_image_level_4 = boss_image_level_3
    ancestor_allie_img = load_image(dir_map, "Ancestor_allie .png", (170, 170))
    oracle_allie_img = load_image(dir_map, "Oracle_allie .png", (170, 170))
    water_image   = load_image_tight(dir_map, "gg_water_new .png", (40, 40))
    background_img_level_1 = load_image_cover(dir_map, "space_background.png", (WIDTH, HEIGHT))
    background_img_level_2 = load_image_cover(dir_map, "Level 2 .png", (WIDTH, HEIGHT))
    background_img_level_3 = load_image_cover(dir_map, "Level_3.png", (WIDTH, HEIGHT))
    _level4_bg_file = (
        find_file(dir_map, "Level_4_scene .png")
        or find_file(dir_map, "Level_4_scene.png")
        or find_file(dir_map, "Level_4.png")
        or find_file(dir_map, "Level 4.png")
        or find_file(dir_map, "Ancestral Realm.png")
    )
    if _level4_bg_file:
        background_img_level_4 = load_image_cover(dir_map, os.path.basename(_level4_bg_file), (WIDTH, HEIGHT))
    else:
        background_img_level_4 = background_img_level_3
    menu_img       = load_image(dir_map, "Start Menu 3.png", (WIDTH, HEIGHT))
    win_img        = load_image(dir_map, "Win Scene 3.png",      (WIDTH, HEIGHT))
    lose_img       = load_image(dir_map, "Lose Screen 3.png",    (WIDTH, HEIGHT))

    music_file = find_file(dir_map, "crab_ass.ogg")
    if music_file:
        try:
            pygame.mixer.music.load(music_file)
            pygame.mixer.music.set_volume(cfg.VOLUME_MUSIC)
            pygame.mixer.music.play(-1)
            print("🎶 Music playing.")
        except pygame.error as err:
            print(f"⚠️ Audio disabled: {err}")
            music_file = None
    else:
        print("⚠️ Music file not found. Continuing without music.")

    level2_music_file = find_level2_music_file(dir_map, music_file)
    if level2_music_file:
        print(f"🎶 Level 2 music ready: {os.path.basename(level2_music_file)}")
    else:
        print("⚠️ No dedicated Level 2 music found. Level 1 BGM will continue.")
    
    level3_music_file = (
        find_file(dir_map, "Level_3_music.ogg")
        or find_file(dir_map, "Level_3_Music.ogg")
        or find_file(dir_map, "Level 3 music.ogg")
    )
    if level3_music_file:
        print(f"🎶 Level 3 music ready: {os.path.basename(level3_music_file)}")
    else:
        print("⚠️ No dedicated Level 3 music found. Level 2 BGM will continue.")
    level4_music_file = (
        find_file(dir_map, "Level_4_music.ogg")
        or find_file(dir_map, "Level 4 music.ogg")
        or find_file(dir_map, "Ancestral Realm music.ogg")
    )
    if level4_music_file:
        print(f"🎶 Level 4 music ready: {os.path.basename(level4_music_file)}")
    else:
        print("⚠️ No dedicated Level 4 music found. Level 3 BGM will continue.")
    
    current_bgm_tag = "level1"

    win_music_file = find_file(dir_map, "WinScene music.ogg")
    lose_music_file = find_file(dir_map, "Lose Scene Music.ogg")
    start_menu_music_file = find_file(dir_map, "Start Menu Music 2.ogg")
    tutorial_music_file = find_file(dir_map, "Tutorial Page music.ogg")

    tutorial_img = [
        load_image(dir_map, "Tutorial Screen 4 .png", (WIDTH, HEIGHT)),
    ]

    shoot_sound = None
    shoot_file = find_file(dir_map, "GUNPis_Shot in 357 magnum 9 mm (ID 0438)_BigSoundBank.com.ogg")
    if shoot_file:
        try:
            shoot_sound = pygame.mixer.Sound(shoot_file)
            shoot_sound.set_volume(cfg.VOLUME_SHOOT_SOUND)
        except pygame.error as err:
            print(f"⚠️ Shoot sound disabled: {err}")

    impact_sound = None
    _impact_sf = find_file(dir_map, "Impact sound 2 .ogg")
    if _impact_sf:
        try:
            impact_sound = pygame.mixer.Sound(_impact_sf)
            impact_sound.set_volume(cfg.VOLUME_IMPACT_SOUND)
        except pygame.error as err:
            print(f"⚠️ Impact sound asset failed, using synth fallback: {err}")
    if impact_sound is None:
        try:
            impact_sound = _make_impact_sound()
        except Exception as err:
            impact_sound = None
            print(f"⚠️ Impact sound disabled: {err}")

    signal_burst_sound = None
    _signal_burst_sf = (
        find_file(dir_map, "Signal Burst sound.ogg")
        or find_file(dir_map, "Signal burst sound.ogg")
        or find_file(dir_map, "Signal Burst.ogg")
    )
    if _signal_burst_sf:
        try:
            signal_burst_sound = pygame.mixer.Sound(_signal_burst_sf)
            signal_burst_sound.set_volume(min(1.0, cfg.VOLUME_IMPACT_SOUND * 1.25))
        except pygame.error as err:
            print(f"⚠️ Signal burst sound asset failed, using synth fallback: {err}")
    if signal_burst_sound is None:
        try:
            signal_burst_sound = _make_signal_burst_sound()
        except Exception as err:
            signal_burst_sound = impact_sound
            print(f"⚠️ Signal burst sound fallback disabled: {err}")

    try:
        siren_sound = _make_siren_sound()
    except Exception as err:
        siren_sound = None
        print(f"⚠️ Siren sound disabled: {err}")

    try:
        powerup_sound = _make_powerup_sound()
    except Exception as err:
        powerup_sound = None
        print(f"⚠️ Power-up sound disabled: {err}")

    sativa_sound = None
    _sativa_sf = find_file(dir_map, "Power Up sativa sound.ogg")
    if _sativa_sf:
        try:
            sativa_sound = pygame.mixer.Sound(_sativa_sf)
            sativa_sound.set_volume(cfg.VOLUME_SATIVA_SOUND)
        except pygame.error:
            pass

    run_sound = None
    _run_sf = find_file(dir_map, "RunningSound.ogg")
    if _run_sf:
        try:
            run_sound = pygame.mixer.Sound(_run_sf)
            run_sound.set_volume(0.7)
            print("🏃 Run sound loaded.")
        except pygame.error as err:
            print(f"⚠️ Run sound disabled: {err}")

    jetpack_sound = None
    _jetpack_sf = find_file(dir_map, "JetpackSound.ogg")
    if _jetpack_sf:
        try:
            jetpack_sound = pygame.mixer.Sound(_jetpack_sf)
            jetpack_sound.set_volume(0.5)
            print("🚀 Jetpack sound loaded.")
        except pygame.error as err:
            print(f"⚠️ Jetpack sound disabled: {err}")

    try:
        landing_sound = _make_landing_sound()
    except Exception as err:
        landing_sound = None
        print(f"⚠️ Landing sound disabled: {err}")

    try:
        near_miss_sound = _make_near_miss_sound()
    except Exception as err:
        near_miss_sound = None
        print(f"⚠️ Near-miss sound disabled: {err}")

    try:
        countdown_tick_sound = _make_countdown_tick_sound()
    except Exception as err:
        countdown_tick_sound = None
        print(f"⚠️ Countdown tick sound disabled: {err}")

    # Combo milestone sounds: 4 escalating chirps for x5 / x10 / x15 / x20+
    # Each level gets a higher base frequency and shorter, snappier duration.
    try:
        combo_sounds = [
            _make_combo_sound( 520,  820, 0.13),   # x5  — warm
            _make_combo_sound( 720, 1100, 0.11),   # x10 — bright
            _make_combo_sound( 950, 1500, 0.09),   # x15 — sharp
            _make_combo_sound(1200, 2000, 0.07),   # x20 — piercing
        ]
    except Exception as err:
        combo_sounds = []
        print(f"⚠️ Combo sounds disabled: {err}")

    font     = pygame.font.SysFont("Arial", 24)
    font_big = pygame.font.SysFont("Arial", 64, bold=True)
    font_med = pygame.font.SysFont("Arial", 36)
    font_popup = pygame.font.SysFont("Arial", 22, bold=True)
    font_huge = pygame.font.SysFont("Arial", 120, bold=True)

    def _fit_banner_text(text: str, color: Tuple[int, int, int], max_width: int,
                         base_size: int = 64, min_size: int = 20) -> pygame.Surface:
        size = base_size
        while size >= min_size:
            surf = pygame.font.SysFont("Arial", size, bold=True).render(text, True, color)
            if surf.get_width() <= max_width:
                return surf
            size -= 2
        return pygame.font.SysFont("Arial", min_size, bold=True).render(text, True, color)

    # ── One-time visual effect surfaces ──────────────────────────────────────
    # Colorkey surface: ~3× faster blit than SRCALPHA (skips transparent pixels; no per-pixel alpha)
    scanline_surf = pygame.Surface((WIDTH, HEIGHT))
    scanline_surf.fill((255, 0, 255))  # magenta = transparent key
    for _sl_y in range(0, HEIGHT, 3):
        pygame.draw.line(scanline_surf, (0, 0, 0), (0, _sl_y), (WIDTH, _sl_y))
    scanline_surf.set_colorkey((255, 0, 255))
    scanline_surf.set_alpha(24 if PHOTOSENSITIVE_SAFE_MODE else 45)
    _chroma_red  = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _chroma_cyan = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    # Pre-allocated overlay surfaces — reused every frame (avoids per-frame allocation & GC)
    _hf_surf     = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _lh_surf     = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _warn_surf   = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _defeat_surf      = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _wtov_surf        = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _cont_ov          = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _cont_ov.fill((0, 0, 0, 190))
    _pov_surf         = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _pov_surf.fill((0, 0, 20, 200))
    _uov_surf         = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _uov_surf.fill((0, 0, 0, 180))
    _trauma_surf      = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _death_flash_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _fb_glow_surf     = pygame.Surface((16, 24), pygame.SRCALPHA)
    _kflash_surf      = pygame.Surface((40, 40), pygame.SRCALPHA)
    _kflash_surf.fill((255, 0, 0, 70 if PHOTOSENSITIVE_SAFE_MODE else 140))
    _dflash_surf      = pygame.Surface((40, 40), pygame.SRCALPHA)
    _dflash_surf.fill((0, 220, 255, 60 if PHOTOSENSITIVE_SAFE_MODE else 130))
    _signal_ring_surf = pygame.Surface((420, 420), pygame.SRCALPHA)
    _water_glow_surf   = pygame.Surface((72, 72), pygame.SRCALPHA)
    _boss_tint_surf   = pygame.Surface((100, 100), pygame.SRCALPHA)
    _sprite_glow_surf = pygame.Surface((240, 240), pygame.SRCALPHA)
    # Pre-rendered HUD surfaces (static text — rendered once, blitted every frame)
    _heart_red_h  = font.render("\u2665", True, _COL_RED)
    _heart_grey_h = font.render("\u2665", True, (70, 70, 70))
    _block_lbl_h  = font.render('BLOCK SIGNAL', True, (180, 220, 255))
    _signal_lbl_h = font.render('SIGNAL BURST', True, (190, 120, 255))
    _sativa_lbl_h = font.render('\u2605 HYDRATED', True, (70, 180, 255))
    _shake_surf   = pygame.Surface((WIDTH, HEIGHT))  # no SRCALPHA; plain pixel copy
    # Dirty caches for text that rarely changes
    _score_cache = {'val': -1, 'surf': None}
    _hs_cache    = {'val': '', 'surf': None}
    _wave_cache  = {'val': -1, 'surf': None}
    _perks_cache  = {'val': '', 'surf': None}
    _scale_cache  = {'key': None, 'surf': None}   # sprite transform.scale cache
    _streak_cache = {'key': None, 'surf': None}   # streak message text cache
    _combo_cache  = {'val': None, 'surf': None}    # combo counter text cache
    _block_pct_cache  = {'val': None, 'col': None, 'surf': None}
    _signal_pct_cache  = {'val': None, 'col': None, 'surf': None}
    _ap_guard_cache    = {'val': -1, 'surf': None}   # ANCESTRAL GUARD counter
    _crem_cache        = {'val': -1, 'surf': None}   # continues-remaining text
    _cn_surf_cache: dict = {}                         # countdown digit (keyed on (secs, color))
    _enemy_roll_cache  = {}
    # Banner cache avoids repeated font.render/_fit_banner_text in the render hot path.
    _banner_cache = {
        'wave_intro': {'key': None, 'title': None, 'mult': None},
        'wave_complete': {'key': None, 'title': None, 'kills': None, 'bonus': None},
        'victory': {'key': None, 'surf': None},
    }
    _level2_intro_title = _fit_banner_text('LEVEL 2', (255, 90, 90), WIDTH - 120)
    _level2_intro_sub = _fit_banner_text(
        'FASTER DRONES  •  TRAUMA MODE',
        (255, 220, 220),
        WIDTH - 120,
        base_size=34,
        min_size=18,
    )
    _level3_intro_title = _fit_banner_text('LEVEL 3', (255, 180, 0), WIDTH - 120)
    _level3_intro_sub = _fit_banner_text(
        'APEX MODE  •  ULTIMATE CHALLENGE',
        (255, 240, 120),
        WIDTH - 120,
        base_size=34,
        min_size=18,
    )
    _level4_intro_title = _fit_banner_text('LEVEL 4', (170, 230, 255), WIDTH - 120)
    _level4_intro_sub = _fit_banner_text(
        'ANCESTRAL PROTECTION  •  FINAL ASCENT',
        (210, 255, 230),
        WIDTH - 120,
        base_size=34,
        min_size=18,
    )
    # Pre-rendered static banner surfaces (text/color never change)
    _cont_q_surf      = font_big.render('CONTINUE?', True, (255, 220, 50))
    _cont_press_surf  = font_med.render('PRESS  SPACE  TO  CONTINUE', True, (200, 200, 255))
    _brage_surf       = font_big.render('\u2620  RAGE  MODE  \u2620', True, (255, 40, 40))
    _warn_text_surf  = font_big.render('\u26a0  WARNING  \u26a0', True, (255, 50, 50))
    _swarm_text_surf = font_big.render('\u26a1  DRONE SWARM!  \u26a1', True, (255, 150, 0))
    _trauma_text_surf = font_big.render('TRAUMA MODE', True, (255, 90, 90))
    _ready_title_safe_surf = font_big.render('PLAYER 1', True, (255, 210, 0))
    _ready_sub_surf = font_big.render('GET  READY!', True, (255, 255, 255))
    _l4_story_allie_name_surf = font_med.render('ANCESTOR ALLIE', True, (54, 118, 158))
    _l4_story_allie_line_surf = font.render('Onyx G, you have done well.', True, (30, 26, 58))
    _l4_story_oracle_name_surf = font_med.render('ORACLE ALLIE', True, (132, 58, 180))
    _l4_story_oracle_line_surf = font.render('You have earned protection from the ancestral realm.', True, (30, 26, 58))
    _l4_story_bless_name_surf = font_med.render('ANCESTRAL BLESSING', True, (34, 126, 88))
    _l4_story_bless_line_surf = font.render('+3 ancestral guard charges active.', True, (30, 26, 58))
    _l4_story_allie_name_shadow = font_med.render('ANCESTOR ALLIE', True, (10, 8, 24))
    _l4_story_allie_line_shadow = font.render('Onyx G, you have done well.', True, (10, 8, 24))
    _l4_story_oracle_name_shadow = font_med.render('ORACLE ALLIE', True, (10, 8, 24))
    _l4_story_oracle_line_shadow = font.render('You have earned protection from the ancestral realm.', True, (10, 8, 24))
    _l4_story_bless_name_shadow = font_med.render('ANCESTRAL BLESSING', True, (10, 8, 24))
    _l4_story_bless_line_shadow = font.render('+3 ancestral guard charges active.', True, (10, 8, 24))
    _l4_bubble_surf = pygame.Surface((520, 170), pygame.SRCALPHA)
    _l4_bubble_small_surf = pygame.Surface((450, 150), pygame.SRCALPHA)
    # Pre-built rage vignette surfaces (static geometry, only two variants)
    _rage_vignette_cache = {
        'normal':   build_rage_vignette(WIDTH, HEIGHT, (200, 0, 0), 70),
        'critical': build_rage_vignette(WIDTH, HEIGHT, (255, 60, 0), 105),
    }

    # ── Constants ─────────────────────────────────────────────────────────────
    SPEED                = 5
    # Player movement feel
    PLAYER_ACCELERATION = 0.88
    PLAYER_DECELERATION = 0.74
    PLAYER_TURN_ACCEL_MULT = 1.30
    PLAYER_MAX_NORMAL_SPEED = 9.0
    PLAYER_MAX_POWER_SPEED = 11.5
    PLAYER_KILL_BOOST_AMOUNT = 0.35
    PLAYER_KILL_BOOST_FRAMES = 75
    PLAYER_NEAR_MISS_BOOST = 0.22
    PLAYER_NEAR_MISS_FRAMES = 36
    PLAYER_BOOST_MAX = 1.10
    FIREBALL_SPEED       = 10
    ENEMY_SPEED          = 2
    ENEMY_SPAWN_INTERVAL = 60
    BULLET_SPEED         = 6
    SHOOT_PROBABILITY    = 0.01
    BEAT_FRAMES          = 34          # ~106 BPM @ 60 fps
    BEAT_PULSE_FRAMES    = 8           # how long the pulse lasts
    FIRE_COOLDOWN        = 7           # slightly snappier shooting
    SHOOT_POSE_FRAMES    = 8           # how long Onyx G holds the upward aiming pose
    BG_SCROLL_SPEED      = 2
    LEVEL_2_SPEED_MULT   = 1.38
    LEVEL_2_INTERVAL_MULT = 0.76
    LEVEL_2_BULLET_BONUS = 1.2
    # Progressive Level 2 curve (Wave 1..5): starts manageable, ramps to high pressure.
    LEVEL_2_SPEED_MULT_CURVE = [1.15, 1.25, 1.40, 1.55, 1.70]
    LEVEL_2_INTERVAL_MULT_CURVE = [0.92, 0.84, 0.76, 0.69, 0.63]
    LEVEL_2_BULLET_BONUS_CURVE = [0.40, 0.70, 1.00, 1.30, 1.60]
    # Level 3 (elite challenge): aggressive from wave 1, peaks at wave 5
    LEVEL_3_SPEED_MULT   = 1.55
    LEVEL_3_INTERVAL_MULT = 0.62
    LEVEL_3_BULLET_BONUS = 1.5
    LEVEL_3_SPEED_MULT_CURVE = [1.35, 1.48, 1.62, 1.76, 1.90]
    LEVEL_3_INTERVAL_MULT_CURVE = [0.80, 0.72, 0.62, 0.55, 0.50]
    LEVEL_3_BULLET_BONUS_CURVE = [0.70, 1.10, 1.50, 1.90, 2.30]
    # Level 4 (ancestral gauntlet): hardest pacing in the run.
    LEVEL_4_SPEED_MULT_CURVE = [1.52, 1.66, 1.80, 1.95, 2.10]
    LEVEL_4_INTERVAL_MULT_CURVE = [0.70, 0.62, 0.56, 0.51, 0.46]
    LEVEL_4_BULLET_BONUS_CURVE = [1.00, 1.45, 1.95, 2.40, 2.85]
    # NPC AI tuning
    NPC_SEPARATION_RADIUS = 44.0
    NPC_SEPARATION_FORCE = 0.42
    NPC_REACTION_FRAMES = {
        1: (18, 30),
        2: (13, 24),
        3: (9, 18),
        4: (7, 14),
    }
    MAX_AIMED_PROJECTILES = {1: 1, 2: 2, 3: 3, 4: 4}
    MAX_HUNTER_SPEED_RATIO = 0.92
    MAX_KAMIKAZE_SPEED_RATIO = 1.18
    ROLE_SHOT_COOLDOWNS = {
        'drifter': (70, 120),
        'tracker': (55, 95),
        'flanker': (48, 82),
        'gunner': (34, 62),
        'hunter': (30, 54),
    }
    # Gore constants
    GORE_ENABLED = True
    GORE_INTENSITY = 1.20
    MAX_BLOOD_DROPLETS = 150
    MAX_BLOOD_CHUNKS = 30
    MAX_BLOOD_DECALS = 48
    BLOOD_GRAVITY = 0.16
    BLOOD_DRAG = 0.985
    BLOOD_TRAIL_ALPHA = 96
    BLOOD_WET_FRAMES = 140
    BLOOD_POOL_CHANCE = 0.10
    BLOOD_COLORS = [
        (112, 0, 12),
        (145, 5, 18),
        (82, 0, 8),
        (165, 18, 22),
        (58, 0, 8),
    ]
    MAX_PARTICLES = 220
    MAX_SCORE_POPUPS = 24
    MAX_DATA_SOULS = 20
    MAX_FIREBALLS = 20
    MAX_SIDE_BULLETS = 32
    MAX_ENEMY_BULLETS = 64
    PICKUP_DROP_CHANCE   = 0.09        # lower generosity: pickups stay valuable
    IFRAME_DURATION      = 90          # fair, but less forgiving
    WAVE_DEFS = [
        {'count': 12, 'interval': 54},
        {'count': 17, 'interval': 43},
        {'count': 24, 'interval': 34},
        {'count': 31, 'interval': 26},
        {'count': 40, 'interval': 19},
    ]
    WAVE_DEFS        = cfg.WAVE_DEFS
    WAVE_MULT        = cfg.WAVE_MULT
    WAVE_ENEMY_SPEED = cfg.WAVE_ENEMY_SPEED
    WAVE_SHOOT_PROB  = cfg.WAVE_SHOOT_PROB
    WAVE_TRACK_GAIN  = cfg.WAVE_TRACK_GAIN
    WAVE_TRACK_CAP   = cfg.WAVE_TRACK_CAP
    WAVE_AIMED_SHOT_RATIO = cfg.WAVE_AIMED_SHOT_RATIO
    WAVE_KAMIKAZE_CHANCE = cfg.WAVE_KAMIKAZE_CHANCE
    WAVE_DIVE_COOLDOWN_MIN = cfg.WAVE_DIVE_COOLDOWN_MIN
    WAVE_DIVE_COOLDOWN_MAX = cfg.WAVE_DIVE_COOLDOWN_MAX
    WAVE_DIVE_BATCH = cfg.WAVE_DIVE_BATCH
    PERKS = cfg.PERKS

    _difficulty_key = str(getattr(cfg, 'DIFFICULTY_PRESET', 'normal')).lower()
    _difficulty = cfg.DIFFICULTY_PRESETS.get(_difficulty_key, cfg.DIFFICULTY_PRESETS['normal'])
    enemy_speed_scale = float(_difficulty.get('enemy_speed_mult', 1.0))
    spawn_interval_scale = float(_difficulty.get('spawn_interval_mult', 1.0))
    shoot_prob_scale = float(_difficulty.get('shoot_prob_mult', 1.0))
    boss_health_scale = float(_difficulty.get('boss_health_mult', 1.0))
    continue_bonus = int(_difficulty.get('continue_bonus', 0.0))
    player_health_bonus = int(_difficulty.get('player_health_bonus', 0.0))
    max_continues = max(0, cfg.CONTINUE_MAX_USES + continue_bonus)

    def _scaled_boss_health(base_value: int) -> int:
        return max(1, int(round(base_value * boss_health_scale)))

    def _pull_runtime_scalars(state: GameState):
        """Single sync point for mutable scalar values edited by systems."""
        return (
            state.score,
            state.health,
            state.signal_meter,
            state.block_signal,
            state.sativa_active,
            state.sativa_timer,
            state.iframe_timer,
        )

    def _approach_vector(current, target, max_delta):
        """Move current vector toward target by at most max_delta."""
        delta = target - current
        if delta.length_squared() == 0:
            return target.copy()
        if delta.length() <= max_delta:
            return target.copy()
        return current + delta.normalize() * max_delta

    def _make_enemy_profile(current_level, current_wave):
        """Create an AI behavior profile for a new enemy."""
        if current_level == 1:
            roles = ['drifter', 'tracker', 'flanker', 'gunner']
            weights = [58, 27, 7, 8]
        elif current_level == 2:
            roles = ['drifter', 'tracker', 'flanker', 'gunner']
            weights = [38, 30, 16, 16]
        elif current_level == 3:
            roles = ['drifter', 'tracker', 'flanker', 'gunner']
            weights = [24, 30, 23, 23]
        else:
            roles = ['tracker', 'flanker', 'gunner', 'hunter']
            weights = [22, 24, 24, 30]
        role = random.choices(roles, weights=weights, k=1)[0]
        rmin, rmax = NPC_REACTION_FRAMES[current_level]
        return {
            'role': role,
            'reaction_frames': random.randint(rmin, rmax),
            'shot_cd': random.randint(28, 70),
            'strafe_dir': random.choice((-1, 1)),
            'flank_offset': random.choice((-220, -170, 170, 220)),
            'phase': random.uniform(0.0, math.tau),
        }

    def _spawn_enemy(x, y):
        """Spawn an enemy with AI profile assigned."""
        enemy = Enemy(
            rect=pygame.Rect(int(x), int(y), 40, 40),
            angle=random.uniform(0, 2 * math.pi),
        )
        enemies.append(enemy)
        enemy_ai_profiles[id(enemy)] = _make_enemy_profile(level, wave)
        return enemy

    def _spawn_blood_burst(
            cx,
            cy,
            intensity=1.0,
            bias=(0.0, 0.0),
            stains=1,
            wet_frames=None,
            gloss_scale=1.0,
            decal_life_scale=1.0):
        """Spawn gore particles (droplets, chunks, decals) at a location."""
        if not GORE_ENABLED:
            return
        total = max(1, int(random.randint(12, 18) * intensity * GORE_INTENSITY))
        bx, by = bias
        _wet_frames = BLOOD_WET_FRAMES if wet_frames is None else max(0, int(wet_frames))
        _decal_life_scale = max(0.2, float(decal_life_scale))
        _gloss_scale = max(0.2, float(gloss_scale))
        _bias_mag = math.hypot(bx, by)
        _dir_x, _dir_y = ((bx / _bias_mag), (by / _bias_mag)) if _bias_mag > 0.001 else (0.0, 0.0)
        for _ in range(total):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(1.8, 6.5) * (0.80 + intensity * 0.28)
            _x = float(cx + random.randint(-5, 5))
            _y = float(cy + random.randint(-5, 5))
            if intensity >= 1.5 and _bias_mag > 0.001:
                # Heavy hits get a forward cone so the splatter reads as directional.
                _cone_push = random.uniform(0.8, 2.8) * (0.7 + intensity * 0.22)
                _spread = random.uniform(-0.95, 0.95)
                _x += _dir_x * random.uniform(0, 8)
                _y += _dir_y * random.uniform(0, 8)
                _vx = math.cos(angle) * speed + bx + _dir_x * _cone_push + (-_dir_y * _spread)
                _vy = math.sin(angle) * speed + by + _dir_y * _cone_push + (_dir_x * _spread)
            else:
                _vx = math.cos(angle) * speed + bx
                _vy = math.sin(angle) * speed + by
            blood_droplets.append({
                'x': _x,
                'y': _y,
                'px': _x,
                'py': _y,
                'vx': _vx,
                'vy': _vy,
                'life': random.randint(24, 52),
                'max': 52,
                'radius': random.randint(1, 3),
                'color': random.choice(BLOOD_COLORS),
            })
        chunk_total = max(1, int(intensity * random.randint(1, 3)))
        for _ in range(chunk_total):
            _cw = random.randint(4, 10)
            _ch = random.randint(3, 8)
            blood_chunks.append({
                'x': float(cx),
                'y': float(cy),
                'vx': random.uniform(-3.8, 3.8) + bx * 0.35,
                'vy': random.uniform(-5.0, -1.2) + by * 0.25,
                'life': random.randint(35, 68),
                'max': 68,
                'w': _cw,
                'h': _ch,
                'spin': random.uniform(-0.24, 0.24),
                'angle': random.uniform(0.0, math.tau),
                'color': random.choice(BLOOD_COLORS[:3]),
            })
        for _ in range(max(0, stains)):
            _size = random.randint(10, 22)
            _base_color = random.choice(BLOOD_COLORS[:3])
            _dry_color = tuple(max(0, int(c * 0.68)) for c in _base_color)
            blood_decals.append({
                'x': int(cx + random.randint(-14, 14)),
                'y': int(cy + random.randint(-10, 10)),
                'w': _size,
                'h': max(6, int(_size * random.uniform(0.55, 1.15))),
                'life': int(random.randint(220, 420) * _decal_life_scale),
                'max': int(420 * _decal_life_scale),
                'wet': _wet_frames,
                'wet_max': max(1, _wet_frames),
                'gloss': _gloss_scale,
                'color': _base_color,
                'dry_color': _dry_color,
            })
        del blood_droplets[:-MAX_BLOOD_DROPLETS]
        del blood_chunks[:-MAX_BLOOD_CHUNKS]
        del blood_decals[:-MAX_BLOOD_DECALS]

    # ── High score (persistent, top 3) ────────────────────────────────────
    hs_file, leaderboard_label = resolve_score_file(
        BASE_DIR,
        str(getattr(cfg, 'HIGH_SCORE_LADDER', 'v2')),
        cfg.HIGH_SCORE_FILE_LEGACY,
        cfg.HIGH_SCORE_FILE_V2,
    )
    scores = load_scores(hs_file, cfg.HIGH_SCORE_ENTRIES, cfg.HIGH_SCORE_DEFAULT_NAME)
    high_score = scores[0][0]
    high_score_name = scores[0][1]

    # ── Start menu (shown once on launch) ─────────────────────────────────
    _start_menu(screen, clock, menu_img, start_menu_music_file,
                tutorial_img=tutorial_img, tutorial_music_file=tutorial_music_file)

    # ── Tutorial screen (shown automatically after START GAME) ────────────
    _tutorial_screen(screen, clock, tutorial_img, tutorial_music_file)

    if music_file:
        try:
            pygame.mixer.music.load(music_file)
            pygame.mixer.music.set_volume(0.7)
            pygame.mixer.music.play(-1)
            current_bgm_tag = "level1"
        except pygame.error:
            pass

    # ── Outer restart loop ────────────────────────────────────────────────────
    restart = True
    while restart:
        restart = False

        replay_events: List[str] = []
        replay_log_path = build_replay_log_path(BASE_DIR)
        append_replay_event(
            replay_events,
            0,
            'run_start',
            f'difficulty={_difficulty_key};max_continues={max_continues}',
        )

        # Reset all game state each run
        sprite_rect        = sprite_image.get_rect(center=(WIDTH // 2, HEIGHT - 100))
        # Player movement state
        player_position = pygame.Vector2(sprite_rect.center)
        player_velocity = pygame.Vector2(0.0, 0.0)
        movement_boost = 0.0
        movement_boost_timer = 0
        # Enemy AI profiles
        enemy_ai_profiles = {}
        # Gore state
        blood_droplets = []
        blood_chunks = []
        blood_decals = []
        blood_fx_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        fireballs          = []
        enemies            = []
        enemy_bullets      = []
        boss_bullets       = []
        enemy_timer        = 0
        fire_timer         = 0
        shoot_pose_timer   = 0
        score              = 0
        health             = max(1, min(8, 6 + player_health_bonus))
        block_signal       = 100
        block_signal_max   = 100
        signal_meter       = 0
        signal_max         = 100
        signal_burst_flash = 0
        signal_burst_ring_timer = 0
        signal_burst_center = (WIDTH // 2, HEIGHT // 2)

        current_background_img = background_img_level_1
        boss_image         = boss_image_level_1
        boss_active        = False
        boss_warned        = False
        boss_defeated      = False
        boss_health        = _scaled_boss_health(105)
        boss_max_health    = _scaled_boss_health(105)
        boss_speed         = 1
        boss_fire_interval = 52
        boss_fire_timer    = 0
        boss_critical      = False
        boss_volley_count  = 0
        boss_rect          = boss_image.get_rect(center=(WIDTH // 2, -100))

        bg_x               = 0
        frame_count        = 0
        health_pickups     = []
        sativa_pickups     = []
        data_souls         = []
        sativa_active      = False
        sativa_timer       = 0
        sativa_dropped     = False
        score_popups       = []
        particles          = []
        shake_timer        = 0
        iframe_timer       = 0
        boss_dir           = 1
        boss_raging        = False
        aimed_bullets      = []
        side_bullets       = []
        side_fire_timer    = 0
        side_shoot_pose_timer = 0
        side_shot_direction = -1
        boss_minions       = []
        boss_minion_timer  = 0
        boss_minion_interval = 120
        combo              = 0
        combo_timer        = 0
        boss_warning_timer = 0
        boss_defeat_timer  = 0
        hit_flash_timer    = 0
        wave               = 1
        level              = 1
        wave_spawned       = 0
        wave_transition_timer = 0
        wave_intro_timer   = 120
        level_intro_timer  = 0
        game_over          = False
        game_won           = False
        ancestral_protection_charges = 0
        pending_level_four_intro = False
        level4_scene_played = False
        continues_used     = 0
        running            = True
        continue_timer     = 0
        wave_kills         = 0
        boss_rage_flash    = 0
        perk_fire_cooldown = FIRE_COOLDOWN
        perk_speed         = SPEED
        perk_double_shot   = False
        perk_power_shot    = False
        perk_lucky_drop    = False
        show_upgrade       = False
        upgrade_choices    = []
        active_perks       = []
        streak_count       = 0
        streak_timer       = 0
        streak_msg_timer   = 0
        streak_text        = ''
        streak_color       = (255, 255, 255)
        # ── PHASE 1: Run and Wave Tracking ───────────────────────────────
        run_stats = {
            'total_enemies_killed': 0,
            'total_damage_taken': 0,
            'total_enemies_escaped': 0,
            'total_near_misses': 0,
            'total_signal_bursts': 0,
            'total_bosses_defeated': 0,
        }
        wave_stats = {
            'wave_kills': 0,
            'wave_damage_taken': 0,
            'wave_enemies_escaped': 0,
            'wave_near_misses': 0,
            'wave_signal_bursts': 0,
        }
        paused             = False
        beat_pulse            = 0
        swarm_active          = False
        swarm_timer           = 0
        swarm_msg_timer       = 0
        next_event_frame      = random.randint(500, 800)
        near_miss_ids         = set()
        near_miss_sound_timer = 0
        chroma_timer          = 0
        boss_death_spiral     = False
        boss_spiral_angle     = 0.0
        trauma_mode           = False
        level4_drone_timer    = 0
        _prev_pose_state      = ''   # tracks last frame's animation state for transition events
        dive_timer            = random.randint(
            WAVE_DIVE_COOLDOWN_MIN[wave - 1], WAVE_DIVE_COOLDOWN_MAX[wave - 1]
        )   # Galaga dive countdown

        def _wave_idx() -> int:
            return max(0, min(wave, len(WAVE_DEFS)) - 1)

        def _level2_curve_idx() -> int:
            return max(0, min(wave, 5) - 1)

        def _enemy_speed_mult() -> float:
            if level >= 4:
                return LEVEL_4_SPEED_MULT_CURVE[_level2_curve_idx()] * enemy_speed_scale
            elif level >= 3:
                return LEVEL_3_SPEED_MULT_CURVE[_level2_curve_idx()] * enemy_speed_scale
            elif level >= 2:
                return LEVEL_2_SPEED_MULT_CURVE[_level2_curve_idx()] * enemy_speed_scale
            else:
                return enemy_speed_scale

        def _spawn_interval_mult() -> float:
            if level >= 4:
                return LEVEL_4_INTERVAL_MULT_CURVE[_level2_curve_idx()] * spawn_interval_scale
            elif level >= 3:
                return LEVEL_3_INTERVAL_MULT_CURVE[_level2_curve_idx()] * spawn_interval_scale
            elif level >= 2:
                return LEVEL_2_INTERVAL_MULT_CURVE[_level2_curve_idx()] * spawn_interval_scale
            else:
                return spawn_interval_scale

        def _bullet_speed_value() -> float:
            if level >= 4:
                return (BULLET_SPEED + LEVEL_4_BULLET_BONUS_CURVE[_level2_curve_idx()]) * enemy_speed_scale
            elif level >= 3:
                return (BULLET_SPEED + LEVEL_3_BULLET_BONUS_CURVE[_level2_curve_idx()]) * enemy_speed_scale
            elif level >= 2:
                return (BULLET_SPEED + LEVEL_2_BULLET_BONUS_CURVE[_level2_curve_idx()]) * enemy_speed_scale
            else:
                return BULLET_SPEED * enemy_speed_scale

        def _boss_burst_particles(cx, cy):
            return [
                Particle(
                    x=float(cx + random.randint(-50, 50)),
                    y=float(cy + random.randint(-50, 50)),
                    vx=random.uniform(-7, 7),
                    vy=random.uniform(-7, 7),
                    life=random.randint(30, 60),
                    max=60,
                    color=random.choice([
                        (255, 200, 0),
                        (255, 100, 0),
                        (255, 255, 255),
                        (200, 200, 255)
                    ])
                )
                for _ in range(40)
            ]

        def _signal_burst_particles(cx, cy):
            _count = 20 if PHOTOSENSITIVE_SAFE_MODE else 36
            _speed = 4.0 if PHOTOSENSITIVE_SAFE_MODE else 6.2
            _colors = [
                (255, 240, 120),
                (255, 170, 80),
                (255, 255, 255),
                (130, 230, 255),
            ]
            spawned = []
            for _ in range(_count):
                ang = random.uniform(0.0, math.tau)
                spd = random.uniform(_speed * 0.55, _speed)
                spawned.append(Particle(
                    x=float(cx),
                    y=float(cy),
                    vx=math.cos(ang) * spd,
                    vy=math.sin(ang) * spd,
                    life=random.randint(14, 22 if PHOTOSENSITIVE_SAFE_MODE else 28),
                    max=28,
                    color=random.choice(_colors),
                ))
            return spawned

        def _reset_wave_stats():
            nonlocal wave_stats
            wave_stats = {
                'wave_kills': 0,
                'wave_damage_taken': 0,
                'wave_enemies_escaped': 0,
                'wave_near_misses': 0,
                'wave_signal_bursts': 0,
            }

        def _defeat_boss():
            nonlocal boss_active, boss_defeated, score, boss_defeat_timer, pending_level_four_intro
            nonlocal run_stats
            if boss_defeated:
                return
            boss_active = False
            boss_defeated = True
            run_stats['total_bosses_defeated'] += 1
            append_replay_event(replay_events, frame_count, 'boss_defeated', f'level={level};wave={wave}')
            score += int(2000 * WAVE_MULT[wave - 1])
            if level == 3:
                pending_level_four_intro = True
            particles.extend(_boss_burst_particles(boss_rect.centerx, boss_rect.centery))
            # Massive gore burst on boss death
            _spawn_blood_burst(
                boss_rect.centerx,
                boss_rect.centery,
                intensity=3.0,
                bias=(0.0, -1.2),
                stains=5,
                wet_frames=260,
                gloss_scale=1.6,
                decal_life_scale=1.45,
            )
            enemies.clear()
            enemy_ai_profiles.clear()
            enemy_bullets.clear()
            aimed_bullets.clear()
            boss_bullets.clear()
            boss_minions.clear()
            boss_defeat_timer = 90

        def _start_level_two():
            nonlocal level, wave, wave_spawned, wave_kills, wave_transition_timer, wave_intro_timer
            nonlocal level_intro_timer, sativa_dropped, boss_warned, boss_defeated, boss_defeat_timer
            nonlocal boss_active, boss_health, boss_max_health, boss_fire_interval, boss_fire_timer
            nonlocal boss_critical, boss_volley_count, boss_rect, boss_dir, boss_raging
            nonlocal boss_minions, boss_minion_timer, boss_minion_interval, boss_warning_timer
            nonlocal boss_rage_flash, aimed_bullets, enemy_bullets, boss_bullets, enemies
            nonlocal side_bullets, health_pickups, sativa_pickups, data_souls, shake_timer
            nonlocal signal_meter, particles, swarm_active, swarm_timer, swarm_msg_timer
            nonlocal next_event_frame, near_miss_ids, chroma_timer, boss_death_spiral
            nonlocal boss_spiral_angle, trauma_mode, dive_timer, current_background_img, boss_image
            nonlocal level4_drone_timer, wave_stats
            nonlocal current_bgm_tag

            # Hard reset into Level 2 so no Level 1 transient state leaks forward.
            level = 2
            current_background_img = background_img_level_2
            boss_image = boss_image_level_2
            wave = 1
            wave_spawned = 0
            wave_kills = 0
            _reset_wave_stats()
            wave_transition_timer = 0
            # Avoid stacked banner clutter right after the Level 2 cinematic.
            wave_intro_timer = 0
            level_intro_timer = 180
            sativa_dropped = False
            trauma_mode = True

            if level2_music_file and current_bgm_tag != "level2":
                try:
                    pygame.mixer.music.load(level2_music_file)
                    pygame.mixer.music.set_volume(cfg.VOLUME_MUSIC)
                    pygame.mixer.music.play(-1)
                    current_bgm_tag = "level2"
                except pygame.error as err:
                    print(f"⚠️ Level 2 music failed: {err}")

            boss_warned = False
            boss_defeated = False
            boss_defeat_timer = 0
            boss_active = False
            boss_max_health = _scaled_boss_health(140)
            boss_health = boss_max_health
            boss_fire_interval = 44
            boss_fire_timer = 0
            boss_critical = False
            boss_volley_count = 0
            boss_rect = boss_image.get_rect(center=(WIDTH // 2, -100))
            boss_dir = 1
            boss_raging = False
            boss_minion_timer = 0
            boss_minion_interval = 96
            boss_warning_timer = 0
            boss_rage_flash = 0
            boss_death_spiral = False
            boss_spiral_angle = 0.0

            enemies.clear()
            enemy_ai_profiles.clear()
            side_bullets.clear()
            enemy_bullets.clear()
            aimed_bullets.clear()
            boss_bullets.clear()
            boss_minions.clear()
            health_pickups.clear()
            sativa_pickups.clear()
            data_souls.clear()
            particles.clear()
            near_miss_ids.clear()

            swarm_active = False
            swarm_timer = 0
            swarm_msg_timer = 0
            next_event_frame = frame_count + random.randint(220, 360)
            dive_timer = random.randint(WAVE_DIVE_COOLDOWN_MIN[0], WAVE_DIVE_COOLDOWN_MAX[0])
            shake_timer = max(shake_timer, 0 if PHOTOSENSITIVE_SAFE_MODE else 24)
            chroma_timer = max(chroma_timer, 0 if PHOTOSENSITIVE_SAFE_MODE else 18)
            signal_meter = min(signal_max, signal_meter + 20)
            level4_drone_timer = 0

            score_popups.append(ScorePopup(
                x=WIDTH // 2,
                y=HEIGHT // 2 - 70,
                timer=135,
                max=135,
                text='LEVEL 2  TRAUMA MODE',
                color=(255, 90, 90),
            ))
            append_replay_event(replay_events, frame_count, 'level_start', 'level=2')

        def _start_level_three():
            nonlocal level, wave, wave_spawned, wave_kills, wave_transition_timer, wave_intro_timer
            nonlocal level_intro_timer, sativa_dropped, boss_warned, boss_defeated, boss_defeat_timer
            nonlocal boss_active, boss_health, boss_max_health, boss_fire_interval, boss_fire_timer
            nonlocal boss_critical, boss_volley_count, boss_rect, boss_dir, boss_raging
            nonlocal boss_minions, boss_minion_timer, boss_minion_interval, boss_warning_timer
            nonlocal boss_rage_flash, aimed_bullets, enemy_bullets, boss_bullets, enemies
            nonlocal side_bullets, health_pickups, sativa_pickups, data_souls, shake_timer
            nonlocal signal_meter, particles, swarm_active, swarm_timer, swarm_msg_timer
            nonlocal next_event_frame, near_miss_ids, chroma_timer, boss_death_spiral
            nonlocal boss_spiral_angle, trauma_mode, dive_timer, current_background_img, boss_image
            nonlocal level4_drone_timer, wave_stats
            nonlocal current_bgm_tag

            # Hard reset into Level 3 — apex difficulty
            level = 3
            current_background_img = background_img_level_3
            boss_image = boss_image_level_3
            wave = 1
            wave_spawned = 0
            wave_kills = 0
            _reset_wave_stats()
            wave_transition_timer = 0
            wave_intro_timer = 0
            level_intro_timer = 180
            sativa_dropped = False
            trauma_mode = True

            if level3_music_file and current_bgm_tag != "level3":
                try:
                    pygame.mixer.music.load(level3_music_file)
                    pygame.mixer.music.set_volume(cfg.VOLUME_MUSIC)
                    pygame.mixer.music.play(-1)
                    current_bgm_tag = "level3"
                except pygame.error as err:
                    print(f"⚠️ Level 3 music failed: {err}")

            boss_warned = False
            boss_defeated = False
            boss_defeat_timer = 0
            boss_active = False
            boss_max_health = _scaled_boss_health(180)
            boss_health = boss_max_health
            boss_fire_interval = 40
            boss_fire_timer = 0
            boss_critical = False
            boss_volley_count = 0
            boss_rect = boss_image.get_rect(center=(WIDTH // 2, -100))
            boss_dir = 1
            boss_raging = False
            boss_minion_timer = 0
            boss_minion_interval = 80
            boss_warning_timer = 0
            boss_rage_flash = 0
            boss_death_spiral = False
            boss_spiral_angle = 0.0

            enemies.clear()
            enemy_ai_profiles.clear()
            side_bullets.clear()
            enemy_bullets.clear()
            aimed_bullets.clear()
            boss_bullets.clear()
            boss_minions.clear()
            health_pickups.clear()
            sativa_pickups.clear()
            data_souls.clear()
            particles.clear()
            near_miss_ids.clear()

            swarm_active = False
            swarm_timer = 0
            swarm_msg_timer = 0
            next_event_frame = frame_count + random.randint(200, 340)
            dive_timer = random.randint(WAVE_DIVE_COOLDOWN_MIN[0], WAVE_DIVE_COOLDOWN_MAX[0])
            shake_timer = max(shake_timer, 0 if PHOTOSENSITIVE_SAFE_MODE else 24)
            chroma_timer = max(chroma_timer, 0 if PHOTOSENSITIVE_SAFE_MODE else 18)
            signal_meter = min(signal_max, signal_meter + 25)
            level4_drone_timer = 0

            score_popups.append(ScorePopup(
                x=WIDTH // 2,
                y=HEIGHT // 2 - 70,
                timer=135,
                max=135,
                text='LEVEL 3  APEX MODE',
                color=(255, 180, 0),
            ))
            append_replay_event(replay_events, frame_count, 'level_start', 'level=3')

        def _start_level_four():
            nonlocal level, wave, wave_spawned, wave_kills, wave_transition_timer, wave_intro_timer
            nonlocal level_intro_timer, sativa_dropped, boss_warned, boss_defeated, boss_defeat_timer
            nonlocal boss_active, boss_health, boss_max_health, boss_fire_interval, boss_fire_timer
            nonlocal boss_critical, boss_volley_count, boss_rect, boss_dir, boss_raging
            nonlocal boss_minions, boss_minion_timer, boss_minion_interval, boss_warning_timer
            nonlocal boss_rage_flash, aimed_bullets, enemy_bullets, boss_bullets, enemies
            nonlocal side_bullets, health_pickups, sativa_pickups, data_souls, shake_timer
            nonlocal signal_meter, particles, swarm_active, swarm_timer, swarm_msg_timer
            nonlocal next_event_frame, near_miss_ids, chroma_timer, boss_death_spiral
            nonlocal boss_spiral_angle, trauma_mode, dive_timer, current_background_img, boss_image
            nonlocal level4_drone_timer, wave_stats
            nonlocal current_bgm_tag, ancestral_protection_charges, pending_level_four_intro, level4_scene_played

            level = 4
            current_background_img = background_img_level_4
            boss_image = boss_image_level_4
            wave = 1
            wave_spawned = 0
            wave_kills = 0
            _reset_wave_stats()
            wave_transition_timer = 0
            wave_intro_timer = 0
            level_intro_timer = 200
            sativa_dropped = False
            trauma_mode = True
            ancestral_protection_charges = max(ancestral_protection_charges, 3)
            pending_level_four_intro = False
            level4_scene_played = True

            _l4_music = level4_music_file or level3_music_file or level2_music_file or music_file
            if _l4_music and current_bgm_tag != "level4":
                try:
                    pygame.mixer.music.load(_l4_music)
                    pygame.mixer.music.set_volume(cfg.VOLUME_MUSIC)
                    pygame.mixer.music.play(-1)
                    current_bgm_tag = "level4"
                except pygame.error as err:
                    print(f"⚠️ Level 4 music failed: {err}")

            boss_warned = False
            boss_defeated = False
            boss_defeat_timer = 0
            boss_active = False
            boss_max_health = _scaled_boss_health(230)
            boss_health = boss_max_health
            boss_fire_interval = 34
            boss_fire_timer = 0
            boss_critical = False
            boss_volley_count = 0
            boss_rect = boss_image.get_rect(center=(WIDTH // 2, -100))
            boss_dir = 1
            boss_raging = False
            boss_minion_timer = 0
            boss_minion_interval = 64
            boss_warning_timer = 0
            boss_rage_flash = 0
            boss_death_spiral = False
            boss_spiral_angle = 0.0

            enemies.clear()
            enemy_ai_profiles.clear()
            side_bullets.clear()
            enemy_bullets.clear()
            aimed_bullets.clear()
            boss_bullets.clear()
            boss_minions.clear()
            health_pickups.clear()
            sativa_pickups.clear()
            data_souls.clear()
            particles.clear()
            near_miss_ids.clear()
            for _ in range(4):
                _spawn_enemy(random.randint(0, WIDTH - 40), random.randint(-220, -40))

            swarm_active = False
            swarm_timer = 0
            swarm_msg_timer = 0
            next_event_frame = frame_count + random.randint(180, 300)
            dive_timer = random.randint(WAVE_DIVE_COOLDOWN_MIN[0], WAVE_DIVE_COOLDOWN_MAX[0])
            shake_timer = max(shake_timer, 0 if PHOTOSENSITIVE_SAFE_MODE else 20)
            chroma_timer = max(chroma_timer, 0 if PHOTOSENSITIVE_SAFE_MODE else 16)
            signal_meter = min(signal_max, signal_meter + 35)
            level4_drone_timer = random.randint(36, 64)

            score_popups.append(ScorePopup(
                x=WIDTH // 2,
                y=HEIGHT // 2 - 50,
                timer=130,
                max=130,
                text='ANCESTRAL PROTECTION +3',
                color=(255, 245, 170),
            ))
            append_replay_event(replay_events, frame_count, 'level_start', 'level=4')

        def _damage_boss(amount, grant_signal=True):
            nonlocal boss_health, signal_meter
            boss_health -= amount
            if impact_sound:
                impact_channel.play(impact_sound)
            if grant_signal:
                signal_meter = min(signal_max, signal_meter + 1)
            if boss_health <= 0:
                _defeat_boss()

        def _damage_player():
            nonlocal health, shake_timer, hit_flash_timer, chroma_timer
            nonlocal iframe_timer, game_over, continue_timer
            nonlocal ancestral_protection_charges, run_stats, wave_stats
            if iframe_timer != 0:
                return
            if ancestral_protection_charges > 0:
                ancestral_protection_charges -= 1
                iframe_timer = 30
                shake_timer = max(shake_timer, 4)
                hit_flash_timer = max(hit_flash_timer, 3)
                score_popups.append(ScorePopup(
                    x=sprite_rect.centerx,
                    y=sprite_rect.top - 24,
                    timer=50,
                    max=50,
                    text='ANCESTRAL GUARD',
                    color=(170, 255, 220),
                ))
                for _ in range(12):
                    _ang = random.uniform(0.0, math.tau)
                    particles.append(Particle(
                        x=float(sprite_rect.centerx),
                        y=float(sprite_rect.centery),
                        vx=math.cos(_ang) * random.uniform(1.5, 3.0),
                        vy=math.sin(_ang) * random.uniform(1.5, 3.0),
                        life=random.randint(10, 16),
                        max=16,
                        color=(170, 255, 220),
                    ))
                if signal_burst_sound:
                    burst_channel.play(signal_burst_sound)
                return
            health -= 1
            run_stats['total_damage_taken'] += 1
            wave_stats['wave_damage_taken'] += 1
            shake_timer = 10
            hit_flash_timer = 8
            chroma_timer = 12
            iframe_timer = IFRAME_DURATION
            # Gore on player hit
            _spawn_blood_burst(
                sprite_rect.centerx,
                sprite_rect.centery,
                intensity=0.8,
                bias=(random.uniform(-0.5, 0.5), -0.8),
                stains=1,
            )
            if impact_sound:
                impact_channel.play(impact_sound)
            if health <= 0:
                game_over = True
                continue_timer = 600
                run_channel.stop()
                jetpack_channel.stop()

        def _drop_enemy_rewards(cx, cy, top_y):
            nonlocal sativa_dropped
            if random.random() < (PICKUP_DROP_CHANCE * 1.6 if perk_lucky_drop else PICKUP_DROP_CHANCE):
                health_pickups.append(pygame.Rect(cx - 8, top_y, 16, 16))
            if not sativa_dropped and wave >= 3:
                sativa_pickups.append(pygame.Rect(cx - 20, top_y, 40, 40))
                sativa_dropped = True
            elif random.random() < 0.02:
                sativa_pickups.append(pygame.Rect(cx - 20, top_y, 40, 40))
            if random.random() < 0.18:
                data_souls.append(pygame.Rect(cx - 10, cy - 10, 20, 20))

        def _register_enemy_destroyed(enemy, popup_color, particle_colors, particle_count):
            nonlocal wave_kills, combo, combo_timer, score, signal_meter
            nonlocal streak_count, streak_timer, streak_text, streak_color, streak_msg_timer
            nonlocal run_stats, wave_stats, movement_boost, movement_boost_timer
            wave_kills += 1
            run_stats['total_enemies_killed'] += 1
            wave_stats['wave_kills'] += 1
            cx, cy = enemy[0].centerx, enemy[0].centery
            combo += 1
            combo_timer = 120
            # Combo milestone audio reward: escalates every 5 kills
            if combo_sounds and combo in (5, 10, 15) or (combo_sounds and combo >= 20 and combo % 5 == 0):
                _clvl = 0 if combo < 10 else 1 if combo < 15 else 2 if combo < 20 else 3
                combo_sounds[_clvl].play()
            points = int((200 if enemy[2] else 100) * combo * WAVE_MULT[wave - 1])
            score += points
            signal_meter = min(signal_max, signal_meter + 2)
            streak_count += 1
            streak_timer = 90
            if streak_count == 2:
                streak_text = 'DOUBLE KILL!'; streak_color = (255, 220,  50); streak_msg_timer = 75
            elif streak_count == 3:
                streak_text = 'TRIPLE KILL!'; streak_color = (255, 150,   0); streak_msg_timer = 75
            elif streak_count == 4:
                streak_text = 'QUAD KILL!';   streak_color = (255,  80,  80); streak_msg_timer = 75
            elif streak_count >= 5:
                streak_text = 'RAMPAGE!';     streak_color = (200,   0, 255); streak_msg_timer = 90
            # Kill boost: reward skill with temporary speed
            movement_boost = min(
                PLAYER_BOOST_MAX,
                movement_boost + PLAYER_KILL_BOOST_AMOUNT,
            )
            movement_boost_timer = PLAYER_KILL_BOOST_FRAMES
            # Trigger gore on kill
            _profile = enemy_ai_profiles.get(id(enemy), {})
            _role = _profile.get('role', 'drifter')
            _is_elite = bool(enemy[2]) or _role in ('hunter', 'gunner')
            gore_force = 1.75 if _is_elite else 0.95
            _spawn_blood_burst(
                cx,
                cy,
                intensity=gore_force,
                bias=(random.uniform(-1.25, 1.25), 0.9),
                stains=3 if _is_elite else 1,
                wet_frames=190 if _is_elite else BLOOD_WET_FRAMES,
                gloss_scale=1.3 if _is_elite else 0.95,
                decal_life_scale=1.22 if _is_elite else 0.9,
            )
            score_popups.append(ScorePopup(
                x=cx,
                y=enemy[0].top,
                timer=45,
                max=45,
                text=f'+{points}' + (f' x{combo}!' if combo > 1 else ''),
                color=popup_color,
            ))
            particles.extend([
                Particle(
                    x=float(cx),
                    y=float(cy),
                    vx=random.uniform(-4, 4),
                    vy=random.uniform(-4, 4),
                    life=random.randint(15, 30),
                    max=30,
                    color=random.choice(particle_colors),
                )
                for _ in range(particle_count)
            ])
            _drop_enemy_rewards(cx, cy, enemy[0].top)
            if impact_sound:
                impact_channel.play(impact_sound)

        def _register_minion_destroyed(minion, popup_color, particle_colors):
            nonlocal score, signal_meter
            cx, cy = minion['rect'].centerx, minion['rect'].centery
            _minion_pts = int(150 * WAVE_MULT[wave - 1])
            score += _minion_pts
            signal_meter = min(signal_max, signal_meter + 4)
            # Trigger gore on minion kill
            _spawn_blood_burst(cx, cy, intensity=1.25, stains=1)
            score_popups.append(ScorePopup(
                x=cx,
                y=minion['rect'].top,
                timer=45,
                max=45,
                text=f'+{_minion_pts}',
                color=popup_color,
            ))
            particles.extend([
                Particle(
                    x=float(cx),
                    y=float(cy),
                    vx=random.uniform(-3, 3),
                    vy=random.uniform(-3, 3),
                    life=random.randint(12, 25),
                    max=25,
                    color=random.choice(particle_colors),
                )
                for _ in range(7)
            ])
            if random.random() < 0.18:
                data_souls.append(pygame.Rect(cx - 10, cy - 10, 20, 20))
            if impact_sound:
                impact_channel.play(impact_sound)

        # ── Inner game loop ───────────────────────────────────────────────────
        raw_dt = 16  # seed for first frame (~60 fps)
        while running:
            dt_mul = max(1.0, min(3.0, raw_dt * 60.0 / 1000.0))

            _bg_speed = BG_SCROLL_SPEED + (1 if trauma_mode else 0)
            bg_x = (bg_x + int(_bg_speed * dt_mul)) % WIDTH
            screen.blit(current_background_img, (bg_x, 0))
            screen.blit(current_background_img, (bg_x - WIDTH, 0))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                # ── Controller hot-plug ────────────────────────────────────
                if event.type == pygame.JOYDEVICEADDED and _joy is None:
                    _joy = pygame.joystick.Joystick(event.device_index)
                    _joy.init()
                    print(f"🎮 Controller connected: {_joy.get_name()}")
                elif event.type == pygame.JOYDEVICEREMOVED:
                    _joy = None
                    print("🎮 Controller disconnected.")
                # ── Continue screen ────────────────────────────────────────
                _do_continue = (
                    event.type == pygame.KEYDOWN
                    and event.key in (pygame.K_SPACE, pygame.K_RETURN)
                ) or (
                    event.type == pygame.JOYBUTTONDOWN
                    and _joy is not None and event.button == 0  # A button
                )
                if continue_timer > 0 and _do_continue:
                    if continues_used < max_continues:
                        continues_used += 1
                        health = max(1, min(8, 3 + max(0, player_health_bonus)))
                        game_over = False
                        continue_timer = 0
                        iframe_timer = 180
                        append_replay_event(replay_events, frame_count, 'continue_used', f'count={continues_used}')
                    elif continues_used >= max_continues:
                        running = False
                        continue_timer = 0
                # ── Pause toggle (ESC  or  Start/B) ───────────────────────
                _toggle_pause = (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                ) or (
                    event.type == pygame.JOYBUTTONDOWN
                    and _joy is not None and event.button in (1, 7)  # B or Start
                )
                if _toggle_pause and not show_upgrade and continue_timer == 0:
                    paused = not paused
                # ── Signal burst (LSHIFT  or  LB) ─────────────────────────
                _do_burst = (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_LSHIFT
                ) or (
                    event.type == pygame.JOYBUTTONDOWN
                    and _joy is not None and event.button == 4  # LB
                )
                if (_do_burst and signal_meter >= signal_max and not show_upgrade
                        and continue_timer == 0 and not paused):
                    signal_burst_center = sprite_rect.center
                    enemy_bullets.clear()
                    aimed_bullets.clear()
                    boss_bullets.clear()
                    burst_points = len(enemies) * 100 + len(boss_minions) * 150
                    run_stats['total_signal_bursts'] += 1
                    wave_stats['wave_signal_bursts'] += 1
                    if boss_active and not boss_defeated:
                        boss_health = max(0, boss_health - 10)
                        if boss_health <= 0:
                            _defeat_boss()
                    enemies.clear()
                    enemy_ai_profiles.clear()
                    boss_minions.clear()
                    score += burst_points
                    signal_meter = 0
                    signal_burst_flash = 18 if PHOTOSENSITIVE_SAFE_MODE else 28
                    signal_burst_ring_timer = 18 if PHOTOSENSITIVE_SAFE_MODE else 24
                    shake_timer = max(shake_timer, 8 if PHOTOSENSITIVE_SAFE_MODE else 20)
                    chroma_timer = max(chroma_timer, 0 if PHOTOSENSITIVE_SAFE_MODE else 10)
                    particles.extend(_signal_burst_particles(*signal_burst_center))
                    if signal_burst_sound:
                        burst_channel.play(signal_burst_sound)
                    elif impact_sound:
                        impact_channel.play(impact_sound)
                    score_popups.append(ScorePopup(
                        x=WIDTH // 2,
                        y=HEIGHT // 2 - 90,
                        timer=90,
                        max=90,
                        text=f'SIGNAL BURST! +{burst_points}',
                        color=(255, 220, 60),
                    ))
                    append_replay_event(replay_events, frame_count, 'signal_burst', f'points={burst_points}')
                if show_upgrade:
                    _uidx = -1
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_1:   _uidx = 0
                        elif event.key == pygame.K_2: _uidx = 1
                        elif event.key == pygame.K_3: _uidx = 2
                    elif event.type == pygame.JOYBUTTONDOWN and _joy is not None:
                        if event.button == 0:   _uidx = 0   # A  → slot 1
                        elif event.button == 2: _uidx = 1   # X  → slot 2
                        elif event.button == 3: _uidx = 2   # Y  → slot 3
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        _ucw, _uch, _ugap = WIDTH - 80, 140, 18
                        _usx = (WIDTH - _ucw) // 2
                        _ucy = 150
                        for _ui in range(3):
                            if pygame.Rect(_usx, _ucy + _ui * (_uch + _ugap), _ucw, _uch).collidepoint(event.pos):
                                _uidx = _ui
                                break
                    if 0 <= _uidx < len(upgrade_choices):
                        _pid = upgrade_choices[_uidx]['id']
                        active_perks.append(upgrade_choices[_uidx]['name'])
                        if _pid == 'rapid_fire':    perk_fire_cooldown = max(5, perk_fire_cooldown - 1)
                        elif _pid == 'speed_boost': perk_speed = min(8, perk_speed + 1)
                        elif _pid == 'extra_heart': health = min(8, health + 1)
                        elif _pid == 'double_shot': perk_double_shot = True
                        elif _pid == 'power_shot':  perk_power_shot = True
                        elif _pid == 'lucky_drop':  perk_lucky_drop = True
                        show_upgrade = False
                        _reset_wave_stats()
                        wave += 1
                        wave_spawned = 0
                        wave_kills   = 0
                        sativa_dropped = False
                        wave_intro_timer = 120

            if game_over and continue_timer > 0:
                frame_count += 1
                continue_timer -= 1
                if continues_used < max_continues:
                    # ── CONTINUE? screen ─────────────────────────────────
                    _cd_secs = max(0, continue_timer // 60)
                    screen.blit(_cont_ov, (0, 0))
                    screen.blit(_cont_q_surf, _cont_q_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 100)))
                    # Frames since last whole-second tick: 0 on the tick frame, rises after
                    _ftick = (60 - continue_timer % 60) % 60
                    if _ftick == 0 and 0 < continue_timer <= 180:
                        if countdown_tick_sound:
                            countdown_tick_sound.play()
                    # Color: white flash on tick decays to red over 18 frames
                    if _cd_secs <= 3:
                        _pt = max(0.0, 1.0 - _ftick / 18.0) if continue_timer <= 180 else 0.0
                        _cn_col = (255, int(60 + 195 * _pt), int(60 + 195 * _pt))
                    else:
                        _cn_col = (255, 200, 60)
                    _cn_key = (_cd_secs, _cn_col)
                    if _cn_key not in _cn_surf_cache:
                        _cn_surf_cache[_cn_key] = font_huge.render(str(_cd_secs), True, _cn_col)
                    screen.blit(_cn_surf_cache[_cn_key],
                                _cn_surf_cache[_cn_key].get_rect(center=(WIDTH // 2, HEIGHT // 2 + 15)))
                    _rem = max_continues - continues_used
                    if _crem_cache['val'] != _rem:
                        _crem_cache['val'] = _rem
                        _crem_cache['surf'] = font_med.render(
                            f'{_rem}  CONTINUE{"S" if _rem != 1 else ""}  REMAINING',
                            True, (180, 80, 255))
                    screen.blit(_crem_cache['surf'],
                                _crem_cache['surf'].get_rect(center=(WIDTH // 2, HEIGHT // 2 + 105)))
                    _cpa = int(200 + 55 * abs(math.sin(frame_count * 0.18)))
                    _cont_press_surf.set_alpha(_cpa)
                    screen.blit(_cont_press_surf,
                                _cont_press_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 150)))
                else:
                    # ── Dramatic GAME OVER screen ─────────────────────────
                    screen.fill((25, 0, 10))
                    _bw = 70
                    for _vr in [(0, 0, WIDTH, _bw), (0, HEIGHT - _bw, WIDTH, _bw),
                                (0, 0, _bw, HEIGHT), (WIDTH - _bw, 0, _bw, HEIGHT)]:
                        pygame.draw.rect(screen, (80, 0, 0), _vr)
                    _goa = min(255, int((600 - continue_timer) * 1.5))
                    _got = font_big.render('GAME  OVER', True, (57, 255, 20))
                    _got.set_alpha(_goa)
                    screen.blit(_got, _got.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 100)))
                    _gos = font_med.render('NO  CONTINUES  REMAINING', True, (180, 80, 255))
                    _gos.set_alpha(_goa)
                    screen.blit(_gos, _gos.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 15)))
                    _gsc = font_med.render(f'FINAL  SCORE:   {score:,}', True, (230, 230, 230))
                    _gsc.set_alpha(_goa)
                    screen.blit(_gsc, _gsc.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 55)))
                    _goph = int(140 + 115 * abs(math.sin(frame_count * 0.12)))
                    _gop = font_med.render('PRESS  ANY  KEY  FOR  FINAL  SCORE', True, (230, 230, 230))
                    _gop.set_alpha(_goph)
                    screen.blit(_gop, _gop.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 135)))
                if continue_timer <= 0:
                    running = False
                pygame.display.flip()
                clock.tick(60)
                continue

            if paused:
                screen.blit(_pov_surf, (0, 0))
                _pt = font_big.render("PAUSED", True, (255, 255, 255))
                screen.blit(_pt, _pt.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40)))
                _ph = font_med.render("Press  ESC  to resume", True, (180, 200, 255))
                screen.blit(_ph, _ph.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 20)))
                pygame.display.flip()
                clock.tick(60)
                continue

            if not show_upgrade:
                keys = pygame.key.get_pressed()
                move_input = pygame.Vector2(
                    int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT]),
                    int(keys[pygame.K_DOWN]) - int(keys[pygame.K_UP]),
                )
                # Left stick overrides keyboard when outside dead zone.
                if _joy is not None:
                    _DEAD = 0.15
                    _jx = _joy.get_axis(0); _jy = _joy.get_axis(1)
                    if abs(_jx) < _DEAD: _jx = 0.0
                    if abs(_jy) < _DEAD: _jy = 0.0
                    # D-pad (buttons 11-14 on Xbox Series X + macOS SDL2)
                    if _joy.get_numbuttons() > 14:
                        if _joy.get_button(11):   _jy = -1.0
                        elif _joy.get_button(12): _jy =  1.0
                        if _joy.get_button(13):   _jx = -1.0
                        elif _joy.get_button(14): _jx =  1.0
                    if _jx != 0.0 or _jy != 0.0:
                        move_input = pygame.Vector2(_jx, _jy)
                # Prevent diagonal turbo speed.
                if move_input.length_squared() > 1.0:
                    move_input = move_input.normalize()
                # Controlled boosts: strong enough to feel, never enough to break dodging.
                if movement_boost_timer > 0:
                    movement_boost_timer -= 1
                else:
                    movement_boost = max(0.0, movement_boost - 0.04 * dt_mul)
                base_speed = min(PLAYER_MAX_NORMAL_SPEED, float(perk_speed))
                beat_bonus = 0.75 if beat_pulse > BEAT_PULSE_FRAMES - 4 else 0.0
                sativa_bonus = 2.0 if sativa_active else 0.0
                max_speed = min(
                    PLAYER_MAX_POWER_SPEED,
                    base_speed + beat_bonus + sativa_bonus + movement_boost,
                )
                target_velocity = move_input * max_speed
                # Turning should feel sharper than simply accelerating from rest.
                turning = (
                    move_input.length_squared() > 0
                    and player_velocity.length_squared() > 0
                    and player_velocity.dot(target_velocity) < 0
                )
                accel = PLAYER_ACCELERATION * (PLAYER_TURN_ACCEL_MULT if turning else 1.0)
                rate = accel if move_input.length_squared() > 0 else PLAYER_DECELERATION
                player_velocity = _approach_vector(
                    player_velocity,
                    target_velocity,
                    rate * dt_mul,
                )
                player_position += player_velocity * dt_mul
                sprite_rect.center = (round(player_position.x), round(player_position.y))
                sprite_rect.clamp_ip(screen_bounds)
                player_position.update(sprite_rect.center)
                # Keep the existing trail, but tie it to actual velocity.
                if player_velocity.length_squared() > 0.55:
                    for _ in range(2):
                        particles.append(Particle(
                            x=float(sprite_rect.centerx + random.randint(-6, 6)),
                            y=float(sprite_rect.bottom - 4),
                            vx=random.uniform(-0.4, 0.4) - player_velocity.x * 0.05,
                            vy=random.uniform(1.5, 3.5) - player_velocity.y * 0.05,
                            life=random.randint(8, 18),
                            max=18,
                            color=random.choice([(0,150,255),(50,200,255),(100,230,255)]),
                        ))

                fire_timer = max(0, fire_timer - 1)
                side_fire_timer = max(0, side_fire_timer - 1)
                shoot_pose_timer = max(0, shoot_pose_timer - 1)
                side_shoot_pose_timer = max(0, side_shoot_pose_timer - 1)
                # Space = shoot up.
                _fire_held = keys[pygame.K_SPACE] or (_joy is not None and _joy.get_axis(5) > 0.20)
                if _fire_held and len(fireballs) < 20 and fire_timer == 0:
                    shoot_pose_timer = SHOOT_POSE_FRAMES
                    if perk_double_shot or sativa_active:
                        fireballs.append(pygame.Rect(sprite_rect.centerx - 16, sprite_rect.top, 8, 16))
                        fireballs.append(pygame.Rect(sprite_rect.centerx + 8,  sprite_rect.top, 8, 16))
                    else:
                        fireballs.append(pygame.Rect(sprite_rect.centerx - 4, sprite_rect.top, 8, 16))
                    # Muzzle flash — Contra-style spark burst at gun barrel
                    _mz_x = float(sprite_rect.centerx)
                    _mz_y = float(sprite_rect.top + 2)
                    for _ in range(4):
                        particles.append({
                            'x': _mz_x + random.uniform(-5, 5),
                            'y': _mz_y,
                            'vx': random.uniform(-2.0, 2.0),
                            'vy': random.uniform(-4.5, -1.0),
                            'life': random.randint(3, 5),
                            'max': 5,
                            'color': random.choice([(255, 255, 180), (255, 200, 50), (255, 130, 20)]),
                        })
                    fire_timer = perk_fire_cooldown
                    if shoot_sound:
                        shoot_sound.play()
                # Command = shoot sideways. The pose follows horizontal movement,
                # or alternates sides while the player is standing still.
                _cmd = (keys[pygame.K_LMETA] or keys[pygame.K_RMETA]
                        or (_joy is not None and _joy.get_button(5)))  # RB
                if _cmd and side_fire_timer == 0:
                    side_shoot_pose_timer = SHOOT_POSE_FRAMES
                    if move_input.x > 0:
                        side_shot_direction = 1
                    elif move_input.x < 0:
                        side_shot_direction = -1
                    elif player_velocity.x > 0.45:
                        side_shot_direction = 1
                    elif player_velocity.x < -0.45:
                        side_shot_direction = -1
                    else:
                        side_shot_direction *= -1
                    cy = float(sprite_rect.centery)
                    cx = float(sprite_rect.centerx)
                    _spds = FIREBALL_SPEED + (2 if sativa_active else 0)
                    if perk_double_shot or sativa_active:
                        side_bullets += [
                            {'x': cx, 'y': cy - 10, 'vx': -_spds, 'vy': 0},
                            {'x': cx, 'y': cy + 10, 'vx': -_spds, 'vy': 0},
                            {'x': cx, 'y': cy - 10, 'vx':  _spds, 'vy': 0},
                            {'x': cx, 'y': cy + 10, 'vx':  _spds, 'vy': 0},
                        ]
                    else:
                        side_bullets += [
                            {'x': cx, 'y': cy, 'vx': -_spds, 'vy': 0},
                            {'x': cx, 'y': cy, 'vx':  _spds, 'vy': 0},
                        ]
                    # Muzzle flash — Contra-style spark burst (fires both directions)
                    for _ in range(4):
                        particles.append({
                            'x': cx + random.uniform(-8, 8),
                            'y': cy + random.uniform(-8, 8),
                            'vx': random.choice([-1, 1]) * random.uniform(3.0, 6.0),
                            'vy': random.uniform(-1.5, 1.5),
                            'life': random.randint(3, 5),
                            'max': 5,
                            'color': random.choice([(255, 255, 180), (255, 200, 50), (255, 130, 20)]),
                        })
                    side_fire_timer = perk_fire_cooldown
                    if shoot_sound:
                        shoot_sound.play()

            for f in fireballs:
                f.y -= int(FIREBALL_SPEED * dt_mul)
                if sativa_active:
                    # Water drip trail — droplets scatter off the trailing edge
                    particles.append({
                        'x': float(f.centerx) + random.uniform(-4, 4),
                        'y': float(f.bottom),
                        'vx': random.uniform(-1.5, 1.5),
                        'vy': random.uniform(-0.5, 1.2),
                        'life': random.randint(6, 10),
                        'max': 10,
                        'color': random.choice([(0, 200, 255), (30, 220, 200), (0, 180, 240)]),
                    })
            fireballs = [f for f in fireballs if f.y > -20]
            for sb in side_bullets:
                sb['x'] += sb['vx'] * dt_mul
                if sativa_active:
                    # Water drip trail — droplets fall from fast-moving side rounds
                    particles.append({
                        'x': float(sb['x']) - (9 if sb['vx'] > 0 else -9),
                        'y': float(sb['y']) + random.uniform(-3, 3),
                        'vx': random.uniform(-0.8, 0.8),
                        'vy': random.uniform(0.5, 2.5),
                        'life': random.randint(5, 9),
                        'max': 9,
                        'color': random.choice([(0, 200, 255), (30, 220, 200), (0, 180, 240)]),
                    })
            side_bullets = [sb for sb in side_bullets if 0 < sb['x'] < WIDTH]

            frame_count += 1
            if frame_count % BEAT_FRAMES == 0:
                beat_pulse = BEAT_PULSE_FRAMES
            if beat_pulse > 0:
                beat_pulse -= 1
            if sativa_active:
                sativa_timer -= 1
                if sativa_timer <= 0:
                    sativa_active = False
            iframe_timer = max(0, iframe_timer - 1)
            near_miss_sound_timer = max(0, near_miss_sound_timer - 1)
            if combo_timer > 0:
                combo_timer -= 1
            else:
                combo = 0
            if streak_timer > 0:
                streak_timer -= 1
                if streak_timer == 0:
                    streak_count = 0
            if streak_msg_timer > 0:
                streak_msg_timer -= 1
            # ── Drone swarm event ─────────────────────────────────────────────
            if (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade and wave_intro_timer == 0):
                if not swarm_active and frame_count >= next_event_frame:
                    swarm_active     = True
                    swarm_timer      = 240
                    swarm_msg_timer  = 90
                    next_event_frame = frame_count + random.randint(400, 700)
                if swarm_active:
                    swarm_timer -= 1
                    if swarm_timer <= 0:
                        swarm_active = False
            if boss_warning_timer > 0:
                boss_warning_timer -= 1
                if boss_warning_timer == 0 and boss_warned and not boss_defeated:
                    _boss_intro_cinematic(screen, clock)
                    boss_active       = True
                    boss_health       = boss_max_health
                    boss_rect.top     = -boss_rect.height
                    boss_rect.centerx = WIDTH // 2
            if wave_intro_timer > 0:
                wave_intro_timer -= 1
            if level_intro_timer > 0:
                level_intro_timer -= 1
            if wave_transition_timer > 0:
                wave_transition_timer -= 1
                if wave_transition_timer == 0:
                    if wave >= 5:
                        boss_warned        = True
                        boss_warning_timer = 60 if PHOTOSENSITIVE_SAFE_MODE else 90
                        boss_health        = boss_max_health
                        if siren_sound:
                            siren_sound.play(loops=2)
                    else:
                        # Clear any lingering bullets before showing upgrade screen
                        enemy_bullets.clear()
                        aimed_bullets.clear()
                        boss_bullets.clear()
                        show_upgrade    = True
                        # Filter boolean perks the player already owns (no benefit repeating them)
                        _owned = set(active_perks)
                        _perk_pool = [
                            p for p in PERKS
                            if not (p['name'] in _owned and p['id'] in ('double_shot', 'power_shot', 'lucky_drop'))
                            and not (p['id'] == 'rapid_fire' and perk_fire_cooldown <= 5)
                            and not (p['id'] == 'speed_boost' and perk_speed >= 8)
                        ]
                        upgrade_choices = random.sample(_perk_pool, k=min(3, len(_perk_pool)))
                if (pending_level_four_intro and (not level4_scene_played) and level == 3 and boss_defeated
                    and boss_defeat_timer <= 0 and not boss_active):
                    _level_four_transition(screen, clock, background_img_level_4)
                    _start_level_four()
            elif (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade
                    and wave_transition_timer == 0
                    and wave_spawned >= WAVE_DEFS[wave - 1]['count']
                    and len(enemies) == 0):
                _wave_bonus = 200 * wave  # scales: 200, 400, 600, 800, 1000
                wave_transition_timer = 120
                score += _wave_bonus
                signal_meter = min(signal_max, signal_meter + 15)
            if (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade
                    and wave_transition_timer == 0 and wave_intro_timer == 0):
                _wave_i = _wave_idx()
                _eff_count    = WAVE_DEFS[_wave_i]['count']
                _eff_interval = max(5, int(WAVE_DEFS[_wave_i]['interval'] * _spawn_interval_mult()))
                if swarm_active:
                    _eff_interval = max(12, int(_eff_interval * 0.65))
                if wave == 5:
                    # Wave 5 should feel like a survival gauntlet before boss.
                    _eff_interval = max(10, int(_eff_interval * 0.85))
                if wave_spawned < _eff_count:
                    enemy_timer += 1
                    if enemy_timer >= _eff_interval:
                        _spawn_enemy(random.randint(0, WIDTH - 40), 0)
                        enemy_timer = 0
                        wave_spawned += 1

                if level >= 4 and wave_spawned < _eff_count:
                    level4_drone_timer -= 1
                    if level4_drone_timer <= 0:
                        _remaining = max(0, _eff_count - wave_spawned)
                        _screen_cap = max(0, 16 - len(enemies))
                        _pack = min(_remaining, _screen_cap, 1 + wave // 2)
                        for _ in range(_pack):
                            _spawn_enemy(random.randint(0, WIDTH - 40), random.randint(-120, -20))
                            wave_spawned += 1
                        level4_drone_timer = random.randint(max(22, 58 - 6 * wave), max(50, 92 - 8 * wave))

            # ── Galaga dive trigger ──────────────────────────────────────────
            dive_timer -= 1
            if dive_timer <= 0 and not boss_active:
                _wave_i = _wave_idx()
                dive_timer = random.randint(
                    WAVE_DIVE_COOLDOWN_MIN[_wave_i],
                    WAVE_DIVE_COOLDOWN_MAX[_wave_i],
                )
                _dcands = [e for e in enemies if not e[2] and e[3] is None and e[0].y > 60]
                _dive_batch = WAVE_DIVE_BATCH[_wave_i]
                for _de in random.sample(_dcands, k=min(_dive_batch, len(_dcands))):
                    _p1x = sprite_rect.centerx + random.choice([-220, 220])
                    _de[3] = {'t': 0.0,
                              'p0': (float(_de[0].centerx), float(_de[0].centery)),
                              'p1': (float(_p1x), float(HEIGHT * 0.55)),
                              'p2': (float(sprite_rect.centerx + random.randint(-25, 25)),
                                     float(HEIGHT + 60))}
                    score_popups.append(ScorePopup(
                        x=_de[0].centerx,
                        y=_de[0].top - 15,
                        timer=35,
                        max=35,
                        text='⚡ DIVE!',
                        color=(0, 220, 255),
                    ))

            for e in enemies:
                _wave_i = _wave_idx()
                if e[3] is not None:
                    # Galaga dive: quadratic bezier arc
                    _d = e[3]
                    _d['t'] = min(1.0, _d['t'] + 0.011)
                    _t = _d['t']; _mt = 1.0 - _t
                    e[0].centerx = int(_mt*_mt*_d['p0'][0] + 2*_mt*_t*_d['p1'][0] + _t*_t*_d['p2'][0])
                    e[0].centery = int(_mt*_mt*_d['p0'][1] + 2*_mt*_t*_d['p1'][1] + _t*_t*_d['p2'][1])
                elif (
                    not e[2]
                    and e[3] is None
                    and e[0].y > cfg.KAMIKAZE_THRESHOLD_Y
                    and random.random() < WAVE_KAMIKAZE_CHANCE[_wave_i]
                ):
                    e[2] = True
                    score_popups.append(ScorePopup(
                        x=e[0].centerx,
                        y=e[0].top - 15,
                        timer=40,
                        max=40,
                        text='\u2620 KAMIKAZE!',
                        color=(255, 50, 50),
                    ))
                if e[2]:
                    _kdx = sprite_rect.centerx - e[0].centerx
                    _kdy = sprite_rect.centery - e[0].centery
                    _kdist = math.hypot(_kdx, _kdy) or 1
                    _kspd  = (WAVE_ENEMY_SPEED[_wave_i] + (3 if wave < 4 else 4)) * _enemy_speed_mult()
                    e[0].x += int(_kdx / _kdist * _kspd * dt_mul)
                    e[0].y += int(_kdy / _kdist * _kspd * dt_mul)
                elif e[3] is None:
                    # Role-based AI movement system
                    _profile = enemy_ai_profiles.get(id(e))
                    if _profile is None:
                        # Fallback for enemies without profile (shouldn't happen)
                        e[0].y += int(WAVE_ENEMY_SPEED[_wave_i] * _enemy_speed_mult() * dt_mul)
                    else:
                        _role = _profile['role']
                        _reaction_frames = NPC_REACTION_FRAMES.get(_role, 0)
                        _profile['reaction_frames'] = max(0, _profile['reaction_frames'] - 1)
                        
                        if _role == 'drifter':
                            # Sine-wave descent with horizontal wobble
                            e[0].y += int(WAVE_ENEMY_SPEED[_wave_i] * _enemy_speed_mult() * dt_mul)
                            _wobble = math.sin(frame_count * 0.04 + e[1]) * 1.8
                            _track_dx = sprite_rect.centerx - e[0].centerx
                            _track_step = max(-WAVE_TRACK_CAP[_wave_i],
                                            min(WAVE_TRACK_CAP[_wave_i], _track_dx * WAVE_TRACK_GAIN[_wave_i] * 0.6))
                            e[0].x = max(0, min(WIDTH - 40, e[0].x + int((_wobble + _track_step) * dt_mul)))
                        
                        elif _role == 'tracker':
                            # Gentle pursuit with phase lag
                            if _profile['reaction_frames'] <= 0:
                                _dx = sprite_rect.centerx - e[0].centerx
                                _dy = sprite_rect.centery - e[0].centery
                                _dist = math.hypot(_dx, _dy) or 1
                                _spd = WAVE_ENEMY_SPEED[_wave_i] * 1.15 * _enemy_speed_mult()
                                _phase_lag = 0.7 + 0.3 * math.sin(_profile['phase'])
                                e[0].x += int((_dx / _dist) * _spd * _phase_lag * dt_mul)
                                e[0].y += int((_dy / _dist) * _spd * 0.8 * dt_mul)
                                _profile['phase'] += 0.05
                            else:
                                e[0].y += int(WAVE_ENEMY_SPEED[_wave_i] * 0.6 * _enemy_speed_mult() * dt_mul)
                        
                        elif _role == 'flanker':
                            # Offset pursuit to flank player
                            if _profile['reaction_frames'] <= 0:
                                _dx = sprite_rect.centerx - e[0].centerx
                                _dy = sprite_rect.centery - e[0].centery
                                _dist = math.hypot(_dx, _dy) or 1
                                _flank_offset = _profile.get('flank_offset', 60)
                                _strafe_dir = _profile.get('strafe_dir', 1)
                                _target_x = sprite_rect.centerx + _flank_offset * _strafe_dir
                                _target_y = sprite_rect.centery + 40
                                _tdx = _target_x - e[0].centerx
                                _tdy = _target_y - e[0].centery
                                _tdist = math.hypot(_tdx, _tdy) or 1
                                _spd = WAVE_ENEMY_SPEED[_wave_i] * 1.1 * _enemy_speed_mult()
                                e[0].x += int((_tdx / _tdist) * _spd * dt_mul)
                                e[0].y += int((_tdy / _tdist) * _spd * 0.75 * dt_mul)
                                e[0].x = max(0, min(WIDTH - 40, e[0].x))
                            else:
                                e[0].y += int(WAVE_ENEMY_SPEED[_wave_i] * 0.5 * _enemy_speed_mult() * dt_mul)
                        
                        elif _role == 'gunner':
                            # Stationary or slow moving, focuses on aimed fire
                            e[0].y += int(WAVE_ENEMY_SPEED[_wave_i] * 0.4 * _enemy_speed_mult() * dt_mul)
                            _track_dx = sprite_rect.centerx - e[0].centerx
                            _track_step = max(-WAVE_TRACK_CAP[_wave_i] * 0.5,
                                            min(WAVE_TRACK_CAP[_wave_i] * 0.5, _track_dx * WAVE_TRACK_GAIN[_wave_i] * 0.4))
                            e[0].x = max(0, min(WIDTH - 40, e[0].x + int(_track_step * dt_mul)))
                        
                        elif _role == 'hunter':
                            # Aggressive pursuit capped at 92% player speed
                            if _profile['reaction_frames'] <= 0:
                                _dx = sprite_rect.centerx - e[0].centerx
                                _dy = sprite_rect.centery - e[0].centery
                                _dist = math.hypot(_dx, _dy) or 1
                                _base_spd = WAVE_ENEMY_SPEED[_wave_i] * 1.45 * _enemy_speed_mult()
                                _max_spd = max(PLAYER_MAX_NORMAL_SPEED, float(perk_speed)) * MAX_HUNTER_SPEED_RATIO
                                _hunt_spd = min(_max_spd, _base_spd)
                                e[0].x += int((_dx / _dist) * _hunt_spd * dt_mul)
                                e[0].y += int((_dy / _dist) * _hunt_spd * dt_mul)
                                e[0].x = max(0, min(WIDTH - 40, e[0].x))
                            else:
                                e[0].y += int(WAVE_ENEMY_SPEED[_wave_i] * 0.7 * _enemy_speed_mult() * dt_mul)
                        
                        # Cooldown-based shooting (all roles)
                        _profile['shot_cd'] = max(0, _profile['shot_cd'] - 1)
                        if _profile['shot_cd'] <= 0:
                            _shoot_prob = WAVE_SHOOT_PROB[_wave_i] * (1.18 if trauma_mode else 1.0) * shoot_prob_scale
                            if random.random() < _shoot_prob:
                                _dx = sprite_rect.centerx - e[0].centerx
                                _dy = sprite_rect.centery - e[0].centery
                                _dist = math.hypot(_dx, _dy) or 1
                                _bspd = _bullet_speed_value()
                                
                                # Role-specific shooting patterns
                                if _role == 'gunner':
                                    # Gunner: always aimed fire
                                    aimed_bullets.append({'x': float(e[0].centerx), 'y': float(e[0].bottom),
                                                        'vx': _dx / _dist * _bspd,
                                                        'vy': _dy / _dist * _bspd})
                                else:
                                    # Others: chance of aimed fire based on wave
                                    if random.random() < WAVE_AIMED_SHOT_RATIO[_wave_i]:
                                        aimed_bullets.append({'x': float(e[0].centerx), 'y': float(e[0].bottom),
                                                            'vx': _dx / _dist * _bspd,
                                                            'vy': _dy / _dist * _bspd})
                                    else:
                                        enemy_bullets.append(pygame.Rect(e[0].centerx - 4, e[0].bottom, 8, 12))
                                
                                # Set cooldown for next shot
                                _role_cooldowns = ROLE_SHOT_COOLDOWNS.get(_role, (30, 60))
                                _profile['shot_cd'] = random.randint(_role_cooldowns[0], _role_cooldowns[1])

            # ── Enemy separation (prevent clumping) ───────────────────────────
            for _i, _e1 in enumerate(enemies):
                for _e2 in enemies[_i+1:]:
                    _dx = _e2[0].centerx - _e1[0].centerx
                    _dy = _e2[0].centery - _e1[0].centery
                    _dist = math.hypot(_dx, _dy) or 1
                    if _dist < NPC_SEPARATION_RADIUS:
                        _push = NPC_SEPARATION_FORCE / (_dist + 0.1)
                        _e1[0].x -= int((_dx / _dist) * _push * dt_mul)
                        _e2[0].x += int((_dx / _dist) * _push * dt_mul)
                        _e1[0].x = max(0, min(WIDTH - 40, _e1[0].x))
                        _e2[0].x = max(0, min(WIDTH - 40, _e2[0].x))

            _escaped_count = 0
            _next_enemies = []
            for e in enemies:
                if e[0].top >= HEIGHT:
                    _escaped_count += 1
                    run_stats['total_enemies_escaped'] += 1
                    wave_stats['wave_enemies_escaped'] += 1
                    continue
                if e[0].bottom <= -60:
                    continue
                _next_enemies.append(e)
            enemies = _next_enemies
            if _escaped_count:
                block_signal -= 5 * _escaped_count
                block_signal = max(0, block_signal)

            if block_signal <= 0 and not game_over:
                block_signal = 0
                game_over = True
                continue_timer = 0
                running = False
                run_channel.stop()
                jetpack_channel.stop()
                score_popups.append(ScorePopup(
                    x=WIDTH // 2,
                    y=HEIGHT // 2 - 80,
                    timer=90,
                    max=90,
                    text='BLOCK SIGNAL LOST',
                    color=(255, 70, 70),
                ))

            for p in health_pickups:
                p.y += int(dt_mul)
            health_pickups = [p for p in health_pickups if p.top < HEIGHT]
            for p in sativa_pickups:
                p.y += int(2 * dt_mul)
            sativa_pickups = [p for p in sativa_pickups if p.top < HEIGHT]
            for ds in data_souls:
                ds.y += int(1.5 * dt_mul)
            data_souls = [ds for ds in data_souls if ds.top < HEIGHT]

            for b in enemy_bullets:
                b.y += int(BULLET_SPEED * dt_mul)
            enemy_bullets = [b for b in enemy_bullets if b.y < HEIGHT]

            for ab in aimed_bullets:
                ab['x'] += ab['vx'] * dt_mul
                ab['y'] += ab['vy'] * dt_mul
            aimed_bullets = [ab for ab in aimed_bullets
                             if 0 < ab['y'] < HEIGHT and 0 < ab['x'] < WIDTH]

            # ── Near-miss bonus ───────────────────────────────────────────────
            # Prune near_miss_ids to only live bullet ids (prevents unbounded growth)
            _live_ids = {id(b) for b in enemy_bullets} | {id(ab) for ab in aimed_bullets}
            near_miss_ids &= _live_ids
            _pcx, _pcy = sprite_rect.centerx, sprite_rect.centery
            for _nmb in enemy_bullets:
                if id(_nmb) not in near_miss_ids:
                    if (math.hypot(_nmb.centerx - _pcx, _nmb.centery - _pcy) < 38
                            and not _nmb.colliderect(sprite_rect)):
                        near_miss_ids.add(id(_nmb))
                        if near_miss_sound and near_miss_sound_timer == 0:
                            near_miss_sound.play()
                            near_miss_sound_timer = 25
                        run_stats['total_near_misses'] += 1
                        wave_stats['wave_near_misses'] += 1
                        score += 50
                        signal_meter = min(signal_max, signal_meter + 5)
                        # Near-miss boost
                        movement_boost = max(movement_boost, PLAYER_NEAR_MISS_BOOST)
                        movement_boost_timer = max(
                            movement_boost_timer,
                            PLAYER_NEAR_MISS_FRAMES,
                        )
                        score_popups.append(ScorePopup(
                            x=_nmb.centerx,
                            y=_nmb.top - 10,
                            timer=30,
                            max=30,
                            text='NEAR MISS +50',
                            color=(100, 255, 255),
                        ))
            for _nmab in aimed_bullets:
                if id(_nmab) not in near_miss_ids:
                    _nmab_r = pygame.Rect(int(_nmab['x']) - 4, int(_nmab['y']) - 6, 8, 12)
                    if (math.hypot(_nmab['x'] - _pcx, _nmab['y'] - _pcy) < 38
                            and not _nmab_r.colliderect(sprite_rect)):
                        near_miss_ids.add(id(_nmab))
                        if near_miss_sound and near_miss_sound_timer == 0:
                            near_miss_sound.play()
                            near_miss_sound_timer = 25
                        run_stats['total_near_misses'] += 1
                        wave_stats['wave_near_misses'] += 1
                        score += 50
                        signal_meter = min(signal_max, signal_meter + 5)
                        # Near-miss boost
                        movement_boost = max(movement_boost, PLAYER_NEAR_MISS_BOOST)
                        movement_boost_timer = max(
                            movement_boost_timer,
                            PLAYER_NEAR_MISS_FRAMES,
                        )
                        score_popups.append(ScorePopup(
                            x=int(_nmab['x']),
                            y=int(_nmab['y']) - 10,
                            timer=30,
                            max=30,
                            text='NEAR MISS +50',
                            color=(100, 255, 255),
                        ))

            if boss_active:
                if not boss_raging and boss_health <= boss_max_health // 2:
                    boss_raging          = True
                    boss_fire_interval   = 28
                    boss_minion_interval = 70
                    shake_timer          = 20
                    boss_rage_flash      = 150
                    score_popups.append(ScorePopup(
                        x=WIDTH // 2,
                        y=HEIGHT // 2 - 80,
                        timer=120,
                        max=120,
                        text='☠  RAGE  MODE  ☠',
                        color=(255, 40, 40),
                    ))
                if not boss_critical and boss_health <= boss_max_health // 4:
                    boss_critical        = True
                    boss_fire_interval   = 20
                    boss_minion_interval = 54
                    shake_timer          = 30
                if not boss_death_spiral and boss_health <= 5:
                    boss_death_spiral    = True
                    boss_fire_interval   = 12
                    shake_timer          = 35
                    score_popups.append(ScorePopup(
                        x=WIDTH // 2,
                        y=HEIGHT // 2 - 80,
                        timer=120,
                        max=120,
                        text='\u2620  FINAL STAND  \u2620',
                        color=(255, 50, 255),
                    ))
                # ── Spawn boss minions ──────────────────────────────────────
                _minion_cap = 5 if boss_raging else 3
                if boss_rect.top >= 50 and len(boss_minions) < _minion_cap:
                    boss_minion_timer += 1
                    if boss_minion_timer >= boss_minion_interval:
                        boss_minion_timer = 0
                        side = random.choice([-1, 1])
                        mx = WIDTH // 4 if side == -1 else WIDTH * 3 // 4
                        boss_minions.append({
                            'rect': pygame.Rect(mx, -32, 32, 32),
                            'phase': random.uniform(0, 2 * math.pi),
                            'fire_timer': random.randint(0, 60),
                        })
                # ── Move boss minions ───────────────────────────────────────
                for bm in boss_minions:
                    bm['rect'].y += int(3 * dt_mul)
                    bm['rect'].x = max(0, min(WIDTH - 32,
                        bm['rect'].x + int(math.sin(frame_count * 0.05 + bm['phase']) * 2 * dt_mul)))
                    bm['fire_timer'] += 1
                    if bm['rect'].top >= 0 and bm['fire_timer'] >= (40 if boss_critical else 52 if boss_raging else 68):
                        bm['fire_timer'] = 0
                        dx = sprite_rect.centerx - bm['rect'].centerx
                        dy = sprite_rect.centery - bm['rect'].centery
                        dist = math.hypot(dx, dy) or 1
                        _bspd = _bullet_speed_value()
                        aimed_bullets.append({
                            'x': float(bm['rect'].centerx),
                            'y': float(bm['rect'].bottom),
                            'vx': dx / dist * _bspd,
                            'vy': dy / dist * _bspd,
                        })
                boss_minions = [bm for bm in boss_minions if bm['rect'].top < HEIGHT]
                hspeed = 0 if boss_death_spiral else (10 if boss_critical else (7 if boss_raging else 4))
                if boss_rect.top < 50:
                    boss_rect.y += int(boss_speed * dt_mul)
                else:
                    _boss_dx = sprite_rect.centerx - boss_rect.centerx
                    _boss_track = 0 if boss_death_spiral else max(-3.0, min(3.0, _boss_dx * (0.020 if boss_critical else 0.014 if boss_raging else 0.008)))
                    boss_rect.x += int((hspeed * boss_dir + _boss_track) * dt_mul)
                    if (boss_raging or boss_critical) and frame_count % (90 if boss_critical else 120) == 0:
                        boss_dir *= -1
                    if boss_rect.right >= WIDTH or boss_rect.left <= 0:
                        boss_dir *= -1
                    boss_fire_timer += 1
                    if boss_fire_timer >= boss_fire_interval:
                        boss_fire_timer = 0
                        boss_volley_count += 1
                        cx = boss_rect.centerx
                        by = boss_rect.bottom
                        if boss_death_spiral:
                            _bspd = _bullet_speed_value()
                            boss_spiral_angle += math.pi / 6
                            for _si in range(8):
                                _ang = boss_spiral_angle + _si * (math.pi / 4)
                                aimed_bullets.append({
                                    'x': float(cx), 'y': float(by),
                                    'vx': math.cos(_ang) * _bspd * 1.2,
                                    'vy': math.sin(_ang) * _bspd * 1.2,
                                })
                            _dx = sprite_rect.centerx - cx
                            _dy = sprite_rect.centery - by
                            _dist = math.hypot(_dx, _dy) or 1
                            aimed_bullets.append({'x': float(cx), 'y': float(by),
                                'vx': _dx / _dist * _bspd * 1.5,
                                'vy': _dy / _dist * _bspd * 1.5})
                            shake_timer = max(shake_timer, 5)
                        elif boss_critical:
                            _bspd = _bullet_speed_value()
                            # 5-bullet fan + aimed shot every volley
                            boss_bullets += [
                                pygame.Rect(cx - 32, by, 10, 16),
                                pygame.Rect(cx - 16, by, 10, 16),
                                pygame.Rect(cx - 5,  by, 10, 16),
                                pygame.Rect(cx + 11, by, 10, 16),
                                pygame.Rect(cx + 27, by, 10, 16),
                            ]
                            _dx = sprite_rect.centerx - cx
                            _dy = sprite_rect.centery - by
                            _dist = math.hypot(_dx, _dy) or 1
                            aimed_bullets.append({'x': float(cx), 'y': float(by),
                                'vx': _dx / _dist * _bspd * 1.3,
                                'vy': _dy / _dist * _bspd * 1.3})
                            shake_timer = max(shake_timer, 6)
                        elif boss_raging:
                            _bspd = _bullet_speed_value()
                            # 5-bullet fan
                            boss_bullets += [
                                pygame.Rect(cx - 28, by, 10, 16),
                                pygame.Rect(cx - 14, by, 10, 16),
                                pygame.Rect(cx - 5,  by, 10, 16),
                                pygame.Rect(cx + 9,  by, 10, 16),
                                pygame.Rect(cx + 23, by, 10, 16),
                            ]
                            # aimed shot every volley in rage
                            if boss_volley_count % 1 == 0:
                                _dx = sprite_rect.centerx - cx
                                _dy = sprite_rect.centery - by
                                _dist = math.hypot(_dx, _dy) or 1
                                aimed_bullets.append({'x': float(cx), 'y': float(by),
                                    'vx': _dx / _dist * _bspd,
                                    'vy': _dy / _dist * _bspd})
                        else:
                            # 2-bullet spread
                            boss_bullets += [
                                pygame.Rect(cx - 12, by, 10, 16),
                                pygame.Rect(cx + 7,  by, 10, 16),
                            ]

                for b in boss_bullets:
                    b.y += int(BULLET_SPEED * dt_mul)
                boss_bullets = [b for b in boss_bullets if b.y < HEIGHT]

            state = GameState(
                sprite_rect=sprite_rect,
                fireballs=fireballs,
                side_bullets=side_bullets,
                enemies=enemies,
                enemy_bullets=enemy_bullets,
                aimed_bullets=aimed_bullets,
                boss_bullets=boss_bullets,
                boss_minions=boss_minions,
                health_pickups=health_pickups,
                sativa_pickups=sativa_pickups,
                data_souls=data_souls,
                score_popups=score_popups,
                score=score,
                health=health,
                signal_meter=signal_meter,
                signal_max=signal_max,
                block_signal=block_signal,
                block_signal_max=block_signal_max,
                sativa_active=sativa_active,
                sativa_timer=sativa_timer,
                iframe_timer=iframe_timer,
                boss_active=boss_active,
                boss_rect=boss_rect,
            )

            def _add_popup(x, y, timer, max_timer, text, color):
                score_popups.append(ScorePopup(x=x, y=y, timer=timer, max=max_timer, text=text, color=color))

            handle_player_bullets_vs_enemies(
                state,
                perk_power_shot,
                _register_enemy_destroyed,
                _register_minion_destroyed,
                _damage_boss,
            )

            handle_side_bullets_vs_enemies(state, _register_enemy_destroyed)
            handle_boss_damage(state, perk_power_shot, _register_minion_destroyed, _damage_boss)
            handle_enemy_bullets_vs_player(state, _damage_player)
            handle_pickups(state, powerup_sound, sativa_sound, _add_popup)

            # Pull scalar updates back out of GameState at a single sync point.
            (
                score,
                health,
                signal_meter,
                block_signal,
                sativa_active,
                sativa_timer,
                iframe_timer,
            ) = _pull_runtime_scalars(state)

            # Sync list state back — systems rebuild these via assignment, not in-place mutation.
            enemies        = state.enemies
            fireballs      = state.fireballs
            side_bullets   = state.side_bullets
            enemy_bullets  = state.enemy_bullets
            aimed_bullets  = state.aimed_bullets
            boss_bullets   = state.boss_bullets
            boss_minions   = state.boss_minions
            health_pickups = state.health_pickups
            sativa_pickups = state.sativa_pickups
            data_souls     = state.data_souls

            # ── Draw player: running, directional shooting, hit, and flight animations ──
            current_sprite_image, current_pose_key, player_render_offset = player_animator.get_frame(
                player_velocity,
                shoot_pose_timer > 0,
                side_shoot_pose_timer > 0,
                side_shot_direction,
                hit_flash_timer > 0,
                frame_count,
            )
            player_render_center = (
                sprite_rect.centerx + player_render_offset[0],
                sprite_rect.centery + player_render_offset[1],
            )

            # ── Loop ambient player movement sounds ──────────────────────────
            _pose_state = current_pose_key.split(':')[0]
            if run_sound:
                if _pose_state.startswith('run_'):
                    if not run_channel.get_busy():
                        run_channel.play(run_sound, loops=-1)
                elif run_channel.get_busy():
                    run_channel.stop()
            if jetpack_sound:
                if _pose_state.startswith('fly_'):
                    if not jetpack_channel.get_busy():
                        jetpack_channel.play(jetpack_sound, loops=-1)
                elif jetpack_channel.get_busy():
                    jetpack_channel.stop()

            # ── Landing impact: dust burst + thud when jetpack → ground ─────
            if _prev_pose_state.startswith('fly_') and not _pose_state.startswith('fly_'):
                _foot_x = float(sprite_rect.centerx)
                _foot_y = float(sprite_rect.bottom - 4)
                _dust_cols = [
                    (210, 200, 180), (190, 185, 165),
                    (170, 165, 145), (200, 190, 170), (180, 172, 155),
                ]
                for _ in range(5):
                    particles.append({
                        'x': _foot_x + random.randint(-14, 14),
                        'y': _foot_y,
                        'vx': random.uniform(-3.5, 3.5),
                        'vy': random.uniform(-2.5, -0.6),
                        'life': random.randint(16, 26),
                        'max': 26,
                        'color': random.choice(_dust_cols),
                    })
                if landing_sound:
                    landing_sound.play()
            _prev_pose_state = _pose_state

            # Invulnerability frames still prevent repeat damage, but never hide
            # the player sprite. This keeps the character readable during combat.
            if beat_pulse > 0 or sativa_active:
                _bp_t    = beat_pulse / BEAT_PULSE_FRAMES if beat_pulse > 0 else 1.0
                _scale_m = 0.45 if sativa_active else 0.18
                _bp_s    = 1.0 + _scale_m * _bp_t
                # Cache scaled sprite by BOTH pose and size.
                _bp_key  = (current_pose_key, round(_bp_s * 50) / 50)
                _bp_w    = int(current_sprite_image.get_width() * _bp_key[1])
                _bp_h    = int(current_sprite_image.get_height() * _bp_key[1])
                if _scale_cache['key'] != _bp_key:
                    _scale_cache['key']  = _bp_key
                    _scale_cache['surf'] = pygame.transform.scale(current_sprite_image, (_bp_w, _bp_h))
                _bp_img  = _scale_cache['surf']
                _bp_r    = _bp_img.get_rect(center=player_render_center)
                # glow ring
                _glow_m  = 1.4 if sativa_active else 0.6
                _glow_r  = int(sprite_rect.width * _glow_m * max(_bp_t, 0.4 if sativa_active else 0))
                if _glow_r > 2:
                    _gcol   = (0, 255, 120) if sativa_active else (255, 200, 0)
                    _glow_a = int((220 if sativa_active else 180) * max(_bp_t, 0.5 if sativa_active else 0))
                    _sprite_glow_surf.fill((0, 0, 0, 0))
                    pygame.draw.circle(_sprite_glow_surf, (*_gcol, _glow_a),
                                       (120, 120), _glow_r)
                    screen.blit(_sprite_glow_surf,
                                (_bp_r.centerx - 120, _bp_r.centery - 120))
                screen.blit(_bp_img, _bp_r)
            else:
                _player_render_rect = current_sprite_image.get_rect(center=player_render_center)
                screen.blit(current_sprite_image, _player_render_rect)

            if ancestral_protection_charges > 0 and iframe_timer % 6 < 3:
                _aura_rad = sprite_rect.width // 2 + 8 + (2 if not PHOTOSENSITIVE_SAFE_MODE else 0)
                _aura_col = (140, 255, 210) if PHOTOSENSITIVE_SAFE_MODE else (190, 255, 230)
                pygame.draw.circle(screen, _aura_col, sprite_rect.center, _aura_rad, 2)

            # Fireball color shifts with shot tier
            if sativa_active:
                _fb_col = (0, 255, 150)
            elif perk_double_shot and perk_power_shot:
                _fb_col = (255, 215, 50)
            elif perk_double_shot:
                _fb_col = (180, 80, 255)
            else:
                _fb_col = _COL_FIREBALL
            for f in fireballs:
                # Trailing tail — dim color extends below (bullet travels up)
                _fb_dim = (max(0, _fb_col[0]//4), max(0, _fb_col[1]//4), max(0, _fb_col[2]//4))
                pygame.draw.rect(screen, _fb_dim, (f.x + 1, f.bottom - 2, 6, 10))
                if _fb_col != _COL_FIREBALL:
                    _fb_glow_surf.fill((*_fb_col, 80))
                    screen.blit(_fb_glow_surf, (f.x - 4, f.y - 4))
                # Main body
                pygame.draw.rect(screen, _fb_col, f)
                # White-yellow hot tip at leading edge (top)
                pygame.draw.rect(screen, (255, 255, 180), (f.x + 2, f.top, 4, 5))
            for sb in side_bullets:
                _sbc     = (0, 220, 255) if not sativa_active else (0, 255, 180)
                _sbc_dim = (0, 65, 80)   if not sativa_active else (0, 70, 55)
                bx, by   = int(sb['x']), int(sb['y'])
                if sb['vx'] > 0:  # right-moving: tail left, tip right
                    pygame.draw.rect(screen, _sbc_dim,        (bx - 20, by - 1, 12, 2))
                    pygame.draw.rect(screen, _sbc,            (bx -  8, by - 2, 16, 4))
                    pygame.draw.rect(screen, (255, 255, 200), (bx +  8, by - 1,  5, 2))
                else:             # left-moving: tail right, tip left
                    pygame.draw.rect(screen, _sbc_dim,        (bx +  9, by - 1, 12, 2))
                    pygame.draw.rect(screen, _sbc,            (bx -  8, by - 2, 16, 4))
                    pygame.draw.rect(screen, (255, 255, 200), (bx - 13, by - 1,  5, 2))
            for e in enemies:
                if level >= 4:
                    _dimg = drone_images_level_4[id(e) % len(drone_images_level_4)]
                elif level >= 2:
                    _dimg = drone_images_level_2[id(e) % 3]
                else:
                    _dimg = drone_image
                screen.blit(_dimg, e[0])
                if e[2] and (not PHOTOSENSITIVE_SAFE_MODE) and frame_count % 8 < 4:
                    screen.blit(_kflash_surf, e[0])
                elif e[3] is not None and (not PHOTOSENSITIVE_SAFE_MODE) and frame_count % 6 < 3:
                    screen.blit(_dflash_surf, e[0])
            for bm in boss_minions:
                screen.blit(minion_image or drone_image, bm['rect'])

            # ── Gore update & render ──────────────────────────────────────────
            # Clear surface for this frame
            blood_fx_surface.fill((0, 0, 0, 0))
            
            # Render persistent decals (stays longest)
            _next_decals = []
            for decal in blood_decals:
                decal['life'] -= 1
                decal['wet'] = max(0, decal['wet'] - 1)
                if decal['life'] > 0:
                    # Fade out alpha
                    _alpha = int(180 * decal['life'] / decal['max'])
                    if _alpha > 0:
                        _wet_mix = decal['wet'] / max(1, decal.get('wet_max', BLOOD_WET_FRAMES))
                        _gloss = decal.get('gloss', 1.0)
                        _base_col = decal['color']
                        _dry_col = decal['dry_color']
                        _blend_col = (
                            int(_base_col[0] * _wet_mix + _dry_col[0] * (1.0 - _wet_mix)),
                            int(_base_col[1] * _wet_mix + _dry_col[1] * (1.0 - _wet_mix)),
                            int(_base_col[2] * _wet_mix + _dry_col[2] * (1.0 - _wet_mix)),
                            _alpha,
                        )
                        pygame.draw.ellipse(
                            blood_fx_surface,
                            _blend_col,
                            (decal['x'], decal['y'], decal['w'], decal['h']),
                        )
                        # Fresh blood catches a tiny highlight before drying.
                        if decal['wet'] > 0 and _alpha > 40:
                            _hx = decal['x'] + max(1, decal['w'] // 4)
                            _hy = decal['y'] + max(1, decal['h'] // 4)
                            _hr = max(1, int((min(decal['w'], decal['h']) // 6) * _gloss))
                            pygame.draw.circle(
                                blood_fx_surface,
                                (255, 210, 210, min(92, int((_alpha // 3) * _gloss))),
                                (_hx, _hy),
                                _hr,
                            )
                    _next_decals.append(decal)
            blood_decals = _next_decals
            
            # Update and render droplets (fast moving, short lived)
            _next_drops = []
            for droplet in blood_droplets:
                droplet['px'] = droplet['x']
                droplet['py'] = droplet['y']
                droplet['vx'] *= BLOOD_DRAG
                droplet['vy'] *= BLOOD_DRAG
                droplet['vy'] += BLOOD_GRAVITY
                droplet['x'] += droplet['vx']
                droplet['y'] += droplet['vy']
                droplet['life'] -= 1
                if droplet['life'] > 0 and 0 <= droplet['x'] < WIDTH and 0 <= droplet['y'] < HEIGHT:
                    # Fade out
                    _alpha = int(200 * droplet['life'] / droplet['max'])
                    if _alpha > 0:
                        _drop_col = droplet['color'] + (_alpha,) if len(droplet['color']) == 3 else droplet['color']
                        _trail_alpha = min(_alpha, BLOOD_TRAIL_ALPHA)
                        _trail_col = droplet['color'] + (_trail_alpha,)
                        pygame.draw.line(
                            blood_fx_surface,
                            _trail_col,
                            (int(droplet['px']), int(droplet['py'])),
                            (int(droplet['x']), int(droplet['y'])),
                            1,
                        )
                        pygame.draw.circle(blood_fx_surface, _drop_col,
                                         (int(droplet['x']), int(droplet['y'])), droplet['radius'])
                    _next_drops.append(droplet)
                elif droplet['life'] <= 0 and random.random() < BLOOD_POOL_CHANCE:
                    _pw = random.randint(5, 11)
                    _ph = random.randint(3, 8)
                    _pool_color = random.choice(BLOOD_COLORS[:3])
                    blood_decals.append({
                        'x': int(droplet['x']) - _pw // 2,
                        'y': int(droplet['y']) - _ph // 2,
                        'w': _pw,
                        'h': _ph,
                        'life': random.randint(160, 280),
                        'max': 280,
                        'wet': max(24, BLOOD_WET_FRAMES // 3),
                        'color': _pool_color,
                        'dry_color': tuple(max(0, int(c * 0.65)) for c in _pool_color),
                    })
            blood_droplets = _next_drops
            
            # Update and render chunks (medium sized, medium lived)
            _next_chunks = []
            for chunk in blood_chunks:
                chunk['vx'] *= BLOOD_DRAG
                chunk['vy'] *= BLOOD_DRAG
                chunk['vy'] += BLOOD_GRAVITY
                chunk['x'] += chunk['vx']
                chunk['y'] += chunk['vy']
                chunk['life'] -= 1
                if chunk['life'] > 0 and 0 <= chunk['x'] < WIDTH - chunk['w'] and 0 <= chunk['y'] < HEIGHT - chunk['h']:
                    _alpha = int(220 * chunk['life'] / chunk['max'])
                    if _alpha > 0:
                        _chunk_col = chunk['color'] + (_alpha,) if len(chunk['color']) == 3 else chunk['color']
                        pygame.draw.ellipse(
                            blood_fx_surface,
                            _chunk_col,
                            (int(chunk['x']), int(chunk['y']), chunk['w'], chunk['h']),
                        )
                    _next_chunks.append(chunk)
            blood_chunks = _next_chunks

            del blood_decals[:-MAX_BLOOD_DECALS]
            
            # Blit accumulated gore to screen
            screen.blit(blood_fx_surface, (0, 0))

            i = 0
            while i < len(particles):
                p = particles[i]
                p['x'] += p['vx']
                p['y'] += p['vy']
                p['life'] -= 1
                if p['life'] > 0:
                    sz = max(1, int(5 * p['life'] / p['max']))
                    pygame.draw.rect(screen, p['color'],
                                     (int(p['x']), int(p['y']), sz, sz))
                    i += 1
                else:
                    # O(1) in-place removal: overwrite slot with last item
                    particles[i] = particles[-1]
                    particles.pop()
            # Safety cap — only triggers during extreme burst phases
            if len(particles) > MAX_PARTICLES:
                del particles[:len(particles) - MAX_PARTICLES]
            # Hard caps prevent worst-case frame spikes during dense boss phases.
            score_popups  = score_popups[-MAX_SCORE_POPUPS:]
            data_souls    = data_souls[-MAX_DATA_SOULS:]
            fireballs     = fireballs[-MAX_FIREBALLS:]
            side_bullets  = side_bullets[-MAX_SIDE_BULLETS:]
            enemy_bullets = enemy_bullets[-MAX_ENEMY_BULLETS:]
            aimed_bullets = aimed_bullets[-MAX_ENEMY_BULLETS:]
            boss_bullets  = boss_bullets[-MAX_ENEMY_BULLETS:]
            for b in enemy_bullets:
                pygame.draw.rect(screen, _COL_EBULLET, b)
            for ab in aimed_bullets:
                pygame.draw.rect(screen, (255, 140, 0),
                                 (int(ab['x']) - 4, int(ab['y']) - 6, 8, 12))
            for p in health_pickups:
                pygame.draw.rect(screen, _COL_PICKUP, p)
                pygame.draw.rect(screen, _COL_WHITE, (p.x + 6, p.y + 2,  4, 12))
                pygame.draw.rect(screen, _COL_WHITE, (p.x + 2, p.y + 6, 12,  4))
            for p in sativa_pickups:
                _water_glow_surf.fill((0, 0, 0, 0))
                _water_glow_a = 80 if PHOTOSENSITIVE_SAFE_MODE else 120
                # Soft halo: concentric circles avoid the hard square box around the bottle.
                pygame.draw.circle(_water_glow_surf, (70, 180, 255, _water_glow_a // 4), (36, 36), 28)
                pygame.draw.circle(_water_glow_surf, (70, 180, 255, _water_glow_a // 2), (36, 36), 22)
                pygame.draw.circle(_water_glow_surf, (70, 180, 255, _water_glow_a), (36, 36), 16)
                screen.blit(_water_glow_surf, (p.centerx - 36, p.centery - 36))
                screen.blit(water_image, p)
                # Keep the halo gentle; no hard border.
            for ds in data_souls:
                pygame.draw.circle(screen, (180, 80, 255), ds.center, 10)
                pygame.draw.circle(screen, (255, 220, 60), ds.center, 4)

            if boss_active:
                screen.blit(boss_image, boss_rect)
                if boss_raging:
                    _boss_tint_alpha = 12 if PHOTOSENSITIVE_SAFE_MODE else int(50 + 30 * math.sin(frame_count * 0.2))
                    _boss_tint_surf.fill((255, 0, 0, _boss_tint_alpha))
                    screen.blit(_boss_tint_surf, boss_rect.topleft)
                    # Static pre-built vignette — just blit, no per-frame rebuild
                    if not PHOTOSENSITIVE_SAFE_MODE:
                        _vignette_key = 'critical' if boss_critical else 'normal'
                        screen.blit(_rage_vignette_cache[_vignette_key], (0, 0))
                bar_x = WIDTH // 2 - 100
                health_ratio = boss_health / boss_max_health
                pygame.draw.rect(screen, _COL_BAR_BG, (bar_x, 70, 200, 20))
                pygame.draw.rect(screen, _COL_BAR_FG, (bar_x, 70, int(200 * health_ratio), 20))
                for b in boss_bullets:
                    pygame.draw.rect(screen, _COL_BBULLET, b)

            _spi = 0
            while _spi < len(score_popups):
                pop = score_popups[_spi]
                pop['timer'] -= 1
                pop['y']     -= 1
                if pop['timer'] > 0:
                    if pop['surf'] is None:
                        pop['surf'] = font_popup.render(pop['text'], True, pop['color'])
                    alpha = int(255 * pop['timer'] / pop['max'])
                    pop['surf'].set_alpha(alpha)
                    screen.blit(pop['surf'], pop['surf'].get_rect(centerx=int(pop['x']), y=int(pop['y'])))
                    _spi += 1
                else:
                    score_popups[_spi] = score_popups[-1]
                    score_popups.pop()

            if _score_cache['val'] != score:
                _score_cache['val'] = score
                _score_cache['surf'] = font.render(f"Score: {score}", True, _COL_WHITE)
            screen.blit(_score_cache['surf'], (10, 10))
            _hs_key = f"{leaderboard_label}:{high_score_name}{high_score}"
            if _hs_cache['val'] != _hs_key:
                _hs_cache['val'] = _hs_key
                _hs_cache['surf'] = font.render(
                    f"Best ({leaderboard_label}): {high_score_name}  {high_score:,}",
                    True,
                    (180, 180, 180),
                )
            screen.blit(_hs_cache['surf'], _hs_cache['surf'].get_rect(right=WIDTH - 10, y=10))
            if not boss_active and not boss_warned and not boss_defeated:
                if _wave_cache['val'] != (level, wave):
                    _wave_cache['val'] = (level, wave)
                    _wave_cache['surf'] = font.render(f"LEVEL {level}  WAVE {wave} / 5", True, (150, 200, 255))
                screen.blit(_wave_cache['surf'], _wave_cache['surf'].get_rect(centerx=WIDTH // 2, y=10))
            for i in range(8):
                screen.blit(_heart_red_h if i < health else _heart_grey_h, (10 + i * 26, 40))
            _bs_danger = block_signal < 25 and not game_over
            if _bs_danger:
                _bs_pulse = abs(math.sin(frame_count * 0.22))
                _block_lbl_h.set_alpha(int(130 + 125 * _bs_pulse))
            else:
                _block_lbl_h.set_alpha(255)
            screen.blit(_block_lbl_h, (10, 70))
            _bs_bg = pygame.Rect(10, 96, 220, 14)
            _bs_ratio = (block_signal / block_signal_max) if block_signal_max else 0
            if _bs_ratio > 0.6:
                _bs_col = (40, 235, 90)
            elif _bs_ratio > 0.3:
                _bs_col = (255, 210, 40)
            else:
                _bs_col = (255, 70, 70)
            pygame.draw.rect(screen, (20, 35, 45), _bs_bg)
            pygame.draw.rect(screen, _bs_col, (_bs_bg.x, _bs_bg.y, int(_bs_bg.width * _bs_ratio), _bs_bg.height))
            if _bs_danger:
                _bs_bdr = (255, int(60 * (1.0 - _bs_pulse)), int(60 * (1.0 - _bs_pulse)))
                pygame.draw.rect(screen, _bs_bdr, _bs_bg.inflate(2, 2), 3)
            else:
                pygame.draw.rect(screen, (230, 230, 255), _bs_bg, 2)
            _bs_pct = int(_bs_ratio * 100)
            if _block_pct_cache['val'] != _bs_pct or _block_pct_cache['col'] != _bs_col:
                _block_pct_cache['val'] = _bs_pct
                _block_pct_cache['col'] = _bs_col
                _block_pct_cache['surf'] = font.render(f"{_bs_pct}%", True, _bs_col)
            screen.blit(_block_pct_cache['surf'], (_bs_bg.right + 8, _bs_bg.y - 5))
            screen.blit(_signal_lbl_h, (10, 118))
            _sig_bg = pygame.Rect(10, 144, 220, 14)
            _sig_ratio = (signal_meter / signal_max) if signal_max else 0
            if signal_meter >= signal_max:
                _sig_col = (255, 220, 60)
            else:
                _sig_col = (180, 80, 255)
            pygame.draw.rect(screen, (30, 20, 45), _sig_bg)
            pygame.draw.rect(screen, _sig_col, (_sig_bg.x, _sig_bg.y, int(_sig_bg.width * _sig_ratio), _sig_bg.height))
            pygame.draw.rect(screen, (230, 230, 255), _sig_bg, 1)
            _sig_pct = int(_sig_ratio * 100)
            _sig_key = (_sig_pct, _sig_col)
            if _signal_pct_cache['val'] != _sig_key:
                _signal_pct_cache['val'] = _sig_key
                _signal_pct_cache['surf'] = font.render(f'{_sig_pct}%', True, _sig_col)
            screen.blit(_signal_pct_cache['surf'], _signal_pct_cache['surf'].get_rect(left=238, centery=_sig_bg.centery))
            if ancestral_protection_charges > 0:
                if _ap_guard_cache['val'] != ancestral_protection_charges:
                    _ap_guard_cache['val']  = ancestral_protection_charges
                    _ap_guard_cache['surf'] = font.render(
                        f'ANCESTRAL GUARD x{ancestral_protection_charges}', True, (170, 255, 220))
                screen.blit(_ap_guard_cache['surf'], (_sig_bg.x, _sig_bg.bottom + 6))
            if active_perks:
                _ap_key = "  ·  ".join(active_perks)
                if _perks_cache['val'] != _ap_key:
                    _perks_cache['val'] = _ap_key
                    _perks_cache['surf'] = font.render(_ap_key, True, (180, 120, 255))
                screen.blit(_perks_cache['surf'], _perks_cache['surf'].get_rect(centerx=WIDTH // 2, y=HEIGHT - 30))
            if sativa_active:
                _sv_w = int((sativa_timer / 600) * 200)
                pygame.draw.rect(screen, (0, 80, 40),  (WIDTH - 220, HEIGHT - 24, 200, 14))
                pygame.draw.rect(screen, (0, 255, 120), (WIDTH - 220, HEIGHT - 24, _sv_w, 14))
                screen.blit(_sativa_lbl_h, _sativa_lbl_h.get_rect(right=WIDTH - 224, centery=HEIGHT - 17))
            if combo > 1 and combo_timer > 0:
                alpha = min(255, combo_timer * 4)
                if _combo_cache['val'] != combo:
                    _combo_cache['val']  = combo
                    _combo_cache['surf'] = font_med.render(f"x{combo} COMBO!", True, (255, 80, 255))
                _combo_cache['surf'].set_alpha(alpha)
                screen.blit(_combo_cache['surf'],
                            _combo_cache['surf'].get_rect(centerx=WIDTH // 2, centery=HEIGHT // 2 - 60))
            if streak_msg_timer > 0:
                _sa = min(255, streak_msg_timer * 6)
                _sk = (streak_text, streak_color)
                if _streak_cache['key'] != _sk:
                    _streak_cache['key']  = _sk
                    _streak_cache['surf'] = font_big.render(streak_text, True, streak_color)
                _streak_cache['surf'].set_alpha(_sa)
                screen.blit(_streak_cache['surf'], _streak_cache['surf'].get_rect(center=(WIDTH // 2, HEIGHT // 2 + 50)))

            if shake_timer > 0:
                shake_timer -= 1
                # Keep shake visible in safe mode with lower amplitude and fewer updates.
                _shake_stride = 3 if PHOTOSENSITIVE_SAFE_MODE else 2
                if frame_count % _shake_stride == 0:
                    _shake_amp = 1 if PHOTOSENSITIVE_SAFE_MODE else 4
                    ox = random.randint(-_shake_amp, _shake_amp)
                    oy = random.randint(-_shake_amp, _shake_amp)
                    _shake_surf.blit(screen, (0, 0))
                    screen.fill((0, 0, 0))
                    screen.blit(_shake_surf, (ox, oy))

            # ── Screen overlays (applied after shake for stability) ─────────────
            if boss_defeat_timer == 0 and hit_flash_timer > 0:
                # Accessibility/safety: do not draw fullscreen hit overlays.
                hit_flash_timer -= 1

            if boss_defeat_timer == 0 and health == 1 and not game_over:
                # Keep low-health warning via hearts/HUD only; no fullscreen border tint.
                pass

            if boss_defeat_timer == 0 and boss_rage_flash > 0:
                boss_rage_flash -= 1
                if not PHOTOSENSITIVE_SAFE_MODE:
                    _bra = min(255, int(boss_rage_flash * 3.4))
                    _brage_surf.set_alpha(_bra)
                    screen.blit(_brage_surf, _brage_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 55)))

            if boss_defeat_timer == 0 and signal_burst_ring_timer > 0:
                _sr_total = 18 if PHOTOSENSITIVE_SAFE_MODE else 24
                _sr_life = signal_burst_ring_timer
                signal_burst_ring_timer -= 1
                _sr_prog = 1.0 - (_sr_life / _sr_total)
                _sr_rad = int(16 + _sr_prog * (120 if PHOTOSENSITIVE_SAFE_MODE else 180))
                _sr_width = max(2, int((9 if PHOTOSENSITIVE_SAFE_MODE else 13) * (1.0 - _sr_prog)))
                _sr_alpha = max(0, int((145 if PHOTOSENSITIVE_SAFE_MODE else 230) * (1.0 - _sr_prog)))
                _signal_ring_surf.fill((0, 0, 0, 0))
                pygame.draw.circle(_signal_ring_surf, (255, 240, 150, _sr_alpha), (210, 210), min(200, _sr_rad), _sr_width)
                if not PHOTOSENSITIVE_SAFE_MODE and _sr_rad > 45:
                    pygame.draw.circle(_signal_ring_surf, (150, 230, 255, _sr_alpha // 2), (210, 210), min(205, _sr_rad + 20), 2)
                screen.blit(_signal_ring_surf, (signal_burst_center[0] - 210, signal_burst_center[1] - 210))

            if boss_defeat_timer == 0 and signal_burst_flash > 0:
                _sf_total = 18 if PHOTOSENSITIVE_SAFE_MODE else 28
                _sf_life = signal_burst_flash
                signal_burst_flash -= 1
                _sf_alpha = max(0, int((55 if PHOTOSENSITIVE_SAFE_MODE else 140) * (_sf_life / _sf_total)))
                _death_flash_surf.fill((255, 248, 220, _sf_alpha))
                screen.blit(_death_flash_surf, (0, 0))

            if boss_defeat_timer == 0 and boss_warning_timer > 0:
                # Text-only boss warning to avoid fullscreen color wash artifacts.
                wt_alpha = 125 if PHOTOSENSITIVE_SAFE_MODE else int(220 * abs(math.sin(frame_count * 0.10)))
                _warn_text_surf.set_alpha(wt_alpha)
                screen.blit(_warn_text_surf, _warn_text_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))

            if wave_intro_timer > 0 and level_intro_timer == 0:
                if wave_intro_timer > 70:
                    # ── Phase 1: PLAYER 1 GET READY ──────────────────────────
                    _rphase = wave_intro_timer - 70          # 1..50
                    _rfade  = min(255, int(_rphase * 5.1))   # fade-in over first 10f
                    if PHOTOSENSITIVE_SAFE_MODE:
                        _r1 = _ready_title_safe_surf
                    else:
                        _rpulse = int(220 + 35 * abs(math.sin(frame_count * 0.22)))
                        _rcol   = (255, _rpulse, 0)          # pulsing arcade yellow
                        _r1 = font_big.render('PLAYER 1', True, _rcol)
                    _r1.set_alpha(_rfade)
                    screen.blit(_r1, _r1.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 38)))
                    _r2 = _ready_sub_surf
                    _r2.set_alpha(_rfade)
                    screen.blit(_r2, _r2.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 22)))
                else:
                    # ── Phase 2: Wave banner ──────────────────────────────────
                    wi_alpha = min(255, wave_intro_timer * 4)
                    _wi_key = (level, wave)
                    if _banner_cache['wave_intro']['key'] != _wi_key:
                        _banner_cache['wave_intro']['key'] = _wi_key
                        _banner_cache['wave_intro']['title'] = _fit_banner_text(
                            f'LEVEL {level}  WAVE {wave}',
                            (100, 200, 255),
                            WIDTH - 120,
                        )
                        _banner_cache['wave_intro']['mult'] = font_med.render(
                            ['1×', '1.5×', '2×', '2.5×', '3×'][wave - 1] + '  SCORE MULTIPLIER',
                            True,
                            (255, 220, 100),
                        )
                    _wi_title = _banner_cache['wave_intro']['title']
                    _wi_mult = _banner_cache['wave_intro']['mult']
                    _wi_title.set_alpha(wi_alpha)
                    screen.blit(_wi_title, _wi_title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))
                    _wi_mult.set_alpha(wi_alpha)
                    screen.blit(_wi_mult, _wi_mult.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 25)))

            if level_intro_timer > 0:
                _lia = min(255, int(level_intro_timer * 2.4))
                if level == 1:
                    # Show nothing for Level 1 (no intro banner currently)
                    pass
                elif level == 2:
                    _level2_intro_title.set_alpha(_lia)
                    screen.blit(_level2_intro_title, _level2_intro_title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 74)))
                    _level2_intro_sub.set_alpha(_lia)
                    screen.blit(_level2_intro_sub, _level2_intro_sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 26)))
                elif level == 3:
                    _level3_intro_title.set_alpha(_lia)
                    screen.blit(_level3_intro_title, _level3_intro_title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 74)))
                    _level3_intro_sub.set_alpha(_lia)
                    screen.blit(_level3_intro_sub, _level3_intro_sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 26)))
                elif level == 4:
                    _level4_intro_title.set_alpha(_lia)
                    screen.blit(_level4_intro_title, _level4_intro_title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 74)))
                    _level4_intro_sub.set_alpha(_lia)
                    screen.blit(_level4_intro_sub, _level4_intro_sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 26)))
                    _stage = level_intro_timer
                    if _stage > 132:
                        _name_surf, _line_surf = _l4_story_allie_name_surf, _l4_story_allie_line_surf
                        _name_shadow, _line_shadow = _l4_story_allie_name_shadow, _l4_story_allie_line_shadow
                    elif _stage > 70:
                        _name_surf, _line_surf = _l4_story_oracle_name_surf, _l4_story_oracle_line_surf
                        _name_shadow, _line_shadow = _l4_story_oracle_name_shadow, _l4_story_oracle_line_shadow
                    else:
                        _name_surf, _line_surf = _l4_story_bless_name_surf, _l4_story_bless_line_surf
                        _name_shadow, _line_shadow = _l4_story_bless_name_shadow, _l4_story_bless_line_shadow

                    _l4_bubble_surf.fill((0, 0, 0, 0))
                    _br = pygame.Rect(12, 12, 496, 146)
                    pygame.draw.rect(_l4_bubble_surf, (252, 244, 255), _br, border_radius=32)
                    pygame.draw.rect(_l4_bubble_surf, (255, 170, 255), _br, 4, border_radius=32)
                    pygame.draw.rect(_l4_bubble_surf, (241, 229, 252), _br.inflate(-16, -16), border_radius=26)
                    _tail = [(406, 150), (456, 166), (386, 144)]
                    pygame.draw.polygon(_l4_bubble_surf, (252, 244, 255), _tail)
                    pygame.draw.polygon(_l4_bubble_surf, (255, 170, 255), _tail, 4)
                    _l4_bubble_surf.set_alpha(_lia)
                    _brect = _l4_bubble_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 74))
                    screen.blit(_l4_bubble_surf, _brect)

                    _name_surf.set_alpha(_lia)
                    _line_surf.set_alpha(_lia)
                    _name_shadow.set_alpha(_lia)
                    _line_shadow.set_alpha(_lia)
                    _npos = _name_surf.get_rect(center=(_brect.centerx, _brect.top + 46))
                    _lpos = _line_surf.get_rect(center=(_brect.centerx, _brect.top + 94))
                    screen.blit(_name_shadow, _npos.move(2, 2))
                    screen.blit(_name_surf, _npos)
                    screen.blit(_line_shadow, _lpos.move(2, 2))
                    screen.blit(_line_surf, _lpos)

            if wave_transition_timer > 0 and not boss_warned:
                _wta = min(210, wave_transition_timer * 3)
                _wtov_surf.fill((0, 0, 15, _wta))
                screen.blit(_wtov_surf, (0, 0))
                _wca = min(255, wave_transition_timer * 4)
                _wc_key = (level, wave, wave_kills)
                if _banner_cache['wave_complete']['key'] != _wc_key:
                    _banner_cache['wave_complete']['key'] = _wc_key
                    _banner_cache['wave_complete']['title'] = _fit_banner_text(
                        f'LEVEL {level}  WAVE {wave} COMPLETE!',
                        (100, 255, 120),
                        WIDTH - 120,
                    )
                    _banner_cache['wave_complete']['kills'] = font_med.render(
                        f'DRONES  ELIMINATED:   {wave_kills}',
                        True,
                        (255, 220, 100),
                    )
                    _banner_cache['wave_complete']['bonus'] = font_med.render(
                        f'WAVE  BONUS:   +{200 * wave}',
                        True,
                        (0, 200, 255),
                    )
                _wc1 = _banner_cache['wave_complete']['title']
                _wc2 = _banner_cache['wave_complete']['kills']
                _wc3 = _banner_cache['wave_complete']['bonus']
                _wc1.set_alpha(_wca)
                screen.blit(_wc1, _wc1.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 70)))
                _wc2.set_alpha(_wca)
                screen.blit(_wc2, _wc2.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
                _wc3.set_alpha(_wca)
                screen.blit(_wc3, _wc3.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 55)))

            # ── Drone swarm banner ────────────────────────────────────────────
            if swarm_msg_timer > 0 and level_intro_timer == 0:
                swarm_msg_timer -= 1
                _swa = min(255, swarm_msg_timer * 6)
                _swarm_text_surf.set_alpha(_swa)
                screen.blit(_swarm_text_surf, _swarm_text_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 110)))

            if trauma_mode:
                if PHOTOSENSITIVE_SAFE_MODE:
                    _trauma_text_surf.set_alpha(90)
                    screen.blit(_trauma_text_surf, _trauma_text_surf.get_rect(center=(WIDTH // 2, 84)))
                elif frame_count % 180 < 40:
                    _taa = int(255 * (1.0 - abs(20 - (frame_count % 40)) / 20))
                    _trauma_text_surf.set_alpha(_taa)
                    screen.blit(_trauma_text_surf, _trauma_text_surf.get_rect(center=(WIDTH // 2, 84)))

            if boss_defeat_timer > 0:
                boss_defeat_timer -= 1
                vt_alpha = min(255, int(255 * (1.0 - boss_defeat_timer / 90.0) * 3.0))
                if level == 1:
                    _victory_text = 'LEVEL 1 CLEAR!'
                elif level == 2:
                    _victory_text = 'LEVEL 2 CLEAR!'
                elif level == 3:
                    _victory_text = 'LEVEL 3 CLEAR!'
                elif level == 4:
                    _victory_text = 'VICTORY!'
                else:
                    _victory_text = 'VICTORY!'
                if _banner_cache['victory']['key'] != _victory_text:
                    _banner_cache['victory']['key'] = _victory_text
                    _banner_cache['victory']['surf'] = _fit_banner_text(_victory_text, (255, 220, 0), WIDTH - 120)
                vt = _banner_cache['victory']['surf']
                vt.set_alpha(vt_alpha)
                screen.blit(vt, vt.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
                if boss_defeat_timer == 0:
                    if level == 1:
                        _level_two_transition(screen, clock, background_img_level_2)
                        _start_level_two()
                    elif level == 2:
                        _level_three_transition(screen, clock, background_img_level_3)
                        _start_level_three()
                    elif level == 3:
                        pending_level_four_intro = False
                        _level_four_transition(screen, clock, background_img_level_4)
                        _start_level_four()
                    elif level == 4:
                        _oracle_victory_message(
                            screen,
                            clock,
                            background_img_level_4,
                            oracle_allie_img,
                            sprite_idle_image,
                        )
                        game_won = True
                        running  = False
                    else:
                        game_won = True
                        running  = False

            if show_upgrade:
                screen.blit(_uov_surf, (0, 0))
                _ut = font_med.render("CHOOSE YOUR UPGRADE", True, (255, 220, 50))
                screen.blit(_ut, _ut.get_rect(center=(WIDTH // 2, 70)))
                _uh = font.render("Press  1 / 2 / 3  or click a card", True, (180, 180, 180))
                screen.blit(_uh, _uh.get_rect(center=(WIDTH // 2, 110)))
                _ucw, _uch, _ugap = WIDTH - 80, 140, 18
                _usx = (WIDTH - _ucw) // 2
                _ucy = 150
                _umx, _umy = pygame.mouse.get_pos()
                for _ui, _upk in enumerate(upgrade_choices):
                    _ury = _ucy + _ui * (_uch + _ugap)
                    _urc = pygame.Rect(_usx, _ury, _ucw, _uch)
                    _uhov = _urc.collidepoint(_umx, _umy)
                    pygame.draw.rect(screen, (40, 30, 70) if not _uhov else (65, 50, 105), _urc, border_radius=14)
                    pygame.draw.rect(screen, _upk['color'], _urc, 3, border_radius=14)
                    _unum = font_big.render(str(_ui + 1), True, _upk['color'])
                    screen.blit(_unum, _unum.get_rect(midleft=(_usx + 18, _ury + _uch // 2)))
                    _uns = font_med.render(_upk['name'], True, (255, 255, 255))
                    screen.blit(_uns, _uns.get_rect(midleft=(_usx + 72, _ury + 40)))
                    _uds = font.render(_upk['desc'], True, (200, 200, 200))
                    screen.blit(_uds, _uds.get_rect(midleft=(_usx + 72, _ury + 88)))

            # ── Chromatic aberration on player hit ─────────────────────────
            if boss_defeat_timer == 0 and chroma_timer > 0 and (not PHOTOSENSITIVE_SAFE_MODE):
                chroma_timer -= 1
                _ca   = int(45 * chroma_timer / 12)
                _coff = max(1, chroma_timer // 3)
                _chroma_red.fill((255, 0, 0, _ca))
                _chroma_cyan.fill((0, 255, 255, _ca))
                screen.blit(_chroma_red,  (-_coff, 0))
                screen.blit(_chroma_cyan, ( _coff, 0))
            # ── CRT scanlines (always on top) ──────────────────────────────
            screen.blit(scanline_surf, (0, 0))
            pygame.display.flip()
            raw_dt = clock.tick(60)
            if frame_count % 30 == 0:
                pygame.display.set_caption(
                    f"Onyx G vs Space Drones | FPS: {clock.get_fps():.0f}")

        append_replay_event(
            replay_events,
            frame_count,
            'run_end',
            f'score={score};won={int(game_won)};game_over={int(game_over)};continues={continues_used}',
        )
        try:
            save_replay_log(replay_log_path, replay_events)
        except Exception as err:
            print(f"Warning: replay log save failed: {err}")

        # ── Save high score (top 3) ──────────────────────────────────────────────
        _earned_place = None
        for _pi, _ps in enumerate(scores):
            if score > _ps[0]:
                _earned_place = _pi
                break
        if _earned_place is not None:
            _new_name = _name_entry_screen(
                screen, clock, font_big, font_med, font,
                place=_earned_place + 1,
                scores=scores,
                new_score=score,
                leaderboard_label=leaderboard_label,
            )
            scores.insert(_earned_place, [score, _new_name, current_score_timestamp()])
            scores = normalize_scores(scores, cfg.HIGH_SCORE_ENTRIES, cfg.HIGH_SCORE_DEFAULT_NAME)
            high_score      = scores[0][0]
            high_score_name = scores[0][1]
            try:
                save_scores(hs_file, scores)
            except Exception as err:
                print(f"Warning: high score save failed: {err}")

        # ── Result screen ───────────────────────────────────────────────────
        if game_over or game_won:
            result_img = win_img if game_won else lose_img
            if game_won and win_music_file:
                try:
                    pygame.mixer.music.load(win_music_file)
                    pygame.mixer.music.set_volume(0.8)
                    pygame.mixer.music.play()
                except pygame.error:
                    pass
            elif game_over and lose_music_file:
                try:
                    pygame.mixer.music.load(lose_music_file)
                    pygame.mixer.music.set_volume(0.8)
                    pygame.mixer.music.play()
                except pygame.error:
                    pass
            action = _result_screen(
                screen, clock, result_img, music_file, score, scores,
                is_lose=game_over,
                block_signal=block_signal,
                continues_used=continues_used,
                leaderboard_label=leaderboard_label,
            )
            if action == "restart":
                restart = True
            elif action == "menu":
                _start_menu(screen, clock, menu_img, start_menu_music_file,
                            tutorial_img=tutorial_img, tutorial_music_file=tutorial_music_file)
                restart = True
            if restart and music_file:
                try:
                    pygame.mixer.music.load(music_file)
                    pygame.mixer.music.set_volume(0.7)
                    pygame.mixer.music.play(-1)
                    current_bgm_tag = "level1"
                except pygame.error:
                    pass

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        pygame.quit()
        sys.exit(1)
