# InfoBadge Editor

`infobadge_editor/` contains the visual editor workflow used to build full-screen badge layouts and send them to the badge firmware over serial.

## Purpose

This editor is designed for the editor firmware variant in:
- `infobadge_editor/fw/infobadge_editor_GDEY029F51H/`
- `infobadge_editor/fw/infobadge_editor_GDEY029F52/`

Those firmware variants receive a full framebuffer and render it on their matching panel.

## Folder Structure

- `fw/infobadge_editor_GDEY029F51H/` - Editor firmware for GDEY029F51H
- `fw/infobadge_editor_GDEY029F52/` - Editor firmware for GDEY029F52
- `python/infobadge_editor.py` - Python launcher script
- `python/editor/` - Modular Python editor package (UI, codec, colors, fonts, config)
- `python/designs/` - Saved design files (`.ibadge.json`)
- `python/fonts/` - Local TTF/OTF fonts shown first in the editor font list

## Firmware Compatibility

| Display model | Resolution | Editor firmware |
| --- | --- | --- |
| `GDEY029F51H` | `384x168` | `infobadge_editor/fw/infobadge_editor_GDEY029F51H/infobadge_editor.ino` |
| `GDEY029F52` | `296x128` | `infobadge_editor/fw/infobadge_editor_GDEY029F52/infobadge_editor.ino` |

## Python Requirements

Install dependencies from:
- `python/requirements.txt`

Example:

```bash
cd infobadge_editor/python
pip install -r requirements.txt
```

## Running the Editor

```bash
cd infobadge_editor/python
python infobadge_editor.py
```

## Design Format

Designs are stored as `.ibadge.json` files and include:
- Canvas size (`canvas.width`, `canvas.height`)
- Layer list (`text`, `image`, `qr`)
- Per-layer positioning and style properties

Default design:
- `python/designs/default_296x128.ibadge.json`

## Serial Protocol (IBF1)

The editor sends a binary frame:

1. Header (`<4sHHBI`, little-endian)
   - `magic`: `IBF1`
   - `width`: selected canvas width
   - `height`: selected canvas height
   - `format`: `0` (`2bpp` indexed)
   - `dataLen`: payload size in bytes
2. Payload (`2bpp` packed)
   - 4 pixels per byte
   - color index: `0=white`, `1=black`, `2=red`, `3=yellow`
