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


def _credits_screen(screen, clock):
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

    btn_w = int(W * 0.285)
    btn_h = int(H * 0.055)
    btn_x = W // 2 - btn_w // 2

    buttons = [
        ("START GAME",  "start",    0.33),
        ("VS MODE",     "soon",     0.39),
        ("HOW TO PLAY", "tutorial", 0.45),
        ("CREDITS",     "credits",  0.51),
        ("EXIT GAME",   "exit",     0.565),
    ]
    rects = [
        (pygame.Rect(btn_x, int(H * yf) - btn_h // 2, btn_w, btn_h), action)
        for _, action, yf in buttons
    ]

    font_soon = _get_arcade_font(22)
    font_btn  = _get_arcade_font(18)
    soon_timer = 0
    highlight  = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 55))

    while True:
        screen.blit(menu_img, (0, 0))
        mx, my = pygame.mouse.get_pos()

        for (rect, _), (label, _, _) in zip(rects, buttons):
            pygame.draw.rect(screen, (15, 10, 35), rect, border_radius=6)
            pygame.draw.rect(screen, (100, 60, 180), rect, 2, border_radius=6)
            if rect.collidepoint(mx, my):
                screen.blit(highlight, rect.topleft)
            _lbl = font_btn.render(label, True, (220, 200, 255))
            screen.blit(_lbl, _lbl.get_rect(center=rect.center))

        if soon_timer > 0:
            t = font_soon.render("Coming Soon!", True, (255, 210, 0))
            screen.blit(t, t.get_rect(center=(W // 2, int(H * 0.27))))
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


def _boss_intro_cinematic(screen, clock):
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
            # Phase 2 – white flash + play impact sound
            if not _hit:
                if _snd:
                    _snd.play()
                _hit = True
            t = (_f - _ends[1]) / _P[2]
            _blit_title(W // 2, H // 2 - 15)
            _fl = pygame.Surface((W, H))
            _fl.fill((255, 255, 255))
            _fl.set_alpha(int(255 * (1.0 - t) ** 2))
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


def _result_screen(screen, clock, img, music_file, score=0, scores=None):
    """Show win or lose image. Returns 'restart' or 'menu'."""
    W, H = screen.get_size()
    _sf  = _get_arcade_font(30)
    _sf2 = _get_arcade_font(20)
    btn_w   = int(W * 0.30)
    btn_h   = int(H * 0.065)
    btn_cx  = int(W * 0.593)
    btn_x   = btn_cx - btn_w // 2

    try_rect  = pygame.Rect(btn_x, int(H * 0.518), btn_w, btn_h)
    menu_rect = pygame.Rect(btn_x, int(H * 0.570), btn_w, btn_h)

    highlight = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 60))

    _top_score  = scores[0][0] if scores else 0
    _RANK_COLS  = [(255, 215, 0), (200, 200, 215), (205, 127, 50)]
    _RANK_LBLS  = ['1ST', '2ND', '3RD']

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
        if score > 0:
            _sc = _sf.render(f"Score:  {_displayed:,}", True, (255, 220, 50))
            screen.blit(_sc, _sc.get_rect(center=(W // 2, int(H * 0.34))))
            if _displayed >= score and score >= _top_score:
                _nb = _sf.render("❖  NEW BEST  ❖", True, (255, 100, 80))
                screen.blit(_nb, _nb.get_rect(center=(W // 2, int(H * 0.40))))
        # ── Mini leaderboard ────────────────────────────────────────────
        if scores:
            _lbx = W // 2
            _lby = int(H * 0.47)
            _hdr = _sf2.render('TOP SCORES', True, (180, 180, 255))
            screen.blit(_hdr, _hdr.get_rect(center=(_lbx, _lby)))
            for _ri, (_rs, _rn) in enumerate(scores):
                _col = _RANK_COLS[_ri]
                _hl  = (score > 0 and _ri == 0 and score >= _top_score)
                _tc  = (255, 255, 255) if _hl else _col
                _ry  = _lby + 34 + _ri * 36
                # Filled circle medal + dark inner ring
                pygame.draw.circle(screen, _col, (_lbx - 120, _ry), 10)
                pygame.draw.circle(screen, (0, 0, 0), (_lbx - 120, _ry), 6)
                _row = _sf2.render(f"{_RANK_LBLS[_ri]}  {_rn}  {_rs:,}", True, _tc)
                screen.blit(_row, _row.get_rect(midleft=(_lbx - 102, _ry - 10)))
        mx, my = pygame.mouse.get_pos()
        for rect in (try_rect, menu_rect):
            if rect.collidepoint(mx, my):
                screen.blit(highlight, rect.topleft)

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
                       place=1, scores=None, new_score=0):
    """Classic 3-letter initials entry on a new high score (top 3 aware)."""
    W, H   = screen.get_size()
    _af_big = _get_arcade_font(30)
    _af_med = _get_arcade_font(20)
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
    else:
        _scr_cx, _scr_cy = W // 2, H // 2
        _scr_top_y = H // 2 - 130

    # ── Place-specific header ─────────────────────────────────────────────
    _PLACE_INFO = {
        1: ('1ST PLACE!', (255, 215,   0)),
        2: ('2ND PLACE!', (200, 200, 215)),
        3: ('3RD PLACE!', (205, 127,  50)),
    }
    _title_text, _title_col = _PLACE_INFO.get(place, ('NEW BEST!', (255, 220, 0)))

    # ── Entry loop ────────────────────────────────────────────────────────
    confirmed_name = None
    while confirmed_name is None:
        screen.fill((0, 0, 0))
        if _cab_frame and _cab_rect:
            screen.blit(_cab_frame, _cab_rect)

        t = _af_big.render(_title_text, True, _title_col)
        screen.blit(t, t.get_rect(center=(_scr_cx, _scr_top_y + 28)))
        sub = _af_big.render('ENTER YOUR INITIALS', True, (255, 255, 255))
        screen.blit(sub, sub.get_rect(center=(_scr_cx, _scr_cy - 35)))
        for i, ch in enumerate(initials):
            col = (57, 255, 20) if i == cursor else (0, 200, 60)
            if i != cursor or (blink // 15) % 2 == 0:
                ls = font_big.render(ch, True, col)
                screen.blit(ls, ls.get_rect(center=(_scr_cx - 60 + i * 60, _scr_cy + 20)))
            pygame.draw.line(screen, col,
                             (_scr_cx - 72 + i * 60, _scr_cy + 58),
                             (_scr_cx - 32 + i * 60, _scr_cy + 58), 3)
        hint = font.render('\u2191\u2193: letter    \u2192: next    ENTER: confirm',
                           True, (0, 160, 50))
        screen.blit(hint, hint.get_rect(center=(_scr_cx, _scr_cy + 100)))
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
        _RANK_COLS   = [(255, 215, 0), (200, 200, 215), (205, 127, 50)]
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

            hof_t = _af_big.render('\u2605  HALL OF FAME  \u2605', True, (255, 215, 0))
            screen.blit(hof_t, hof_t.get_rect(center=(_scr_cx, _scr_top_y + 25)))

            for _ri, (_rs, _rn) in enumerate(_preview):
                _ry  = _scr_cy - 35 + _ri * 72
                _col = _RANK_COLS[_ri]
                _new = (_ri == place - 1)

                # Highlight row for the just-entered score
                if _new:
                    _bg = pygame.Surface((520, 58), pygame.SRCALPHA)
                    _bg.fill((255, 255, 0, 35))
                    screen.blit(_bg, _bg.get_rect(center=(_scr_cx, _ry)))

                # Filled circle medal + dark inner ring
                pygame.draw.circle(screen, _col, (_scr_cx - 158, _ry), 12)
                pygame.draw.circle(screen, (0, 0, 0), (_scr_cx - 158, _ry), 7)
                rank_s = _af_med.render(_RANK_LABELS[_ri], True, _col)
                screen.blit(rank_s, rank_s.get_rect(midright=(_scr_cx - 120, _ry)))
                name_s = _af_med.render(_rn, True, (255, 255, 255) if _new else _col)
                screen.blit(name_s, name_s.get_rect(center=(_scr_cx, _ry)))
                sc_s = _af_med.render(f'{_rs:,}', True, _col)
                screen.blit(sc_s, sc_s.get_rect(midleft=(_scr_cx + 100, _ry)))

            cont_s = _af_med.render('Press any key to continue\u2026', True, (110, 110, 110))
            screen.blit(cont_s, cont_s.get_rect(center=(_scr_cx, _scr_cy + 120)))
            pygame.display.flip()
            clock.tick(60)
            _hof_timer += 1
            for _ev in pygame.event.get():
                if _ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if _ev.type == pygame.KEYDOWN:
                    _hof_timer = 9999   # break out

    return confirmed_name


def build_rage_vignette(width, height, color, base_alpha):
    """Builds a reusable boss-rage screen-edge vignette surface."""
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    depth = height // 3
    for y in range(0, depth, 12):
        alpha = int(base_alpha * (1.0 - y / depth))
        pygame.draw.rect(surf, (*color, alpha), (0, y, width, 12))
        pygame.draw.rect(surf, (*color, alpha), (0, height - y - 12, width, 12))
    return surf


def main():
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.init()
    impact_channel = pygame.mixer.Channel(0)  # dedicated channel — never dropped

    WIDTH, HEIGHT = 675, 900
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Onyx G vs Space Drones")
    clock = pygame.time.Clock()

    dir_map = _build_dir_map()

    # ── One-time asset loads ──────────────────────────────────────────────────
    sprite_image   = load_image(dir_map, "onyxg_vs_cranium.png",  (80, 160))
    drone_image    = load_image(dir_map, "drone_spaceship.png",   (40, 40))
    minion_image   = load_image(dir_map, "tibbixel-dot-com-4947-wpng 2.png", (32, 32))
    boss_image     = load_image(dir_map, "cranium_commander 2.png", (100, 100))
    sativa_image   = load_image(dir_map, "Power UP sativa .png",  (40, 40))
    background_img = load_image(dir_map, "space_background.png",  (WIDTH, HEIGHT))
    menu_img       = load_image(dir_map, "Start Menu 3.png", (WIDTH, HEIGHT))
    win_img        = load_image(dir_map, "Win Scene 3.png",      (WIDTH, HEIGHT))
    lose_img       = load_image(dir_map, "Lose Screen 2.png",    (WIDTH, HEIGHT))

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

    tutorial_img = load_image(dir_map, "Tutorial Screen 2 .png", (WIDTH, HEIGHT))

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

    sativa_sound = None
    _sativa_sf = find_file(dir_map, "Power Up sativa sound.ogg")
    if _sativa_sf:
        try:
            sativa_sound = pygame.mixer.Sound(_sativa_sf)
            sativa_sound.set_volume(0.85)
        except pygame.error:
            pass

    font     = pygame.font.SysFont("Arial", 24)
    font_big = pygame.font.SysFont("Arial", 64, bold=True)
    font_med = pygame.font.SysFont("Arial", 36)
    font_popup = pygame.font.SysFont("Arial", 22, bold=True)
    font_huge = pygame.font.SysFont("Arial", 120, bold=True)

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 170))

    # ── One-time visual effect surfaces ──────────────────────────────────────
    # Colorkey surface: ~3× faster blit than SRCALPHA (skips transparent pixels; no per-pixel alpha)
    scanline_surf = pygame.Surface((WIDTH, HEIGHT))
    scanline_surf.fill((255, 0, 255))  # magenta = transparent key
    for _sl_y in range(0, HEIGHT, 3):
        pygame.draw.line(scanline_surf, (0, 0, 0), (0, _sl_y), (WIDTH, _sl_y))
    scanline_surf.set_colorkey((255, 0, 255))
    scanline_surf.set_alpha(45)
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
    _death_flash_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _fb_glow_surf     = pygame.Surface((16, 24), pygame.SRCALPHA)
    _kflash_surf      = pygame.Surface((40, 40), pygame.SRCALPHA)
    _kflash_surf.fill((255, 0, 0, 140))
    _dflash_surf      = pygame.Surface((40, 40), pygame.SRCALPHA)
    _dflash_surf.fill((0, 220, 255, 130))
    _boss_tint_surf   = pygame.Surface((100, 100), pygame.SRCALPHA)
    _sprite_glow_surf = pygame.Surface((240, 240), pygame.SRCALPHA)
    # Pre-rendered HUD surfaces (static text — rendered once, blitted every frame)
    _heart_red_h  = font.render("\u2665", True, _COL_RED)
    _heart_grey_h = font.render("\u2665", True, (70, 70, 70))
    _sativa_lbl_h = font.render('\u2605 SATIVA', True, (0, 255, 120))
    _shake_surf   = pygame.Surface((WIDTH, HEIGHT))  # no SRCALPHA; plain pixel copy
    # Dirty caches for text that rarely changes
    _score_cache = {'val': -1, 'surf': None}
    _hs_cache    = {'val': '', 'surf': None}
    _wave_cache  = {'val': -1, 'surf': None}
    _perks_cache  = {'val': '', 'surf': None}
    _scale_cache  = {'key': None, 'surf': None}   # sprite transform.scale cache
    _streak_cache = {'key': None, 'surf': None}   # streak message text cache
    _combo_cache  = {'val': None, 'surf': None}    # combo counter text cache
    # Pre-rendered static banner surfaces (text/color never change)
    _brage_surf      = font_big.render('\u2620  RAGE  MODE  \u2620', True, (255, 40, 40))
    _warn_text_surf  = font_big.render('\u26a0  WARNING  \u26a0', True, (255, 50, 50))
    _swarm_text_surf = font_big.render('\u26a1  DRONE SWARM!  \u26a1', True, (255, 150, 0))
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
    BEAT_FRAMES          = 34          # ~106 BPM @ 60 fps (60/34×60=105.9; use 30 for 120 BPM)
    BEAT_PULSE_FRAMES     = 8           # how long the pulse lasts
    FIRE_COOLDOWN        = 8
    BG_SCROLL_SPEED      = 2
    PICKUP_DROP_CHANCE   = 0.15
    IFRAME_DURATION      = 90
    WAVE_DEFS = [
        {'count': 12, 'interval': 50},
        {'count': 18, 'interval': 40},
        {'count': 24, 'interval': 30},
        {'count': 30, 'interval': 22},
        {'count': 38, 'interval': 15},
    ]
    WAVE_MULT        = [1.0, 1.5, 2.0, 2.5, 3.0]
    WAVE_ENEMY_SPEED = [3, 3, 4, 4, 5]
    WAVE_SHOOT_PROB  = [0.008, 0.008, 0.009, 0.009, 0.005]
    PERKS = [
        {'id': 'rapid_fire',  'name': 'RAPID FIRE',   'desc': 'Fire rate +50%',       'color': (255, 200,  50)},
        {'id': 'speed_boost', 'name': 'SPEED BOOST',  'desc': 'Movement speed +2',    'color': ( 50, 220, 255)},
        {'id': 'extra_heart', 'name': 'EXTRA HEARTS', 'desc': 'Gain +2 HP',           'color': (255,  80,  80)},
        {'id': 'double_shot', 'name': 'DOUBLE SHOT',  'desc': 'Fire twin bullets',    'color': (200, 100, 255)},
        {'id': 'power_shot',  'name': 'POWER SHOT',   'desc': 'Boss takes 2x damage', 'color': (255, 150,  50)},
        {'id': 'lucky_drop',  'name': 'LUCKY DROP',   'desc': '2x pickup drop rate',  'color': (100, 255, 100)},
    ]

    # ── High score (persistent, top 3) ────────────────────────────────────
    hs_file = os.path.join(BASE_DIR, 'highscore.txt')
    scores = [[0, 'AAA'], [0, 'AAA'], [0, 'AAA']]
    try:
        with open(hs_file) as _f:
            for _i, _line in enumerate(_f.read().strip().splitlines()[:3]):
                _p = _line.strip().split()
                if _p:
                    scores[_i][0] = int(_p[0])
                    if len(_p) > 1:
                        scores[_i][1] = _p[1][:3].upper()
    except Exception:
        pass
    high_score      = scores[0][0]
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
        boss_health        = 70
        boss_max_health    = 70
        boss_speed         = 1
        boss_fire_interval = 45
        boss_fire_timer    = 0
        boss_critical      = False
        boss_volley_count  = 0
        boss_rect          = boss_image.get_rect(center=(WIDTH // 2, -100))

        bg_x               = 0
        frame_count        = 0
        health_pickups     = []
        sativa_pickups     = []
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
        boss_minion_interval = 100
        combo              = 0
        combo_timer        = 0
        boss_warning_timer = 0
        boss_defeat_timer  = 0
        hit_flash_timer    = 0
        wave               = 1
        wave_spawned       = 0
        wave_transition_timer = 0
        wave_intro_timer   = 120
        game_over          = False
        game_won           = False
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
        dive_timer            = random.randint(200, 350)   # Galaga dive countdown

        # ── Inner game loop ───────────────────────────────────────────────────
        raw_dt = 16  # seed for first frame (~60 fps)
        while running:
            dt_mul = max(1.0, min(3.0, raw_dt * 60.0 / 1000.0))

            bg_x = (bg_x + int(BG_SCROLL_SPEED * dt_mul)) % WIDTH
            screen.blit(background_img, (bg_x, 0))
            screen.blit(background_img, (bg_x - WIDTH, 0))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if continue_timer > 0 and event.type == pygame.KEYDOWN \
                        and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    health = 3
                    game_over = False
                    continue_timer = 0
                    iframe_timer = 180
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE \
                        and not show_upgrade and continue_timer == 0:
                    paused = not paused
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
                        if _pid == 'rapid_fire':    perk_fire_cooldown = max(4, perk_fire_cooldown - 4)
                        elif _pid == 'speed_boost': perk_speed = min(9, perk_speed + 2)
                        elif _pid == 'extra_heart': health = min(8, health + 2)
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
                _cd_secs = max(0, continue_timer // 60)
                screen.blit(_cont_ov, (0, 0))
                _ct = font_big.render('CONTINUE?', True, (255, 220, 50))
                screen.blit(_ct, _ct.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 80)))
                _cn_col = (255, 60, 60) if _cd_secs <= 3 else (255, 200, 60)
                _cn = font_huge.render(str(_cd_secs), True, _cn_col)
                screen.blit(_cn, _cn.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 20)))
                _cpa = int(200 + 55 * abs(math.sin(frame_count * 0.18)))
                _cp = font_med.render('PRESS  SPACE  TO  CONTINUE', True, (200, 200, 255))
                _cp.set_alpha(_cpa)
                screen.blit(_cp, _cp.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 130)))
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
                sprite_rect.clamp_ip(pygame.Rect(0, 0, WIDTH, HEIGHT))
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
                side_fire_timer = max(0, side_fire_timer - 1)
                # Space = shoot up
                if keys[pygame.K_SPACE] and len(fireballs) < 20 and fire_timer == 0:
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
                            and not (p['id'] == 'rapid_fire' and perk_fire_cooldown <= 4)
                            and not (p['id'] == 'speed_boost' and perk_speed >= 9)
                        ]
                        upgrade_choices = random.sample(_perk_pool, k=min(3, len(_perk_pool)))
            elif (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade
                    and wave_spawned >= WAVE_DEFS[wave - 1]['count']
                    and len(enemies) == 0):
                _wave_bonus = 200 * wave  # scales: 200, 400, 600, 800, 1000
                wave_transition_timer = 120
                score += _wave_bonus
            if (not boss_active and not boss_warned and not boss_defeated
                    and not show_upgrade
                    and wave_transition_timer == 0 and wave_intro_timer == 0):
                _eff_count    = WAVE_DEFS[wave - 1]['count']
                _eff_interval = max(5, WAVE_DEFS[wave - 1]['interval'])
                if swarm_active:
                    _eff_interval = max(5, _eff_interval // 2)
                if wave_spawned < _eff_count:
                    enemy_timer += 1
                    if enemy_timer >= _eff_interval:
                        enemies.append([pygame.Rect(random.randint(0, WIDTH - 40), 0, 40, 40),
                                        random.uniform(0, 2 * math.pi), False, None])
                        enemy_timer = 0
                        wave_spawned += 1

            # ── Galaga dive trigger ──────────────────────────────────────────
            dive_timer -= 1
            if dive_timer <= 0 and not boss_active:
                dive_timer = random.randint(200, 360)
                _dcands = [e for e in enemies if not e[2] and e[3] is None and e[0].y > 60]
                for _de in random.sample(_dcands, k=min(2, len(_dcands))):
                    _p1x = sprite_rect.centerx + random.choice([-220, 220])
                    _de[3] = {'t': 0.0,
                              'p0': (float(_de[0].centerx), float(_de[0].centery)),
                              'p1': (float(_p1x), float(HEIGHT * 0.55)),
                              'p2': (float(sprite_rect.centerx + random.randint(-25, 25)),
                                     float(HEIGHT + 60))}
                    score_popups.append({'x': _de[0].centerx, 'y': _de[0].top - 15,
                                         'timer': 35, 'max': 35,
                                         'text': '⚡ DIVE!', 'color': (0, 220, 255)})

            for e in enemies:
                if e[3] is not None:
                    # Galaga dive: quadratic bezier arc
                    _d = e[3]
                    _d['t'] = min(1.0, _d['t'] + 0.011)
                    _t = _d['t']; _mt = 1.0 - _t
                    e[0].centerx = int(_mt*_mt*_d['p0'][0] + 2*_mt*_t*_d['p1'][0] + _t*_t*_d['p2'][0])
                    e[0].centery = int(_mt*_mt*_d['p0'][1] + 2*_mt*_t*_d['p1'][1] + _t*_t*_d['p2'][1])
                elif not e[2] and e[3] is None and e[0].y > 120 and random.random() < 0.0025:
                    e[2] = True
                    score_popups.append({'x': e[0].centerx, 'y': e[0].top - 15,
                                         'timer': 40, 'max': 40,
                                         'text': '\u2620 KAMIKAZE!', 'color': (255, 50, 50)})
                if e[2]:
                    _kdx = sprite_rect.centerx - e[0].centerx
                    _kdy = sprite_rect.centery - e[0].centery
                    _kdist = math.hypot(_kdx, _kdy) or 1
                    _kspd  = WAVE_ENEMY_SPEED[wave - 1] + 3
                    e[0].x += int(_kdx / _kdist * _kspd * dt_mul)
                    e[0].y += int(_kdy / _kdist * _kspd * dt_mul)
                elif e[3] is None:
                    e[0].y += int(WAVE_ENEMY_SPEED[wave - 1] * dt_mul)
                    e[0].x = max(0, min(WIDTH - 40,
                        e[0].x + int(math.sin(frame_count * 0.04 + e[1]) * 1.5 * dt_mul)))
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
            enemies = [e for e in enemies if e[0].top < HEIGHT and e[0].bottom > -60]

            for p in health_pickups:
                p.y += int(dt_mul)
            health_pickups = [p for p in health_pickups if p.top < HEIGHT]
            for p in sativa_pickups:
                p.y += int(2 * dt_mul)
            sativa_pickups = [p for p in sativa_pickups if p.top < HEIGHT]

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
                        score_popups.append({'x': _nmb.centerx, 'y': _nmb.top - 10,
                                             'timer': 30, 'max': 30,
                                             'text': 'NEAR MISS +50', 'color': (100, 255, 255)})
            for _nmab in aimed_bullets:
                if id(_nmab) not in near_miss_ids:
                    _nmab_r = pygame.Rect(int(_nmab['x']) - 4, int(_nmab['y']) - 6, 8, 12)
                    if (math.hypot(_nmab['x'] - _pcx, _nmab['y'] - _pcy) < 38
                            and not _nmab_r.colliderect(sprite_rect)):
                        near_miss_ids.add(id(_nmab))
                        score += 50
                        score_popups.append({'x': int(_nmab['x']), 'y': int(_nmab['y']) - 10,
                                             'timer': 30, 'max': 30,
                                             'text': 'NEAR MISS +50', 'color': (100, 255, 255)})

            if boss_active:
                if not boss_raging and boss_health <= boss_max_health // 2:
                    boss_raging          = True
                    boss_fire_interval   = 20
                    boss_minion_interval = 55
                    shake_timer          = 20
                    boss_rage_flash      = 150
                    score_popups.append({'x': WIDTH // 2, 'y': HEIGHT // 2 - 80,
                                         'timer': 120, 'max': 120,
                                         'text': '☠  RAGE  MODE  ☠', 'color': (255, 40, 40)})
                if not boss_critical and boss_health <= boss_max_health // 4:
                    boss_critical        = True
                    boss_fire_interval   = 12
                    boss_minion_interval = 40
                    shake_timer          = 30
                if not boss_death_spiral and boss_health <= 5:
                    boss_death_spiral    = True
                    boss_fire_interval   = 8
                    shake_timer          = 35
                    score_popups.append({'x': WIDTH // 2, 'y': HEIGHT // 2 - 80,
                                         'timer': 120, 'max': 120,
                                         'text': '\u2620  FINAL STAND  \u2620',
                                         'color': (255, 50, 255)})
                # ── Spawn boss minions ──────────────────────────────────────
                _minion_cap = 6 if boss_raging else 4
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
                    if bm['rect'].top >= 0 and bm['fire_timer'] >= (45 if boss_critical else 58 if boss_raging else 75):
                        bm['fire_timer'] = 0
                        dx = sprite_rect.centerx - bm['rect'].centerx
                        dy = sprite_rect.centery - bm['rect'].centery
                        dist = math.hypot(dx, dy) or 1
                        aimed_bullets.append({
                            'x': float(bm['rect'].centerx),
                            'y': float(bm['rect'].bottom),
                            'vx': dx / dist * BULLET_SPEED,
                            'vy': dy / dist * BULLET_SPEED,
                        })
                boss_minions = [bm for bm in boss_minions if bm['rect'].top < HEIGHT]
                hspeed = 0 if boss_death_spiral else (7 if boss_critical else (5 if boss_raging else 3))
                if boss_rect.top < 50:
                    boss_rect.y += int(boss_speed * dt_mul)
                else:
                    boss_rect.x += int(hspeed * boss_dir * dt_mul)
                    if boss_rect.right >= WIDTH or boss_rect.left <= 0:
                        boss_dir *= -1
                    boss_fire_timer += 1
                    if boss_fire_timer >= boss_fire_interval:
                        boss_fire_timer = 0
                        boss_volley_count += 1
                        cx = boss_rect.centerx
                        by = boss_rect.bottom
                        if boss_death_spiral:
                            boss_spiral_angle += math.pi / 6
                            for _si in range(8):
                                _ang = boss_spiral_angle + _si * (math.pi / 4)
                                aimed_bullets.append({
                                    'x': float(cx), 'y': float(by),
                                    'vx': math.cos(_ang) * BULLET_SPEED * 1.2,
                                    'vy': math.sin(_ang) * BULLET_SPEED * 1.2,
                                })
                            _dx = sprite_rect.centerx - cx
                            _dy = sprite_rect.centery - by
                            _dist = math.hypot(_dx, _dy) or 1
                            aimed_bullets.append({'x': float(cx), 'y': float(by),
                                'vx': _dx / _dist * BULLET_SPEED * 1.5,
                                'vy': _dy / _dist * BULLET_SPEED * 1.5})
                            shake_timer = max(shake_timer, 5)
                        elif boss_critical:
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
                                'vx': _dx / _dist * BULLET_SPEED * 1.3,
                                'vy': _dy / _dist * BULLET_SPEED * 1.3})
                            shake_timer = max(shake_timer, 6)
                        elif boss_raging:
                            # 5-bullet fan
                            boss_bullets += [
                                pygame.Rect(cx - 28, by, 10, 16),
                                pygame.Rect(cx - 14, by, 10, 16),
                                pygame.Rect(cx - 5,  by, 10, 16),
                                pygame.Rect(cx + 9,  by, 10, 16),
                                pygame.Rect(cx + 23, by, 10, 16),
                            ]
                            # aimed shot every other volley
                            if boss_volley_count % 2 == 0:
                                _dx = sprite_rect.centerx - cx
                                _dy = sprite_rect.centery - by
                                _dist = math.hypot(_dx, _dy) or 1
                                aimed_bullets.append({'x': float(cx), 'y': float(by),
                                    'vx': _dx / _dist * BULLET_SPEED,
                                    'vy': _dy / _dist * BULLET_SPEED})
                        else:
                            # 2-bullet spread
                            boss_bullets += [
                                pygame.Rect(cx - 12, by, 10, 16),
                                pygame.Rect(cx + 7,  by, 10, 16),
                            ]

                for b in boss_bullets:
                    b.y += BULLET_SPEED
                boss_bullets = [b for b in boss_bullets if b.y < HEIGHT]

            for f in fireballs[:]:
                for e in enemies[:]:
                    if f.colliderect(e[0]):
                        fireballs.remove(f)
                        enemies.remove(e)
                        wave_kills += 1
                        cx, cy = e[0].centerx, e[0].centery
                        combo += 1
                        combo_timer = 120
                        points = int((200 if e[2] else 100) * combo * WAVE_MULT[wave - 1])
                        score += points
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
                        if not sativa_dropped and wave >= 3:
                            sativa_pickups.append(pygame.Rect(cx - 20, e[0].top, 40, 40))
                            sativa_dropped = True
                        elif random.random() < 0.02:  # 2% rare chance in other waves
                            sativa_pickups.append(pygame.Rect(cx - 20, e[0].top, 40, 40))
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        break

            for f in fireballs[:]:
                for bm in boss_minions[:]:
                    if f.colliderect(bm['rect']):
                        if f in fireballs: fireballs.remove(f)
                        boss_minions.remove(bm)
                        _minion_pts = int(150 * WAVE_MULT[wave - 1])
                        score += _minion_pts
                        score_popups.append({'x': bm['rect'].centerx, 'y': bm['rect'].top,
                                             'timer': 45, 'max': 45,
                                             'text': f'+{_minion_pts}', 'color': (255, 120, 0)})
                        particles += [
                            {'x': float(bm['rect'].centerx), 'y': float(bm['rect'].centery),
                             'vx': random.uniform(-3, 3), 'vy': random.uniform(-3, 3),
                             'life': random.randint(12, 25), 'max': 25,
                             'color': random.choice([(255,180,0),(255,80,0),(200,200,255)])}
                            for _ in range(7)
                        ]
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        break

            for f in fireballs[:]:
                if boss_active and boss_rect.colliderect(f):
                    if f not in fireballs:
                        continue
                    fireballs.remove(f)
                    boss_health -= (2 if perk_power_shot else 1)
                    if impact_sound:
                        impact_channel.play(impact_sound)
                    if boss_health <= 0:
                        boss_active   = False
                        boss_defeated = True
                        score        += int(2000 * WAVE_MULT[wave - 1])
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
                        boss_minions.clear()
                        boss_defeat_timer = 90

            # ── Side bullets vs enemies ──────────────────────────────────────
            for sb in side_bullets[:]:
                _sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
                for e in enemies[:]:
                    if _sbr.colliderect(e[0]):
                        side_bullets.remove(sb)
                        enemies.remove(e)
                        wave_kills += 1
                        cx, cy = e[0].centerx, e[0].centery
                        combo += 1; combo_timer = 120
                        points = int((200 if e[2] else 100) * combo * WAVE_MULT[wave - 1])
                        score += points
                        streak_count += 1; streak_timer = 90
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
                            'color': (0, 220, 255)})
                        particles += [
                            {'x': float(cx), 'y': float(cy),
                             'vx': random.uniform(-4, 4), 'vy': random.uniform(-4, 4),
                             'life': random.randint(15, 30), 'max': 30,
                             'color': random.choice([(0,200,255),(0,150,255),(100,230,255)])}
                            for _ in range(8)
                        ]
                        if random.random() < (PICKUP_DROP_CHANCE * 2 if perk_lucky_drop else PICKUP_DROP_CHANCE):
                            health_pickups.append(pygame.Rect(cx - 8, e[0].top, 16, 16))
                        if not sativa_dropped and wave >= 3:
                            sativa_pickups.append(pygame.Rect(cx - 20, e[0].top, 40, 40))
                            sativa_dropped = True
                        elif random.random() < 0.02:
                            sativa_pickups.append(pygame.Rect(cx - 20, e[0].top, 40, 40))
                        if impact_sound: impact_channel.play(impact_sound)
                        break
            for sb in side_bullets[:]:
                _sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
                for bm in boss_minions[:]:
                    if _sbr.colliderect(bm['rect']):
                        if sb in side_bullets: side_bullets.remove(sb)
                        boss_minions.remove(bm)
                        _minion_pts = int(150 * WAVE_MULT[wave - 1])
                        score += _minion_pts
                        score_popups.append({'x': bm['rect'].centerx, 'y': bm['rect'].top,
                                             'timer': 45, 'max': 45,
                                             'text': f'+{_minion_pts}', 'color': (0, 220, 255)})
                        particles += [
                            {'x': float(bm['rect'].centerx), 'y': float(bm['rect'].centery),
                             'vx': random.uniform(-3, 3), 'vy': random.uniform(-3, 3),
                             'life': random.randint(12, 25), 'max': 25,
                             'color': random.choice([(0,200,255),(0,150,255),(255,180,0)])}
                            for _ in range(7)
                        ]
                        if impact_sound: impact_channel.play(impact_sound)
                        break
            for sb in side_bullets[:]:
                _sbr = pygame.Rect(int(sb['x']) - 8, int(sb['y']) - 4, 16, 8)
                if boss_active and boss_rect.colliderect(_sbr):
                    if sb not in side_bullets:
                        continue
                    side_bullets.remove(sb)
                    boss_health -= (2 if perk_power_shot else 1)
                    if impact_sound: impact_channel.play(impact_sound)
                    if boss_health <= 0:
                        boss_active = False; boss_defeated = True
                        score += int(2000 * WAVE_MULT[wave - 1])
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
                        boss_minions.clear()
                        boss_defeat_timer = 90

            for e in enemies[:]:
                if e[0].colliderect(sprite_rect):
                    enemies.remove(e)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        chroma_timer    = 12
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            continue_timer = 600

            for b in enemy_bullets[:]:
                if b.colliderect(sprite_rect):
                    enemy_bullets.remove(b)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        chroma_timer    = 12
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            continue_timer = 600

            for ab in aimed_bullets[:]:
                abr = pygame.Rect(int(ab['x']) - 4, int(ab['y']) - 6, 8, 12)
                if abr.colliderect(sprite_rect):
                    aimed_bullets.remove(ab)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        chroma_timer    = 12
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            continue_timer = 600

            for bm in boss_minions[:]:
                if bm['rect'].colliderect(sprite_rect):
                    boss_minions.remove(bm)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        chroma_timer    = 12
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            continue_timer = 600

            for b in boss_bullets[:]:
                if b.colliderect(sprite_rect):
                    boss_bullets.remove(b)
                    if iframe_timer == 0:
                        health -= 1
                        shake_timer     = 10
                        hit_flash_timer = 8
                        chroma_timer    = 12
                        iframe_timer = IFRAME_DURATION
                        if impact_sound:
                            impact_channel.play(impact_sound)
                        if health <= 0:
                            game_over = True
                            continue_timer = 600

            for p in health_pickups[:]:
                if p.colliderect(sprite_rect):
                    health_pickups.remove(p)
                    health = min(health + 1, 8)
                    score_popups.append({'x': sprite_rect.centerx, 'y': sprite_rect.top,
                                         'timer': 45, 'max': 45,
                                         'text': '+1 HP', 'color': (0, 255, 80)})
                    if powerup_sound:
                        pygame.mixer.find_channel(True).play(powerup_sound)
            for p in sativa_pickups[:]:
                if p.colliderect(sprite_rect):
                    sativa_pickups.remove(p)
                    health = 8  # full heal on sativa pickup
                    sativa_active = True
                    sativa_timer  = 600
                    iframe_timer  = 300  # 5 seconds invincibility
                    score_popups.append({'x': sprite_rect.centerx, 'y': sprite_rect.top - 20,
                                         'timer': 75, 'max': 75,
                                         'text': '★ SATIVA MODE ★', 'color': (0, 255, 120)})
                    if sativa_sound:
                        sativa_sound.play()

            if iframe_timer == 0 or iframe_timer % 8 < 4:
                if beat_pulse > 0 or sativa_active:
                    _bp_t    = beat_pulse / BEAT_PULSE_FRAMES if beat_pulse > 0 else 1.0
                    _scale_m = 0.45 if sativa_active else 0.18
                    _bp_s    = 1.0 + _scale_m * _bp_t
                    # Cache scaled sprite: round to nearest 2% to avoid per-frame alloc
                    _bp_key  = round(_bp_s * 50) / 50
                    _bp_w    = int(sprite_rect.width  * _bp_key)
                    _bp_h    = int(sprite_rect.height * _bp_key)
                    if _scale_cache['key'] != _bp_key:
                        _scale_cache['key']  = _bp_key
                        _scale_cache['surf'] = pygame.transform.scale(sprite_image, (_bp_w, _bp_h))
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
                    screen.blit(sprite_image, sprite_rect)
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
                if _fb_col is not _COL_FIREBALL:
                    _fb_glow_surf.fill((*_fb_col, 80))
                    screen.blit(_fb_glow_surf, (f.x - 4, f.y - 4))
                pygame.draw.rect(screen, _fb_col, f)
            for sb in side_bullets:
                _sbc = (0, 220, 255) if not sativa_active else (0, 255, 180)
                pygame.draw.rect(screen, _sbc, (int(sb['x']) - 8, int(sb['y']) - 4, 16, 8))
            for e in enemies:
                screen.blit(drone_image, e[0])
                if e[2] and frame_count % 8 < 4:
                    screen.blit(_kflash_surf, e[0])
                elif e[3] is not None and frame_count % 6 < 3:
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
            # Hard cap: keep the most recently added 300 particles
            particles = next_particles[-300:]
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
                if sativa_image:
                    screen.blit(sativa_image, p)
                else:
                    pygame.draw.rect(screen, (0, 255, 120), p)
                # pulsing green border
                _sa_b = int(80 + 80 * math.sin(frame_count * 0.15))
                pygame.draw.rect(screen, (0, _sa_b, 60), p, 2)

            if boss_active:
                screen.blit(boss_image, boss_rect)
                if boss_raging:
                    _boss_tint_surf.fill((255, 0, 0, int(50 + 30 * math.sin(frame_count * 0.2))))
                    screen.blit(_boss_tint_surf, boss_rect.topleft)
                    # Static pre-built vignette — just blit, no per-frame rebuild
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
                    if 'surf' not in pop:
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
            _hs_key = f"{high_score_name}{high_score}"
            if _hs_cache['val'] != _hs_key:
                _hs_cache['val'] = _hs_key
                _hs_cache['surf'] = font.render(f"Best: {high_score_name}  {high_score:,}", True, (180, 180, 180))
            screen.blit(_hs_cache['surf'], _hs_cache['surf'].get_rect(right=WIDTH - 10, y=10))
            if not boss_active and not boss_warned and not boss_defeated:
                if _wave_cache['val'] != wave:
                    _wave_cache['val'] = wave
                    _wave_cache['surf'] = font.render(f"WAVE  {wave} / 5", True, (150, 200, 255))
                screen.blit(_wave_cache['surf'], _wave_cache['surf'].get_rect(centerx=WIDTH // 2, y=10))
            for i in range(8):
                screen.blit(_heart_red_h if i < health else _heart_grey_h, (10 + i * 26, 40))
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
                ox = random.randint(-6, 6)
                oy = random.randint(-6, 6)
                _shake_surf.blit(screen, (0, 0))
                screen.fill((0, 0, 0))
                screen.blit(_shake_surf, (ox, oy))

            # ── Screen overlays (applied after shake for stability) ─────────────
            if hit_flash_timer > 0:
                hit_flash_timer -= 1
                _hf_surf.fill((255, 0, 0, int(110 * hit_flash_timer / 8)))
                screen.blit(_hf_surf, (0, 0))

            if health == 1 and not game_over:
                pa = int(55 + 35 * math.sin(frame_count * 0.12))
                _lh_surf.fill((0, 0, 0, 0))
                bw = 55
                for r in [(0, 0, WIDTH, bw), (0, HEIGHT - bw, WIDTH, bw),
                           (0, 0, bw, HEIGHT), (WIDTH - bw, 0, bw, HEIGHT)]:
                    pygame.draw.rect(_lh_surf, (255, 0, 0, pa), r)
                screen.blit(_lh_surf, (0, 0))

            if boss_rage_flash > 0:
                boss_rage_flash -= 1
                _bra = min(255, int(boss_rage_flash * 3.4))
                _brage_surf.set_alpha(_bra)
                screen.blit(_brage_surf, _brage_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 55)))

            if boss_warning_timer > 0:
                wa = int(35 * abs(math.sin(frame_count * 0.15)))
                _warn_surf.fill((180, 0, 0, wa))
                screen.blit(_warn_surf, (0, 0))
                wt_alpha = int(255 * abs(math.sin(frame_count * 0.2)))
                _warn_text_surf.set_alpha(wt_alpha)
                screen.blit(_warn_text_surf, _warn_text_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))

            if wave_intro_timer > 0:
                if wave_intro_timer > 70:
                    # ── Phase 1: PLAYER 1 GET READY ──────────────────────────
                    _rphase = wave_intro_timer - 70          # 1..50
                    _rfade  = min(255, int(_rphase * 5.1))   # fade-in over first 10f
                    _rpulse = int(220 + 35 * abs(math.sin(frame_count * 0.22)))
                    _rcol   = (255, _rpulse, 0)              # pulsing arcade yellow
                    _r1 = font_big.render('PLAYER 1', True, _rcol)
                    _r1.set_alpha(_rfade)
                    screen.blit(_r1, _r1.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 38)))
                    _r2 = font_big.render('GET  READY!', True, (255, 255, 255))
                    _r2.set_alpha(_rfade)
                    screen.blit(_r2, _r2.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 22)))
                else:
                    # ── Phase 2: Wave banner ──────────────────────────────────
                    wi_alpha = min(255, wave_intro_timer * 4)
                    wi = font_big.render(f'- WAVE  {wave} -', True, (100, 200, 255))
                    wi.set_alpha(wi_alpha)
                    screen.blit(wi, wi.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))
                    wm = font_med.render(['1×', '1.5×', '2×', '2.5×', '3×'][wave - 1] + '  SCORE MULTIPLIER', True, (255, 220, 100))
                    wm.set_alpha(wi_alpha)
                    screen.blit(wm, wm.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 25)))

            if wave_transition_timer > 0 and not boss_warned:
                _wta = min(210, wave_transition_timer * 3)
                _wtov_surf.fill((0, 0, 15, _wta))
                screen.blit(_wtov_surf, (0, 0))
                _wca = min(255, wave_transition_timer * 4)
                _wc1 = font_big.render(f'WAVE  {wave}  COMPLETE!', True, (100, 255, 120))
                _wc1.set_alpha(_wca)
                screen.blit(_wc1, _wc1.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 70)))
                _wc2 = font_med.render(f'DRONES  ELIMINATED:   {wave_kills}', True, (255, 220, 100))
                _wc2.set_alpha(_wca)
                screen.blit(_wc2, _wc2.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
                _wc3 = font_med.render(f'WAVE  BONUS:   +{200 * wave}', True, (0, 200, 255))
                _wc3.set_alpha(_wca)
                screen.blit(_wc3, _wc3.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 55)))

            # ── Drone swarm banner ────────────────────────────────────────────
            if swarm_msg_timer > 0:
                swarm_msg_timer -= 1
                _swa = min(255, swarm_msg_timer * 6)
                _swarm_text_surf.set_alpha(_swa)
                screen.blit(_swarm_text_surf, _swarm_text_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 110)))

            if boss_defeat_timer > 0:
                boss_defeat_timer -= 1
                fa = int(220 * boss_defeat_timer / 90)
                _defeat_surf.fill((255, 255, 255, fa))
                screen.blit(_defeat_surf, (0, 0))
                vt_alpha = min(255, int(255 * (1.0 - boss_defeat_timer / 90.0) * 3.0))
                vt = font_big.render('VICTORY!', True, (255, 220, 0))
                vt.set_alpha(vt_alpha)
                screen.blit(vt, vt.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
                if boss_defeat_timer == 0:
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
            if chroma_timer > 0:
                chroma_timer -= 1
                _ca   = int(80 * chroma_timer / 12)
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
                place=_earned_place + 1, scores=scores, new_score=score)
            scores.insert(_earned_place, [score, _new_name])
            scores = scores[:3]
            high_score      = scores[0][0]
            high_score_name = scores[0][1]
            try:
                with open(hs_file, 'w') as _f:
                    _f.write('\n'.join(f'{s[0]} {s[1]}' for s in scores))
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
            action = _result_screen(screen, clock, result_img, music_file, score, scores)
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
