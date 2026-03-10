# InfoBadge Editor Firmware for GDEY029F51H

This firmware variant is for badges assembled with the **Good Display GDEY029F51H** panel.

## Main Sketch

- `infobadge_editor.ino`

## Protocol

This sketch implements the same `IBF1` serial framebuffer protocol used by the editor application, with a logical canvas of `384x168` pixels and `2bpp` packed color data.

## When to Use It

Use this folder when flashing the editor firmware onto an InfoBadge with a **GDEY029F51H** display.

If your badge uses **GDEY029F52**, use `../infobadge_editor_GDEY029F52/` instead.
