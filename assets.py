from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import pygame


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def build_dir_map(base_dir: str = BASE_DIR) -> Dict[str, str]:
    """Build case-insensitive directory map for cross-platform asset loading."""
    return {e.lower(): e for e in os.listdir(base_dir)}


def load_image(dir_map: Dict[str, str], filename: str, size: Tuple[int, int], base_dir: str = BASE_DIR) -> pygame.Surface:
    entry = dir_map.get(filename.lower())
    if entry:
        try:
            img = pygame.image.load(os.path.join(base_dir, entry)).convert_alpha()
            return pygame.transform.scale(img, size)
        except pygame.error as err:
            print(f"⚠️ Failed to load {filename}: {err}")
    print(f"⚠️ Missing asset: {filename}. Using placeholder.")
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((255, 0, 255, 255))
    return surf


def find_file(dir_map: Dict[str, str], filename: str, base_dir: str = BASE_DIR) -> Optional[str]:
    """Locate a file in base_dir using case-insensitive lookup."""
    entry = dir_map.get(filename.lower())
    return os.path.join(base_dir, entry) if entry else None
