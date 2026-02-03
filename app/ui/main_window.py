from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import Qt, QRect, QSize, QTimer
from PyQt6.QtGui import (
    QAction,
    QCloseEvent,
    QCursor,
    QPainter,
    QTextFormat,
    QFont,
    QColor,
    QTextCursor,
    QIcon,
    QPen,
    QFontDatabase,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QPlainTextEdit,
    QTabWidget,
    QTabBar,
    QMenu,
    QWidget,
    QVBoxLayout,
    QInputDialog,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QStyle,
    QStyleOptionTab,
)

import markdown

from ..config import ConfigManager
from ..core.file_manager import FileManager


class LineNumberArea(QWidget):
    """
    Поле для отображения номеров строк слева от редактора.
    """

    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        self._editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """
    QPlainTextEdit с полем номеров строк и подсветкой текущей строки.
    """

    def __init__(self, parent: Optional[QWidget] = None, font_size: int = 12) -> None:
        super().__init__(parent)
        self._line_number_area = LineNumberArea(self)
        # таймер для debounce сортировки при редактировании
        self._sort_timer = QTimer(self)
        self._sort_timer.setSingleShot(True)
        self._sort_timer.timeout.connect(self._sort_lines)
        # колбэк для сохранения размера шрифта
        self._on_font_size_changed: Optional[Callable[[int], None]] = None

        # устанавливаем размер шрифта с поддержкой эмодзи
        font = self.font()
        font.setPointSize(font_size)
        
        # Улучшенная поддержка эмодзи через QFontDatabase (статический класс)
        available_families = QFontDatabase.families()
        
        # Список возможных эмодзи шрифтов в порядке приоритета
        emoji_font_candidates = [
            "Noto Color Emoji",
            "Noto Emoji",
            "Apple Color Emoji",
            "Segoe UI Emoji",
            "EmojiOne Color",
            "Twitter Color Emoji",
            "JoyPixels",
        ]
        
        # Собираем список доступных эмодзи шрифтов
        fallback_families = [font.family()]  # Основной шрифт
        for emoji_font in emoji_font_candidates:
            if emoji_font in available_families:
                fallback_families.append(emoji_font)
        
        # Если нашли эмодзи шрифты, добавляем их в fallback
        if len(fallback_families) > 1:
            font.setFamilies(fallback_families)
        else:
            # Если эмодзи шрифты не найдены, пробуем использовать системный шрифт с поддержкой эмодзи
            # Многие системы имеют встроенную поддержку эмодзи через основной шрифт
            font_family = font.family()
            # Пробуем установить шрифт, который может поддерживать эмодзи
            if "DejaVu" in font_family or "Liberation" in font_family:
                # Для DejaVu/Liberation пробуем добавить Noto как fallback
                font.setFamilies([font_family, "Noto Color Emoji", "Noto Emoji"])
        
        self.setFont(font)

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.textChanged.connect(self._on_text_changed)

        self._update_line_number_area_width(0)
        self._highlight_current_line()

    # --- номера строк ---
    def line_number_area_width(self) -> int:
        digits = 1
        max_block = max(1, self.blockCount())
        while max_block >= 10:
            max_block //= 10
            digits += 1
        # небольшой отступ + ширина цифр
        char_width = self.fontMetrics().horizontalAdvance("9")
        return 4 + digits * char_width + 6

    def _update_line_number_area_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), Qt.GlobalColor.transparent)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.contentOffset().y() + self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        # стиль для номеров строк
        font = self.font()
        painter.setFont(font)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)

                # активная строка — жирнее
                if block_number == self.textCursor().blockNumber():
                    font.setWeight(QFont.Weight.Bold)
                else:
                    font.setWeight(QFont.Weight.Normal)
                painter.setFont(font)

                painter.setPen(Qt.GlobalColor.gray)
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 4,
                    int(self.blockBoundingRect(block).height()),
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    # --- подсветка текущей строки ---
    def _highlight_current_line(self) -> None:
        extra_selections = []

        if not self.isReadOnly():
            current_block_number = self.textCursor().blockNumber()
            alt_color = self.palette().alternateBase().color()
            alt_color.setAlpha(40)

            block = self.document().firstBlock()
            while block.isValid():
                text = block.text().rstrip("\n")
                color: Optional[QColor] = None

                # постоянная подсветка по символам в конце строки
                if text.endswith("+"):
                    color = QColor("#234d2a")  # зелёный фон
                elif text.endswith("-"):
                    color = QColor("#5a1f1f")  # красный фон
                elif text.endswith("!"):
                    color = QColor("#806b1a")  # жёлтый/оранжевый фон
                # если нет спец. символа, но это активная строка — мягкая подсветка
                elif block.blockNumber() == current_block_number:
                    color = alt_color

                if color is not None:
                    selection = QTextEdit.ExtraSelection()
                    selection.format.setBackground(color)
                    selection.format.setProperty(
                        QTextFormat.Property.FullWidthSelection, True
                    )
                    cursor = QTextCursor(block)
                    cursor.clearSelection()
                    selection.cursor = cursor
                    extra_selections.append(selection)

                block = block.next()

        self.setExtraSelections(extra_selections)

    # --- масштабирование текста (Ctrl + / Ctrl -) ---
    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                font = self.font()
                size = max(6, min(font.pointSize() + 1, 48))
                font.setPointSize(size)
                self.setFont(font)
                self._update_line_number_area_width(0)
                # вызываем колбэк для сохранения размера шрифта
                if self._on_font_size_changed:
                    self._on_font_size_changed(size)
                return
            if event.key() == Qt.Key.Key_Minus:
                font = self.font()
                size = max(6, min(font.pointSize() - 1, 48))
                font.setPointSize(size)
                self.setFont(font)
                self._update_line_number_area_width(0)
                # вызываем колбэк для сохранения размера шрифта
                if self._on_font_size_changed:
                    self._on_font_size_changed(size)
                return

        super().keyPressEvent(event)

    # --- автосортировка строк ---
    def _on_text_changed(self) -> None:
        """
        При изменении текста запускаем таймер для сортировки (debounce).
        """
        self._sort_timer.stop()
        self._sort_timer.start(500)  # сортировка через 500мс после последнего изменения

    def _sort_lines(self) -> None:
        """
        Сортирует строки по правилам:
        - строки с '-' в конце — самый верх
        - строки с '!' в конце — ниже красных
        - строки без символов — в середине
        - строки с '+' в конце — внизу
        """
        current_text = self.toPlainText()
        lines = current_text.split("\n")
        if not lines:
            return

        # сохраняем позицию курсора до сортировки
        cursor = self.textCursor()
        old_block_number = cursor.blockNumber()
        old_column = cursor.positionInBlock()
        old_line_text = ""
        if 0 <= old_block_number < len(lines):
            old_line_text = lines[old_block_number]

        # разделяем строки по категориям
        minus_lines: list[str] = []
        exclamation_lines: list[str] = []
        normal_lines: list[str] = []
        plus_lines: list[str] = []

        for line in lines:
            stripped = line.rstrip()
            if stripped.endswith("-"):
                minus_lines.append(line)
            elif stripped.endswith("!"):
                exclamation_lines.append(line)
            elif stripped.endswith("+"):
                plus_lines.append(line)
            else:
                normal_lines.append(line)

        # собираем в нужном порядке
        sorted_lines = minus_lines + exclamation_lines + normal_lines + plus_lines

        # устанавливаем отсортированный текст
        new_text = "\n".join(sorted_lines)
        if new_text != current_text:
            # блокируем сигналы, чтобы не запускать таймер при программном изменении
            self.blockSignals(True)
            self.setPlainText(new_text)
            self.blockSignals(False)

            # пытаемся восстановить позицию курсора
            if old_line_text:
                new_lines = new_text.split("\n")
                try:
                    new_block_number = new_lines.index(old_line_text)
                    new_cursor = QTextCursor(self.document().findBlockByNumber(new_block_number))
                    # восстанавливаем колонку
                    new_cursor.setPosition(
                        new_cursor.block().position() + min(old_column, len(new_cursor.block().text()))
                    )
                    self.setTextCursor(new_cursor)
                except ValueError:
                    # если строку не нашли, ставим курсор в начало
                    self.setTextCursor(QTextCursor(self.document()))


class EditorTab(QWidget):
    """
    Простая вкладка-редактор на базе QPlainTextEdit.
    """

    def __init__(self, initial_text: str = "", parent: Optional[QWidget] = None, font_size: int = 12, is_markdown: bool = False) -> None:
        super().__init__(parent)
        self._is_markdown = is_markdown
        self._is_preview_mode = is_markdown  # для markdown файлов начинаем с предпросмотра
        
        self.editor = CodeEditor(self, font_size=font_size)
        self.editor.setPlainText(initial_text)
        
        # Для markdown файлов добавляем предпросмотр и кнопку переключения
        self.preview = None
        self.toggle_button = None
        
        if is_markdown:
            self.preview = QTextEdit(self)
            self.preview.setReadOnly(True)
            self.preview.setStyleSheet("""
                QTextEdit {
                    background-color: #262335;
                    color: #E5E9F0;
                    border: none;
                }
            """)
            self._update_preview()
            
            self.toggle_button = QPushButton("Редактировать", self)
            self.toggle_button.setStyleSheet("""
                QPushButton {
                    background-color: #3A3756;
                    color: #E5E9F0;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #4A4566;
                }
            """)
            self.toggle_button.clicked.connect(self._toggle_mode)
            
            # Контейнер для кнопки
            button_container = QWidget(self)
            button_layout = QHBoxLayout(button_container)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.addStretch()
            button_layout.addWidget(self.toggle_button)
            
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(button_container)
            
            # Добавляем оба виджета в layout, но показываем только нужный
            # Важно: сначала добавляем editor, потом preview, чтобы они были в правильном порядке
            layout.addWidget(self.editor)
            layout.addWidget(self.preview)
            
            if self._is_preview_mode:
                self.editor.hide()
                self.preview.show()
                self.preview.raise_()  # Поднимаем preview наверх
            else:
                self.preview.hide()
                self.editor.show()
                self.editor.raise_()  # Поднимаем editor наверх
        else:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.editor)
        
        # Подключаем обновление предпросмотра при изменении текста
        if is_markdown:
            self.editor.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        """Обновляет предпросмотр при изменении текста (если в режиме предпросмотра)."""
        if self._is_preview_mode:
            self._update_preview()

    def _update_preview(self) -> None:
        """Обновляет HTML предпросмотр из Markdown."""
        if not self.preview:
            return
        md_text = self.editor.toPlainText()
        html = markdown.markdown(md_text, extensions=['fenced_code', 'tables'])
        # Добавляем базовые стили для предпросмотра
        styled_html = f"""
        <style>
            body {{ background-color: #262335; color: #E5E9F0; font-family: sans-serif; padding: 10px; }}
            code {{ background-color: #3A3756; padding: 2px 4px; border-radius: 3px; }}
            pre {{ background-color: #3A3756; padding: 10px; border-radius: 5px; overflow-x: auto; }}
            a {{ color: #8B9DC3; }}
            h1, h2, h3, h4, h5, h6 {{ color: #E5E9F0; }}
            blockquote {{ border-left: 3px solid #4A4566; padding-left: 10px; margin-left: 0; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #3A3756; padding: 8px; }}
            th {{ background-color: #3A3756; }}
        </style>
        {html}
        """
        self.preview.setHtml(styled_html)

    def _toggle_mode(self) -> None:
        """Переключает между режимом редактирования и предпросмотра."""
        if not self._is_markdown:
            return
        
        self._is_preview_mode = not self._is_preview_mode
        
        if self._is_preview_mode:
            self._update_preview()
            self.editor.hide()
            self.preview.show()
            self.preview.raise_()  # Поднимаем preview наверх
            self.toggle_button.setText("Редактировать")
        else:
            self.preview.hide()
            self.editor.show()
            self.editor.raise_()  # Поднимаем editor наверх
            self.toggle_button.setText("Предпросмотр")

    def get_text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)
        # сортируем строки сразу после загрузки (только для не-markdown)
        if not self._is_markdown:
            self.editor._sort_lines()
        elif self._is_preview_mode:
            self._update_preview()


class MainWindow(QMainWindow):
    """
    Главное окно без рамки, с табами-файлами и простым текстовым холстом.
    """

    def __init__(self, file_manager: FileManager, config: ConfigManager) -> None:
        super().__init__()
        self._file_manager = file_manager
        self._config = config

        self._init_window_flags()
        self._init_ui()
        self._restore_tabs_from_files()

    # --- оформление окна ---
    def _init_window_flags(self) -> None:
        # Безрамочное окно. Hyprland корректно работает с такими окнами.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowSystemMenuHint
        )
        # Глобальная тёмная цветовая схема в стиле #241B2F / #262335
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #241B2F;
                color: #E5E9F0;
            }

            QTabWidget::pane {
                border: 0px;
                background: #241B2F;
            }

            QTabBar::tab {
                background: #241B2F;
                color: #E5E9F0;
                padding: 6px 12px;
                margin-right: 2px;
                border-radius: 6px 6px 0 0;
            }

            QTabBar::tab:selected {
                background: #262335;
            }

            QTabBar::tab:hover {
                background: #2B2940;
            }

            QPlainTextEdit {
                background-color: #262335;
                color: #E5E9F0;
                border: none;
                selection-background-color: #3A3756;
                selection-color: #E5E9F0;
            }

            QScrollBar:vertical, QScrollBar:horizontal {
                background: #241B2F;
                border: none;
                margin: 0px;
            }

            QScrollBar::handle {
                background: #3A3756;
                border-radius: 4px;
            }

            QScrollBar::handle:hover {
                background: #4A4566;
            }

            QFileDialog {
                background-color: #241B2F;
                color: #E5E9F0;
            }
            """
        )

    # --- UI ---
    def _init_ui(self) -> None:
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(False)  # Убираем крестики
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBarClicked.connect(self._on_tab_bar_clicked)
        self.tabs.tabBarDoubleClicked.connect(self._on_tab_bar_double_clicked)

        self.setCentralWidget(self.tabs)

        # Горячие клавиши: Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+S
        self._create_actions()

    def _create_actions(self) -> None:
        new_action = QAction("New", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._on_new_file)

        open_action = QAction("Open", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_file_dialog)

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save)

        save_as_action = QAction("Save As", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_as)

        close_tab_action = QAction("Close Tab", self)
        close_tab_action.setShortcut("Ctrl+Q")
        close_tab_action.triggered.connect(self._on_close_current_tab)

        self.addAction(new_action)
        self.addAction(open_action)
        self.addAction(save_action)
        self.addAction(save_as_action)
        self.addAction(close_tab_action)

    # --- работа с табами и FileManager ---

    def _restore_tabs_from_files(self) -> None:
        self.tabs.clear()

        state = self._config.state
        titles_from_state = state.titles
        font_size = state.font_size

        for i, path in enumerate(self._file_manager.files):
            text = self._file_manager.get_buffer(i)
            # если в конфиге есть своё имя вкладки — используем его, иначе имя файла или "untitled"
            if 0 <= i < len(titles_from_state) and titles_from_state[i].strip():
                title = titles_from_state[i].strip()
            else:
                title = path.name if path and path.name else "untitled"
            is_md = path and path.suffix.lower() == ".md"
            self._create_editor_tab(text, title, font_size, is_markdown=is_md)

        self._ensure_plus_tab()

        # Восстанавливаем активную вкладку из конфига
        active_index = state.active_index
        # Проверяем, что индекс валиден (не выходит за границы и не является вкладкой "+")
        if 0 <= active_index < self.tabs.count():
            # Пропускаем вкладку "+" если она оказалась на позиции active_index
            if not self._is_plus_tab(active_index):
                self.tabs.setCurrentIndex(active_index)
                self._file_manager._active_index = active_index
            else:
                # Если активная вкладка была "+", выбираем предыдущую или первую
                if active_index > 0:
                    self.tabs.setCurrentIndex(active_index - 1)
                    self._file_manager._active_index = active_index - 1
                elif self.tabs.count() > 1:
                    # Если есть другие вкладки, выбираем первую (не "+")
                    self.tabs.setCurrentIndex(0)
                    self._file_manager._active_index = 0
        else:
            # Если индекс невалиден, выбираем первую вкладку (если есть)
            if self.tabs.count() > 1:
                self.tabs.setCurrentIndex(0)
                self._file_manager._active_index = 0

    def _sync_current_editor_to_manager(self) -> None:
        idx = self.tabs.currentIndex()
        if idx < 0:
            return
        widget = self.tabs.widget(idx)
        if isinstance(widget, EditorTab):
            self._file_manager.set_buffer(widget.get_text(), idx)

    def _refresh_tab_title(self, index: int) -> None:
        if index < 0 or index >= len(self._file_manager.files):
            return
        path = self._file_manager.files[index]
        title = path.name if path and path.name else "untitled"
        self.tabs.setTabText(index, title)

    # --- слоты / обработчики ---

    def _on_new_file(self) -> None:
        self._sync_current_editor_to_manager()
        idx = self._file_manager.new_file()
        font_size = self._config.state.font_size
        index = self._create_editor_tab("", "untitled", font_size)
        self._ensure_plus_tab()
        # текущая вкладка в менеджере и в UI должны совпадать
        self.tabs.setCurrentIndex(index)

    def _on_open_file_dialog(self) -> None:
        self._sync_current_editor_to_manager()
        before_count = len(self._file_manager.files)
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open file",
            "",
            "Text files (*.txt);;Markdown files (*.md);;All files (*.*)",
        )
        if not path_str:
            return

        idx = self._file_manager.open_file(Path(path_str))
        text = self._file_manager.get_buffer(idx)

        after_count = len(self._file_manager.files)
        is_new = after_count > before_count

        if not is_new and 0 <= idx < self.tabs.count():
            # файл уже был открыт — просто обновим текст в соответствующей вкладке
            widget = self.tabs.widget(idx)
            if isinstance(widget, EditorTab):
                widget.set_text(text)
            # Делаем эту вкладку активной
            self.tabs.setCurrentIndex(idx)
            self._file_manager._active_index = idx
        else:
            # новый файл — создаём новую вкладку перед «+»
            font_size = self._config.state.font_size
            path = Path(path_str)
            is_md = path.suffix.lower() == ".md"
            index = self._create_editor_tab(text, path.name, font_size, is_markdown=is_md)
            self._ensure_plus_tab()
            # Делаем новую вкладку активной
            self.tabs.setCurrentIndex(index)
            self._file_manager._active_index = idx

        self._refresh_tab_title(idx)

    def _on_save(self) -> None:
        self._sync_current_editor_to_manager()
        idx = self.tabs.currentIndex()
        if idx < 0:
            return

        current_path = self._file_manager.files[idx]
        if not current_path:
            self._on_save_as()
            return

        try:
            self._file_manager.save_file(index=idx)
        except Exception:
            return
        self._refresh_tab_title(idx)

    def _on_save_as(self) -> None:
        self._sync_current_editor_to_manager()
        idx = self.tabs.currentIndex()
        if idx < 0:
            return

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save file as",
            "",
            "Text files (*.txt);;All files (*.*)",
        )
        if not path_str:
            return

        path = Path(path_str)
        try:
            self._file_manager.save_file(path=path, index=idx)
        except Exception:
            return
        self._refresh_tab_title(idx)

    def _on_tab_close_requested(self, index: int) -> None:
        if index < 0:
            return
        # нельзя закрыть служебную вкладку с "+"
        if self._is_plus_tab(index):
            return
        # синхронизируем текст перед закрытием
        widget = self.tabs.widget(index)
        if isinstance(widget, EditorTab):
            self._file_manager.set_buffer(widget.get_text(), index)
        self._file_manager.close_file(index)
        self.tabs.removeTab(index)
        self._ensure_plus_tab()

    def _on_close_current_tab(self) -> None:
        """
        Закрывает текущую активную вкладку по Ctrl+Q.
        """
        current_index = self.tabs.currentIndex()
        if current_index >= 0:
            self._on_tab_close_requested(current_index)

    def _on_tab_changed(self, index: int) -> None:
        # при переключении вкладки обновляем активный индекс в FileManager
        if index < 0:
            return
        # игнорируем служебную вкладку с "+"
        if self._is_plus_tab(index):
            return
        self._sync_current_editor_to_manager()
        self._file_manager._active_index = index  # внутренний индекс; можно обернуть в метод

    def _on_tab_bar_clicked(self, index: int) -> None:
        """
        Обработка клика по вкладке: если это вкладка «+» — показываем меню создания/открытия.
        """
        if self._is_plus_tab(index):
            # не переключаемся на неё, а открываем меню
            self.tabs.setCurrentIndex(self._file_manager.active_index)
            self._on_new_tab_menu()

    def _on_tab_bar_double_clicked(self, index: int) -> None:
        """
        Двойной клик по имени вкладки — переименование вкладки.
        """
        if index < 0:
            return
        # не даём переименовывать служебную вкладку «+»
        if self._is_plus_tab(index):
            return
        old_title = self.tabs.tabText(index)
        new_title, ok = QInputDialog.getText(
            self,
            "Переименовать вкладку",
            "Имя вкладки:",
            text=old_title,
        )
        if ok and new_title.strip():
            self.tabs.setTabText(index, new_title.strip())

    def _on_new_tab_menu(self) -> None:
        """
        Меню по клику на вкладку «+»:
        - новый файл
        - открыть существующий
        """
        menu = QMenu(self)
        new_action = menu.addAction("Новый файл")
        open_action = menu.addAction("Открыть файл…")

        action = menu.exec(QCursor.pos())
        if action is new_action:
            self._on_new_file()
        elif action is open_action:
            self._on_open_file_dialog()

    def _create_editor_tab(self, text: str, title: str, font_size: int = 12, is_markdown: bool = False) -> int:
        """
        Создаёт вкладку-редактор, вставляя её перед вкладкой «+», если она есть.
        """
        tab = EditorTab(initial_text=text, font_size=font_size, is_markdown=is_markdown)
        # автосохранение при каждом изменении текста
        tab.editor.textChanged.connect(self._on_editor_text_changed)
        # колбэк для сохранения размера шрифта при изменении
        tab.editor._on_font_size_changed = lambda size: self._on_font_size_changed(size)
        plus_idx = -1
        for i in range(self.tabs.count()):
            if self._is_plus_tab(i):
                plus_idx = i
                break

        if plus_idx >= 0:
            index = self.tabs.insertTab(plus_idx, tab, title)
        else:
            index = self.tabs.addTab(tab, title)
        return index

    def _on_editor_text_changed(self) -> None:
        """
        Автосохранение в реальном времени: обновляем буфер и, если есть путь, пишем на диск.
        """
        sender = self.sender()
        if not isinstance(sender, QPlainTextEdit):
            return

        # находим вкладку, которой принадлежит этот редактор
        idx = -1
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, EditorTab) and widget.editor is sender:
                idx = i
                break

        if idx < 0 or self._is_plus_tab(idx):
            return

        # обновляем буфер
        self._file_manager.set_buffer(sender.toPlainText(), idx)

        # если у этого буфера уже есть путь — сохраняем на диск
        files = self._file_manager.files
        if 0 <= idx < len(files):
            path = files[idx]
            if path and not path.is_dir():
                try:
                    self._file_manager.save_file(index=idx)
                except Exception:
                    # если сохранить не удалось, просто игнорируем
                    pass

    def _ensure_plus_tab(self) -> None:
        """
        Гарантирует наличие служебной вкладки «+» в самом конце.
        """
        # удаляем старую вкладку «+», если была
        for i in range(self.tabs.count()):
            if self._is_plus_tab(i):
                self.tabs.removeTab(i)
                break

        plus_widget = QWidget()
        plus_index = self.tabs.addTab(plus_widget, "+")
        # на служебной вкладке не должно быть кнопки сохранения
        self.tabs.tabBar().setTabButton(plus_index, QTabBar.ButtonPosition.RightSide, None)

    def _is_plus_tab(self, index: int) -> bool:
        return 0 <= index < self.tabs.count() and self.tabs.tabText(index) == "+"

    # --- события окна ---

    def _on_font_size_changed(self, font_size: int) -> None:
        """
        Сохраняет размер шрифта в конфиг при изменении.
        """
        self._sync_current_editor_to_manager()
        titles: list[str] = []
        for i in range(self.tabs.count()):
            if self._is_plus_tab(i):
                continue
            titles.append(self.tabs.tabText(i))
        self._file_manager.save_state(titles, font_size)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        # перед закрытием — синхронизируем буферы и сохраняем список файлов и заголовков вкладок
        self._sync_current_editor_to_manager()
        titles: list[str] = []
        for i in range(self.tabs.count()):
            # пропускаем служебную вкладку "+"
            if self._is_plus_tab(i):
                continue
            titles.append(self.tabs.tabText(i))
        # получаем текущий размер шрифта из активной вкладки и сохраняем активный индекс
        font_size = 12
        idx = self.tabs.currentIndex()
        if idx >= 0:
            widget = self.tabs.widget(idx)
            if isinstance(widget, EditorTab):
                font_size = widget.editor.font().pointSize()
            # Обновляем активный индекс в file_manager перед сохранением
            self._file_manager._active_index = idx
        self._file_manager.save_state(titles, font_size)
        super().closeEvent(event)


