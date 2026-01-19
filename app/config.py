from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional


CONFIG_DIR = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "hyprtext"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class AppState:
    last_files: List[str]
    active_index: int
    titles: List[str]
    buffers: List[str]
    font_size: int


class ConfigManager:
    """
    Отвечает за сохранение и загрузку состояния приложения (последние файлы и активная вкладка).
    """

    def __init__(self) -> None:
        self._state = AppState(last_files=[], active_index=0, titles=[], buffers=[], font_size=12)
        self._load()

    @property
    def state(self) -> AppState:
        return self._state

    def _load(self) -> None:
        try:
            if CONFIG_FILE.exists():
                with CONFIG_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self._state = AppState(
                    last_files=data.get("last_files", []),
                    active_index=int(data.get("active_index", 0)),
                    titles=data.get("titles", []),
                    buffers=data.get("buffers", []),
                    font_size=int(data.get("font_size", 12)),
                )
        except Exception:
            # если конфиг битый — просто игнорируем
            self._state = AppState(last_files=[], active_index=0, titles=[], buffers=[], font_size=12)

    def save(
        self,
        last_files: List[Path],
        active_index: int,
        titles: List[str],
        buffers: List[str],
        font_size: int,
    ) -> None:
        self._state = AppState(
            last_files=[str(p) for p in last_files],
            active_index=active_index,
            titles=titles,
            buffers=buffers,
            font_size=font_size,
        )
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(asdict(self._state), f, ensure_ascii=False, indent=2)


