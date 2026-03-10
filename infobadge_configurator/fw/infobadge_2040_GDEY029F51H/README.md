# InfoBadge Firmware for GDEY029F51H

This firmware variant is dedicated to the **Good Display GDEY029F51H** e-paper panel used by this hardware revision of InfoBadge.

## Why This Firmware Exists

E-paper firmwares are tightly coupled to the panel model.
The **GDEY029F51H** requires:

- The matching panel driver provided by the installed `GxEPD2` library
- Correct panel geometry/orientation handling
- Update behavior compatible with this controller

Because of that, this folder contains a firmware variant that is intentionally specific to this panel and should be used when your badge uses **GDEY029F51H**.

## Main Sketch

- `infobadge_2040.ino`

## Related Files in This Folder

- `fonts/` (GFX font headers used by the sketch)

## When to Use It

Use this firmware if your device is assembled with the **GDEY029F51H** panel.

If your badge uses **GDEY029F52**, use the dedicated firmware variant in `../infobadge_2040_GDEY029F52/` instead.
