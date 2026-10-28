"""Окно приложения MAUT.

Запуск: python app.py [файл.json]
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")

from gui.tabs import (AlternativesTab, CompareTab, CriteriaTab, CurvesTab,  # noqa: E402
                      IndependenceTab, WeightsTab)
from gui.widgets import show_error  # noqa: E402
from maut import MautError, Project  # noqa: E402

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"


class App:
    def __init__(self, root: tk.Tk, path: str | None = None):
        self.root = root
        self.project = Project("Новый проект")
        self.path: Path | None = None
        self.dirty = False
        root.title("MAUT")
        self._fit_window()
        if sys.platform.startswith("linux"):
            ttk.Style().theme_use("clam")
        self._menu()

        bar = ttk.Frame(root, padding=(8, 6, 8, 0))
        bar.pack(fill="x")
        for text, cmd in (("Новый", self.new), ("Открыть…", self.open), ("Сохранить", self.save),
                          ("Пример «Аэропорт»", lambda: self.load_example("airport_empty.json")),
                          ("Пример заполненный", lambda: self.load_example("airport.json"))):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Label(bar, text="Название:").pack(side="left", padx=(16, 4))
        self.title_var = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.title_var, width=40)
        e.pack(side="left")
        e.bind("<FocusOut>", lambda _: self._set_title())
        e.bind("<Return>", lambda _: self._set_title())

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = []
        for cls, text in ((CriteriaTab, "1. Критерии"), (CurvesTab, "2. Функции полезности"),
                          (IndependenceTab, "3. Независимость"), (WeightsTab, "4. Веса"),
                          (AlternativesTab, "5. Альтернативы"), (CompareTab, "6. Сравнение режимов")):
            tab = cls(self.nb, self)
            self.nb.add(tab, text=text)
            self.tabs.append(tab)
        self.nb.bind("<<NotebookTabChanged>>", lambda _: self._current().refresh())

        self.status = ttk.Label(root, text="", anchor="w", padding=(8, 2))
        self.status.pack(fill="x", side="bottom")
        root.protocol("WM_DELETE_WINDOW", self.quit)

        if path:
            self._load(Path(path))
        self.refresh_all()

    def _fit_window(self):
        """Окно 1360×860, а если экран меньше (или в Windows включено масштабирование) — на весь экран."""
        root = self.root
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.minsize(min(1100, sw - 40), min(700, sh - 80))
        if sw >= 1400 and sh >= 940:
            root.geometry("1360x860")
            return
        try:
            root.state("zoomed")              # Windows
        except tk.TclError:
            root.attributes("-zoomed", True)  # Linux

    def _menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=False)
        f.add_command(label="Новый", command=self.new)
        f.add_command(label="Открыть…", command=self.open)
        f.add_command(label="Сохранить", command=self.save)
        f.add_command(label="Сохранить как…", command=self.save_as)
        f.add_separator()
        f.add_command(label="Пример «Аэропорт» (только критерии)",
                      command=lambda: self.load_example("airport_empty.json"))
        f.add_command(label="Пример «Аэропорт» (заполненный)", command=lambda: self.load_example("airport.json"))
        f.add_separator()
        f.add_command(label="Выход", command=self.quit)
        m.add_cascade(label="Файл", menu=f)
        self.root.config(menu=m)

    def _current(self):
        return self.tabs[self.nb.index(self.nb.select())]

    # --------------------------------------------------------------- обновление

    def changed(self):
        self.dirty = True
        self.refresh_all()

    def refresh_all(self):
        self._current().refresh()
        self.title_var.set(self.project.title)
        name = self.path.name if self.path else "без имени"
        self.root.title(f"MAUT — {name}{' *' if self.dirty else ''}")
        self.status.config(text="   ".join(f"{k}: {v}" for k, v in self.project.progress()))

    def _set_title(self):
        t = self.title_var.get().strip()
        if t != self.project.title:
            self.project.title = t
            self.changed()

    # --------------------------------------------------------------- файлы

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("MAUT", "Сохранить изменения в текущем проекте?")
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def new(self):
        if self._confirm_discard():
            self.project, self.path, self.dirty = Project("Новый проект"), None, False
            self.refresh_all()

    def open(self):
        if not self._confirm_discard():
            return
        f = filedialog.askopenfilename(filetypes=[("Проект MAUT", "*.json"), ("Все файлы", "*.*")],
                                       initialdir=str(EXAMPLES) if EXAMPLES.exists() else None)
        if f:
            self._load(Path(f))

    def _load(self, path: Path):
        try:
            self.project = Project.load(path)
        except (OSError, MautError, KeyError, ValueError) as e:
            show_error(MautError(f"Не удалось открыть {path.name}: {e}"))
            return
        self.path, self.dirty = path, False
        self.refresh_all()

    def load_example(self, name: str):
        if not self._confirm_discard():
            return
        self._load(EXAMPLES / name)
        self.path = None  # пример не перезаписываем: «Сохранить» спросит имя
        self.refresh_all()

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        try:
            self.project.save(self.path)
        except OSError as e:
            show_error(e)
            return False
        self.dirty = False
        self.refresh_all()
        return True

    def save_as(self) -> bool:
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Проект MAUT", "*.json")])
        if not f:
            return False
        self.path = Path(f)
        return self.save()

    def quit(self):
        if self._confirm_discard():
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()


if __name__ == "__main__":
    main()
