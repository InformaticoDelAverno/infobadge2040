RESOLUTION_OPTIONS = [
    ("296x128", 296, 128),
    ("384x168", 384, 168),
]

SCALE = 1

BAUDRATE = 115200
MAGIC = b"IBF1"
FORMAT_2BPP = 0

SERIAL_READY_TIMEOUT = 8.0
SERIAL_ACK_TIMEOUT = 130.0
SERIAL_READ_TIMEOUT = 0.5

PALETTE = [
    (255, 255, 255),  # 0 = white
    (0, 0, 0),        # 1 = black
    (255, 0, 0),      # 2 = red
    (255, 255, 0),    # 3 = yellow
]

BADGE_COLORS = [
    ("White", "#ffffff"),
    ("Black", "#000000"),
    ("Red", "#ff0000"),
    ("Yellow", "#ffff00"),
]

BADGE_COLOR_NAME_TO_HEX = {name: value for name, value in BADGE_COLORS}
