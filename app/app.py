from pathlib import Path

from PyQt6.QtWidgets import QApplication
from .ui.main_window import MainWindow, EditorTab
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
    
    # Если передан путь к файлу в аргументах командной строки, открываем его
    # ВАЖНО: это делается ПОСЛЕ восстановления вкладок из конфига и показа окна
    # Обрабатываем все аргументы (могут быть несколько файлов)
    # Используем QTimer для отложенного выполнения, чтобы окно успело полностью инициализироваться
    from PyQt6.QtCore import QTimer
    def open_files_from_args():
        if len(sys.argv) > 1:
            for arg in sys.argv[1:]:
                file_path = Path(arg).resolve()  # Используем абсолютный путь
                if file_path.exists() and file_path.is_file():
                    # Проверяем, не открыт ли уже этот файл в file_manager
                    is_already_in_manager = False
                    manager_index = -1
                    for i, f in enumerate(window._file_manager.files):
                        if f and f.resolve() == file_path:
                            is_already_in_manager = True
                            manager_index = i
                            break
                    
                    if is_already_in_manager and manager_index >= 0:
                        # Файл уже в менеджере (из конфига) - обновляем текст с диска и активируем вкладку
                        idx = manager_index
                        # Обновляем текст файла с диска
                        try:
                            text = file_path.read_text(encoding="utf-8")
                            window._file_manager.set_buffer(text, idx)
                        except Exception:
                            text = window._file_manager.get_buffer(idx)
                        
                        # Ищем соответствующую вкладку - проверяем по пути файла
                        tab_index = -1
                        for i in range(window.tabs.count()):
                            if window._is_plus_tab(i):
                                continue
                            # Проверяем по пути файла в менеджере
                            if i < len(window._file_manager.files):
                                manager_file = window._file_manager.files[i]
                                if manager_file and manager_file.resolve() == file_path:
                                    tab_index = i
                                    break
                        
                        if tab_index >= 0:
                            # Вкладка существует - обновляем текст и активируем
                            widget = window.tabs.widget(tab_index)
                            if isinstance(widget, EditorTab):
                                widget.set_text(text)
                            window.tabs.setCurrentIndex(tab_index)
                            window._file_manager._active_index = tab_index
                        else:
                            # Вкладки нет (не восстановилась) - создаём вкладку
                            font_size = window._config.state.font_size
                            is_md = file_path.suffix.lower() == ".md"
                            index = window._create_editor_tab(text, file_path.name, font_size, is_markdown=is_md)
                            window._ensure_plus_tab()
                            window.tabs.setCurrentIndex(index)
                            window._file_manager._active_index = idx
                    else:
                        # Новый файл - добавляем в менеджер и создаём вкладку
                        idx = window._file_manager.open_file(file_path)
                        text = window._file_manager.get_buffer(idx)
                        font_size = window._config.state.font_size
                        is_md = file_path.suffix.lower() == ".md"
                        index = window._create_editor_tab(text, file_path.name, font_size, is_markdown=is_md)
                        window._ensure_plus_tab()
                        window.tabs.setCurrentIndex(index)
                        window._file_manager._active_index = idx
    
    # Запускаем открытие файлов через небольшой таймер, чтобы окно успело инициализироваться
    QTimer.singleShot(100, open_files_from_args)

    sys.exit(app.exec())












