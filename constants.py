"""
Onyx G vs Space Drones — Game Constants & Configuration
Centralized configuration for tuning difficulty, balance, and visual settings.
"""

from typing import List, Dict, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# DISPLAY & RENDERING
# ──────────────────────────────────────────────────────────────────────────────
WIDTH: int = 675
HEIGHT: int = 900
TARGET_FPS: int = 60

# Color Constants (RGB tuples)
COL_FIREBALL: Tuple[int, int, int] = (255, 100, 0)
COL_EBULLET: Tuple[int, int, int] = (255, 0, 255)
COL_BBULLET: Tuple[int, int, int] = (255, 255, 0)
COL_BAR_BG: Tuple[int, int, int] = (255, 0, 0)
COL_BAR_FG: Tuple[int, int, int] = (0, 255, 0)
COL_WHITE: Tuple[int, int, int] = (255, 255, 255)
COL_RED: Tuple[int, int, int] = (255, 50, 50)
COL_PICKUP: Tuple[int, int, int] = (0, 255, 80)

# ──────────────────────────────────────────────────────────────────────────────
# PLAYER MECHANICS
# ──────────────────────────────────────────────────────────────────────────────
PLAYER_SPEED: int = 5
PLAYER_START_X: int = WIDTH // 2
PLAYER_START_Y: int = HEIGHT - 100
PLAYER_SIZE: Tuple[int, int] = (80, 160)
PLAYER_MAX_HEALTH: int = 6

# Firepower
FIREBALL_SPEED: int = 10
FIRE_COOLDOWN: int = 7  # frames between shots
SHOOT_POSE_FRAMES: int = 8
FIREBALL_CAP: int = 20

# Movement
BG_SCROLL_SPEED: int = 2
IFRAME_DURATION: int = 90  # invulnerability frames after hit
BEAT_FRAMES: int = 34  # ~106 BPM @ 60 fps
BEAT_PULSE_FRAMES: int = 8

# ──────────────────────────────────────────────────────────────────────────────
# ENEMY MECHANICS
# ──────────────────────────────────────────────────────────────────────────────
ENEMY_SPAWN_INTERVAL: int = 60
BULLET_SPEED: int = 6
SHOOT_PROBABILITY: float = 0.01
PICKUP_DROP_CHANCE: float = 0.09

# Wave-Dependent Difficulty Scaling
WAVE_DEFS: List[Dict[str, int]] = [
    {'count': 15, 'interval': 46},   # Wave 1: still warmup, but more lively pacing
    {'count': 19, 'interval': 46},   # Wave 2: slightly faster spawns
    {'count': 28, 'interval': 34},   # Wave 3: first real pressure
    {'count': 40, 'interval': 24},   # Wave 4: sustained aggression
    {'count': 56, 'interval': 16},   # Wave 5: pre-boss survival gauntlet
]

WAVE_MULT: List[float] = [1.0, 1.4, 1.8, 2.3, 3.0]
WAVE_ENEMY_SPEED: List[int] = [2, 3, 4, 5, 6]
WAVE_SHOOT_PROB: List[float] = [0.0046, 0.0056, 0.0084, 0.0106, 0.0132]
WAVE_TRACK_GAIN: List[float] = [0.006, 0.010, 0.030, 0.050, 0.070]
WAVE_TRACK_CAP: List[float] = [0.8, 1.0, 2.5, 3.8, 5.0]
WAVE_AIMED_SHOT_RATIO: List[float] = [0.08, 0.14, 0.28, 0.38, 0.50]

# Enemy Drone Behaviors
KAMIKAZE_THRESHOLD_Y: int = 120  # y-position to trigger kamikaze
WAVE_KAMIKAZE_CHANCE: List[float] = [0.0015, 0.0022, 0.0032, 0.0054, 0.0070]
WAVE_DIVE_COOLDOWN_MIN: List[int] = [280, 240, 200, 150, 120]
WAVE_DIVE_COOLDOWN_MAX: List[int] = [420, 340, 280, 210, 170]
WAVE_DIVE_BATCH: List[int] = [1, 1, 2, 3, 4]
DIVE_TRIGGER_Y: int = 60

# ──────────────────────────────────────────────────────────────────────────────
# BOSS MECHANICS
# ──────────────────────────────────────────────────────────────────────────────
BOSS_SIZE: Tuple[int, int] = (100, 100)
BOSS_MAX_HEALTH: int = 105

# Boss Phase Thresholds (% health remaining)
BOSS_RAGING_THRESHOLD: float = 0.5
BOSS_CRITICAL_THRESHOLD: float = 0.25
BOSS_DEATH_SPIRAL_THRESHOLD: int = 5

# Boss Fire Intervals (frames between attacks, lower = more frequent)
BOSS_FIRE_INTERVAL_NORMAL: int = 52
BOSS_FIRE_INTERVAL_RAGING: int = 28
BOSS_FIRE_INTERVAL_CRITICAL: int = 20
BOSS_FIRE_INTERVAL_DEATH: int = 12

# Boss Movement & Behavior
BOSS_SPEED_NORMAL: int = 4
BOSS_SPEED_RAGING: int = 7
BOSS_SPEED_CRITICAL: int = 10
BOSS_WARNING_TIMER: int = 90
BOSS_MINION_INTERVAL_NORMAL: int = 120
BOSS_MINION_INTERVAL_RAGING: int = 70
BOSS_MINION_INTERVAL_CRITICAL: int = 54
BOSS_MINION_CAP_NORMAL: int = 3
BOSS_MINION_CAP_RAGING: int = 5

# Boss Attacks
BOSS_BULLET_SPREAD_WIDTH: int = 28  # pixels between bullets in spread
BOSS_VOLLEY_COUNT_FAN: int = 5  # bullets in fan pattern
BOSS_VOLLEY_MULTIPLIER_CRITICAL: float = 1.3
BOSS_VOLLEY_MULTIPLIER_DEATH: float = 1.5

# ──────────────────────────────────────────────────────────────────────────────
# GAME STATE MECHANICS
# ──────────────────────────────────────────────────────────────────────────────
BLOCK_SIGNAL_MAX: int = 100
SIGNAL_METER_MAX: int = 100
SIGNAL_BURST_CLEAR_RADIUS: int = 0  # affects all enemies
SIGNAL_BURST_BOSS_DAMAGE: int = 10
SIGNAL_BURST_POINTS: int = 100  # per enemy cleared

# Combo & Streak System
COMBO_TIMEOUT_FRAMES: int = 120
COMBO_TEXT_COLOR: Tuple[int, int, int] = (255, 80, 255)
COMBO_ALPHA_RAMP: float = 4.0

STREAK_TIMEOUT_FRAMES: int = 90
STREAK_2X_TEXT: str = "DOUBLE KILL!"
STREAK_3X_TEXT: str = "TRIPLE KILL!"
STREAK_4X_TEXT: str = "QUAD KILL!"
STREAK_5X_TEXT: str = "RAMPAGE!"

# Scoring
SCORE_BASE_DRONE: int = 100
SCORE_BASE_BOSS_DRONE: int = 200
SCORE_MINION: int = 150
SCORE_NEAR_MISS: int = 50
SCORE_CONTINUE_PENALTY: int = 1500

# ──────────────────────────────────────────────────────────────────────────────
# VISUAL EFFECTS & TIMING
# ──────────────────────────────────────────────────────────────────────────────
SHAKE_TIMER_DEFAULT: int = 10
SHAKE_TIMER_HIT_FLASH: int = 8
SHAKE_TIMER_BOSS_HIT: int = 6
SHAKE_TIMER_BOSS_RAGE: int = 20
SHAKE_TIMER_BURST: int = 18
SHAKE_TIMER_CRITICAL: int = 30
SHAKE_TIMER_DEATH_SPIRAL: int = 35

HIT_FLASH_CHROMA_TIMER: int = 12
BOSS_RAGE_FLASH_TIMER: int = 150
SIGNAL_BURST_FLASH_TIMER: int = 24

# Continue & Game Over Screens
CONTINUE_SCREEN_DURATION: int = 600  # 10 seconds @ 60 fps
CONTINUE_MAX_USES: int = 2
GAME_OVER_SCREEN_DURATION: int = 90

# Wave Transitions
WAVE_INTRO_TIMER: int = 120
WAVE_TRANSITION_TIMER: int = 120

# Swarm Event (random drone wave)
SWARM_TIMER: int = 240
SWARM_MSG_TIMER: int = 90
SWARM_SPAWN_MIN_DELAY: int = 400
SWARM_SPAWN_MAX_DELAY: int = 700
SWARM_SPAWN_INTERVAL_REDUCTION: float = 0.65

# ──────────────────────────────────────────────────────────────────────────────
# POWER-UP & PERK SYSTEM
# ──────────────────────────────────────────────────────────────────────────────
SATIVA_DURATION: int = 600  # frames (10 sec @ 60fps)
SATIVA_SPEED_BOOST: int = 4
SATIVA_FIREBALL_SPEED_BOOST: int = 2
SATIVA_DAMAGE_MITIGATION: float = 0.5  # takes half damage
HEALTH_PICKUP_DROP_CHANCE: float = 0.09
HEALTH_PICKUP_LEGENDARY_DROP_CHANCE: float = 0.144  # with lucky_drop perk (1.6x)

# Perk Definitions
PERKS: List[Dict[str, any]] = [
    {
        'id': 'rapid_fire',
        'name': 'RAPID FIRE',
        'desc': 'Fire rate +20%',
        'color': (255, 200, 50),
        'max_stacks': 3,
        'fire_cooldown_reduction': 1,
    },
    {
        'id': 'speed_boost',
        'name': 'SPEED BOOST',
        'desc': 'Movement speed +1',
        'color': (50, 220, 255),
        'max_stacks': 3,
        'speed_increase': 1,
    },
    {
        'id': 'extra_heart',
        'name': 'EXTRA HEARTS',
        'desc': 'Gain +1 HP',
        'color': (255, 80, 80),
        'max_stacks': 2,
        'health_increase': 1,
    },
    {
        'id': 'double_shot',
        'name': 'DOUBLE SHOT',
        'desc': 'Fire twin bullets',
        'color': (200, 100, 255),
        'max_stacks': 1,
    },
    {
        'id': 'power_shot',
        'name': 'POWER SHOT',
        'desc': 'Boss takes 2x damage',
        'color': (255, 150, 50),
        'max_stacks': 1,
    },
    {
        'id': 'lucky_drop',
        'name': 'LUCKY DROP',
        'desc': '1.6x pickup drop rate',
        'color': (100, 255, 100),
        'max_stacks': 1,
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# RANK SYSTEM
# ──────────────────────────────────────────────────────────────────────────────
RANK_SCORE_S: int = 12000
RANK_SCORE_A: int = 9000
RANK_SCORE_B: int = 6500
RANK_SCORE_C: int = 3500

RANK_TITLES: Dict[str, str] = {
    'S': 'GHETTO GEEK GOD',
    'A': 'ELITE HACKER',
    'B': 'BLOCK DEFENDER',
    'C': 'STREET SURVIVOR',
    'D': 'LOST SIGNAL',
}

# Rank Calculation
RANK_SIGNAL_MULTIPLIER: int = 20
RANK_CONTINUE_PENALTY: int = 1500

# ──────────────────────────────────────────────────────────────────────────────
# AUDIO SETTINGS
# ──────────────────────────────────────────────────────────────────────────────
AUDIO_INIT_FREQ: int = 44100
AUDIO_INIT_SIZE: int = -16
AUDIO_INIT_CHANNELS: int = 2
AUDIO_INIT_BUFFER: int = 512

VOLUME_MUSIC: float = 0.7
VOLUME_SHOOT_SOUND: float = 0.5
VOLUME_IMPACT_SOUND: float = 0.8
VOLUME_SATIVA_SOUND: float = 0.85

# ──────────────────────────────────────────────────────────────────────────────
# PHYSICS & DELTA-TIME
# ──────────────────────────────────────────────────────────────────────────────
DT_MUL_MIN: float = 1.0
DT_MUL_MAX: float = 3.0
DT_SEED_FRAME: int = 16  # milliseconds for first frame

# ──────────────────────────────────────────────────────────────────────────────
# COLLISION & HITBOX TUNING
# ──────────────────────────────────────────────────────────────────────────────
NEAR_MISS_RADIUS: int = 38  # pixels from player center
ENEMY_HITBOX_SIZE: Tuple[int, int] = (40, 40)
MINION_HITBOX_SIZE: Tuple[int, int] = (32, 32)
FIREBALL_SIZE: Tuple[int, int] = (8, 16)
SIDE_BULLET_SIZE: Tuple[int, int] = (16, 8)
BOSS_BULLET_SIZE: Tuple[int, int] = (10, 16)
AIMED_BULLET_HITBOX: Tuple[int, int] = (8, 12)

# ──────────────────────────────────────────────────────────────────────────────
# HIGH SCORE & PERSISTENCE
# ──────────────────────────────────────────────────────────────────────────────
HIGH_SCORE_FILE_LEGACY: str = 'highscore.txt'
HIGH_SCORE_FILE_V2: str = 'highscore_v2.txt'
# Active ladder can be: 'legacy' or 'v2'
HIGH_SCORE_LADDER: str = 'v2'
# Backward-compatibility alias used by older code paths.
HIGH_SCORE_FILE: str = HIGH_SCORE_FILE_V2
HIGH_SCORE_ENTRIES: int = 3
HIGH_SCORE_DEFAULT_NAME: str = 'AAA'

# ──────────────────────────────────────────────────────────────────────────────
# DIFFICULTY PRESETS (Future Upgrade)
# ──────────────────────────────────────────────────────────────────────────────
# Active preset can be: 'easy', 'normal', or 'hard'
DIFFICULTY_PRESET: str = 'normal'

# Tuning multipliers used by the main loop to scale challenge and survivability.
DIFFICULTY_PRESETS: Dict[str, Dict[str, float]] = {
    'easy': {
        'enemy_speed_mult': 0.88,
        'spawn_interval_mult': 1.16,
        'shoot_prob_mult': 0.78,
        'boss_health_mult': 0.86,
        'continue_bonus': 1.0,
        'player_health_bonus': 1.0,
    },
    'normal': {
        'enemy_speed_mult': 1.0,
        'spawn_interval_mult': 1.0,
        'shoot_prob_mult': 1.0,
        'boss_health_mult': 1.0,
        'continue_bonus': 0.0,
        'player_health_bonus': 0.0,
    },
    'hard': {
        'enemy_speed_mult': 1.14,
        'spawn_interval_mult': 0.88,
        'shoot_prob_mult': 1.24,
        'boss_health_mult': 1.18,
        'continue_bonus': -1.0,
        'player_health_bonus': -1.0,
    },
}
