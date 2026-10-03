import sys
import pygame

pygame.init()
pygame.joystick.init()

W, H = 900, 560
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Onyx G - Xbox Controller Test")
clock = pygame.time.Clock()

font = pygame.font.SysFont("Arial", 24, bold=True)
small = pygame.font.SysFont("Arial", 18)

def draw_line(text, y, color=(235, 235, 245)):
    surf = small.render(text, True, color)
    screen.blit(surf, (28, y))

def snapshot(js):
    axes = [round(js.get_axis(i), 2) for i in range(js.get_numaxes())]
    buttons = [js.get_button(i) for i in range(js.get_numbuttons())]
    hats = [js.get_hat(i) for i in range(js.get_numhats())]
    return axes, buttons, hats

def open_joysticks():
    found = []
    count = pygame.joystick.get_count()
    print(f"\nPygame {pygame.version.ver}")
    print(f"Joystick count: {count}")
    for i in range(count):
        js = pygame.joystick.Joystick(i)
        js.init()
        found.append(js)
        print(f"\nController {i}: {js.get_name()}")
        print(f"  GUID: {js.get_guid() if hasattr(js, 'get_guid') else 'n/a'}")
        print(f"  axes={js.get_numaxes()} buttons={js.get_numbuttons()} hats={js.get_numhats()}")
    if not found:
        print("\nNO CONTROLLER DETECTED BY PYGAME.")
        print("Leave this window open, connect/pair the controller, then press any controller button.")
    return found

joysticks = open_joysticks()
last = {}
recent_events = []

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            continue

        name = pygame.event.event_name(event.type)

        if event.type == pygame.JOYDEVICEADDED:
            print(f"JOYDEVICEADDED device_index={event.device_index}")
            joysticks = open_joysticks()
            last.clear()
        elif event.type == pygame.JOYDEVICEREMOVED:
            print(f"JOYDEVICEREMOVED instance_id={getattr(event, 'instance_id', '?')}")
            joysticks = open_joysticks()
            last.clear()

        if (
            "Joy" in name
            or "Controller" in name
            or event.type in (
                getattr(pygame, "JOYAXISMOTION", -1),
                getattr(pygame, "JOYBUTTONDOWN", -1),
                getattr(pygame, "JOYBUTTONUP", -1),
                getattr(pygame, "JOYHATMOTION", -1),
            )
        ):
            msg = f"{name}: {event}"
            print(msg)
            recent_events.append(msg)
            recent_events = recent_events[-8:]

    screen.fill((10, 9, 22))
    title = font.render("Xbox Controller Diagnostic", True, (225, 210, 255))
    screen.blit(title, (28, 22))

    if not joysticks:
        draw_line("Pygame sees 0 controllers.", 72, (255, 110, 110))
        draw_line("Keep this window open, pair/connect the Xbox controller, then press buttons.", 108)
        draw_line("If this stays at 0, the issue is Mac/Pygame detection — not the game controls.", 138)
    else:
        y = 72
        draw_line(f"Pygame sees {len(joysticks)} controller(s).", y, (110, 255, 150))
        y += 36
        for idx, js in enumerate(joysticks):
            try:
                axes, buttons, hats = snapshot(js)
            except pygame.error:
                continue

            key = js.get_instance_id()
            prev = last.get(key)
            if prev != (axes, buttons, hats):
                print(f"POLL {idx}: axes={axes} buttons={buttons} hats={hats}")
                last[key] = (axes, buttons, hats)

            draw_line(f"[{idx}] {js.get_name()}", y, (255, 230, 150))
            y += 28
            draw_line(f"axes: {axes}", y)
            y += 28
            draw_line(f"buttons: {buttons}", y)
            y += 28
            draw_line(f"hats: {hats}", y)
            y += 42

    draw_line("Recent input events:", 390, (190, 170, 255))
    y = 420
    for msg in recent_events[-5:]:
        draw_line(msg[:105], y, (190, 200, 220))
        y += 24

    draw_line("Press ESC to quit.", H - 34, (150, 150, 165))

    keys = pygame.key.get_pressed()
    if keys[pygame.K_ESCAPE]:
        running = False

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
