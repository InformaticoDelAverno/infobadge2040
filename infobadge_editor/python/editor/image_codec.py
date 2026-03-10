from PIL import Image

from .color_utils import nearest_palette_index
from .config import PALETTE


def quantize_to_palette(img):
    """
    Convierte una imagen RGB cualquiera a la paleta de 4 colores del badge.
    """
    src = img.convert("RGB")
    out = Image.new("RGB", src.size)
    src_px = src.load()
    out_px = out.load()

    for y in range(src.height):
        for x in range(src.width):
            out_px[x, y] = PALETTE[nearest_palette_index(src_px[x, y])]

    return out


def pack_2bpp(img, width, height):
    """
    Empaqueta la imagen en 2 bits por pixel:
    - 4 pixeles por byte
    - bits [7:6]   = pixel 0
    - bits [5:4]   = pixel 1
    - bits [3:2]   = pixel 2
    - bits [1:0]   = pixel 3
    """
    rgb = quantize_to_palette(img.resize((width, height), Image.Resampling.LANCZOS))
    px = rgb.load()
    packed = bytearray((width * height + 3) // 4)

    for i in range(width * height):
        x = i % width
        y = i // width
        idx = nearest_palette_index(px[x, y])
        shift = (3 - (i & 0x03)) * 2
        packed[i >> 2] |= (idx & 0x03) << shift

    return bytes(packed)
