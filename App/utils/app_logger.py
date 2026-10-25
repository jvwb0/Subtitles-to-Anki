# utils/app_logger.py
"""
Centralized logging: rotating log file + console output, plus global hooks
so uncaught exceptions (main thread, background threads, and Qt's own
warnings) are always captured to disk instead of silently vanishing.

This project is going to grow for months — "why did it just crash" needs to
be answerable from logs/app.log, not guesswork.
"""

import logging
import logging.handlers
import os
import sys
import threading
import faulthandler

_LOG_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
_FAULT_FILE = os.path.join(_LOG_DIR, "faulthandler.log")

_configured = False
_fault_file_handle = None  # must stay open for the lifetime of the process


def setup_logging(level=logging.INFO):
    """Configure the root logger. Safe to call multiple times (no-ops after the first)."""
    global _configured
    if _configured:
        return
    _configured = True

    os.makedirs(_LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _install_exception_hooks(root)
    _install_qt_message_handler(root)
    _install_faulthandler()

    root.info("=" * 60)
    root.info("Logging initialized — log file: %s", _LOG_FILE)


def _install_exception_hooks(root: logging.Logger):
    """Route uncaught exceptions from the main thread AND background threads
    into the log, so a silent crash always leaves a traceback behind."""

    def log_unhandled(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        root.critical("Uncaught exception (main thread)", exc_info=(exc_type, exc_value, exc_tb))

    def log_unhandled_thread(args: threading.ExceptHookArgs):
        root.critical(
            "Uncaught exception in thread %r",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_unhandled
    threading.excepthook = log_unhandled_thread


def _install_qt_message_handler(root: logging.Logger):
    """Forward Qt's internal warnings/errors (e.g. cross-thread widget access,
    invalid geometry, etc.) into the log — these are often the real cause
    behind a GUI app that 'just crashes' with no Python traceback."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return

    level_map = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(msg_type, context, message):
        root.log(level_map.get(msg_type, logging.WARNING), "[Qt] %s", message)

    qInstallMessageHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _install_faulthandler():
    """Catch native-level crashes (segfaults, access violations) that bypass
    sys.excepthook entirely — e.g. a bad ctypes/WinAPI call or a crash inside
    a C extension (Qt, CUDA, PyAudio). Writes the native Python call stack of
    every thread to logs/faulthandler.log at the moment of the crash.
    """
    global _fault_file_handle
    _fault_file_handle = open(_FAULT_FILE, "a", encoding="utf-8")
    faulthandler.enable(file=_fault_file_handle, all_threads=True)
