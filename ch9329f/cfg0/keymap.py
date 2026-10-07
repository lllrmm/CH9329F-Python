from __future__ import annotations


MODIFIERS = {
    "ctrl": 0x01,
    "lctrl": 0x01,
    "shift": 0x02,
    "lshift": 0x02,
    "alt": 0x04,
    "lalt": 0x04,
    "win": 0x08,
    "gui": 0x08,
    "lwin": 0x08,
    "lgui": 0x08,
    "rctrl": 0x10,
    "rshift": 0x20,
    "ralt": 0x40,
    "rwin": 0x80,
    "rgui": 0x80,
}

KEYS = {
    "enter": 0x28,
    "return": 0x28,
    "esc": 0x29,
    "escape": 0x29,
    "backspace": 0x2A,
    "tab": 0x2B,
    "space": 0x2C,
    "capslock": 0x39,
    "printscreen": 0x46,
    "scrolllock": 0x47,
    "pause": 0x48,
    "insert": 0x49,
    "home": 0x4A,
    "pageup": 0x4B,
    "delete": 0x4C,
    "end": 0x4D,
    "pagedown": 0x4E,
    "right": 0x4F,
    "left": 0x50,
    "down": 0x51,
    "up": 0x52,
    "numlock": 0x53,
    "menu": 0x65,
}
KEYS.update({chr(ord("a") + i): 0x04 + i for i in range(26)})
KEYS.update({str(i): 0x27 if i == 0 else 0x1D + i for i in range(10)})
KEYS.update({f"f{i}": 0x39 + i for i in range(1, 13)})

# US keyboard layout: character -> (modifier, HID key code).
CHAR_KEYS: dict[str, tuple[int, int]] = {}
for letter in "abcdefghijklmnopqrstuvwxyz":
    CHAR_KEYS[letter] = (0, KEYS[letter])
    CHAR_KEYS[letter.upper()] = (MODIFIERS["shift"], KEYS[letter])
for digit in "0123456789":
    CHAR_KEYS[digit] = (0, KEYS[digit])

for plain, shifted, code in (
    ("`", "~", 0x35),
    ("1", "!", 0x1E),
    ("2", "@", 0x1F),
    ("3", "#", 0x20),
    ("4", "$", 0x21),
    ("5", "%", 0x22),
    ("6", "^", 0x23),
    ("7", "&", 0x24),
    ("8", "*", 0x25),
    ("9", "(", 0x26),
    ("0", ")", 0x27),
    ("-", "_", 0x2D),
    ("=", "+", 0x2E),
    ("[", "{", 0x2F),
    ("]", "}", 0x30),
    ("\\", "|", 0x31),
    (";", ":", 0x33),
    ("'", '"', 0x34),
    (",", "<", 0x36),
    (".", ">", 0x37),
    ("/", "?", 0x38),
):
    CHAR_KEYS[plain] = (0, code)
    CHAR_KEYS[shifted] = (MODIFIERS["shift"], code)

CHAR_KEYS.update(
    {
        " ": (0, KEYS["space"]),
        "\t": (0, KEYS["tab"]),
        "\n": (0, KEYS["enter"]),
        "\r": (0, KEYS["enter"]),
    }
)


def parse_combo(spec: str) -> tuple[int, list[int]]:
    modifier = 0
    keycodes: list[int] = []
    for token in (part.strip().lower() for part in spec.split("+")):
        if not token:
            continue
        if token in MODIFIERS:
            modifier |= MODIFIERS[token]
        elif token in KEYS:
            keycodes.append(KEYS[token])
        elif len(token) == 1 and token in CHAR_KEYS:
            extra_modifier, keycode = CHAR_KEYS[token]
            modifier |= extra_modifier
            keycodes.append(keycode)
        else:
            raise ValueError(f"unknown key: {token}")
    if not modifier and not keycodes:
        raise ValueError("no keys specified")
    if len(keycodes) > 6:
        raise ValueError("a keyboard report supports at most 6 regular keys")
    return modifier, keycodes
