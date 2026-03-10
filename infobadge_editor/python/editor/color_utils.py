from PIL import ImageColor

from .config import BADGE_COLORS, PALETTE


def nearest_palette_index(rgb):
    """Devuelve el indice de la paleta mas cercano a un color RGB."""
    r, g, b = rgb
    best_i = 0
    best_d = 10**18

    for i, (pr, pg, pb) in enumerate(PALETTE):
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_d:
            best_d = d
            best_i = i

    return best_i


def tk_to_hex(color):
    if isinstance(color, tuple):
        return "#%02x%02x%02x" % color
    return str(color).lower()


def normalize_badge_hex(color):
    """Fuerza cualquier color a uno de los 4 colores reales del badge."""
    color = tk_to_hex(color)
    try:
        rgb = ImageColor.getrgb(color)
    except Exception:
        rgb = PALETTE[0]

    idx = nearest_palette_index(rgb)
    return "#%02x%02x%02x" % PALETTE[idx]


def hex_to_badge_label(color):
    color = normalize_badge_hex(color)
    for name, value in BADGE_COLORS:
        if value == color:
            return name
    return "White"
