# views/native_effects.py
"""
Best-effort native Windows visual effects (Mica/Acrylic backdrop, dark title bar).
No-ops silently on non-Windows or older Windows builds — this is cosmetic only,
never required for the app to function.
"""

import ctypes
import sys

from utils.app_logger import get_logger

logger = get_logger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMSBT_MAINWINDOW = 2  # Mica


def _dwm_set_window_attribute(hwnd: int, attribute: int, value: int) -> None:
    """Thin, explicitly-typed wrapper around DwmSetWindowAttribute.

    ctypes calls into WinAPI without explicit argtypes/restype rely on
    default int marshaling, which is usually fine here but is the kind of
    thing that can corrupt the stack (hard native crash, no Python
    traceback) if it ever mismatches — declaring the signature explicitly
    removes that risk category entirely.
    """
    dwmapi = ctypes.windll.dwmapi
    dwmapi.DwmSetWindowAttribute.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
    ]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

    c_value = ctypes.c_int(value)
    result = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), attribute, ctypes.byref(c_value), ctypes.sizeof(c_value)
    )
    if result != 0:
        raise OSError(f"DwmSetWindowAttribute({attribute}) failed, HRESULT={result:#x}")


def apply_windows_backdrop(widget, dark: bool):
    """Apply the Windows 11 Mica backdrop + matching dark/light title bar to a
    top-level widget. Safe to call on any platform/OS version — silently does
    nothing if unsupported (Windows 11 22621+ required for Mica)."""
    if sys.platform != "win32":
        return

    hwnd = int(widget.winId())

    try:
        _dwm_set_window_attribute(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)
    except Exception:
        logger.warning("Could not set dark title bar (non-fatal)", exc_info=True)

    try:
        _dwm_set_window_attribute(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, _DWMSBT_MAINWINDOW)
    except Exception:
        logger.warning("Could not set Mica backdrop — likely pre-Win11 22621 (non-fatal)", exc_info=True)
