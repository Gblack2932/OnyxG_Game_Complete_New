import os

# macOS + Xbox Series X controllers can be detected by SDL HIDAPI while
# reporting no live buttons/axes. Disable HIDAPI before pygame/SDL loads so
# SDL falls back to the macOS joystick backend that delivers input.
os.environ.setdefault("SDL_JOYSTICK_HIDAPI", "0")

from onyxg_vs_cranium import main


if __name__ == "__main__":
    main()
