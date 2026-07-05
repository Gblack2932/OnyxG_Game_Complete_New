from __future__ import annotations

import array
import math
import random

import pygame


def make_impact_sound() -> pygame.mixer.Sound:
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


def make_siren_sound() -> pygame.mixer.Sound:
    """Generate a procedural siren/alarm sound."""
    sr, dur = 44100, 0.5
    n = int(sr * dur)
    f0, f1 = 440, 1100
    samples = [
        max(-32768, min(32767, int(
            math.sin(2 * math.pi * (f0 * (i / sr) + (f1 - f0) * (i / sr) ** 2 / (2 * dur))) * 26000
        )))
        for i in range(n)
    ]
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.65)
    return snd


def make_powerup_sound() -> pygame.mixer.Sound:
    """Generate a procedural power-up/success sound."""
    sr, dur = 44100, 0.25
    n = int(sr * dur)
    f0, f1 = 350, 950
    fade = max(1, int(sr * 0.04))
    samples = [
        max(-32768, min(32767, int(
            math.sin(2 * math.pi * (f0 * (i / sr) + (f1 - f0) * (i / sr) ** 2 / (2 * dur)))
            * (min(i, n - i, fade) / fade) * 22000
        )))
        for i in range(n)
    ]
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.55)
    return snd
