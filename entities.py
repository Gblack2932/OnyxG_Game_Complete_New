"""
Onyx G vs Space Drones — Game Entity Classes
Defines all game entities (enemies, bullets, particles, etc.) with type safety.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Optional, List, Dict, Any
import pygame
import math


@dataclass
class Enemy:
    """Represents a standard enemy drone."""
    rect: pygame.Rect
    angle: float  # Movement phase angle for sinusoidal tracking
    is_kamikaze: bool = False
    dive_state: Optional[Dict[str, Any]] = None

    # Backward-compatible index access while main loop is being refactored.
    def __getitem__(self, idx: int):
        if idx == 0:
            return self.rect
        if idx == 1:
            return self.angle
        if idx == 2:
            return self.is_kamikaze
        if idx == 3:
            return self.dive_state
        raise IndexError(idx)

    def __setitem__(self, idx: int, value) -> None:
        if idx == 0:
            self.rect = value
            return
        if idx == 1:
            self.angle = value
            return
        if idx == 2:
            self.is_kamikaze = value
            return
        if idx == 3:
            self.dive_state = value
            return
        raise IndexError(idx)

    def update(self, dt_mul: float, wave: int, frame_count: int, 
               sprite_center: Tuple[int, int], width: int, height: int,
               wave_enemy_speed: List[int], wave_track_gain: List[float],
               wave_track_cap: List[float]) -> None:
        """Update enemy position based on wave difficulty and player tracking."""
        from constants import WAVE_SHOOT_PROB
        
        if self.dive_state is not None:
            # Handle Galaga-style dive attack
            self._update_dive(dt_mul)
        elif self.is_kamikaze:
            # Chase player directly
            self._chase_player(dt_mul, sprite_center, wave, wave_enemy_speed)
        else:
            # Normal wave movement with sinusoidal tracking
            self._normal_movement(dt_mul, wave, frame_count, sprite_center, 
                                width, wave_enemy_speed, wave_track_gain, wave_track_cap)

    def _update_dive(self, dt_mul: float) -> None:
        """Execute quadratic Bezier curve dive trajectory."""
        d = self.dive_state
        d['t'] = min(1.0, d['t'] + 0.011)
        t = d['t']
        mt = 1.0 - t
        
        # Quadratic Bezier: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
        self.rect.centerx = int(mt*mt*d['p0'][0] + 2*mt*t*d['p1'][0] + t*t*d['p2'][0])
        self.rect.centery = int(mt*mt*d['p0'][1] + 2*mt*t*d['p1'][1] + t*t*d['p2'][1])

    def _chase_player(self, dt_mul: float, sprite_center: Tuple[int, int], 
                     wave: int, wave_enemy_speed: List[int]) -> None:
        """Direct pursuit toward player (kamikaze mode)."""
        dx = sprite_center[0] - self.rect.centerx
        dy = sprite_center[1] - self.rect.centery
        dist = math.hypot(dx, dy) or 1
        
        chase_speed = wave_enemy_speed[wave - 1] + (3 if wave < 4 else 4)
        self.rect.x += int(dx / dist * chase_speed * dt_mul)
        self.rect.y += int(dy / dist * chase_speed * dt_mul)

    def _normal_movement(self, dt_mul: float, wave: int, frame_count: int,
                        sprite_center: Tuple[int, int], width: int,
                        wave_enemy_speed: List[int], wave_track_gain: List[float],
                        wave_track_cap: List[float]) -> None:
        """Standard wave movement with player tracking."""
        # Vertical descent
        self.rect.y += int(wave_enemy_speed[wave - 1] * dt_mul)
        
        # Horizontal tracking toward player
        track_dx = sprite_center[0] - self.rect.centerx
        track_step = max(-wave_track_cap[wave - 1],
                        min(wave_track_cap[wave - 1], track_dx * wave_track_gain[wave - 1]))
        
        sine_wave = math.sin(frame_count * 0.04 + self.angle) * 1.2
        new_x = self.rect.x + int((sine_wave + track_step) * dt_mul)
        self.rect.x = max(0, min(width - self.rect.width, new_x))

    def is_off_screen(self, height: int) -> bool:
        """Check if enemy has left the play area."""
        return self.rect.top >= height or self.rect.bottom <= -60


@dataclass
class BossMinionEnemy:
    """Represents a minion spawned by the boss."""
    rect: pygame.Rect
    phase: float  # Sinusoidal movement phase
    fire_timer: int = 0

    def __getitem__(self, key: str):
        if key == 'rect':
            return self.rect
        if key == 'phase':
            return self.phase
        if key == 'fire_timer':
            return self.fire_timer
        raise KeyError(key)

    def __setitem__(self, key: str, value) -> None:
        if key == 'rect':
            self.rect = value
            return
        if key == 'phase':
            self.phase = value
            return
        if key == 'fire_timer':
            self.fire_timer = value
            return
        raise KeyError(key)

    def update(self, dt_mul: float, frame_count: int, width: int) -> None:
        """Update minion position and rotation."""
        self.rect.y += int(3 * dt_mul)
        self.rect.x = max(0, min(width - self.rect.width,
            self.rect.x + int(math.sin(frame_count * 0.05 + self.phase) * 2 * dt_mul)))
        self.fire_timer += 1

    def is_off_screen(self, height: int) -> bool:
        """Check if minion has left the play area."""
        return self.rect.top >= height


@dataclass
class Bullet:
    """Represents a player fireball projectile."""
    rect: pygame.Rect

    def update(self, dt_mul: float, fireball_speed: int) -> None:
        """Update bullet position upward."""
        self.rect.y -= int(fireball_speed * dt_mul)

    def is_off_screen(self) -> bool:
        """Check if bullet left play area."""
        return self.rect.y <= -20


@dataclass
class SideBullet:
    """Represents a side-firing bullet (command key)."""
    x: float
    y: float
    vx: float
    vy: float

    def update(self, dt_mul: float) -> None:
        """Update bullet position."""
        self.x += self.vx * dt_mul
        self.y += self.vy * dt_mul

    def is_off_screen(self, width: int) -> bool:
        """Check if bullet left play area."""
        return not (0 < self.x < width)

    def get_rect(self) -> pygame.Rect:
        """Get hitbox for collision detection."""
        return pygame.Rect(int(self.x) - 8, int(self.y) - 4, 16, 8)


@dataclass
class AimedBullet:
    """Represents an enemy or boss aimed (homing) bullet."""
    x: float
    y: float
    vx: float
    vy: float

    def update(self, dt_mul: float) -> None:
        """Update bullet position."""
        self.x += self.vx * dt_mul
        self.y += self.vy * dt_mul

    def is_off_screen(self, width: int, height: int) -> bool:
        """Check if bullet left play area."""
        return not (0 < self.y < height and 0 < self.x < width)

    def get_rect(self) -> pygame.Rect:
        """Get hitbox for collision detection."""
        return pygame.Rect(int(self.x) - 4, int(self.y) - 6, 8, 12)


@dataclass
class BossBullet:
    """Represents a boss straight-line bullet."""
    rect: pygame.Rect

    def update(self, dt_mul: float, bullet_speed: int) -> None:
        """Update bullet position downward."""
        self.rect.y += int(bullet_speed * dt_mul)

    def is_off_screen(self, height: int) -> bool:
        """Check if bullet left play area."""
        return self.rect.y >= height


@dataclass
class Particle:
    """Represents a visual particle effect (no collision)."""
    x: float
    y: float
    vx: float
    vy: float
    life: int
    max: int
    color: Tuple[int, int, int]

    def update(self, dt_mul: float = 1.0) -> None:
        """Update particle position and age."""
        self.x += self.vx * dt_mul
        self.y += self.vy * dt_mul
        self.life -= 1

    def is_alive(self) -> bool:
        """Check if particle still has remaining life."""
        return self.life > 0

    def get_alpha(self) -> int:
        """Calculate alpha (fade) value based on remaining life."""
        return int(255 * self.life / self.max)

    def __getitem__(self, key: str):
        if key == 'x':
            return self.x
        if key == 'y':
            return self.y
        if key == 'vx':
            return self.vx
        if key == 'vy':
            return self.vy
        if key == 'life':
            return self.life
        if key == 'max':
            return self.max
        if key == 'color':
            return self.color
        raise KeyError(key)

    def __setitem__(self, key: str, value) -> None:
        if key == 'x':
            self.x = value
            return
        if key == 'y':
            self.y = value
            return
        if key == 'vx':
            self.vx = value
            return
        if key == 'vy':
            self.vy = value
            return
        if key == 'life':
            self.life = value
            return
        if key == 'max':
            self.max = value
            return
        if key == 'color':
            self.color = value
            return
        raise KeyError(key)


@dataclass
class ScorePopup:
    """Represents a floating score/text popup."""
    x: float
    y: float
    text: str
    color: Tuple[int, int, int]
    timer: int
    max: int
    surf: Optional[pygame.Surface] = None

    def update(self) -> None:
        """Update popup age and position."""
        self.timer -= 1
        self.y -= 1

    def is_alive(self) -> bool:
        """Check if popup still visible."""
        return self.timer > 0

    def get_alpha(self) -> int:
        """Calculate alpha (fade) value based on remaining life."""
        return int(255 * self.timer / self.max)

    def __getitem__(self, key: str):
        if key == 'x':
            return self.x
        if key == 'y':
            return self.y
        if key == 'text':
            return self.text
        if key == 'color':
            return self.color
        if key == 'timer':
            return self.timer
        if key == 'max':
            return self.max
        if key == 'surf':
            return self.surf
        raise KeyError(key)

    def __setitem__(self, key: str, value) -> None:
        if key == 'x':
            self.x = value
            return
        if key == 'y':
            self.y = value
            return
        if key == 'text':
            self.text = value
            return
        if key == 'color':
            self.color = value
            return
        if key == 'timer':
            self.timer = value
            return
        if key == 'max':
            self.max = value
            return
        if key == 'surf':
            self.surf = value
            return
        raise KeyError(key)


@dataclass
class HealthPickup:
    """Represents a health recovery power-up."""
    rect: pygame.Rect

    def update(self, dt_mul: float) -> None:
        """Update pickup position (falling)."""
        self.rect.y += int(dt_mul)

    def is_off_screen(self, height: int) -> bool:
        """Check if pickup left play area."""
        return self.rect.top >= height


@dataclass
class SativaPickup:
    """Represents a sativa (power mode) power-up."""
    rect: pygame.Rect

    def update(self, dt_mul: float) -> None:
        """Update pickup position (falling faster)."""
        self.rect.y += int(2 * dt_mul)

    def is_off_screen(self, height: int) -> bool:
        """Check if pickup left play area."""
        return self.rect.top >= height


@dataclass
class DataSoul:
    """Represents a data soul collectible (no function, visual only)."""
    rect: pygame.Rect

    def update(self, dt_mul: float) -> None:
        """Update soul position (falling slowly)."""
        self.rect.y += int(1.5 * dt_mul)

    def is_off_screen(self, height: int) -> bool:
        """Check if soul left play area."""
        return self.rect.top >= height


@dataclass
class Boss:
    """Represents the boss enemy."""
    rect: pygame.Rect
    health: int
    max_health: int
    fire_timer: int = 0
    fire_interval: int = 52
    minion_timer: int = 0
    minion_interval: int = 120
    direction: int = 1  # 1 = right, -1 = left
    is_raging: bool = False
    is_critical: bool = False
    is_death_spiral: bool = False
    spiral_angle: float = 0.0
    volley_count: int = 0

    @property
    def health_ratio(self) -> float:
        """Get health as a ratio (0.0 to 1.0)."""
        return max(0.0, self.health / self.max_health)

    def take_damage(self, amount: int) -> None:
        """Reduce boss health."""
        self.health = max(0, self.health - amount)

    def is_defeated(self) -> bool:
        """Check if boss is dead."""
        return self.health <= 0

    def update_phase(self) -> None:
        """Update boss phase based on health thresholds."""
        from constants import BOSS_RAGING_THRESHOLD, BOSS_CRITICAL_THRESHOLD, BOSS_DEATH_SPIRAL_THRESHOLD
        
        if not self.is_raging and self.health <= self.max_health * BOSS_RAGING_THRESHOLD:
            self.is_raging = True
        
        if not self.is_critical and self.health <= self.max_health * BOSS_CRITICAL_THRESHOLD:
            self.is_critical = True
        
        if not self.is_death_spiral and self.health <= BOSS_DEATH_SPIRAL_THRESHOLD:
            self.is_death_spiral = True
