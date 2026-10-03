import os
import sys

# Same macOS Xbox workaround used by the game: force SDL away from the
# HIDAPI path that can detect the pad but return only zero-valued input.
os.environ.setdefault("SDL_JOYSTICK_HIDAPI", "0")

import pygame

try:
    from pygame._sdl2 import controller as gc
except Exception as exc:
    print("SDL2 controller import failed:", exc)
    raise

pygame.init()
pygame.joystick.init()
gc.init()
gc.set_eventstate(True)

W, H = 980, 700
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Onyx G - SDL2 Xbox Live Test")
clock = pygame.time.Clock()

font = pygame.font.SysFont("Arial", 25, bold=True)
small = pygame.font.SysFont("Menlo", 17)

AXES = [
    ("LEFT X", pygame.CONTROLLER_AXIS_LEFTX),
    ("LEFT Y", pygame.CONTROLLER_AXIS_LEFTY),
    ("RIGHT X", pygame.CONTROLLER_AXIS_RIGHTX),
    ("RIGHT Y", pygame.CONTROLLER_AXIS_RIGHTY),
    ("LT", pygame.CONTROLLER_AXIS_TRIGGERLEFT),
    ("RT", pygame.CONTROLLER_AXIS_TRIGGERRIGHT),
]

BUTTONS = [
    ("A", pygame.CONTROLLER_BUTTON_A),
    ("B", pygame.CONTROLLER_BUTTON_B),
    ("X", pygame.CONTROLLER_BUTTON_X),
    ("Y", pygame.CONTROLLER_BUTTON_Y),
    ("BACK", pygame.CONTROLLER_BUTTON_BACK),
    ("GUIDE", pygame.CONTROLLER_BUTTON_GUIDE),
    ("START", pygame.CONTROLLER_BUTTON_START),
    ("L3", pygame.CONTROLLER_BUTTON_LEFTSTICK),
    ("R3", pygame.CONTROLLER_BUTTON_RIGHTSTICK),
    ("LB", pygame.CONTROLLER_BUTTON_LEFTSHOULDER),
    ("RB", pygame.CONTROLLER_BUTTON_RIGHTSHOULDER),
    ("DPAD UP", pygame.CONTROLLER_BUTTON_DPAD_UP),
    ("DPAD DOWN", pygame.CONTROLLER_BUTTON_DPAD_DOWN),
    ("DPAD LEFT", pygame.CONTROLLER_BUTTON_DPAD_LEFT),
    ("DPAD RIGHT", pygame.CONTROLLER_BUTTON_DPAD_RIGHT),
]

print("Pygame:", pygame.version.ver, "SDL:", pygame.get_sdl_version())
print("SDL controller count:", gc.get_count())

controller = None
for i in range(gc.get_count()):
    ok = gc.is_controller(i)
    print(f"index {i}: is_controller={ok}, name={gc.name_forindex(i)}")
    if ok and controller is None:
        controller = gc.Controller(i)

if controller is None:
    print("NO SDL2 GAME CONTROLLER FOUND")
    sys.exit(1)

print("Controller mapping:", controller.get_mapping())
print("\nPress buttons and move sticks. Changes will print below.\n")

last_axes = {}
last_buttons = {}
recent = []

def line(text, x, y, color=(235,235,245)):
    surf = small.render(text, True, color)
    screen.blit(surf, (x, y))

running = True
while running:
    # Pump the SDL event queue every frame.
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        elif event.type in (
            pygame.CONTROLLERAXISMOTION,
            pygame.CONTROLLERBUTTONDOWN,
            pygame.CONTROLLERBUTTONUP,
            pygame.CONTROLLERDEVICEADDED,
            pygame.CONTROLLERDEVICEREMOVED,
            pygame.CONTROLLERDEVICEREMAPPED,
        ):
            msg = f"EVENT {pygame.event.event_name(event.type)}: {event}"
            print(msg)
            recent.append(msg)
            recent = recent[-8:]

    axes = {}
    for name, const in AXES:
        try:
            raw = controller.get_axis(const)
        except Exception as exc:
            raw = f"ERR:{exc}"
        axes[name] = raw
        if last_axes.get(name) != raw:
            if isinstance(raw, int) and abs(raw) > 1000:
                print(f"AXIS {name}: {raw}")
            last_axes[name] = raw

    buttons = {}
    for name, const in BUTTONS:
        try:
            pressed = bool(controller.get_button(const))
        except Exception as exc:
            pressed = False
            recent.append(f"BUTTON {name} ERROR: {exc}")
        buttons[name] = pressed
        if last_buttons.get(name) != pressed:
            if pressed:
                print(f"BUTTON {name}: PRESSED")
            last_buttons[name] = pressed

    screen.fill((10, 9, 22))
    title = font.render("SDL2 Xbox Controller - Live Input Test", True, (230, 215, 255))
    screen.blit(title, (28, 22))

    line(f"Controller: {gc.name_forindex(0)}", 28, 70, (255,230,150))
    line("Move the LEFT STICK and press A. Values must change live.", 28, 102, (150,255,180))

    y = 150
    line("AXES", 28, y, (190,170,255))
    y += 30
    for name, _ in AXES:
        raw = axes[name]
        active = isinstance(raw, int) and abs(raw) > 1000
        line(f"{name:8}  {str(raw):>8}", 28, y, (110,255,150) if active else (215,215,225))
        y += 27

    x2 = 360
    y2 = 150
    line("BUTTONS", x2, y2, (190,170,255))
    y2 += 30
    for name, _ in BUTTONS:
        pressed = buttons[name]
        line(f"{name:12} {'PRESSED' if pressed else '-'}", x2, y2,
             (110,255,150) if pressed else (215,215,225))
        y2 += 27

    line("RECENT SDL EVENTS", 28, 510, (190,170,255))
    yy = 540
    for msg in recent[-5:]:
        line(msg[:115], 28, yy, (190,200,220))
        yy += 25

    line("ESC quits.", 28, H - 34, (150,150,165))
    pygame.display.flip()
    clock.tick(60)

controller.quit()
gc.quit()
pygame.quit()
