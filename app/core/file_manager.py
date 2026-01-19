from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from ..config import ConfigManager


class FileManager:
    """
    Управляет списком открытых файлов, загрузкой/сохранением и состоянием вкладок.
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._files: List[Path] = []
        self._buffers: List[str] = []
        self._active_index: int = 0

        self._restore_from_config()

    # --- публичные свойства ---

    @property
    def files(self) -> List[Path]:
        return list(self._files)

    @property
    def active_index(self) -> int:
        return self._active_index

    def get_buffer(self, index: Optional[int] = None) -> str:
        idx = self._active_index if index is None else index
        if 0 <= idx < len(self._buffers):
            return self._buffers[idx]
        return ""

    # --- операции с файлами ---

    def open_file(self, path: Path) -> int:
        """
        Открыть файл (если уже открыт — просто активировать вкладку).
        Возвращает индекс вкладки.
        """
        # если файл уже открыт — активировать
        for i, p in enumerate(self._files):
            if p == path:
                self._active_index = i
                return i

        text = ""
        try:
            if path.exists():
                text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""

        self._files.append(path)
        self._buffers.append(text)
        self._active_index = len(self._files) - 1
        return self._active_index

    def new_file(self) -> int:
        """
        Создать новый «безымянный» файл (пока без привязки к пути).
        """
        self._files.append(Path(""))
        self._buffers.append("")
        self._active_index = len(self._files) - 1
        return self._active_index

    def set_buffer(self, text: str, index: Optional[int] = None) -> None:
        idx = self._active_index if index is None else index
        if 0 <= idx < len(self._buffers):
            self._buffers[idx] = text

    def save_file(self, path: Optional[Path] = None, index: Optional[int] = None) -> Path:
        idx = self._active_index if index is None else index
        if idx < 0 or idx >= len(self._buffers):
            raise IndexError("Нет активного буфера для сохранения")

        if path is not None:
            self._files[idx] = path

        target = self._files[idx]
        if not target:
            raise ValueError("Не указан путь для сохранения файла")
        # Защита от попытки сохранить в директорию (например, если пользователь выбрал ".")
        if target.exists() and target.is_dir():
            raise ValueError(f"Нельзя сохранить в директорию: {target}")

        target.write_text(self._buffers[idx], encoding="utf-8")
        return target

    def close_file(self, index: Optional[int] = None) -> None:
        idx = self._active_index if index is None else index
        if 0 <= idx < len(self._files):
            self._files.pop(idx)
            self._buffers.pop(idx)
            if self._files:
                self._active_index = max(0, idx - 1)
            else:
                self._active_index = 0

    # --- конфиг ---

    def _restore_from_config(self) -> None:
        state = self._config.state
        self._files = []
        self._buffers = []
        self._active_index = 0

        last_files = state.last_files
        buffers = getattr(state, "buffers", [])
        max_len = max(len(last_files), len(buffers))

        for i in range(max_len):
            p_str = last_files[i] if i < len(last_files) else ""
            buf = buffers[i] if i < len(buffers) else ""

            path = Path(p_str) if p_str else Path("")
            text = buf

            # если есть валидный путь к файлу — пробуем перечитать с диска,
            # а если не получилось, оставляем буфер из конфига
            if p_str:
                try:
                    if path.exists() and path.is_file():
                        text = path.read_text(encoding="utf-8")
                except Exception:
                    pass

            self._files.append(path)
            self._buffers.append(text)

        # если конфиг пустой — создадим один новый файл
        if not self._files:
            self.new_file()
        else:
            if 0 <= state.active_index < len(self._files):
                self._active_index = state.active_index

    def save_state(self, titles: List[str]) -> None:
        """
        Сохраняет текущее состояние файлов, активный индекс, заголовки вкладок и буферы.
        """
        self._config.save(self._files, self._active_index, titles, self._buffers)


