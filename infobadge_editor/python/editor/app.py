import json
import os
import struct
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageTk
from serial import Serial, SerialException
import serial.tools.list_ports

from .color_utils import hex_to_badge_label, normalize_badge_hex
from .config import (
    BADGE_COLOR_NAME_TO_HEX,
    BAUDRATE,
    FORMAT_2BPP,
    MAGIC,
    RESOLUTION_OPTIONS,
    SCALE,
    SERIAL_ACK_TIMEOUT,
    SERIAL_READ_TIMEOUT,
    SERIAL_READY_TIMEOUT,
)
from .font_utils import discover_font_files, normalize_font_family
from .image_codec import pack_2bpp, quantize_to_palette

try:
    import qrcode
except Exception:
    qrcode = None

class BadgeDesignerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("InfoBadge2040 Bitmap Designer")
        self.root.geometry("1320x760")

        self.items = []
        self.selected_index = None
        self.drag_start = None

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_fonts_root = os.path.join(base_dir, "fonts")
        self.font_files = discover_font_files(local_fonts_root=local_fonts_root)
        self.available_fonts = list(self.font_files.keys())
        self.resolution_options = list(RESOLUTION_OPTIONS)
        self.resolution_map = {label: (w, h) for label, w, h in self.resolution_options}
        self.var_resolution = tk.StringVar(value=self.resolution_options[0][0])
        self.canvas_w, self.canvas_h = self.resolution_map[self.var_resolution.get()]

        self.build_ui()
        self.refresh_layer_list()
        self.render_preview()

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------

    def build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        right = ttk.Frame(main, width=370)
        right.pack(side="right", fill="y")

        self.preview_canvas = tk.Canvas(
            left,
            width=self.canvas_w * SCALE,
            height=self.canvas_h * SCALE,
            bg="#f0f0f0",
            highlightthickness=1,
            highlightbackground="#999999",
        )
        self.preview_canvas.pack(anchor="nw", pady=8)
        self.preview_canvas.bind("<Button-1>", self.on_canvas_click)
        self.preview_canvas.bind("<B1-Motion>", self.on_canvas_drag)

        controls = ttk.Frame(left)
        controls.pack(anchor="nw", fill="x")

        ttk.Label(controls, text="Resolution").pack(side="left", padx=(0, 4))
        self.resolution_combo = ttk.Combobox(
            controls,
            values=[label for label, _, _ in self.resolution_options],
            textvariable=self.var_resolution,
            state="readonly",
            width=10,
        )
        self.resolution_combo.pack(side="left", padx=(0, 10))
        self.resolution_combo.bind("<<ComboboxSelected>>", self.on_resolution_select)

        ttk.Button(controls, text="Add Text", command=self.add_text).pack(side="left", padx=2)
        ttk.Button(controls, text="Add Image", command=self.add_image).pack(side="left", padx=2)
        ttk.Button(controls, text="Add QR", command=self.add_qr).pack(side="left", padx=2)
        ttk.Button(controls, text="Delete", command=self.delete_selected).pack(side="left", padx=2)
        ttk.Button(controls, text="Move Up", command=lambda: self.move_layer(-1)).pack(side="left", padx=2)
        ttk.Button(controls, text="Move Down", command=lambda: self.move_layer(1)).pack(side="left", padx=2)
        ttk.Button(controls, text="Save Design", command=self.save_design_file).pack(side="left", padx=6)
        ttk.Button(controls, text="Load Design", command=self.load_design_file).pack(side="left", padx=2)

        serial_frame = ttk.LabelFrame(left, text="Send to Badge", padding=8)
        serial_frame.pack(anchor="nw", fill="x", pady=10)

        ttk.Label(serial_frame, text="Serial Port").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(serial_frame, values=self.get_serial_ports(), width=38)
        self.port_combo.grid(row=0, column=1, padx=6)
        ttk.Button(serial_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2)

        ttk.Button(serial_frame, text="Send Current Design", command=self.send_design).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0)
        )
        ttk.Button(serial_frame, text="Run Test Pattern", command=self.send_test_pattern).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0)
        )

        monitor_header = ttk.Frame(serial_frame)
        monitor_header.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        ttk.Label(monitor_header, text="Serial Monitor").pack(side="left")
        ttk.Button(monitor_header, text="Clear", command=self.clear_serial_monitor).pack(side="right")

        self.serial_monitor = scrolledtext.ScrolledText(serial_frame, wrap="word", height=8)
        self.serial_monitor.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.serial_monitor.configure(state="disabled")

        serial_frame.columnconfigure(1, weight=1)

        layers_frame = ttk.LabelFrame(right, text="Layers", padding=6)
        layers_frame.pack(fill="x")

        self.layer_list = tk.Listbox(layers_frame, height=12)
        self.layer_list.pack(fill="x")
        self.layer_list.bind("<<ListboxSelect>>", self.on_layer_select)

        props = ttk.LabelFrame(right, text="Properties", padding=8)
        props.pack(fill="both", expand=True, pady=(8, 0))

        self.var_type = tk.StringVar()
        self.var_text = tk.StringVar()
        self.var_font = tk.StringVar(value=self.available_fonts[0])
        self.var_size = tk.IntVar(value=18)
        self.var_bold = tk.BooleanVar(value=False)
        self.var_italic = tk.BooleanVar(value=False)
        self.var_fg = tk.StringVar(value="#000000")
        self.var_bg = tk.StringVar(value="#ffffff")
        self.var_fg_label = tk.StringVar(value=hex_to_badge_label("#000000"))
        self.var_bg_label = tk.StringVar(value=hex_to_badge_label("#ffffff"))
        self.var_x = tk.IntVar(value=10)
        self.var_y = tk.IntVar(value=10)
        self.var_w = tk.IntVar(value=80)
        self.var_h = tk.IntVar(value=40)
        self.var_keep_aspect = tk.BooleanVar(value=True)

        row = 0
        ttk.Label(props, text="Type").grid(row=row, column=0, sticky="w")
        ttk.Label(props, textvariable=self.var_type).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(props, text="Text").grid(row=row, column=0, sticky="w")
        self.entry_text = ttk.Entry(props, textvariable=self.var_text)
        self.entry_text.grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(props, text="Font").grid(row=row, column=0, sticky="w")
        self.font_combo = ttk.Combobox(props, values=self.available_fonts, textvariable=self.var_font, state="readonly")
        self.font_combo.grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(props, text="Size").grid(row=row, column=0, sticky="w")
        ttk.Spinbox(props, from_=6, to=96, textvariable=self.var_size, width=8).grid(row=row, column=1, sticky="w")
        row += 1

        style_row = ttk.Frame(props)
        style_row.grid(row=row, column=1, sticky="w")
        self.bold_chk = ttk.Checkbutton(style_row, text="Bold", variable=self.var_bold)
        self.bold_chk.pack(side="left")
        self.italic_chk = ttk.Checkbutton(style_row, text="Italic", variable=self.var_italic)
        self.italic_chk.pack(side="left", padx=(8, 0))
        ttk.Label(props, text="Style").grid(row=row, column=0, sticky="w")
        row += 1

        ttk.Label(props, text="FG Color").grid(row=row, column=0, sticky="w")
        fgrow = ttk.Frame(props)
        fgrow.grid(row=row, column=1, sticky="ew")
        self.fg_combo = ttk.Combobox(
            fgrow,
            values=list(BADGE_COLOR_NAME_TO_HEX.keys()),
            textvariable=self.var_fg_label,
            state="readonly",
            width=14,
        )
        self.fg_combo.pack(side="left", fill="x", expand=True)
        self.fg_swatch = tk.Canvas(fgrow, width=18, height=18, highlightthickness=1, highlightbackground="#666666")
        self.fg_swatch.pack(side="left", padx=(6, 0))
        self.fg_combo.bind("<<ComboboxSelected>>", self.on_fg_color_select)
        row += 1

        ttk.Label(props, text="BG Color").grid(row=row, column=0, sticky="w")
        bgrow = ttk.Frame(props)
        bgrow.grid(row=row, column=1, sticky="ew")
        self.bg_combo = ttk.Combobox(
            bgrow,
            values=list(BADGE_COLOR_NAME_TO_HEX.keys()),
            textvariable=self.var_bg_label,
            state="readonly",
            width=14,
        )
        self.bg_combo.pack(side="left", fill="x", expand=True)
        self.bg_swatch = tk.Canvas(bgrow, width=18, height=18, highlightthickness=1, highlightbackground="#666666")
        self.bg_swatch.pack(side="left", padx=(6, 0))
        self.bg_combo.bind("<<ComboboxSelected>>", self.on_bg_color_select)
        row += 1

        ttk.Label(props, text="X").grid(row=row, column=0, sticky="w")
        self.spin_x = ttk.Spinbox(props, from_=0, to=self.canvas_w, textvariable=self.var_x, width=8)
        self.spin_x.grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(props, text="Y").grid(row=row, column=0, sticky="w")
        self.spin_y = ttk.Spinbox(props, from_=0, to=self.canvas_h, textvariable=self.var_y, width=8)
        self.spin_y.grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(props, text="Width").grid(row=row, column=0, sticky="w")
        self.spin_w = ttk.Spinbox(props, from_=1, to=self.canvas_w, textvariable=self.var_w, width=8)
        self.spin_w.grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(props, text="Height").grid(row=row, column=0, sticky="w")
        self.spin_h = ttk.Spinbox(props, from_=1, to=self.canvas_h, textvariable=self.var_h, width=8)
        self.spin_h.grid(row=row, column=1, sticky="w")
        row += 1

        self.keep_aspect_chk = ttk.Checkbutton(props, text="Lock aspect (image)", variable=self.var_keep_aspect)
        self.keep_aspect_chk.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        ttk.Button(props, text="Apply", command=self.apply_properties).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )

        props.columnconfigure(1, weight=1)
        self.refresh_color_swatches()

    def find_resolution_label(self, w, h):
        for label, rw, rh in self.resolution_options:
            if rw == w and rh == h:
                return label
        return None

    def update_canvas_constraints(self):
        self.preview_canvas.configure(width=self.canvas_w * SCALE, height=self.canvas_h * SCALE)
        self.spin_x.configure(to=self.canvas_w)
        self.spin_y.configure(to=self.canvas_h)
        self.spin_w.configure(to=self.canvas_w)
        self.spin_h.configure(to=self.canvas_h)

    def clamp_all_items_to_canvas(self):
        for item in self.items:
            if item["type"] in ("image", "qr"):
                item["w"] = max(1, min(self.canvas_w, int(item.get("w", 1))))
                item["h"] = max(1, min(self.canvas_h, int(item.get("h", 1))))
            x, y = self.clamp_item_position(item, int(item.get("x", 0)), int(item.get("y", 0)))
            item["x"] = x
            item["y"] = y

    def apply_resolution(self, label):
        size = self.resolution_map.get(label)
        if size is None:
            return
        self.canvas_w, self.canvas_h = size
        self.update_canvas_constraints()
        self.clamp_all_items_to_canvas()
        self.load_properties_from_selected()
        self.render_preview()

    def on_resolution_select(self, _evt=None):
        self.apply_resolution(self.var_resolution.get())

    # -------------------------------------------------------------------------
    # Puertos serie
    # -------------------------------------------------------------------------

    def get_serial_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    def refresh_ports(self):
        self.port_combo["values"] = self.get_serial_ports()

    # -------------------------------------------------------------------------
    # Gestión de ítems
    # -------------------------------------------------------------------------

    def add_text(self):
        item = {
            "type": "text",
            "text": "Texto",
            "font": self.available_fonts[0],
            "size": 18,
            "bold": False,
            "italic": False,
            "fg": "#000000",
            "bg": "#ffffff",
            "x": 10,
            "y": 10,
        }
        self.items.append(item)
        self.select_index(len(self.items) - 1)
        self.refresh_layer_list()
        self.render_preview()

    def add_image(self):
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[
                (
                    "Image files",
                    "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.PNG *.JPG *.JPEG *.BMP *.GIF *.WEBP",
                ),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            pil = Image.open(path).convert("RGBA")
        except Exception as exc:
            messagebox.showerror("Image error", str(exc))
            return

        w, h = pil.size
        w = min(w, self.canvas_w)
        h = min(h, self.canvas_h)

        item = {
            "type": "image",
            "path": path,
            "pil": pil,
            "x": 10,
            "y": 10,
            "w": w,
            "h": h,
            "orig_w": pil.width,
            "orig_h": pil.height,
            "keep_aspect": True,
        }
        self.items.append(item)
        self.select_index(len(self.items) - 1)
        self.refresh_layer_list()
        self.render_preview()

    def add_qr(self):
        if qrcode is None:
            messagebox.showerror("QR error", "Missing dependency 'qrcode'. Install requirements first.")
            return

        default_qr_w = max(8, min(64, self.canvas_w))
        default_qr_h = max(8, min(64, self.canvas_h))
        item = {
            "type": "qr",
            "data": "https://example.com",
            "fg": "#000000",
            "bg": "#ffffff",
            "x": 10,
            "y": 10,
            "w": default_qr_w,
            "h": default_qr_h,
        }
        self.items.append(item)
        self.select_index(len(self.items) - 1)
        self.refresh_layer_list()
        self.render_preview()

    def delete_selected(self):
        if self.selected_index is None:
            return

        self.items.pop(self.selected_index)

        if not self.items:
            self.selected_index = None
        else:
            self.selected_index = min(self.selected_index, len(self.items) - 1)

        self.refresh_layer_list()
        self.load_properties_from_selected()
        self.render_preview()

    def move_layer(self, direction):
        if self.selected_index is None:
            return

        i = self.selected_index
        j = i + direction
        if j < 0 or j >= len(self.items):
            return

        self.items[i], self.items[j] = self.items[j], self.items[i]
        self.select_index(j)
        self.refresh_layer_list()
        self.render_preview()

    def refresh_layer_list(self):
        self.layer_list.delete(0, tk.END)

        for i, item in enumerate(self.items):
            if item["type"] == "text":
                label = f"{i}: TEXT '{item['text'][:20]}'"
            elif item["type"] == "qr":
                label = f"{i}: QR '{item['data'][:20]}'"
            else:
                label = f"{i}: IMAGE '{os.path.basename(item['path'])}'"
            self.layer_list.insert(tk.END, label)

        if self.selected_index is not None and self.items:
            self.layer_list.selection_set(self.selected_index)

    def on_layer_select(self, _evt=None):
        sel = self.layer_list.curselection()
        if not sel:
            return
        self.select_index(sel[0])

    def select_index(self, idx):
        self.selected_index = idx
        self.layer_list.selection_clear(0, tk.END)
        self.layer_list.selection_set(idx)
        self.load_properties_from_selected()

    def get_item_size(self, item):
        if item["type"] == "text":
            return self.measure_text(item)
        return int(item.get("w", 1)), int(item.get("h", 1))

    def clamp_item_position(self, item, x, y):
        w, h = self.get_item_size(item)
        w = max(1, w)
        h = max(1, h)

        x = max(0, min(self.canvas_w - w, x))
        y = max(0, min(self.canvas_h - h, y))
        return x, y

    def load_properties_from_selected(self):
        if self.selected_index is None or not self.items:
            self.var_type.set("")
            self.keep_aspect_chk.configure(state="disabled")
            self.bold_chk.configure(state="disabled")
            self.italic_chk.configure(state="disabled")
            self.var_bold.set(False)
            self.var_italic.set(False)
            self.var_fg.set("#000000")
            self.var_bg.set("#ffffff")
            self.var_fg_label.set("Black")
            self.var_bg_label.set("White")
            self.refresh_color_swatches()
            return

        item = self.items[self.selected_index]
        self.var_type.set(item["type"])
        self.var_x.set(item.get("x", 0))
        self.var_y.set(item.get("y", 0))

        if item["type"] == "text":
            self.entry_text.configure(state="normal")
            self.font_combo.configure(state="readonly")
            self.keep_aspect_chk.configure(state="disabled")
            self.bold_chk.configure(state="normal")
            self.italic_chk.configure(state="normal")
            self.var_text.set(item["text"])
            self.var_font.set(item["font"])
            self.var_size.set(item["size"])
            self.var_bold.set(bool(item.get("bold", False)))
            self.var_italic.set(bool(item.get("italic", False)))
            self.var_fg.set(normalize_badge_hex(item["fg"]))
            self.var_bg.set(normalize_badge_hex(item["bg"]))
            self.var_fg_label.set(hex_to_badge_label(self.var_fg.get()))
            self.var_bg_label.set(hex_to_badge_label(self.var_bg.get()))
            self.var_w.set(80)
            self.var_h.set(30)
            self.var_keep_aspect.set(True)

        elif item["type"] == "qr":
            self.entry_text.configure(state="normal")
            self.font_combo.configure(state="disabled")
            self.keep_aspect_chk.configure(state="disabled")
            self.bold_chk.configure(state="disabled")
            self.italic_chk.configure(state="disabled")
            self.var_text.set(item["data"])
            self.var_size.set(18)
            self.var_bold.set(False)
            self.var_italic.set(False)
            self.var_fg.set(normalize_badge_hex(item["fg"]))
            self.var_bg.set(normalize_badge_hex(item["bg"]))
            self.var_fg_label.set(hex_to_badge_label(self.var_fg.get()))
            self.var_bg_label.set(hex_to_badge_label(self.var_bg.get()))
            self.var_w.set(item["w"])
            self.var_h.set(item["h"])
            self.var_keep_aspect.set(True)

        else:
            self.entry_text.configure(state="disabled")
            self.font_combo.configure(state="disabled")
            self.keep_aspect_chk.configure(state="normal")
            self.bold_chk.configure(state="disabled")
            self.italic_chk.configure(state="disabled")
            self.var_text.set("")
            self.var_size.set(18)
            self.var_bold.set(False)
            self.var_italic.set(False)
            self.var_fg.set("#000000")
            self.var_bg.set("#ffffff")
            self.var_fg_label.set(hex_to_badge_label("#000000"))
            self.var_bg_label.set(hex_to_badge_label("#ffffff"))
            self.var_w.set(item["w"])
            self.var_h.set(item["h"])
            self.var_keep_aspect.set(bool(item.get("keep_aspect", True)))

        self.refresh_color_swatches()

    def apply_properties(self):
        if self.selected_index is None:
            return

        item = self.items[self.selected_index]

        if item["type"] == "text":
            item["text"] = self.var_text.get()
            item["font"] = self.var_font.get()
            item["size"] = max(6, min(96, self.var_size.get()))
            item["bold"] = bool(self.var_bold.get())
            item["italic"] = bool(self.var_italic.get())
            item["fg"] = normalize_badge_hex(self.var_fg.get())
            item["bg"] = normalize_badge_hex(self.var_bg.get())
            self.var_fg.set(item["fg"])
            self.var_bg.set(item["bg"])
            self.var_fg_label.set(hex_to_badge_label(item["fg"]))
            self.var_bg_label.set(hex_to_badge_label(item["bg"]))

        elif item["type"] == "qr":
            item["data"] = self.var_text.get().strip()
            item["fg"] = normalize_badge_hex(self.var_fg.get())
            item["bg"] = normalize_badge_hex(self.var_bg.get())
            self.var_fg.set(item["fg"])
            self.var_bg.set(item["bg"])
            self.var_fg_label.set(hex_to_badge_label(item["fg"]))
            self.var_bg_label.set(hex_to_badge_label(item["bg"]))
            item["w"] = max(8, min(self.canvas_w, self.var_w.get()))
            item["h"] = max(8, min(self.canvas_h, self.var_h.get()))

        else:
            old_w = int(item.get("w", 1))
            old_h = int(item.get("h", 1))
            new_w = max(1, min(self.canvas_w, self.var_w.get()))
            new_h = max(1, min(self.canvas_h, self.var_h.get()))
            keep_aspect = bool(self.var_keep_aspect.get())

            if keep_aspect:
                orig_w = max(1, int(item.get("orig_w", old_w)))
                orig_h = max(1, int(item.get("orig_h", old_h)))
                ratio = orig_w / orig_h

                if new_w != old_w and new_h == old_h:
                    new_h = max(1, min(self.canvas_h, int(round(new_w / ratio))))
                elif new_h != old_h and new_w == old_w:
                    new_w = max(1, min(self.canvas_w, int(round(new_h * ratio))))
                else:
                    new_h = max(1, min(self.canvas_h, int(round(new_w / ratio))))

                self.var_w.set(new_w)
                self.var_h.set(new_h)

            item["w"] = new_w
            item["h"] = new_h
            item["keep_aspect"] = keep_aspect

        x, y = self.clamp_item_position(item, self.var_x.get(), self.var_y.get())
        item["x"] = x
        item["y"] = y
        self.var_x.set(x)
        self.var_y.set(y)

        self.refresh_layer_list()
        self.render_preview()
        self.refresh_color_swatches()

    def on_fg_color_select(self, _evt=None):
        label = self.var_fg_label.get()
        self.var_fg.set(BADGE_COLOR_NAME_TO_HEX.get(label, "#000000"))
        self.refresh_color_swatches()

    def on_bg_color_select(self, _evt=None):
        label = self.var_bg_label.get()
        self.var_bg.set(BADGE_COLOR_NAME_TO_HEX.get(label, "#ffffff"))
        self.refresh_color_swatches()

    def _paint_swatch(self, canvas, color):
        canvas.delete("all")
        canvas.create_rectangle(1, 1, 17, 17, fill=color, outline="#333333")

    def refresh_color_swatches(self):
        self._paint_swatch(self.fg_swatch, self.var_fg.get())
        self._paint_swatch(self.bg_swatch, self.var_bg.get())

    # -------------------------------------------------------------------------
    # Composición y render local
    # -------------------------------------------------------------------------

    def compose_image(self):
        base = Image.new("RGBA", (self.canvas_w, self.canvas_h), (255, 255, 255, 255))

        for item in self.items:
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))

            if item["type"] == "text":
                text_img = self.build_text_image(item)
                base.alpha_composite(text_img, (x, y))

            elif item["type"] == "image":
                src = item["pil"]
                w = int(item.get("w", src.width))
                h = int(item.get("h", src.height))
                resized = src.resize((w, h), Image.Resampling.LANCZOS)
                base.alpha_composite(resized, (x, y))

            elif item["type"] == "qr":
                if qrcode is None:
                    continue

                data = item.get("data", "").strip()
                if not data:
                    continue

                w = int(item.get("w", 64))
                h = int(item.get("h", 64))
                fg = item.get("fg", "#000000")
                bg = item.get("bg", "#ffffff")

                qr_img = self.build_qr_image(data, w, h, fg, bg)
                base.alpha_composite(qr_img, (x, y))

        return base.convert("RGB")

    def measure_text(self, item):
        img = self.build_text_image(item)
        return max(1, img.width), max(1, img.height)

    def load_font(self, font_name, size, bold=False, italic=False):
        fnt = ImageFont.load_default()
        real_bold = False
        real_italic = False

        try:
            font_path, real_bold, real_italic = self.find_font_variant(font_name, bold, italic)
            if font_path:
                fnt = ImageFont.truetype(font_path, size)
        except Exception:
            pass

        return fnt, real_bold, real_italic

    def find_font_variant(self, font_name, bold, italic):
        exact = self.font_files.get(font_name)
        n_exact = font_name.split(" [", 1)[0].lower()
        exact_bold = ("bold" in n_exact) or ("black" in n_exact) or ("semibold" in n_exact)
        exact_italic = ("italic" in n_exact) or ("oblique" in n_exact)

        if not bold and not italic:
            return exact, exact_bold, exact_italic

        desired_bold = bold
        desired_italic = italic
        family = normalize_font_family(font_name)

        scored = []
        for name, path in self.font_files.items():
            n = name.split(" [", 1)[0].lower()
            if normalize_font_family(name) != family:
                continue

            has_bold = ("bold" in n) or ("black" in n) or ("semibold" in n)
            has_italic = ("italic" in n) or ("oblique" in n)

            score = 0
            if has_bold == desired_bold:
                score += 2
            if has_italic == desired_italic:
                score += 2
            if has_bold != desired_bold:
                score -= 1
            if has_italic != desired_italic:
                score -= 1

            scored.append((score, name, path, has_bold, has_italic))

        if scored:
            scored.sort(key=lambda t: (-t[0], t[1].lower()))
            return scored[0][2], scored[0][3], scored[0][4]

        return exact, exact_bold, exact_italic

    def build_text_image(self, item):
        text = item.get("text", "")
        font_name = item.get("font", self.available_fonts[0])
        size = int(item.get("size", 18))
        want_bold = bool(item.get("bold", False))
        want_italic = bool(item.get("italic", False))
        fg = item.get("fg", "#000000")
        bg = item.get("bg", "#ffffff")

        fnt, real_bold, real_italic = self.load_font(font_name, size, want_bold, want_italic)
        synth_bold = want_bold and not real_bold
        synth_italic = want_italic and not real_italic
        stroke = 1 if synth_bold else 0

        tmp = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        left, top, right, bottom = d.textbbox((0, 0), text, font=fnt, stroke_width=stroke)
        w = max(1, right - left)
        h = max(1, bottom - top)
        ox = -left
        oy = -top

        try:
            fg_rgb = ImageColor.getrgb(fg)
        except Exception:
            fg_rgb = (0, 0, 0)

        try:
            bg_rgb = ImageColor.getrgb(bg)
        except Exception:
            bg_rgb = (255, 255, 255)

        if not synth_italic:
            out = Image.new("RGBA", (w, h), (bg_rgb[0], bg_rgb[1], bg_rgb[2], 255))
            draw = ImageDraw.Draw(out)
            draw.text((ox, oy), text, fill=fg_rgb, font=fnt, stroke_width=stroke, stroke_fill=fg_rgb)
            return out

        glyph = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glyph)
        gdraw.text((ox, oy), text, fill=fg_rgb, font=fnt, stroke_width=stroke, stroke_fill=fg_rgb)

        skew = 0.25
        sw = w + int(h * skew)
        sheared = glyph.transform(
            (sw, h),
            Image.Transform.AFFINE,
            (1, -skew, int(h * skew), 0, 1, 0),
            resample=Image.Resampling.BICUBIC,
        )

        out = Image.new("RGBA", (sw, h), (bg_rgb[0], bg_rgb[1], bg_rgb[2], 255))
        out.alpha_composite(sheared, (0, 0))
        return out

    def build_qr_image(self, data, width, height, fg_color, bg_color):
        qr = qrcode.QRCode(border=0)
        qr.add_data(data)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        size = len(matrix)

        try:
            fg = ImageColor.getrgb(fg_color)
        except Exception:
            fg = (0, 0, 0)

        try:
            bg = ImageColor.getrgb(bg_color)
        except Exception:
            bg = (255, 255, 255)

        img = Image.new("RGB", (size, size), bg)
        px = img.load()

        for y in range(size):
            row = matrix[y]
            for x in range(size):
                if row[x]:
                    px[x, y] = fg

        return img.resize((width, height), Image.Resampling.NEAREST).convert("RGBA")

    def render_preview(self):
        img = quantize_to_palette(self.compose_image())
        scaled = img.resize((self.canvas_w * SCALE, self.canvas_h * SCALE), Image.Resampling.NEAREST)
        self._preview_photo = ImageTk.PhotoImage(scaled)

        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, image=self._preview_photo, anchor="nw")

        if self.selected_index is not None and self.items:
            item = self.items[self.selected_index]
            x = int(item.get("x", 0)) * SCALE
            y = int(item.get("y", 0)) * SCALE

            if item["type"] == "text":
                w, h = self.measure_text(item)
            else:
                w = int(item.get("w", 40))
                h = int(item.get("h", 40))

            self.preview_canvas.create_rectangle(
                x,
                y,
                x + w * SCALE,
                y + h * SCALE,
                outline="#00aaff",
                width=2,
            )

    def item_at_point(self, px, py):
        x = px // SCALE
        y = py // SCALE

        for idx in range(len(self.items) - 1, -1, -1):
            item = self.items[idx]
            ix = int(item.get("x", 0))
            iy = int(item.get("y", 0))

            if item["type"] == "text":
                iw, ih = self.measure_text(item)
            else:
                iw = int(item.get("w", 0))
                ih = int(item.get("h", 0))

            if ix <= x <= ix + iw and iy <= y <= iy + ih:
                return idx

        return None

    def on_canvas_click(self, event):
        idx = self.item_at_point(event.x, event.y)
        if idx is None:
            return

        self.select_index(idx)
        item = self.items[idx]
        self.drag_start = {
            "mx": event.x // SCALE,
            "my": event.y // SCALE,
            "ix": int(item.get("x", 0)),
            "iy": int(item.get("y", 0)),
        }
        self.render_preview()

    def on_canvas_drag(self, event):
        if self.selected_index is None or not self.drag_start:
            return

        item = self.items[self.selected_index]
        nx = self.drag_start["ix"] + (event.x // SCALE - self.drag_start["mx"])
        ny = self.drag_start["iy"] + (event.y // SCALE - self.drag_start["my"])

        nx, ny = self.clamp_item_position(item, nx, ny)
        item["x"] = nx
        item["y"] = ny
        self.var_x.set(nx)
        self.var_y.set(ny)
        self.render_preview()

    # -------------------------------------------------------------------------
    # Serie: apertura, limpieza, envío y espera de ACK
    # -------------------------------------------------------------------------

    def wait_for_ready(self, ser, timeout=SERIAL_READY_TIMEOUT):
        deadline = time.time() + timeout
        lines = []
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            lines.append(line)
            self.append_serial_log("RX", line)
            if line == "IBF1_READY":
                return True, lines
        return False, lines

    def wait_for_protocol_result(self, ser, timeout=SERIAL_ACK_TIMEOUT):
        deadline = time.time() + timeout
        lines = []

        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            lines.append(line)

            if line.startswith("ERR_"):
                return line, lines

            if line == "OK":
                return line, lines

        return "", lines

    def parse_size_from_lines(self, lines):
        for line in lines:
            if not line.startswith("SIZE "):
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            try:
                w = int(parts[1])
                h = int(parts[2])
            except ValueError:
                continue
            if w > 0 and h > 0:
                return w, h
        return None

    def query_size(self, ser, timeout=1.5):
        lines = []
        size = None
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        self.append_serial_log("TX", "SIZE?")
        ser.write(b"SIZE?\n")
        ser.flush()

        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            lines.append(line)
            self.append_serial_log("RX", line)
            parsed = self.parse_size_from_lines([line])
            if parsed is not None:
                size = parsed
                break
        return size, lines

    def query_size_until_ready(self, ser, timeout=12.0, interval=0.7):
        """
        El RP2040 puede reiniciarse al abrir el puerto y perder mensajes de boot.
        Consultamos activamente SIZE? hasta obtener una respuesta.
        """
        lines = []
        deadline = time.time() + timeout
        next_query = 0.0

        while time.time() < deadline:
            now = time.time()
            if now >= next_query:
                ser.reset_output_buffer()
                self.append_serial_log("TX", "SIZE?")
                ser.write(b"SIZE?\n")
                ser.flush()
                next_query = now + interval

            raw = ser.readline()
            if not raw:
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            lines.append(line)
            self.append_serial_log("RX", line)
            parsed = self.parse_size_from_lines([line])
            if parsed is not None:
                return parsed, lines

        return None, lines

    def format_serial_tail(self, lines, max_lines=10):
        if not lines:
            return "(no response)"
        tail = lines[-max_lines:]
        return "\n".join(tail)

    def append_serial_log(self, direction, text):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {direction} {text}\n"
        self.serial_monitor.configure(state="normal")
        self.serial_monitor.insert("end", line)
        self.serial_monitor.see("end")
        self.serial_monitor.configure(state="disabled")

    def clear_serial_monitor(self):
        self.serial_monitor.configure(state="normal")
        self.serial_monitor.delete("1.0", "end")
        self.serial_monitor.configure(state="disabled")

    def show_selectable_dialog(self, title, text):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("760x420")

        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill="both", expand=True)

        box = scrolledtext.ScrolledText(frame, wrap="word", height=18)
        box.pack(fill="both", expand=True)
        box.insert("1.0", text)
        box.configure(state="normal")
        box.focus_set()

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(8, 0))

        def copy_all():
            dlg.clipboard_clear()
            dlg.clipboard_append(box.get("1.0", "end-1c"))

        ttk.Button(btns, text="Copy", command=copy_all).pack(side="left")
        ttk.Button(btns, text="Close", command=dlg.destroy).pack(side="right")

    def send_design(self):
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showerror("Error", "Select a serial port.")
            return

        self.append_serial_log("INFO", f"Send start on {port} ({self.canvas_w}x{self.canvas_h})")
        img = self.compose_image()
        packed = pack_2bpp(img, self.canvas_w, self.canvas_h)
        header = struct.pack("<4sHHBI", MAGIC, self.canvas_w, self.canvas_h, FORMAT_2BPP, len(packed))

        try:
            with Serial(port, BAUDRATE, timeout=SERIAL_READ_TIMEOUT, write_timeout=8) as ser:
                # Tras abrir, muchos RP2040 hacen auto-reset; damos margen antes del handshake.
                time.sleep(1.8)
                detected_size, boot_lines = self.query_size_until_ready(ser, timeout=SERIAL_READY_TIMEOUT + 6.0)
                ready = detected_size is not None

                if detected_size is not None and detected_size != (self.canvas_w, self.canvas_h):
                    self.show_selectable_dialog(
                        "Size mismatch",
                        (
                            f"Firmware size is {detected_size[0]}x{detected_size[1]} but editor is set to {self.canvas_w}x{self.canvas_h}.\n"
                            "Update rotation/size to match before sending.\n\n"
                            f"Boot log:\n{chr(10).join(boot_lines[-15:]) if boot_lines else '(no response)'}"
                        ),
                    )
                    return

                ser.reset_input_buffer()
                ser.reset_output_buffer()
                self.append_serial_log("TX", f"HEADER magic=IBF1 w={self.canvas_w} h={self.canvas_h} fmt={FORMAT_2BPP} len={len(packed)}")
                ser.write(header)
                self.append_serial_log("TX", f"PAYLOAD {len(packed)} bytes")
                ser.write(packed)
                ser.flush()
                ack, response_lines = self.wait_for_protocol_result(ser, timeout=SERIAL_ACK_TIMEOUT)
                self.append_serial_log("INFO", f"ACK={ack or '(none)'}")

            boot_txt = "\n".join(boot_lines[-10:]) if boot_lines else "(no response)"
            resp_txt = "\n".join(response_lines[-15:]) if response_lines else "(no response)"

            if ack == "OK":
                messagebox.showinfo("Success", f"Design sent and rendered successfully ({self.canvas_w}x{self.canvas_h}).")
                return

            self.show_selectable_dialog(
                "Sent with warning",
                (
                    f"{'Firmware not ready (IBF1_READY not seen) or no ACK.' if not ready and ack == '' else 'Firmware returned warning/error.'}\n"
                    f"Tried size: {self.canvas_w}x{self.canvas_h}\n\n"
                    f"Boot log:\n{boot_txt}\n\n"
                    f"Response log:\n{resp_txt}"
                ),
            )

        except SerialException as exc:
            self.append_serial_log("ERR", str(exc))
            self.show_selectable_dialog("Serial Error", str(exc))

    def send_test_pattern(self):
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showerror("Error", "Select a serial port.")
            return

        self.append_serial_log("INFO", f"Test pattern on {port}")

        try:
            with Serial(port, BAUDRATE, timeout=SERIAL_READ_TIMEOUT, write_timeout=8) as ser:
                time.sleep(1.8)
                _, _ = self.query_size_until_ready(ser, timeout=SERIAL_READY_TIMEOUT + 6.0)

                ser.reset_input_buffer()
                ser.reset_output_buffer()
                self.append_serial_log("TX", "TEST")
                ser.write(b"TEST\n")
                ser.flush()

                deadline = time.time() + SERIAL_ACK_TIMEOUT
                lines = []
                ack = ""
                while time.time() < deadline:
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    lines.append(line)
                    self.append_serial_log("RX", line)
                    if line == "OK_TEST":
                        ack = line
                        break
                    if line.startswith("ERR_"):
                        ack = line
                        break

            if ack == "OK_TEST":
                messagebox.showinfo("Success", "Test pattern rendered.")
                return

            resp_txt = "\n".join(lines[-20:]) if lines else "(no response)"
            self.show_selectable_dialog(
                "Test pattern warning",
                f"No OK_TEST received.\n\nResponse log:\n{resp_txt}",
            )
        except SerialException as exc:
            self.append_serial_log("ERR", str(exc))
            self.show_selectable_dialog("Serial Error", str(exc))

    # -------------------------------------------------------------------------
    # Save / load
    # -------------------------------------------------------------------------

    def save_design_file(self):
        path = filedialog.asksaveasfilename(
            title="Save design",
            defaultextension=".ibadge.json",
            filetypes=[("InfoBadge design", "*.ibadge.json"), ("JSON", "*.json")],
        )
        if not path:
            return

        data = {
            "version": 1,
            "canvas": {"width": self.canvas_w, "height": self.canvas_h},
            "items": [],
        }

        for item in self.items:
            if item["type"] == "text":
                data["items"].append(
                    {
                        "type": "text",
                        "text": item.get("text", ""),
                        "font": item.get("font", self.available_fonts[0]),
                        "size": int(item.get("size", 18)),
                        "bold": bool(item.get("bold", False)),
                        "italic": bool(item.get("italic", False)),
                        "fg": normalize_badge_hex(item.get("fg", "#000000")),
                        "bg": normalize_badge_hex(item.get("bg", "#ffffff")),
                        "x": int(item.get("x", 0)),
                        "y": int(item.get("y", 0)),
                    }
                )
            elif item["type"] == "image":
                data["items"].append(
                    {
                        "type": "image",
                        "path": item.get("path", ""),
                        "x": int(item.get("x", 0)),
                        "y": int(item.get("y", 0)),
                        "w": int(item.get("w", 32)),
                        "h": int(item.get("h", 32)),
                        "orig_w": int(item.get("orig_w", 32)),
                        "orig_h": int(item.get("orig_h", 32)),
                        "keep_aspect": bool(item.get("keep_aspect", True)),
                    }
                )
            elif item["type"] == "qr":
                data["items"].append(
                    {
                        "type": "qr",
                        "data": item.get("data", ""),
                        "fg": normalize_badge_hex(item.get("fg", "#000000")),
                        "bg": normalize_badge_hex(item.get("bg", "#ffffff")),
                        "x": int(item.get("x", 0)),
                        "y": int(item.get("y", 0)),
                        "w": int(item.get("w", 64)),
                        "h": int(item.get("h", 64)),
                    }
                )

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Saved", f"Design saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def load_design_file(self):
        path = filedialog.askopenfilename(
            title="Load design",
            filetypes=[("InfoBadge design", "*.ibadge.json"), ("JSON", "*.json")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))
            return

        canvas = data.get("canvas", {})
        file_w = canvas.get("width")
        file_h = canvas.get("height")
        try:
            file_w = int(file_w)
            file_h = int(file_h)
        except (TypeError, ValueError):
            file_w = None
            file_h = None

        if file_w and file_h:
            if (file_w, file_h) != (self.canvas_w, self.canvas_h):
                label = self.find_resolution_label(file_w, file_h)
                if label is not None:
                    self.var_resolution.set(label)
                    self.apply_resolution(label)
                else:
                    messagebox.showwarning(
                        "Canvas size mismatch",
                        (
                            f"Design canvas is {file_w}x{file_h}, but current editor size is "
                            f"{self.canvas_w}x{self.canvas_h}.\n"
                            "The design will be loaded and clamped to the current size."
                        ),
                    )

        items = data.get("items", [])
        loaded = []
        missing_images = []
        design_dir = os.path.dirname(os.path.abspath(path))

        for item in items:
            t = item.get("type")

            if t == "text":
                loaded.append(
                    {
                        "type": "text",
                        "text": item.get("text", ""),
                        "font": item.get("font", self.available_fonts[0]),
                        "size": int(item.get("size", 18)),
                        "bold": bool(item.get("bold", False)),
                        "italic": bool(item.get("italic", False)),
                        "fg": normalize_badge_hex(item.get("fg", "#000000")),
                        "bg": normalize_badge_hex(item.get("bg", "#ffffff")),
                        "x": int(item.get("x", 0)),
                        "y": int(item.get("y", 0)),
                    }
                )

            elif t == "image":
                raw_img_path = item.get("path", "")
                if not raw_img_path:
                    missing_images.append("(empty path)")
                    continue
                img_path = raw_img_path
                if not os.path.isabs(img_path):
                    img_path = os.path.join(design_dir, img_path)
                if not os.path.exists(img_path):
                    missing_images.append(raw_img_path)
                    continue

                try:
                    pil = Image.open(img_path).convert("RGBA")
                except Exception:
                    missing_images.append(raw_img_path)
                    continue

                loaded.append(
                    {
                        "type": "image",
                        "path": img_path,
                        "pil": pil,
                        "x": int(item.get("x", 0)),
                        "y": int(item.get("y", 0)),
                        "w": int(item.get("w", min(pil.width, self.canvas_w))),
                        "h": int(item.get("h", min(pil.height, self.canvas_h))),
                        "orig_w": int(item.get("orig_w", pil.width)),
                        "orig_h": int(item.get("orig_h", pil.height)),
                        "keep_aspect": bool(item.get("keep_aspect", True)),
                    }
                )

            elif t == "qr":
                loaded.append(
                    {
                        "type": "qr",
                        "data": item.get("data", ""),
                        "fg": normalize_badge_hex(item.get("fg", "#000000")),
                        "bg": normalize_badge_hex(item.get("bg", "#ffffff")),
                        "x": int(item.get("x", 0)),
                        "y": int(item.get("y", 0)),
                        "w": int(item.get("w", 64)),
                        "h": int(item.get("h", 64)),
                    }
                )

        self.items = loaded
        self.clamp_all_items_to_canvas()
        self.selected_index = 0 if self.items else None
        self.refresh_layer_list()
        self.load_properties_from_selected()
        self.render_preview()

        if missing_images:
            messagebox.showwarning(
                "Loaded with warnings",
                "Some image layers were skipped because files were not found."
            )


def main():
    root = tk.Tk()
    BadgeDesignerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
