from PyQt6.QtWidgets import QApplication
from .ui.main_window import MainWindow
from .config import ConfigManager
from .core.file_manager import FileManager


def run_app() -> None:
    """
    Точка входа для GUI-приложения.
    """
    import sys

    app = QApplication(sys.argv)

    config = ConfigManager()
    file_manager = FileManager(config)

    window = MainWindow(file_manager=file_manager, config=config)
    window.show()

    sys.exit(app.exec())










