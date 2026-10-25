import sys

import ctranslate2
from PySide6.QtWidgets import QApplication

from utils.app_logger import setup_logging, get_logger
from views.main_window import MainWindow
from views.theme import Theme

setup_logging()
logger = get_logger(__name__)


def main():
    gpu_count = ctranslate2.get_cuda_device_count()
    logger.info("CUDA available: %s (%d device(s))", gpu_count > 0, gpu_count)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Windows' native style ignores most QSS — Fusion actually applies it
    app.setStyleSheet(Theme.stylesheet())

    try:
        window = MainWindow()
        window.show()
    except Exception:
        logger.critical("Fatal error during startup", exc_info=True)
        raise

    sys.exit(app.exec())



if __name__ == "__main__":
    main()
