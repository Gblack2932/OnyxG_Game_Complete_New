"""
Onyx G vs Space Drones — Main Game Loop
A retro-arcade shmup with procedural boss AI, combo scoring, and roguelike progression.

Architecture:
  - constants.py: All game config, difficulty scaling, tuning
  - entities.py: Typed entity classes (Enemy, Bullet, Particle, etc.)
  - onyxg_vs_cranium.py: Asset loading, UI, and main game loop
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
    GameState,
    handle_boss_damage,
    handle_enemy_bullets_vs_player,
    handle_pickups,
    handle_player_bullets_vs_enemies,
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
            _l2c = pygame.font.SysFont("Arial", 72, bold=True).render("LEVEL 2", True, (255, _pulse // 2, _pulse // 2))
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
            for _ri, (_rs, _rn) in enumerate(scores):
                _col = _RANK_COLS[_ri]
                _hl  = (score > 0 and _ri == 0 and score >= _top_score)
                _tc  = (255, 255, 255) if _hl else _col
                if is_lose:
                    _ry  = _lby + 22 + _ri * lose_row_gap
                    _name_max = monitor_safe.width - 170
                    pygame.draw.circle(screen, _col, (_lbx - 120, _ry), 10)
                    pygame.draw.circle(screen, (0, 0, 0), (_lbx - 120, _ry), 6)
                    _row = _sf2.render(f"{_RANK_LBLS[_ri]}  {_rn}  {_rs:,}", True, _tc)
                    screen.blit(_row, _row.get_rect(midleft=(_lbx - 102, _ry - 10)))
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
        _preview.insert(place - 1, [new_score, confirmed_name])
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

            for _ri, (_rs, _rn) in enumerate(_preview):
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


def _normalize_scores(raw_scores: List[List[Any]], entries: int, default_name: str) -> List[List[Any]]:
    """Return a canonical top-score table sorted high-to-low and safely shaped."""
    normalized: List[List[Any]] = []
    for row in raw_scores:
        try:
            _score = max(0, int(row[0]))
        except (TypeError, ValueError, IndexError):
            _score = 0
        try:
            _name = str(row[1]).strip().upper()[:3]
        except (TypeError, ValueError, IndexError):
            _name = ""
        if not _name:
            _name = default_name
        normalized.append([_score, _name])

    normalized.sort(key=lambda s: s[0], reverse=True)
    normalized = normalized[:entries]
    while len(normalized) < entries:
        normalized.append([0, default_name])
    return normalized


def main() -> None:
    """
    Main game loop initialization and execution.
    
    Handles:
    - Asset loading and caching
    - Menu flow (start, tutorial, gameplay, results)
    - Audio initialization
    - Outer restart loop for consecutive runs
    """
    pygame.mixer.pre_init(cfg.AUDIO_INIT_FREQ, cfg.AUDIO_INIT_SIZE, 
                          cfg.AUDIO_INIT_CHANNELS, cfg.AUDIO_INIT_BUFFER)
    pygame.init()
    impact_channel = pygame.mixer.Channel(0)  # dedicated channel — never dropped

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
    # Keep this name for existing rect init and fallback paths.
    sprite_image       = sprite_idle_image
    drone_image    = load_image(dir_map, "drone_spaceship.png",   (40, 40))
    drone_images_level_2 = load_drone_sheet_sprites(dir_map, "Drones Level 2 .png", (44, 44))
    minion_image   = load_image(dir_map, "tibbixel-dot-com-4947-wpng 2.png", (32, 32))
    boss_image_level_1 = load_image(dir_map, "cranium_commander 2.png", (100, 100))
    boss_image_level_2 = load_image(dir_map, "Agent boss Level 2.png", (124, 124))
    water_image   = load_image_tight(dir_map, "gg_water_new .png", (40, 40))
    background_img_level_1 = load_image_cover(dir_map, "space_background.png", (WIDTH, HEIGHT))
    background_img_level_2 = load_image_cover(dir_map, "Level 2 .png", (WIDTH, HEIGHT))
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
    _water_glow_surf   = pygame.Surface((72, 72), pygame.SRCALPHA)
    _boss_tint_surf   = pygame.Surface((100, 100), pygame.SRCALPHA)
    _sprite_glow_surf = pygame.Surface((240, 240), pygame.SRCALPHA)
    # Pre-rendered HUD surfaces (static text — rendered once, blitted every frame)
    _heart_red_h  = font.render("\u2665", True, _COL_RED)
    _heart_grey_h = font.render("\u2665", True, (70, 70, 70))
    _block_lbl_h  = font.render('BLOCK SIGNAL', True, (180, 220, 255))
    _signal_lbl_h = font.render('SIGNAL BURST', True, (190, 120, 255))
    _sativa_lbl_h = font.render('\u2605 BOTTLED WATER', True, (70, 180, 255))
    _shake_surf   = pygame.Surface((WIDTH, HEIGHT))  # no SRCALPHA; plain pixel copy
    # Dirty caches for text that rarely changes
    _score_cache = {'val': -1, 'surf': None}
    _hs_cache    = {'val': '', 'surf': None}
    _wave_cache  = {'val': -1, 'surf': None}
    _perks_cache  = {'val': '', 'surf': None}
    _scale_cache  = {'key': None, 'surf': None}   # sprite transform.scale cache
    _streak_cache = {'key': None, 'surf': None}   # streak message text cache
    _combo_cache  = {'val': None, 'surf': None}    # combo counter text cache
    _block_pct_cache = {'val': None, 'col': None, 'surf': None}
    _signal_pct_cache = {'val': None, 'col': None, 'surf': None}
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
    # Pre-rendered static banner surfaces (text/color never change)
    _brage_surf      = font_big.render('\u2620  RAGE  MODE  \u2620', True, (255, 40, 40))
    _warn_text_surf  = font_big.render('\u26a0  WARNING  \u26a0', True, (255, 50, 50))
    _swarm_text_surf = font_big.render('\u26a1  DRONE SWARM!  \u26a1', True, (255, 150, 0))
    _trauma_text_surf = font_big.render('TRAUMA MODE', True, (255, 90, 90))
    _ready_title_safe_surf = font_big.render('PLAYER 1', True, (255, 210, 0))
    _ready_sub_surf = font_big.render('GET  READY!', True, (255, 255, 255))
    # Pre-built rage vignette surfaces (static geometry, only two variants)
    _rage_vignette_cache = {
        'normal':   build_rage_vignette(WIDTH, HEIGHT, (200, 0, 0), 70),
        'critical': build_rage_vignette(WIDTH, HEIGHT, (255, 60, 0), 105),
    }

    # ── Constants ─────────────────────────────────────────────────────────────
    SPEED                = 5
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

    # ── High score (persistent, top 3) ────────────────────────────────────
    hs_file_legacy = os.path.join(BASE_DIR, cfg.HIGH_SCORE_FILE_LEGACY)
    hs_file_v2 = os.path.join(BASE_DIR, cfg.HIGH_SCORE_FILE_V2)
    _lb_choice = str(getattr(cfg, 'HIGH_SCORE_LADDER', 'v2')).lower()
    if _lb_choice == 'legacy':
        hs_file = hs_file_legacy
        leaderboard_label = 'LEGACY'
    else:
        hs_file = hs_file_v2
        leaderboard_label = 'V2'
    scores = [[0, cfg.HIGH_SCORE_DEFAULT_NAME] for _ in range(cfg.HIGH_SCORE_ENTRIES)]
    try:
        with open(hs_file) as _f:
            _loaded = []
            for _line in _f.read().strip().splitlines()[:cfg.HIGH_SCORE_ENTRIES]:
                _p = _line.strip().split()
                if not _p:
                    continue
                try:
                    _loaded.append([int(_p[0]), _p[1][:3].upper() if len(_p) > 1 else cfg.HIGH_SCORE_DEFAULT_NAME])
                except ValueError:
                    print(f"Warning: skipping malformed high score row: {_line!r}")
            scores = _normalize_scores(_loaded, cfg.HIGH_SCORE_ENTRIES, cfg.HIGH_SCORE_DEFAULT_NAME)
    except Exception as err:
        print(f"Warning: high score load failed: {err}")
        scores = _normalize_scores(scores, cfg.HIGH_SCORE_ENTRIES, cfg.HIGH_SCORE_DEFAULT_NAME)
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

        # Reset all game state each run
        sprite_rect        = sprite_image.get_rect(center=(WIDTH // 2, HEIGHT - 100))
        fireballs          = []
        enemies            = []
        enemy_bullets      = []
        boss_bullets       = []
        enemy_timer        = 0
        fire_timer         = 0
        shoot_pose_timer   = 0
        score              = 0
        health             = 6
        block_signal       = 100
        block_signal_max   = 100
        signal_meter       = 0
        signal_max         = 100
        signal_burst_flash = 0

        current_background_img = background_img_level_1
        boss_image         = boss_image_level_1
        boss_active        = False
        boss_warned        = False
        boss_defeated      = False
        boss_health        = 105
        boss_max_health    = 105
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
        paused             = False
        beat_pulse            = 0
        swarm_active          = False
        swarm_timer           = 0
        swarm_msg_timer       = 0
        next_event_frame      = random.randint(500, 800)
        near_miss_ids         = set()
        chroma_timer          = 0
        boss_death_spiral     = False
        boss_spiral_angle     = 0.0
        trauma_mode           = False
        dive_timer            = random.randint(
            WAVE_DIVE_COOLDOWN_MIN[wave - 1], WAVE_DIVE_COOLDOWN_MAX[wave - 1]
        )   # Galaga dive countdown

        def _wave_idx() -> int:
            return max(0, min(wave, len(WAVE_DEFS)) - 1)

        def _level2_curve_idx() -> int:
            return max(0, min(wave, 5) - 1)

        def _enemy_speed_mult() -> float:
            return LEVEL_2_SPEED_MULT_CURVE[_level2_curve_idx()] if level >= 2 else 1.0

        def _spawn_interval_mult() -> float:
            return LEVEL_2_INTERVAL_MULT_CURVE[_level2_curve_idx()] if level >= 2 else 1.0

        def _bullet_speed_value() -> float:
            return BULLET_SPEED + (LEVEL_2_BULLET_BONUS_CURVE[_level2_curve_idx()] if level >= 2 else 0.0)

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

        def _defeat_boss():
            nonlocal boss_active, boss_defeated, score, boss_defeat_timer
            if boss_defeated:
                return
            boss_active = False
            boss_defeated = True
            score += int(2000 * WAVE_MULT[wave - 1])
            particles.extend(_boss_burst_particles(boss_rect.centerx, boss_rect.centery))
            enemies.clear()
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
            nonlocal current_bgm_tag

            # Hard reset into Level 2 so no Level 1 transient state leaks forward.
            level = 2
            current_background_img = background_img_level_2
            boss_image = boss_image_level_2
            wave = 1
            wave_spawned = 0
            wave_kills = 0
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
            boss_health = 140
            boss_max_health = 140
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

            score_popups.append(ScorePopup(
                x=WIDTH // 2,
                y=HEIGHT // 2 - 70,
                timer=135,
                max=135,
                text='LEVEL 2  TRAUMA MODE',
                color=(255, 90, 90),
            ))

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
            if iframe_timer != 0:
                return
            health -= 1
            shake_timer = 10
            hit_flash_timer = 8
            chroma_timer = 12
            iframe_timer = IFRAME_DURATION
            if impact_sound:
                impact_channel.play(impact_sound)
            if health <= 0:
                game_over = True
                continue_timer = 600

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
            wave_kills += 1
            cx, cy = enemy[0].centerx, enemy[0].centery
            combo += 1
            combo_timer = 120
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
                if continue_timer > 0 and event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN) and continues_used < 2:
                        continues_used += 1
                        health = 3
                        game_over = False
                        continue_timer = 0
                        iframe_timer = 180
                    elif continues_used >= 2:
                        running = False
                        continue_timer = 0
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE \
                        and not show_upgrade and continue_timer == 0:
                    paused = not paused
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_LSHIFT
                        and signal_meter >= signal_max and not show_upgrade
                        and continue_timer == 0 and not paused):
                    enemy_bullets.clear()
                    aimed_bullets.clear()
                    boss_bullets.clear()
                    burst_points = len(enemies) * 100 + len(boss_minions) * 150
                    if boss_active and not boss_defeated:
                        boss_health = max(0, boss_health - 10)
                        if boss_health <= 0:
                            _defeat_boss()
                    enemies.clear()
                    boss_minions.clear()
                    score += burst_points
                    signal_meter = 0
                    signal_burst_flash = 24
                    shake_timer = max(shake_timer, 18)
                    score_popups.append(ScorePopup(
                        x=WIDTH // 2,
                        y=HEIGHT // 2 - 90,
                        timer=90,
                        max=90,
                        text=f'SIGNAL BURST! +{burst_points}',
                        color=(255, 220, 60),
                    ))
                if show_upgrade:
                    _uidx = -1
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_1:   _uidx = 0
                        elif event.key == pygame.K_2: _uidx = 1
                        elif event.key == pygame.K_3: _uidx = 2
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
                        wave += 1
                        wave_spawned = 0
                        wave_kills   = 0
                        sativa_dropped = False
                        wave_intro_timer = 120

            if game_over and continue_timer > 0:
                frame_count += 1
                continue_timer -= 1
                if continues_used < 2:
                    # ── CONTINUE? screen ─────────────────────────────────
                    _cd_secs = max(0, continue_timer // 60)
                    screen.blit(_cont_ov, (0, 0))
                    _ct = font_big.render('CONTINUE?', True, (255, 220, 50))
                    screen.blit(_ct, _ct.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 100)))
                    _cn_col = (255, 60, 60) if _cd_secs <= 3 else (255, 200, 60)
                    _cn = font_huge.render(str(_cd_secs), True, _cn_col)
                    screen.blit(_cn, _cn.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 15)))
                    _rem = 2 - continues_used
                    _crem = font_med.render(
                        f'{_rem}  CONTINUE{"S" if _rem != 1 else ""}  REMAINING',
                        True, (180, 80, 255))
                    screen.blit(_crem, _crem.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 105)))
                    _cpa = int(200 + 55 * abs(math.sin(frame_count * 0.18)))
                    _cp = font_med.render('PRESS  SPACE  TO  CONTINUE', True, (200, 200, 255))
                    _cp.set_alpha(_cpa)
                    screen.blit(_cp, _cp.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 150)))
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
                _spd  = perk_speed + (2 if beat_pulse > BEAT_PULSE_FRAMES - 4 else 0) + (4 if sativa_active else 0)
                _dspd = int(_spd * dt_mul)
                if keys[pygame.K_LEFT]  and sprite_rect.left   > 0:     sprite_rect.x -= _dspd
                if keys[pygame.K_RIGHT] and sprite_rect.right  < WIDTH:  sprite_rect.x += _dspd
                if keys[pygame.K_UP]    and sprite_rect.top    > 0:      sprite_rect.y -= _dspd
                if keys[pygame.K_DOWN]  and sprite_rect.bottom < HEIGHT: sprite_rect.y += _dspd
                sprite_rect.clamp_ip(screen_bounds)
                if any(keys[k] for k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN)):
                    for _ in range(2):
                        particles.append(Particle(
                            x=float(sprite_rect.centerx + random.randint(-6, 6)),
                            y=float(sprite_rect.bottom - 4),
                            vx=random.uniform(-0.4, 0.4),
                            vy=random.uniform(1.5, 3.5),
                            life=random.randint(8, 18),
                            max=18,
                            color=random.choice([(0,150,255),(50,200,255),(100,230,255)]),
                        ))

                fire_timer = max(0, fire_timer - 1)
                side_fire_timer = max(0, side_fire_timer - 1)
                shoot_pose_timer = max(0, shoot_pose_timer - 1)
                # Space = shoot up.
                if keys[pygame.K_SPACE] and len(fireballs) < 20 and fire_timer == 0:
                    shoot_pose_timer = SHOOT_POSE_FRAMES
                    if perk_double_shot or sativa_active:
                        fireballs.append(pygame.Rect(sprite_rect.centerx - 16, sprite_rect.top, 8, 16))
                        fireballs.append(pygame.Rect(sprite_rect.centerx + 8,  sprite_rect.top, 8, 16))
                    else:
                        fireballs.append(pygame.Rect(sprite_rect.centerx - 4, sprite_rect.top, 8, 16))
                    fire_timer = perk_fire_cooldown
                    if shoot_sound:
                        shoot_sound.play()
                # Command = shoot sideways
                _cmd = keys[pygame.K_LMETA] or keys[pygame.K_RMETA]
                if _cmd and side_fire_timer == 0:
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
                    side_fire_timer = perk_fire_cooldown
                    if shoot_sound:
                        shoot_sound.play()

            for f in fireballs:
                f.y -= int(FIREBALL_SPEED * dt_mul)
            fireballs = [f for f in fireballs if f.y > -20]
            for sb in side_bullets:
                sb['x'] += sb['vx'] * dt_mul
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
            elif (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade
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
                        enemies.append(Enemy(
                            rect=pygame.Rect(random.randint(0, WIDTH - 40), 0, 40, 40),
                            angle=random.uniform(0, 2 * math.pi),
                        ))
                        enemy_timer = 0
                        wave_spawned += 1

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
                    e[0].y += int(WAVE_ENEMY_SPEED[_wave_i] * _enemy_speed_mult() * dt_mul)
                    _track_dx = sprite_rect.centerx - e[0].centerx
                    _track_step = max(-WAVE_TRACK_CAP[_wave_i],
                                      min(WAVE_TRACK_CAP[_wave_i], _track_dx * WAVE_TRACK_GAIN[_wave_i] * _enemy_speed_mult()))
                    e[0].x = max(0, min(WIDTH - 40,
                        e[0].x + int((math.sin(frame_count * 0.04 + e[1]) * 1.2 + _track_step) * dt_mul)))
                    _shoot_prob = WAVE_SHOOT_PROB[_wave_i] * (1.18 if trauma_mode else 1.0)
                    if random.random() < _shoot_prob:
                        _bspd = _bullet_speed_value()
                        if random.random() < WAVE_AIMED_SHOT_RATIO[_wave_i]:
                            dx = sprite_rect.centerx - e[0].centerx
                            dy = sprite_rect.centery - e[0].centery
                            dist = math.hypot(dx, dy) or 1
                            aimed_bullets.append({'x': float(e[0].centerx), 'y': float(e[0].bottom),
                                                  'vx': dx / dist * _bspd,
                                                  'vy': dy / dist * _bspd})
                        else:
                            enemy_bullets.append(pygame.Rect(e[0].centerx - 4, e[0].bottom, 8, 12))
            _escaped_count = 0
            _next_enemies = []
            for e in enemies:
                if e[0].top >= HEIGHT:
                    _escaped_count += 1
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
                        score += 50
                        signal_meter = min(signal_max, signal_meter + 5)
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
                        score += 50
                        signal_meter = min(signal_max, signal_meter + 5)
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

            # ── Draw player: idle pose or upward shooting pose ───────────────────────────
            current_sprite_image = sprite_shoot_image if shoot_pose_timer > 0 else sprite_idle_image
            current_pose_key = "shoot" if shoot_pose_timer > 0 else "idle"

            if iframe_timer == 0 or iframe_timer % 8 < 4:
                if beat_pulse > 0 or sativa_active:
                    _bp_t    = beat_pulse / BEAT_PULSE_FRAMES if beat_pulse > 0 else 1.0
                    _scale_m = 0.45 if sativa_active else 0.18
                    _bp_s    = 1.0 + _scale_m * _bp_t
                    # Cache scaled sprite by BOTH pose and size.
                    _bp_key  = (current_pose_key, round(_bp_s * 50) / 50)
                    _bp_w    = int(sprite_rect.width  * _bp_key[1])
                    _bp_h    = int(sprite_rect.height * _bp_key[1])
                    if _scale_cache['key'] != _bp_key:
                        _scale_cache['key']  = _bp_key
                        _scale_cache['surf'] = pygame.transform.scale(current_sprite_image, (_bp_w, _bp_h))
                    _bp_img  = _scale_cache['surf']
                    _bp_r    = _bp_img.get_rect(center=sprite_rect.center)
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
                    screen.blit(current_sprite_image, sprite_rect)

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
                if _fb_col != _COL_FIREBALL:
                    _fb_glow_surf.fill((*_fb_col, 80))
                    screen.blit(_fb_glow_surf, (f.x - 4, f.y - 4))
                pygame.draw.rect(screen, _fb_col, f)
            for sb in side_bullets:
                _sbc = (0, 220, 255) if not sativa_active else (0, 255, 180)
                pygame.draw.rect(screen, _sbc, (int(sb['x']) - 8, int(sb['y']) - 4, 16, 8))
            for e in enemies:
                _dimg = drone_images_level_2[id(e) % 3] if level >= 2 else drone_image
                screen.blit(_dimg, e[0])
                if e[2] and (not PHOTOSENSITIVE_SAFE_MODE) and frame_count % 8 < 4:
                    screen.blit(_kflash_surf, e[0])
                elif e[3] is not None and (not PHOTOSENSITIVE_SAFE_MODE) and frame_count % 6 < 3:
                    screen.blit(_dflash_surf, e[0])
            for bm in boss_minions:
                screen.blit(minion_image or drone_image, bm['rect'])
            next_particles = []
            for p in particles:
                p['x'] += p['vx']
                p['y'] += p['vy']
                p['life'] -= 1
                if p['life'] > 0:
                    sz = max(1, int(5 * p['life'] / p['max']))
                    pygame.draw.rect(screen, p['color'],
                                     (int(p['x']), int(p['y']), sz, sz))
                    next_particles.append(p)
            # Hard caps prevent worst-case frame spikes during dense boss phases.
            particles = next_particles[-MAX_PARTICLES:]
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

            next_popups = []
            for pop in score_popups:
                pop['timer'] -= 1
                pop['y']     -= 1
                if pop['timer'] > 0:
                    if pop['surf'] is None:
                        pop['surf'] = font_popup.render(pop['text'], True, pop['color'])
                    alpha = int(255 * pop['timer'] / pop['max'])
                    pop['surf'].set_alpha(alpha)
                    screen.blit(pop['surf'], pop['surf'].get_rect(centerx=int(pop['x']), y=int(pop['y'])))
                    next_popups.append(pop)
            score_popups = next_popups

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
                # Full-screen copy is expensive; skip it in safe mode and halve update rate otherwise.
                if not PHOTOSENSITIVE_SAFE_MODE and frame_count % 2 == 0:
                    ox = random.randint(-4, 4)
                    oy = random.randint(-4, 4)
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

            if boss_defeat_timer == 0 and signal_burst_flash > 0:
                # Accessibility/safety: suppress fullscreen signal-burst flash.
                signal_burst_flash -= 1

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
                _level2_intro_title.set_alpha(_lia)
                screen.blit(_level2_intro_title, _level2_intro_title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 74)))
                _level2_intro_sub.set_alpha(_lia)
                screen.blit(_level2_intro_sub, _level2_intro_sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 26)))

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
                _victory_text = 'VICTORY!' if level >= 2 else 'LEVEL 1 CLEAR!'
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
            scores.insert(_earned_place, [score, _new_name])
            scores = _normalize_scores(scores, cfg.HIGH_SCORE_ENTRIES, cfg.HIGH_SCORE_DEFAULT_NAME)
            high_score      = scores[0][0]
            high_score_name = scores[0][1]
            try:
                with open(hs_file, 'w') as _f:
                    _f.write('\n'.join(f'{s[0]} {s[1]}' for s in scores))
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
