import array
import math
import os
import random
import sys
import traceback

import pygame

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Colour constants ──────────────────────────────────────────────────────────
_COL_FIREBALL = (255, 100,   0)
_COL_EBULLET  = (255,   0, 255)
_COL_BBULLET  = (255, 255,   0)
_COL_BAR_BG   = (255,   0,   0)
_COL_BAR_FG   = (  0, 255,   0)
_COL_WHITE    = (255, 255, 255)
_COL_RED      = (255,  50,  50)
_COL_PICKUP   = (  0, 255,  80)


def _build_dir_map():
    return {e.lower(): e for e in os.listdir(BASE_DIR)}


def load_image(dir_map, filename, size):
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


def find_file(dir_map, filename):
    entry = dir_map.get(filename.lower())
    return os.path.join(BASE_DIR, entry) if entry else None


def _make_impact_sound():
    n = int(44100 * 0.15)
    samples = [
        max(-32768, min(32767, int(random.uniform(-1, 1) * (1.0 - i / n) * 28000)))
        for i in range(n)
    ]
    stereo = array.array('h', [s for s in samples for _ in range(2)])
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.6)
    return snd


def _make_siren_sound():
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


def _make_powerup_sound():
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


def _tutorial_screen(screen, clock, tutorial_img, tutorial_music_file=None):
    """Show the tutorial / how-to-play image. Returns when the player dismisses it."""
    if tutorial_music_file:
        try:
            pygame.mixer.music.load(tutorial_music_file)
            pygame.mixer.music.set_volume(0.7)
            pygame.mixer.music.play(-1)
        except pygame.error:
            pass
    W, H = screen.get_size()
    font_hint = pygame.font.SysFont("Arial", 28, bold=True)
    hint = font_hint.render("Press  ESC  or  BACKSPACE  to return", True, (220, 220, 220))
    hint_rect = hint.get_rect(center=(W // 2, H - 28))

    while True:
        screen.blit(tutorial_img, (0, 0))
        hint.set_alpha(180)
        screen.blit(hint, hint_rect)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_RETURN):
                    return
            if event.type == pygame.MOUSEBUTTONDOWN:
                return

        pygame.display.flip()
        clock.tick(60)


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

    btn_w = int(W * 0.285)
    btn_h = int(H * 0.072)
    btn_x = W // 2 - btn_w // 2

    buttons = [
        ("START GAME",  "start",    0.493),
        ("VS MODE",     "soon",     0.572),
        ("HOW TO PLAY", "tutorial", 0.650),
        ("CREDITS",     "soon",     0.725),
        ("EXIT GAME",   "exit",     0.800),
    ]
    rects = [
        (pygame.Rect(btn_x, int(H * yf) - btn_h // 2, btn_w, btn_h), action)
        for _, action, yf in buttons
    ]

    font_soon  = pygame.font.SysFont("Arial", 30, bold=True)
    soon_timer = 0
    highlight  = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 55))

    while True:
        screen.blit(menu_img, (0, 0))
        mx, my = pygame.mouse.get_pos()

        for rect, _ in rects:
            if rect.collidepoint(mx, my):
                screen.blit(highlight, rect.topleft)

        if soon_timer > 0:
            t = font_soon.render("Coming Soon!", True, (255, 210, 0))
            screen.blit(t, t.get_rect(center=(W // 2, H - 36)))
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
                        else:
                            soon_timer = 120

        pygame.display.flip()
        clock.tick(60)


def _result_screen(screen, clock, img, music_file, score=0, high_score=0):
    """Show win or lose image. Returns 'restart' or 'menu'."""
    W, H = screen.get_size()
    _sf = pygame.font.SysFont("Arial", 38, bold=True)
    btn_w   = int(W * 0.29)
    btn_h   = int(H * 0.079)
    btn_cx  = int(W * 0.655)          # horizontal centre of buttons
    btn_x   = btn_cx - btn_w // 2

    try_rect  = pygame.Rect(btn_x, int(H * 0.537), btn_w, btn_h)
    menu_rect = pygame.Rect(btn_x, int(H * 0.646), btn_w, btn_h)

    highlight = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 60))

    while True:
        screen.blit(img, (0, 0))
        if score > 0:
            _sc = _sf.render(f"Score:  {score:,}", True, (255, 220, 50))
            screen.blit(_sc, _sc.get_rect(center=(W // 2, int(H * 0.42))))
            if score >= high_score:
                _nb = _sf.render("❖  NEW BEST  ❖", True, (255, 100, 80))
                screen.blit(_nb, _nb.get_rect(center=(W // 2, int(H * 0.47))))
        mx, my = pygame.mouse.get_pos()
        for rect in (try_rect, menu_rect):
            if rect.collidepoint(mx, my):
                screen.blit(highlight, rect.topleft)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_r):
                    return "restart"
                if event.key in (pygame.K_ESCAPE, pygame.K_m):
                    return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if try_rect.collidepoint(event.pos):
                    return "restart"
                if menu_rect.collidepoint(event.pos):
                    return "menu"

        pygame.display.flip()
        clock.tick(60)


def main():
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.init()
    impact_channel = pygame.mixer.Channel(0)  # dedicated channel — never dropped

    WIDTH, HEIGHT = 1600, 900
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Onyx G vs Space Drones")
    clock = pygame.time.Clock()

    dir_map = _build_dir_map()

    # ── One-time asset loads ──────────────────────────────────────────────────
    sprite_image   = load_image(dir_map, "onyxg_vs_cranium.png",  (64, 128))
    drone_image    = load_image(dir_map, "drone_spaceship.png",   (40, 40))
    boss_image     = load_image(dir_map, "cranium_commander.png", (100, 100))
    background_img = load_image(dir_map, "space_background.png",  (WIDTH, HEIGHT))
    menu_img       = load_image(dir_map, "Start Menu Image May 25, 2026 at 08_47_06 PM (1).png", (WIDTH, HEIGHT))
    win_img        = load_image(dir_map, "Win Screen Image May 25, 2026 at 08_59_06 PM.png",     (WIDTH, HEIGHT))
    lose_img       = load_image(dir_map, "Lose Screen Image May 25, 2026 at 09_01_59 PM.png",    (WIDTH, HEIGHT))

    music_file = find_file(dir_map, "crab_ass.ogg")
    if music_file:
        try:
            pygame.mixer.music.load(music_file)
            pygame.mixer.music.set_volume(0.7)
            pygame.mixer.music.play(-1)
            print("🎶 Music playing.")
        except pygame.error as err:
            print(f"⚠️ Audio disabled: {err}")
            music_file = None
    else:
        print("⚠️ Music file not found. Continuing without music.")

    win_music_file = find_file(dir_map, "WinScene music.ogg")
    lose_music_file = find_file(dir_map, "Lose Scene Music.ogg")
    start_menu_music_file = find_file(dir_map, "Start Menu Music.ogg")
    tutorial_music_file = find_file(dir_map, "Tutorial Page music.ogg")

    tutorial_img = load_image(dir_map, "Tutorial Screen.png", (WIDTH, HEIGHT))

    shoot_sound = None
    shoot_file = find_file(dir_map, "GUNPis_Shot in 357 magnum 9 mm (ID 0438)_BigSoundBank.com.ogg")
    if shoot_file:
        try:
            shoot_sound = pygame.mixer.Sound(shoot_file)
            shoot_sound.set_volume(0.5)
        except pygame.error as err:
            print(f"⚠️ Shoot sound disabled: {err}")

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

    font     = pygame.font.SysFont("Arial", 24)
    font_big = pygame.font.SysFont("Arial", 64, bold=True)
    font_med = pygame.font.SysFont("Arial", 36)
    font_popup = pygame.font.SysFont("Arial", 22, bold=True)

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 170))

    # ── Constants ─────────────────────────────────────────────────────────────
    SPEED                = 5
    FIREBALL_SPEED       = 10
    ENEMY_SPEED          = 2
    ENEMY_SPAWN_INTERVAL = 60
    BULLET_SPEED         = 6
    SHOOT_PROBABILITY    = 0.01
    FIRE_COOLDOWN        = 12
    BG_SCROLL_SPEED      = 2
    PICKUP_DROP_CHANCE   = 0.15
    IFRAME_DURATION      = 90
    WAVE_DEFS = [
        {'count':  8, 'interval': 60},
        {'count': 12, 'interval': 50},
        {'count': 16, 'interval': 40},
        {'count': 20, 'interval': 30},
        {'count': 25, 'interval': 20},
    ]
    WAVE_MULT        = [1.0, 1.5, 2.0, 2.5, 3.0]
    WAVE_ENEMY_SPEED = [2, 2, 3, 3, 4]
    WAVE_SHOOT_PROB  = [0.008, 0.008, 0.009, 0.009, 0.005]
    PERKS = [
        {'id': 'rapid_fire',  'name': 'RAPID FIRE',   'desc': 'Fire rate +50%',       'color': (255, 200,  50)},
        {'id': 'speed_boost', 'name': 'SPEED BOOST',  'desc': 'Movement speed +2',    'color': ( 50, 220, 255)},
        {'id': 'extra_heart', 'name': 'EXTRA HEARTS', 'desc': 'Gain +2 HP',           'color': (255,  80,  80)},
        {'id': 'double_shot', 'name': 'DOUBLE SHOT',  'desc': 'Fire twin bullets',    'color': (200, 100, 255)},
        {'id': 'power_shot',  'name': 'POWER SHOT',   'desc': 'Boss takes 2x damage', 'color': (255, 150,  50)},
        {'id': 'lucky_drop',  'name': 'LUCKY DROP',   'desc': '2x pickup drop rate',  'color': (100, 255, 100)},
    ]

    # ── High score (persistent) ────────────────────────────────────────────
    hs_file = os.path.join(BASE_DIR, 'highscore.txt')
    try:
        with open(hs_file) as _f:
            high_score = int(_f.read().strip())
    except Exception:
        high_score = 0

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
        score              = 0
        health             = 6

        boss_active        = False
        boss_warned        = False
        boss_defeated      = False
        boss_health        = 20
        boss_max_health    = 20
        boss_speed         = 1
        boss_fire_interval = 60
        boss_fire_timer    = 0
        boss_rect          = boss_image.get_rect(center=(WIDTH // 2, -100))

        bg_x               = 0
        frame_count        = 0
        health_pickups     = []
        score_popups       = []
        particles          = []
        shake_timer        = 0
        iframe_timer       = 0
        boss_dir           = 1
        boss_raging        = False
        aimed_bullets      = []
        combo              = 0
        combo_timer        = 0
        boss_warning_timer = 0
        boss_defeat_timer  = 0
        hit_flash_timer    = 0
        wave               = 1
        wave_spawned       = 0
        wave_transition_timer = 0
        wave_intro_timer   = 90
        game_over          = False
        game_won           = False
        running            = True
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

        # ── Inner game loop ───────────────────────────────────────────────────
        while running:

            bg_x = (bg_x + BG_SCROLL_SPEED) % WIDTH
            screen.blit(background_img, (bg_x, 0))
            screen.blit(background_img, (bg_x - WIDTH, 0))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and not show_upgrade:
                    paused = not paused
                if show_upgrade:
                    _uidx = -1
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_1:   _uidx = 0
                        elif event.key == pygame.K_2: _uidx = 1
                        elif event.key == pygame.K_3: _uidx = 2
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        _ucw, _uch, _ugap = 280, 190, 30
                        _usx = (WIDTH - (3 * _ucw + 2 * _ugap)) // 2
                        _ucy = HEIGHT // 2 - _uch // 2
                        for _ui in range(3):
                            if pygame.Rect(_usx + _ui * (_ucw + _ugap), _ucy, _ucw, _uch).collidepoint(event.pos):
                                _uidx = _ui
                                break
                    if 0 <= _uidx < len(upgrade_choices):
                        _pid = upgrade_choices[_uidx]['id']
                        active_perks.append(upgrade_choices[_uidx]['name'])
                        if _pid == 'rapid_fire':    perk_fire_cooldown = max(4, perk_fire_cooldown - 4)
                        elif _pid == 'speed_boost': perk_speed = min(9, perk_speed + 2)
                        elif _pid == 'extra_heart': health = min(8, health + 2)
                        elif _pid == 'double_shot': perk_double_shot = True
                        elif _pid == 'power_shot':  perk_power_shot = True
                        elif _pid == 'lucky_drop':  perk_lucky_drop = True
                        show_upgrade = False
                        wave += 1
                        wave_spawned = 0
                        wave_intro_timer = 90

            if paused:
                _pov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                _pov.fill((0, 0, 20, 200))
                screen.blit(_pov, (0, 0))
                _pt = font_big.render("PAUSED", True, (255, 255, 255))
                screen.blit(_pt, _pt.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40)))
                _ph = font_med.render("Press  ESC  to resume", True, (180, 200, 255))
                screen.blit(_ph, _ph.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 20)))
                pygame.display.flip()
                clock.tick(60)
                continue

            if not show_upgrade:
                keys = pygame.key.get_pressed()
                if keys[pygame.K_LEFT]  and sprite_rect.left   > 0:     sprite_rect.x -= perk_speed
                if keys[pygame.K_RIGHT] and sprite_rect.right  < WIDTH:  sprite_rect.x += perk_speed
                if keys[pygame.K_UP]    and sprite_rect.top    > 0:      sprite_rect.y -= perk_speed
                if keys[pygame.K_DOWN]  and sprite_rect.bottom < HEIGHT: sprite_rect.y += perk_speed
                if any(keys[k] for k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN)):
                    for _ in range(2):
                        particles.append({
                            'x': float(sprite_rect.centerx + random.randint(-6, 6)),
                            'y': float(sprite_rect.bottom - 4),
                            'vx': random.uniform(-0.4, 0.4),
                            'vy': random.uniform(1.5, 3.5),
                            'life': random.randint(8, 18), 'max': 18,
                            'color': random.choice([(0,150,255),(50,200,255),(100,230,255)])
                        })

                fire_timer = max(0, fire_timer - 1)
                if keys[pygame.K_SPACE] and len(fireballs) < 10 and fire_timer == 0:
                    if perk_double_shot:
                        fireballs.append(pygame.Rect(sprite_rect.centerx - 16, sprite_rect.top, 8, 16))
                        fireballs.append(pygame.Rect(sprite_rect.centerx + 8,  sprite_rect.top, 8, 16))
                    else:
                        fireballs.append(pygame.Rect(sprite_rect.centerx - 4, sprite_rect.top, 8, 16))
                    fire_timer = perk_fire_cooldown
                    if shoot_sound:
                        shoot_sound.play()

            for f in fireballs:
                f.y -= FIREBALL_SPEED
            fireballs = [f for f in fireballs if f.y > -20]

            frame_count += 1
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
            if boss_warning_timer > 0:
                boss_warning_timer -= 1
                if boss_warning_timer == 0 and boss_warned and not boss_defeated:
                    boss_active       = True
                    boss_rect.top     = -boss_rect.height
                    boss_rect.centerx = WIDTH // 2
            if wave_intro_timer > 0:
                wave_intro_timer -= 1
            if wave_transition_timer > 0:
                wave_transition_timer -= 1
                if wave_transition_timer == 0:
                    if wave >= 5:
                        boss_warned        = True
                        boss_warning_timer = 90
                        boss_health        = boss_max_health
                        if siren_sound:
                            siren_sound.play(loops=2)
                    else:
                        show_upgrade    = True
                        upgrade_choices = random.sample(PERKS, 3)
            elif (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade
                    and wave_spawned >= WAVE_DEFS[wave - 1]['count']
                    and len(enemies) == 0):
                wave_transition_timer = 120
                score += 200
            if (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade
                    and wave_transition_timer == 0 and wave_intro_timer == 0):
                w = WAVE_DEFS[wave - 1]
                if wave_spawned < w['count']:
                    enemy_timer += 1
                    if enemy_timer >= w['interval']:
                        enemies.append([pygame.Rect(random.randint(0, WIDTH - 40), 0, 40, 40),
                                        random.uniform(0, 2 * math.pi)])
                        enemy_timer = 0
                        wave_spawned += 1

            for e in enemies:
                e[0].y += WAVE_ENEMY_SPEED[wave - 1]
                e[0].x = max(0, min(WIDTH - 40,
                    e[0].x + int(math.sin(frame_count * 0.04 + e[1]) * 1.5)))
                if random.random() < WAVE_SHOOT_PROB[wave - 1]:
                    if random.random() < 0.15:
                        dx = sprite_rect.centerx - e[0].centerx
                        dy = sprite_rect.centery - e[0].centery
                        dist = math.hypot(dx, dy) or 1
                        aimed_bullets.append({'x': float(e[0].centerx), 'y': float(e[0].bottom),
                                              'vx': dx / dist * BULLET_SPEED,
                                              'vy': dy / dist * BULLET_SPEED})
                    else:
                        enemy_bullets.append(pygame.Rect(e[0].centerx - 4, e[0].bottom, 8, 12))
            enemies = [e for e in enemies if e[0].top < HEIGHT]

            for p in health_pickups:
                p.y += 1
            health_pickups = [p for p in health_pickups if p.top < HEIGHT]

            for b in enemy_bullets:
                b.y += BULLET_SPEED
            enemy_bullets = [b for b in enemy_bullets if b.y < HEIGHT]

            for ab in aimed_bullets:
                ab['x'] += ab['vx']
                ab['y'] += ab['vy']
            aimed_bullets = [ab for ab in aimed_bullets
                             if 0 < ab['y'] < HEIGHT and 0 < ab['x'] < WIDTH]

            if boss_active:
                if not boss_raging and boss_health <= int(boss_max_health * 0.3):
                    boss_raging        = True
                    boss_fire_interval = 30
                hspeed = 4 if boss_raging else 2
                if boss_rect.top < 50:
                    boss_rect.y += boss_speed
                else:
                    boss_rect.x += hspeed * boss_dir
                    if boss_rect.right >= WIDTH or boss_rect.left <= 0:
                        boss_dir *= -1
                    boss_fire_timer += 1
                    if boss_fire_timer >= boss_fire_interval:
                        boss_fire_timer = 0
                        cx = boss_rect.centerx
                        if boss_raging:
                            boss_bullets += [
                                pygame.Rect(cx - 25, boss_rect.bottom, 10, 16),
                                pygame.Rect(cx - 5,  boss_rect.bottom, 10, 16),
                                pygame.Rect(cx + 15, boss_rect.bottom, 10, 16),
                            ]
                        else:
                            boss_bullets.append(
                                pygame.Rect(cx - 5, boss_rect.bottom, 10, 16))

                for b in boss_bullets:
                    b.y += BULLET_SPEED
                boss_bullets = [b for b in boss_bullets if b.y < HEIGHT]

            for f in fireballs[:]:
                for e in enemies[:]:
                    if f.colliderect(e[0]):
                        fireballs.remove(f)
                        enemies.remove(e)
                        cx, cy = e[0].centerx, e[0].centery
                        combo += 1
                        combo_timer = 90
                        points = int(100 * combo * WAVE_MULT[wave - 1])
                        score += points
                        streak_count += 1
                        streak_timer = 60
                        if streak_count == 2:
                            streak_text = 'DOUBLE KILL!'; streak_color = (255, 220,  50); streak_msg_timer = 75
                        elif streak_count == 3:
                            streak_text = 'TRIPLE KILL!'; streak_color = (255, 150,   0); streak_msg_timer = 75
                        elif streak_count == 4:
                            streak_text = 'QUAD KILL!';   streak_color = (255,  80,  80); streak_msg_timer = 75
                        elif streak_count >= 5:
                            streak_text = 'RAMPAGE!';     streak_color = (200,   0, 255); streak_msg_timer = 90
                        score_popups.append({
                            'x': cx, 'y': e[0].top, 'timer': 45, 'max': 45,
                            'text': f'+{points}' + (f' x{combo}!' if combo > 1 else ''),
                            'color': (255, 80, 255) if combo > 1 else (255, 220, 0)})
                        particles += [
                            {'x': float(cx), 'y': float(cy),
                             'vx': random.uniform(-4, 4), 'vy': random.uniform(-4, 4),
                             'life': random.randint(15, 30), 'max': 30,
                             'color': random.choice([(255,200,0),(255,100,0),(255,50,0)])}
                            for _ in range(10)
                        ]
                        if random.random() < (PICKUP_DROP_CHANCE * 2 if perk_lucky_drop else PICKUP_DROP_CHANCE):
                            health_pickups.append(pygame.Rect(cx - 8, e[0].top, 16, 16))
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        break

            for f in fireballs[:]:
                if boss_active and boss_rect.colliderect(f):
                    fireballs.remove(f)
                    boss_health -= (2 if perk_power_shot else 1)
                    if impact_sound:
                        impact_channel.play(impact_sound)
                    if boss_health <= 0:
                        boss_active   = False
                        boss_defeated = True
                        score        += int(1000 * WAVE_MULT[wave - 1])
                        bcx, bcy = boss_rect.centerx, boss_rect.centery
                        particles += [
                            {'x': float(bcx + random.randint(-50, 50)),
                             'y': float(bcy + random.randint(-50, 50)),
                             'vx': random.uniform(-7, 7), 'vy': random.uniform(-7, 7),
                             'life': random.randint(30, 60), 'max': 60,
                             'color': random.choice([(255,200,0),(255,100,0),(255,255,255),(200,200,255)])}
                            for _ in range(40)
                        ]
                        enemies.clear()
                        enemy_bullets.clear()
                        aimed_bullets.clear()
                        boss_bullets.clear()
                        boss_defeat_timer = 90

            for e in enemies[:]:
                if e[0].colliderect(sprite_rect):
                    enemies.remove(e)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            running = False

            for b in enemy_bullets[:]:
                if b.colliderect(sprite_rect):
                    enemy_bullets.remove(b)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            running = False

            for ab in aimed_bullets[:]:
                abr = pygame.Rect(int(ab['x']) - 4, int(ab['y']) - 6, 8, 12)
                if abr.colliderect(sprite_rect):
                    aimed_bullets.remove(ab)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            running = False

            for b in boss_bullets[:]:
                if b.colliderect(sprite_rect):
                    boss_bullets.remove(b)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            running = False

            for p in health_pickups[:]:
                if p.colliderect(sprite_rect):
                    health_pickups.remove(p)
                    health = min(health + 1, 8)
                    score_popups.append({'x': sprite_rect.centerx, 'y': sprite_rect.top,
                                         'timer': 45, 'max': 45,
                                         'text': '+HP', 'color': (0, 255, 80)})
                    if powerup_sound:
                        powerup_sound.play()

            if iframe_timer == 0 or iframe_timer % 8 < 4:
                screen.blit(sprite_image, sprite_rect)
            for f in fireballs:
                pygame.draw.rect(screen, _COL_FIREBALL, f)
            for e in enemies:
                screen.blit(drone_image, e[0])
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
            particles = next_particles
            for b in enemy_bullets:
                pygame.draw.rect(screen, _COL_EBULLET, b)
            for ab in aimed_bullets:
                pygame.draw.rect(screen, (255, 140, 0),
                                 (int(ab['x']) - 4, int(ab['y']) - 6, 8, 12))
            for p in health_pickups:
                pygame.draw.rect(screen, _COL_PICKUP, p)
                pygame.draw.rect(screen, _COL_WHITE, (p.x + 6, p.y + 2,  4, 12))
                pygame.draw.rect(screen, _COL_WHITE, (p.x + 2, p.y + 6, 12,  4))

            if boss_active:
                screen.blit(boss_image, boss_rect)
                if boss_raging:
                    rs = pygame.Surface((boss_rect.width, boss_rect.height), pygame.SRCALPHA)
                    rs.fill((255, 0, 0, int(50 + 30 * math.sin(frame_count * 0.2))))
                    screen.blit(rs, boss_rect.topleft)
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
                    alpha = int(255 * pop['timer'] / pop['max'])
                    s = font_popup.render(pop['text'], True, pop['color'])
                    s.set_alpha(alpha)
                    screen.blit(s, s.get_rect(centerx=int(pop['x']), y=int(pop['y'])))
                    next_popups.append(pop)
            score_popups = next_popups

            screen.blit(font.render(f"Score: {score}", True, _COL_WHITE), (10, 10))
            hs_surf = font.render(f"Best: {high_score}", True, (180, 180, 180))
            screen.blit(hs_surf, hs_surf.get_rect(right=WIDTH - 10, y=10))
            if not boss_active and not boss_warned and not boss_defeated:
                wv_surf = font.render(f"WAVE  {wave} / 5", True, (150, 200, 255))
                screen.blit(wv_surf, wv_surf.get_rect(centerx=WIDTH // 2, y=10))
            for i in range(8):
                color = _COL_RED if i < health else (70, 70, 70)
                screen.blit(font.render("♥", True, color), (10 + i * 26, 40))
            if active_perks:
                _ap = font.render("  ·  ".join(active_perks), True, (180, 120, 255))
                screen.blit(_ap, _ap.get_rect(centerx=WIDTH // 2, y=HEIGHT - 30))
            if combo > 1 and combo_timer > 0:
                alpha = min(255, combo_timer * 4)
                ct = font_med.render(f"x{combo} COMBO!", True, (255, 80, 255))
                ct.set_alpha(alpha)
                screen.blit(ct, ct.get_rect(centerx=WIDTH // 2, centery=HEIGHT // 2 - 60))
            if streak_msg_timer > 0:
                _sa = min(255, streak_msg_timer * 6)
                _ss = font_big.render(streak_text, True, streak_color)
                _ss.set_alpha(_sa)
                screen.blit(_ss, _ss.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 50)))

            if shake_timer > 0:
                shake_timer -= 1
                ox = random.randint(-6, 6)
                oy = random.randint(-6, 6)
                tmp = screen.copy()
                screen.fill((0, 0, 0))
                screen.blit(tmp, (ox, oy))

            # ── Screen overlays (applied after shake for stability) ─────────────
            if hit_flash_timer > 0:
                hit_flash_timer -= 1
                hf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                hf.fill((255, 0, 0, int(110 * hit_flash_timer / 8)))
                screen.blit(hf, (0, 0))

            if health == 1 and not game_over:
                pa = int(55 + 35 * math.sin(frame_count * 0.12))
                lh_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                bw = 55
                for r in [(0, 0, WIDTH, bw), (0, HEIGHT - bw, WIDTH, bw),
                           (0, 0, bw, HEIGHT), (WIDTH - bw, 0, bw, HEIGHT)]:
                    pygame.draw.rect(lh_surf, (255, 0, 0, pa), r)
                screen.blit(lh_surf, (0, 0))

            if boss_warning_timer > 0:
                wa = int(35 * abs(math.sin(frame_count * 0.15)))
                warn_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                warn_surf.fill((180, 0, 0, wa))
                screen.blit(warn_surf, (0, 0))
                wt_alpha = int(255 * abs(math.sin(frame_count * 0.2)))
                wt = font_big.render('\u26a0  WARNING  \u26a0', True, (255, 50, 50))
                wt.set_alpha(wt_alpha)
                screen.blit(wt, wt.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))

            if wave_intro_timer > 0:
                wi_alpha = min(255, wave_intro_timer * 5)
                wi = font_big.render(f'- WAVE  {wave} -', True, (100, 200, 255))
                wi.set_alpha(wi_alpha)
                screen.blit(wi, wi.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))
                wm = font_med.render(['1×', '1.5×', '2×', '2.5×', '3×'][wave - 1] + '  SCORE MULTIPLIER', True, (255, 220, 100))
                wm.set_alpha(wi_alpha)
                screen.blit(wm, wm.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 25)))

            if wave_transition_timer > 0 and not boss_warned:
                wc_alpha = min(255, wave_transition_timer * 4)
                wc = font_med.render(f'WAVE {wave} COMPLETE!   +200', True, (100, 255, 120))
                wc.set_alpha(wc_alpha)
                screen.blit(wc, wc.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))

            if boss_defeat_timer > 0:
                boss_defeat_timer -= 1
                fa = int(220 * boss_defeat_timer / 90)
                fs = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                fs.fill((255, 255, 255, fa))
                screen.blit(fs, (0, 0))
                vt_alpha = min(255, int(255 * (1.0 - boss_defeat_timer / 90.0) * 3.0))
                vt = font_big.render('VICTORY!', True, (255, 220, 0))
                vt.set_alpha(vt_alpha)
                screen.blit(vt, vt.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
                if boss_defeat_timer == 0:
                    game_won = True
                    running  = False

            if show_upgrade:
                _uov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                _uov.fill((0, 0, 0, 180))
                screen.blit(_uov, (0, 0))
                _ut = font_big.render("CHOOSE YOUR UPGRADE", True, (255, 220, 50))
                screen.blit(_ut, _ut.get_rect(center=(WIDTH // 2, 110)))
                _uh = font.render("Click a card  or press  1 / 2 / 3", True, (180, 180, 180))
                screen.blit(_uh, _uh.get_rect(center=(WIDTH // 2, 170)))
                _ucw, _uch, _ugap = 280, 190, 30
                _usx = (WIDTH - (3 * _ucw + 2 * _ugap)) // 2
                _ucy = HEIGHT // 2 - _uch // 2
                _umx, _umy = pygame.mouse.get_pos()
                for _ui, _upk in enumerate(upgrade_choices):
                    _urx = _usx + _ui * (_ucw + _ugap)
                    _urc = pygame.Rect(_urx, _ucy, _ucw, _uch)
                    _uhov = _urc.collidepoint(_umx, _umy)
                    pygame.draw.rect(screen, (40, 30, 70) if not _uhov else (65, 50, 105), _urc, border_radius=14)
                    pygame.draw.rect(screen, _upk['color'], _urc, 3, border_radius=14)
                    _uns = font_med.render(_upk['name'], True, (255, 255, 255))
                    screen.blit(_uns, _uns.get_rect(center=(_urx + _ucw // 2, _ucy + 55)))
                    _uds = font.render(_upk['desc'], True, (200, 200, 200))
                    screen.blit(_uds, _uds.get_rect(center=(_urx + _ucw // 2, _ucy + 100)))
                    _unum = font_med.render(str(_ui + 1), True, _upk['color'])
                    screen.blit(_unum, _unum.get_rect(center=(_urx + _ucw // 2, _ucy + 150)))

            pygame.display.flip()
            clock.tick(60)

        # ── Save high score ──────────────────────────────────────────────────
        if score > high_score:
            high_score = score
            try:
                with open(hs_file, 'w') as _f:
                    _f.write(str(high_score))
            except Exception:
                pass

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
            action = _result_screen(screen, clock, result_img, music_file, score, high_score)
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
