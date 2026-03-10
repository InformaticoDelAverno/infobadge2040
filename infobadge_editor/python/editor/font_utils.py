import os


def discover_font_files(local_fonts_root=None):
    """
    Busca fuentes locales y luego fuentes del sistema.
    """
    roots = []
    if local_fonts_root:
        roots.append(local_fonts_root)

    roots.extend(
        [
            # Linux
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"),
            # Windows
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
            os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts"),
            # macOS
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.expanduser("~/Library/Fonts"),
        ]
    )

    fonts = {}
    name_counts = {}
    source_priority = {}
    abs_local = os.path.abspath(local_fonts_root) if local_fonts_root else None

    def add_font(name, path, base, priority):
        if name not in fonts:
            fonts[name] = path
            name_counts[name] = 1
            source_priority[name] = priority
            return

        name_counts[name] += 1
        label = f"{name} [{os.path.basename(base)} #{name_counts[name]}]"
        while label in fonts:
            name_counts[name] += 1
            label = f"{name} [{os.path.basename(base)} #{name_counts[name]}]"
        fonts[label] = path
        source_priority[label] = priority

    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        priority = 0 if abs_local and os.path.abspath(root) == abs_local else 1

        for base, _, files in os.walk(root):
            for name in files:
                low = name.lower()
                if not (low.endswith(".ttf") or low.endswith(".otf")):
                    continue

                path = os.path.join(base, name)
                add_font(name, path, base, priority)

    if not fonts:
        return {"default": None}

    ordered = sorted(
        fonts.items(),
        key=lambda x: (source_priority.get(x[0], 1), x[0].lower()),
    )
    return dict(ordered)


def normalize_font_family(name):
    clean_name = name.split(" [", 1)[0]
    base = os.path.splitext(clean_name)[0].lower()

    for token in [
        "bolditalic",
        "boldoblique",
        "semibolditalic",
        "semibold",
        "demibold",
        "extrabold",
        "ultrabold",
        "black",
        "italic",
        "oblique",
        "bold",
        "regular",
        "roman",
        "book",
        "medium",
    ]:
        base = base.replace(token, "")

    return "".join(ch for ch in base if ch.isalnum())
