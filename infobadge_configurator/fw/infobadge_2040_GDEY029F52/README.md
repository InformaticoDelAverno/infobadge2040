# InfoBadge Firmware for GDEY029F52

This firmware variant is dedicated to the **Good Display GDEY029F52** e-paper panel used by this hardware revision of InfoBadge.

## Why This Firmware Exists

E-paper firmwares are tightly coupled to the panel model.  
The **GDEY029F52** requires:

- A specific display driver implementation (`GxEPD2_290c_GDEY029F52.*`)
- Matching panel geometry/orientation handling
- Correct waveform/update behavior for this controller

Because of that, this folder contains a firmware variant that is intentionally specific to this panel and should be used when your badge uses **GDEY029F52**.

## Main Sketch

- `infobadge_2040.ino`

## Related Files in This Folder

- `GxEPD2_290c_GDEY029F52.h`
- `GxEPD2_290c_GDEY029F52.cpp`
- `fonts/` (GFX font headers used by the sketch)

## When to Use It

Use this firmware if your device is assembled with the **GDEY029F52** panel.

If you migrate to a different e-paper model, create or use a dedicated firmware variant for that panel instead of reusing this one directly.
