# -*- coding: UTF-8 -*-
"""
Pure colour maths for the Revit MCP — no Revit, no pyRevit, no CLR.

Why this file exists
--------------------
Every module under ``revit_mcp/`` imports ``pyrevit``, ``Autodesk`` or
``System`` at the top, so none of them can even be *imported* outside Revit —
which means none of their logic could be tested. Stubbing the CLR would be a
large fiction, and the kind that buys false confidence.

The honest split is this one: the *arithmetic* that turns a count or a
position into RGB never needed Revit at all. It lives here, is covered by the
suite that runs on any machine, and ``colors.py`` wraps the results into
``DB.Color`` — which is the only part that genuinely needs the Revit API.

Everything here returns plain ``(r, g, b)`` tuples of ints in 0..255.
"""

# Visually distinct base colours, in the order they are handed out.
BASE_COLORS = [
    (255, 0, 0),  # Red
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (255, 255, 0),  # Yellow
    (255, 0, 255),  # Magenta
    (0, 255, 255),  # Cyan
    (255, 128, 0),  # Orange
    (128, 0, 255),  # Purple
    (255, 128, 128),  # Pink
    (128, 255, 128),  # Light Green
    (128, 128, 255),  # Light Blue
    (255, 255, 128),  # Light Yellow
    (128, 0, 0),  # Dark Red
    (0, 128, 0),  # Dark Green
    (0, 0, 128),  # Dark Blue
    (128, 128, 0),  # Olive
    (128, 0, 128),  # Dark Magenta
    (0, 128, 128),  # Teal
    (192, 192, 192),  # Silver
    (128, 128, 128),  # Gray
    (255, 192, 203),  # Light Pink
    (255, 165, 0),  # Orange Red
    (255, 20, 147),  # Deep Pink
    (50, 205, 50),  # Lime Green
    (30, 144, 255),  # Dodger Blue
]

# Past the base list, each further cycle is dimmed by this much...
CYCLE_DIMMING = 0.15
# ...but never below this, or the "distinct" colours all become black.
MIN_BRIGHTNESS = 0.3


def distinct_rgb(count):
    """``count`` visually distinct RGB triples.

    Beyond ``len(BASE_COLORS)`` the list cycles, dimming each round, so the
    26th colour is a darker Red rather than a repeat of Red.
    """
    out = []
    for i in range(count):
        if i < len(BASE_COLORS):
            out.append(BASE_COLORS[i])
            continue
        r, g, b = BASE_COLORS[i % len(BASE_COLORS)]
        cycle = i // len(BASE_COLORS)
        factor = max(MIN_BRIGHTNESS, 1.0 - (cycle * CYCLE_DIMMING))
        out.append((int(r * factor), int(g * factor), int(b * factor)))
    return out


def interpolate_rgb(position):
    """Blue → green → red, for ``position`` in 0.0..1.0 (clamped)."""
    position = max(0.0, min(1.0, position))
    return (
        int(255 * position),
        int(255 * (1 - abs(2 * position - 1))),  # peaks in the middle
        int(255 * (1 - position)),
    )


def gradient_rgb(count):
    """``count`` steps of the same gradient, ends included.

    A single step is red, not blue: it is the "top of the scale" colour, and a
    one-element legend showing the cold end would read as "nothing here".
    """
    if count <= 1:
        return [(255, 0, 0)]
    return [interpolate_rgb(float(i) / (count - 1)) for i in range(count)]


def hex_to_rgb(hex_color, fallback=(255, 0, 0)):
    """``"#FF0000"`` or ``"FF0000"`` → ``(255, 0, 0)``.

    Anything unparseable returns ``fallback`` instead of raising: this is fed
    by user input, and a colour that cannot be read must not take down a run
    that had already coloured elements.
    """
    texto = str(hex_color).lstrip("#")
    try:
        return tuple(int(texto[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return fallback


def safe_float(value_str):
    """Value for SORTING — never raises, and unsortable goes last.

    Accepts a unit suffix (``"3.5 m"``, ``"120mm"``) by trimming the trailing
    non-numeric characters. Empty, ``None`` and anything that still will not
    parse become ``inf``, which puts them at the end of an ascending sort
    instead of at the front, where they would look like the smallest value.
    """
    if not value_str or value_str == "None":
        return float("inf")
    limpo = str(value_str).strip()
    sufixo = 0
    for char in reversed(limpo):
        # ``isdecimal``, not ``isdigit``: in Python 3 ``"²".isdigit()`` is
        # True. With ``isdigit`` the scan stopped on the ² of ``"15 m²"``,
        # trimmed nothing, failed to parse and returned ``inf`` — so a room
        # area written in the unit architects actually use sorted as if it had
        # never been measured. Superscripts are digits; they are not decimals.
        if char.isdecimal() or char in ".-+":
            break
        sufixo += 1
    try:
        return float(limpo[:-sufixo] if sufixo else limpo)
    except (ValueError, TypeError):
        return float("inf")
