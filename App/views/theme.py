# views/theme.py
"""
Single source of truth for the app's color palette, fonts, and Qt stylesheet
(QSS — Qt's CSS-like styling language). Windows 11 style: light/dark palette
chosen automatically from the OS setting, vibrant blue accent, rounded flat
surfaces. Pairs with views/native_effects.py for the real Mica backdrop.
"""

import sys


def _detect_windows_dark_mode() -> bool:
    """Read the 'Apps use dark mode' setting from the registry. Defaults to
    dark if unavailable (non-Windows, older Windows, or key missing)."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return True


_DARK_PALETTE = {
    "WINDOW_BG": "#3a3a3c",
    "CARD_BG": "#454548",
    "SURFACE": "#454548",
    "SURFACE_HOVER": "#515154",
    "BORDER": "#5a5a5e",
    "FG": "#f2f2f2",
    "MUTED_FG": "#b8b8bc",
    "BG": "#2e2e30",            # subtitle overlay bar (rendered translucent via Theme.rgba)
}

_LIGHT_PALETTE = {
    "WINDOW_BG": "#f3f3f3",
    "CARD_BG": "#ffffff",
    "SURFACE": "#ffffff",
    "SURFACE_HOVER": "#eaf3ff",
    "BORDER": "#e1e1e1",
    "FG": "#1b1b1b",
    "MUTED_FG": "#6b6b6b",
    "BG": "#ffffff",
}

# Shared across both modes — a single vibrant-blue brand identity.
_SHARED = {
    "ACCENT": "#2f8ef4",
    "ACCENT_HOVER": "#57a5f7",
    "GREEN": "#3fb950",
    "GREEN_BG": "#12321a",
    "RED": "#e5484d",
    "RED_BG": "#3a1618",
    "FONT_FAMILY": "Segoe UI Variable, Segoe UI",
    "FONT_WORD": ("Segoe UI", 22, "bold"),
    "FONT_CARD_TITLE": ("Segoe UI", 16, "bold"),
    "FONT_CARD_PRON": ("Segoe UI", 12),
    "FONT_CARD_POS": ("Segoe UI", 11, "italic"),
    "FONT_CARD_BODY": ("Segoe UI", 11),
    "FONT_CARD_EXAMPLE": ("Segoe UI", 10, "italic"),
    "FONT_CARD_META": ("Segoe UI", 9),
    "FONT_TRANSLATION": ("Segoe UI", 18),
}


class Theme:
    IS_DARK: bool

    # populated by _apply_palette() below — declared here for readability/discoverability
    WINDOW_BG = CARD_BG = SURFACE = SURFACE_HOVER = BORDER = FG = MUTED_FG = BG = ""
    ACCENT = ACCENT_HOVER = GREEN = GREEN_BG = RED = RED_BG = FONT_FAMILY = ""
    FONT_WORD = FONT_CARD_TITLE = FONT_CARD_PRON = FONT_CARD_POS = None
    FONT_CARD_BODY = FONT_CARD_EXAMPLE = FONT_CARD_META = FONT_TRANSLATION = None

    # ── role aliases used by the subtitle overlay / detail cards ──────
    HOVER_FG = CARD_TITLE_FG = CARD_DEF_FG = CARD_GRAM_FG = ""
    CARD_PRON_FG = CARD_EXAMPLE_FG = CARD_SYN_FG = CARD_ANT_FG = ""
    CARD_ERR_FG = CARD_SECTION_FG = TRANSLATION_FG = ""

    @classmethod
    def _apply_palette(cls):
        cls.IS_DARK = _detect_windows_dark_mode()
        palette = {**(_DARK_PALETTE if cls.IS_DARK else _LIGHT_PALETTE), **_SHARED}
        for key, value in palette.items():
            setattr(cls, key, value)

        # role aliases (kept few in number — a clean minimal palette, not a
        # different hue per role like the old theme had)
        cls.HOVER_FG = cls.ACCENT
        cls.CARD_TITLE_FG = cls.ACCENT
        cls.CARD_DEF_FG = cls.FG
        cls.CARD_GRAM_FG = cls.MUTED_FG
        cls.CARD_PRON_FG = cls.ACCENT
        cls.CARD_EXAMPLE_FG = cls.MUTED_FG
        cls.CARD_SYN_FG = cls.GREEN
        cls.CARD_ANT_FG = cls.RED
        cls.CARD_ERR_FG = cls.RED
        cls.CARD_SECTION_FG = cls.MUTED_FG
        cls.TRANSLATION_FG = cls.MUTED_FG

    @classmethod
    def rgba(cls, hex_color: str, alpha: int) -> str:
        """Convert '#RRGGBB' + an alpha (0-255) into a QSS rgba() string."""
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

    @classmethod
    def font_css(cls, spec) -> str:
        """Convert a (family, size, *style) tuple into QSS font properties.

        Qt stylesheets override QFont set via setFont() for any property the
        stylesheet also defines — since the app-wide stylesheet sets a base
        font-size, a widget-level setFont() alone is silently ignored unless
        the widget's own stylesheet re-declares font-size. Use this helper
        instead of setFont() for any label that needs a non-default size.
        """
        family, size, *style = spec
        weight = "bold" if "bold" in style else "normal"
        font_style = "italic" if "italic" in style else "normal"
        return (
            f"font-family: '{family}'; font-size: {size}px; "
            f"font-weight: {weight}; font-style: {font_style};"
        )

    @classmethod
    def stylesheet(cls) -> str:
        """Application-wide QSS (Qt's CSS-like styling language).

        Deliberately does NOT set `background` on the blanket `QWidget`
        selector — every plain QWidget/QLabel used purely as a layout
        container (e.g. inside the subtitle overlay's rounded card) would
        otherwise paint its own opaque rectangle on top of its parent's
        background, creating a visible "box behind the box" glitch.
        Backgrounds are set explicitly below, only where a surface is
        actually meant to be visible (buttons, inputs, dialogs, cards).
        """
        return f"""
        QWidget {{
            color: {cls.FG};
            font-family: {cls.FONT_FAMILY};
            font-size: 13px;
        }}
        QMainWindow {{
            background: transparent;
        }}
        QDialog {{
            background: {cls.WINDOW_BG};
        }}
        QLabel[role="heading"] {{
            font-size: 15px;
            font-weight: 600;
            color: {cls.FG};
        }}
        QLabel[role="muted"] {{
            color: {cls.MUTED_FG};
            font-size: 11px;
        }}
        QLabel[role="status"] {{
            color: {cls.ACCENT};
            font-weight: 600;
        }}
        QPushButton {{
            background: {cls.SURFACE};
            border: 1px solid {cls.BORDER};
            border-radius: 6px;
            padding: 8px 18px;
            color: {cls.FG};
        }}
        QPushButton:hover:!disabled {{
            background: {cls.SURFACE_HOVER};
            border-color: {cls.ACCENT};
        }}
        QPushButton:pressed {{
            background: {cls.BORDER};
        }}
        QPushButton:disabled {{
            color: {cls.MUTED_FG};
            border-color: {cls.BORDER};
        }}
        QPushButton[variant="primary"] {{
            background: {cls.ACCENT};
            border: none;
            color: #ffffff;
            font-weight: 600;
        }}
        QPushButton[variant="primary"]:hover:!disabled {{
            background: {cls.ACCENT_HOVER};
        }}
        QPushButton[variant="danger"] {{
            background: transparent;
            border: 1px solid {cls.RED};
            color: {cls.RED};
        }}
        QPushButton[variant="danger"]:hover:!disabled {{
            background: {cls.RED_BG};
        }}
        QPushButton[variant="success"] {{
            background: transparent;
            border: 1px solid {cls.GREEN};
            color: {cls.GREEN};
        }}
        QPushButton[variant="success"]:hover:!disabled {{
            background: {cls.GREEN_BG};
        }}
        QComboBox, QLineEdit, QTextEdit, QPlainTextEdit {{
            background: {cls.SURFACE};
            border: 1px solid {cls.BORDER};
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: {cls.ACCENT};
        }}
        QComboBox:hover, QLineEdit:hover {{
            border-color: {cls.ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background: {cls.SURFACE};
            border: 1px solid {cls.BORDER};
            selection-background-color: {cls.ACCENT};
            outline: none;
        }}
        QCheckBox {{
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {cls.BORDER};
            background: {cls.SURFACE};
        }}
        QCheckBox::indicator:checked {{
            background: {cls.ACCENT};
            border-color: {cls.ACCENT};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {cls.BORDER};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {cls.ACCENT};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QToolTip {{
            background: {cls.CARD_BG};
            color: {cls.FG};
            border: 1px solid {cls.BORDER};
            padding: 4px 8px;
            border-radius: 4px;
        }}
        """


Theme._apply_palette()
