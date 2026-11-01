"""Pro File Packer Enterprise - generator plikow, pakowanie, rozpakowywanie,
bezpieczenstwo (hashe, format PFA) oraz GUI (PySide6) i CLI w jednym pliku.

Uruchomienie GUI:   python ZIPps.py
Uruchomienie CLI:   python ZIPps.py --help
"""

__version__ = "2.0.0"
__app_name__ = "Pro File Packer Enterprise"

import os
import sys
import json
import math
import stat
import shutil
import struct
import zlib
import time
import uuid
import hashlib
import zipfile
import tarfile
import fnmatch
import argparse
import tempfile
import subprocess
import threading
import traceback
import webbrowser
import py_compile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

#: czy PySide6 jest dostepne (CLI dziala takze bez Qt)
QT_AVAILABLE = True
#: szczegoly bledu importu Qt (pusty, gdy Qt jest dostepne)
_qt_error_details = ""

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
        QFormLayout, QGridLayout, QLayout, QLabel, QLineEdit, QPlainTextEdit,
        QPushButton, QToolButton, QFileDialog, QComboBox, QSpinBox, QCheckBox,
        QMessageBox, QListWidget, QListWidgetItem, QProgressBar, QStyle, QSplitter,
        QGroupBox, QAbstractItemView, QSizePolicy, QDialog, QDialogButtonBox, QMenu,
        QTextBrowser, QTableWidget, QTableWidgetItem
    )
    from PySide6.QtCore import (Qt, Signal, QObject, QThread, QEvent, QTimer, QSize,
                                qVersion)
    from PySide6.QtGui import (
        QDragEnterEvent, QDropEvent, QIcon, QPixmap, QPainter, QColor, QPen, QAction,
        QKeySequence, QShortcut, QActionGroup
    )
except ImportError as _qt_error:  # pragma: no cover - zalezy od srodowiska
    QT_AVAILABLE = False
    _qt_error_details = str(_qt_error)

#: wersja Qt uzywana w okienku "O programie" (brak, gdy Qt niedostepne)
QT_VERSION = qVersion() if QT_AVAILABLE else "niedostepne"


class QtUnavailableError(RuntimeError):
    """Podniesiony, gdy GUI jest wymagane, a PySide6 nie zostalo zainstalowane."""


def require_qt() -> None:
    """Rzuc czytelny blad, jezeli PySide6 nie jest dostepne."""
    if QT_AVAILABLE:
        return
    raise QtUnavailableError(
        "Brakuje biblioteki PySide6, ktora jest wymagana przez interfejs graficzny.\n"
        "Zainstaluj ja poleceniem:\n\n    pip install PySide6\n\n"
        "Szczegoly: %s" % _qt_error_details)


# =====================================================================
#  Styl interfejsu
# =====================================================================

#: sciezka pliku ze stylem QSS (wczytywany leniwie przy starcie GUI)
QSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.qss")


def load_stylesheet() -> str:
    """Wczytuje arkusz stylow z pliku style.qss (pusty napis, gdy plik nie istnieje)."""
    try:
        with open(QSS_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as ex:
        Logger().error("Nie udalo sie wczytac %s: %s" % (QSS_PATH, ex))
        return ""


# =====================================================================
#  Tlumaczenia (polski / angielski)
# =====================================================================

LANG = {
    "en": {
        "app_title": "Pro File Packer Enterprise",
        "menu_file": "&File",
        "menu_tools": "&Tools",
        "menu_view": "&View",
        "menu_help": "&Help",
        "tab_generate": "File Generator",
        "tab_pack": "Pack Files",
        "tab_unpack": "Unpack Archive",
        "tab_security": "Security",
        "tab_settings": "Settings",
        "lang_label": "Language",
        "select_files": "Select files",
        "select_folder": "Select folder",
        "select_archive": "Select archive",
        "output_folder": "Output folder",
        "archive_format": "Archive format",
        "btn_pack": "Pack",
        "btn_unpack": "Unpack",
        "btn_generate_text": "Text file",
        "btn_generate_bin": "Binary file",
        "btn_generate_pyc": "Python .pyc",
        "btn_generate_c": "C file",
        "btn_generate_cpp": "C++ file",
        "btn_generate_raw": "RAW image",
        "btn_generate_json": "JSON data",
        "btn_generate_markdown": "Markdown",
        "btn_generate_script": "Python script",
        "file_name": "File name",
        "file_ext": "Extension",
        "bin_size": "Binary size (bytes)",
        "code_area": "Content / Python code",
        "log": "Log",
        "status_ready": "Ready",
        "status_packing": "Packing...",
        "status_unpacking": "Unpacking...",
        "status_generating": "Generating...",
        "status_hashing": "Hashing...",
        "status_testing": "Testing...",
        "recursive": "Pack folders recursively",
        "filter_ext": "Extension filter (e.g. .txt;.c)",
        "archive_contents": "Archive contents",
        "extract_all": "Extract all",
        "extract_selected": "Extract selected",
        "progress": "Progress",
        "hash_file": "Hash file",
        "hash_algo": "Algorithm",
        "hash_result": "Result",
        "pfa_create": "Create PFA archive",
        "pfa_unpack": "Unpack PFA archive",
        "pfa_file": "PFA file",
        "error": "Error",
        "generated": "File generated: ",
        "packed": "Archive created: ",
        "unpacked": "Archive unpacked to: ",
        "drag_hint": "Drag files or archives here",
        # --- v2 ---
        "group_source": "Files to pack",
        "group_output": "Archive",
        "group_archive": "Archive",
        "group_extract": "Extraction options",
        "group_archive_tools": "Archive tools",
        "group_hash": "File checksums",
        "group_pfa": "Custom PFA archives",
        "group_appearance": "Appearance and behaviour",
        "group_about": "About",
        "group_generator": "Generator",
        "add_files": "Add files",
        "add_folder": "Add folder",
        "remove": "Remove",
        "clear": "Clear",
        "save_list": "Save list",
        "load_list": "Load list",
        "items_count": "{0} file(s), {1}",
        "archive_path": "Archive path",
        "browse": "Browse...",
        "format_zip": "ZIP (.zip)",
        "format_tar": "TAR (.tar)",
        "format_targz": "TAR GZIP (.tar.gz)",
        "format_tarbz2": "TAR BZIP2 (.tar.bz2)",
        "format_tarxz": "TAR XZ (.tar.xz)",
        "format_pfa": "PFA (custom)",
        "compression_level": "Compression level",
        "include_root": "Store folder names in archive",
        "follow_symlinks": "Follow symbolic links",
        "password": "Password (AES-256 for ZIP / encryption for PFA)",
        "confirm_password": "Repeat password",
        "password_optional": "(optional)",
        "add_to_archive": "Add files to existing archive",
        "create_archive": "Create archive",
        "load_archive": "Load",
        "verify_archive": "Test archive",
        "filter": "Filter",
        "select_all": "Select all",
        "select_none": "Deselect all",
        "folder_not_exist": "Folder does not exist",
        "file_not_exist": "File does not exist",
        "no_files": "No files to process",
        "invalid_size": "Invalid size",
        "password_mismatch": "Passwords do not match!",
        "need_password": "This archive requires a password. Enter it and try again.",
        "wrong_password": "Wrong password or corrupted archive.",
        "unsupported_zstd": "Compression requires Python 3.14+ (ZIP_ZSTANDARD).",
        "unknown_format": "Unrecognized archive format",
        "archive_ok": "Archive test finished: {0} file(s), {1}",
        "archive_damaged": "Archive is damaged: {0}",
        "unknown_entry": "Unknown entry",
        "hash_multi": "Hash a directory",
        "compare": "Compare with expected",
        "copy": "Copy",
        "save": "Save to file",
        "hash_empty": "Enter a file path and an expected hash",
        "hash_match": "Hash MATCHES the expected value.",
        "hash_mismatch": "Hash does NOT match the expected value!",
        "done": "Done: {0}",
        "busy": "Another operation is still running, please wait.",
        "status_working": "Working...",
        "status_done": "Done",
        "status_error": "Error",
        "status_cancelled": "Cancelled",
        "status_paths": "{0} file(s), {1}",
        "cancelled": "Operation cancelled",
        "appearance_qss": "Enable dark theme (QSS)",
        "appearance_default_dir": "Default folder",
        "language": "Language",
        "save_settings": "Save settings",
        "settings_path": "Settings file",
        "about_text": (
            "<h3>{name} v{ver}</h3>"
            "<p>All-in-one tool: generates files, packs and unpacks archives "
            "(ZIP/TAR/PFA), computes checksums, handles AES-256 encrypted ZIP and "
            "custom encrypted PFA archives.</p>"
            "<p>Archive extraction is protected against <b>Zip Slip</b> attacks, "
            "and encrypted archives are guarded against bit-flipping attacks.</p>"
            "<p>Python {py} | PySide6 {qt} | {platform}</p>"
        ),
        "close": "Close",
        "quit": "Quit",
        "clear_log": "Clear log",
        "save_log": "Save log",
        "open_in_editor": "Open in editor",
        "open_folder": "Open containing folder",
        "total_size": "Total",
        "scan_hidden": "Skip hidden files",
        "include_dirs": "Include empty folders",
        "files": "File",
        "folder": "Folder",
        "inspect": "Inspect",
        "inspect_pyc": "Inspect .pyc",
        "info_title": "File information",
        "pattern_help": "Wildcards allowed: e.g. *.py, *.txt;*.md",
        "font_size": "Font size",
        "modal_dialogs": "Show confirmation dialogs (otherwise log + status bar)",
        "preset_label": "Preset",
        "preset_empty": "Empty text file",
        "preset_markdown": "Markdown document",
        "preset_license": "MIT license",
        "preset_gitignore": ".gitignore",
        "confirmed": "Confirmed",
        "result": "Result",
        "extract_to": "Extract to",
        "overwrite_existing": "Overwrite existing files",
        "reset": "Reset",
        "cmd_copy_path": "Copy path",
        "cmd_reveal": "Show in Explorer",
        "cmd_remove": "Remove from list",
        "shortcut_help_title": "Keyboard shortcuts",
        "shortcut_help": (
            "<table cellpadding=2>"
            "<tr><td>Ctrl+1..6</td><td>Switch between tabs</td></tr>"
            "<tr><td>Ctrl+O</td><td>Add files (Pack tab)</td></tr>"
            "<tr><td>Ctrl+Shift+O</td><td>Add folder (Pack tab)</td></tr>"
            "<tr><td>Ctrl+E</td><td>Create archive</td></tr>"
            "<tr><td>Ctrl+U</td><td>Unpack all</td></tr>"
            "<tr><td>Ctrl+G</td><td>Generate file</td></tr>"
            "<tr><td>Ctrl+Shift+H</td><td>Hash file</td></tr>"
            "<tr><td>F5</td><td>Refresh / validate</td></tr>"
            "<tr><td>Del</td><td>Remove selected from list</td></tr>"
            "<tr><td>Ctrl+L</td><td>Clear log</td></tr>"
            "</table>"
        ),
        "about": "About",
        "about_author": "Author",
        "about_name": "Author",
        "about_company": "Company",
        "about_email": "Email",
        "about_github": "GitHub",
        "help": "Help",
        "act_open_generated": "Open generated file",
        "act_add_files": "Add files",
        "act_add_folder": "Add folder",
        "act_pack": "Create archive",
        "act_unpack": "Unpack all",
        "act_generate": "Generate file",
        "act_hash": "Hash file",
        "act_test": "Test archive",
        "act_clear_log": "Clear log",
        "act_save_log": "Save log",
        "act_quit": "Quit",
    },
    "pl": {
        "app_title": "Pro File Packer Enterprise",
        "menu_file": "&Plik",
        "menu_tools": "&Narzedzia",
        "menu_view": "&Widok",
        "menu_help": "&Pomoc",
        "tab_generate": "Generator plikow",
        "tab_pack": "Pakowanie",
        "tab_unpack": "Rozpakowywanie",
        "tab_security": "Bezpieczenstwo",
        "tab_settings": "Ustawienia",
        "lang_label": "Jezyk",
        "select_files": "Wybierz pliki",
        "select_folder": "Wybierz folder",
        "select_archive": "Wybierz archiwum",
        "output_folder": "Folder wyjsciowy",
        "archive_format": "Format archiwum",
        "btn_pack": "Pakuj",
        "btn_unpack": "Rozpakuj",
        "btn_generate_text": "Plik tekstowy",
        "btn_generate_bin": "Plik binarny",
        "btn_generate_pyc": "Python .pyc",
        "btn_generate_c": "Plik C",
        "btn_generate_cpp": "Plik C++",
        "btn_generate_raw": "Obraz RAW",
        "btn_generate_json": "Dane JSON",
        "btn_generate_markdown": "Markdown",
        "btn_generate_script": "Skrypt Python",
        "file_name": "Nazwa pliku",
        "file_ext": "Rozszerzenie",
        "bin_size": "Rozmiar binarny (bajty)",
        "code_area": "Zawartosc / kod Pythona",
        "log": "Log",
        "status_ready": "Gotowe",
        "status_packing": "Pakowanie...",
        "status_unpacking": "Rozpakowywanie...",
        "status_generating": "Generowanie...",
        "status_hashing": "Obliczanie hasha...",
        "status_testing": "Testowanie...",
        "recursive": "Dodaj foldery rekurencyjnie",
        "filter_ext": "Filtr rozszerzen (np. .txt;.c)",
        "archive_contents": "Zawartosc archiwum",
        "extract_all": "Rozpakuj wszystko",
        "extract_selected": "Rozpakuj wybrane",
        "progress": "Postep",
        "hash_file": "Haszuj plik",
        "hash_algo": "Algorytm",
        "hash_result": "Wynik",
        "pfa_create": "Utworz archiwum PFA",
        "pfa_unpack": "Rozpakuj archiwum PFA",
        "pfa_file": "Plik PFA",
        "error": "Blad",
        "generated": "Wygenerowano plik: ",
        "packed": "Utworzono archiwum: ",
        "unpacked": "Rozpakowano archiwum do: ",
        "drag_hint": "Przeciagnij pliki lub archiwa tutaj",
        # --- v2 ---
        "group_source": "Pliki do spakowania",
        "group_output": "Archiwum",
        "group_archive": "Archiwum",
        "group_extract": "Opcje rozpakowywania",
        "group_archive_tools": "Narzedzia archiwum",
        "group_hash": "Sumy kontrolne plikow",
        "group_pfa": "Archiwa wlasne PFA",
        "group_appearance": "Wyglad i zachowanie",
        "group_about": "O programie",
        "group_generator": "Generator",
        "add_files": "Dodaj pliki",
        "add_folder": "Dodaj folder",
        "remove": "Usun",
        "clear": "Wyczysc",
        "save_list": "Zapisz liste",
        "load_list": "Wczytaj liste",
        "items_count": "{0} plik(ow), {1}",
        "archive_path": "Sciezka archiwum",
        "browse": "Przegladaj...",
        "format_zip": "ZIP (.zip)",
        "format_tar": "TAR (.tar)",
        "format_targz": "TAR GZIP (.tar.gz)",
        "format_tarbz2": "TAR BZIP2 (.tar.bz2)",
        "format_tarxz": "TAR XZ (.tar.xz)",
        "format_pfa": "PFA (wlasny)",
        "compression_level": "Poziom kompresji",
        "include_root": "Zachowaj nazwy folderow w archiwum",
        "follow_symlinks": "Podazaj za dowiazaniami symbolicznymi",
        "password": "Haslo (AES-256 dla ZIP / szyfrowanie PFA)",
        "confirm_password": "Powtorz haslo",
        "password_optional": "(opcjonalne)",
        "add_to_archive": "Dopisz do istniejacego archiwum",
        "create_archive": "Utworz archiwum",
        "load_archive": "Wczytaj",
        "verify_archive": "Testuj archiwum",
        "filter": "Filtruj",
        "select_all": "Zaznacz wszystko",
        "select_none": "Odznacz wszystko",
        "folder_not_exist": "Folder nie istnieje",
        "file_not_exist": "Plik nie istnieje",
        "no_files": "Brak plikow do przetworzenia",
        "invalid_size": "Nieprawidlowy rozmiar",
        "password_mismatch": "Hasla nie sa identyczne!",
        "need_password": "To archiwum jest zaszyfrowane. Podaj haslo i sprobuj ponownie.",
        "wrong_password": "Bledne haslo lub uszkodzone archiwum.",
        "unsupported_zstd": "Ta kompresja wymaga Pythona 3.14+ (ZIP_ZSTANDARD).",
        "unknown_format": "Nierozpoznany format archiwum",
        "archive_ok": "Test archiwum zakonczony: {0} plik(ow), {1}",
        "archive_damaged": "Archiwum jest uszkodzone: {0}",
        "unknown_entry": "Nieznany wpis",
        "hash_multi": "Haszuj katalog",
        "compare": "Porownaj z oczekiwanym",
        "copy": "Kopiuj",
        "save": "Zapisz do pliku",
        "hash_empty": "Podaj sciezke pliku i oczekiwany hash",
        "hash_match": "Hash ZGODNY z oczekiwanym.",
        "hash_mismatch": "Hash NIE zgadza sie z oczekiwanym!",
        "done": "Gotowe: {0}",
        "busy": "Inna operacja nadal trwa, poczekaj.",
        "status_working": "Praca...",
        "status_done": "Gotowe",
        "status_error": "Blad",
        "status_cancelled": "Anulowano",
        "status_paths": "{0} plik(ow), {1}",
        "cancelled": "Operacja przerwana",
        "appearance_qss": "Wlacz ciemny motyw (QSS)",
        "appearance_default_dir": "Domyslny folder",
        "language": "Jezyk",
        "save_settings": "Zapisz ustawienia",
        "settings_path": "Plik ustawien",
        "about_text": (
            "<h3>{name} v{ver}</h3>"
            "<p>Narzedzie all-in-one: generator plikow, pakowanie i rozpakowywanie "
            "archiwow (ZIP/TAR/PFA), sumy kontrolne, obsluga ZIP z AES-256 oraz "
            "wlasnego formatu PFA z szyfrowaniem.</p>"
            "<p>Rozpakowywanie jest zabezpieczone przed atakiem <b>Zip Slip</b>, "
            "a archiwa szyfrowane sa chronione przed manipulacja bitami.</p>"
            "<p>Python {py} | PySide6 {qt} | {platform}</p>"
        ),
        "close": "Zamknij",
        "quit": "Wyjscie",
        "clear_log": "Wyczysc log",
        "save_log": "Zapisz log",
        "open_in_editor": "Otworz w edytorze",
        "open_folder": "Otworz folder",
        "total_size": "Razem",
        "scan_hidden": "Pomijaj pliki ukryte",
        "include_dirs": "Dodawaj puste foldery",
        "files": "Pliki",
        "folder": "Folder",
        "inspect": "Sprawdz plik",
        "inspect_pyc": "Sprawdz .pyc",
        "info_title": "Informacje o pliku",
        "pattern_help": "Dozwolone wzorce: *.py, *.txt;*.md",
        "font_size": "Rozmiar czcionki",
        "modal_dialogs": "Pokazuj okna potwierdzen (inaczej log + pasek statusu)",
        "preset_label": "Szablon",
        "preset_empty": "Pusty plik tekstowy",
        "preset_markdown": "Dokument Markdown",
        "preset_license": "Licencja MIT",
        "preset_gitignore": ".gitignore",
        "confirmed": "Potwierdzone",
        "result": "Wynik",
        "extract_to": "Rozpakuj do",
        "overwrite_existing": "Nadpisuj istniejace pliki",
        "reset": "Resetuj",
        "cmd_copy_path": "Kopiuj sciezke",
        "cmd_reveal": "Pokaz w Eksploratorze",
        "cmd_remove": "Usun z listy",
        "shortcut_help_title": "Skroty klawiaturowe",
        "shortcut_help": (
            "<table cellpadding=2>"
            "<tr><td>Ctrl+1..6</td><td>Przelaczanie zakladek</td></tr>"
            "<tr><td>Ctrl+O</td><td>Dodaj pliki (zakladka Pakowanie)</td></tr>"
            "<tr><td>Ctrl+Shift+O</td><td>Dodaj folder (zakladka Pakowanie)</td></tr>"
            "<tr><td>Ctrl+E</td><td>Utworz archiwum</td></tr>"
            "<tr><td>Ctrl+U</td><td>Rozpakuj wszystko</td></tr>"
            "<tr><td>Ctrl+G</td><td>Wygeneruj plik</td></tr>"
            "<tr><td>Ctrl+Shift+H</td><td>Haszuj plik</td></tr>"
            "<tr><td>F5</td><td>Odswiez / waliduj</td></tr>"
            "<tr><td>Del</td><td>Usun zaznaczone z listy</td></tr>"
            "<tr><td>Ctrl+L</td><td>Wyczysc log</td></tr>"
            "</table>"
        ),
        "about": "O programie",
        "about_author": "Autor",
        "about_name": "Autor",
        "about_company": "Firma",
        "about_email": "Email",
        "about_github": "GitHub",
        "help": "Pomoc",
        "act_open_generated": "Otworz wygenerowany plik",
        "act_add_files": "Dodaj pliki",
        "act_add_folder": "Dodaj folder",
        "act_pack": "Utworz archiwum",
        "act_unpack": "Rozpakuj wszystko",
        "act_generate": "Wygeneruj plik",
        "act_hash": "Haszuj plik",
        "act_test": "Testuj archiwum",
        "act_clear_log": "Wyczysc log",
        "act_save_log": "Zapisz log",
        "act_quit": "Wyjscie",
    },
}


# =====================================================================
#  Konfiguracja (trwala, zapisywana w pliku JSON)
# =====================================================================

def config_path() -> str:
    """Sciezka pliku ustawien uzytkownika."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ZIPps", "settings.json")


class Settings:
    """Ustawienia aplikacji zapisywane w pliku JSON (z tolerancja bledow)."""

    DEFAULTS = {
        "language": "pl",
        "dark_theme": True,
        "default_dir": "",
        "last_format": "zip",
        "compression_level": 6,
        "keep_relative": True,
        "skip_hidden": True,
        "include_dirs": True,
        "follow_symlinks": False,
        "rename_on_exists": True,
        "strip_root": True,
        "modal_dialogs": True,        # True: okna komunikatow, False: tylko log/powiadomienia
    }

    def __init__(self, path: str | None = None):
        self.path = path or config_path()
        self.language = self.DEFAULTS["language"]
        self.dark_theme = self.DEFAULTS["dark_theme"]
        self.default_dir = self.DEFAULTS["default_dir"]
        self.last_format = self.DEFAULTS["last_format"]
        self.compression_level = self.DEFAULTS["compression_level"]
        self.keep_relative = self.DEFAULTS["keep_relative"]
        self.skip_hidden = self.DEFAULTS["skip_hidden"]
        self.include_dirs = self.DEFAULTS["include_dirs"]
        self.follow_symlinks = self.DEFAULTS["follow_symlinks"]
        self.rename_on_exists = self.DEFAULTS["rename_on_exists"]
        self.strip_root = self.DEFAULTS["strip_root"]
        self.modal_dialogs = self.DEFAULTS["modal_dialogs"]
        self.load()

    # -- tlumaczenia -------------------------------------------------
    def t(self, key: str, *args) -> str:
        table = LANG.get(self.language) or LANG["en"]
        text = table.get(key) or LANG["en"].get(key, key)
        if args:
            try:
                return text.format(*args)
            except (IndexError, KeyError):
                return text
        return text

    # -- trwalosc ----------------------------------------------------
    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for key in self.DEFAULTS:
            if key in data:
                setattr(self, key, data[key])
        if self.language not in LANG:
            self.language = self.DEFAULTS["language"]

    def save(self) -> bool:
        data = {key: getattr(self, key) for key in self.DEFAULTS}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False


settings = Settings()


# =====================================================================
#  Funkcje pomocnicze
# =====================================================================

ARCHIVE_EXTS = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2",
                ".tar.xz", ".txz", ".pfa")

#: domyslna zawartosc pola edycji w generatorze
DEFAULT_GEN_CODE = (
    "# Przykladowa tresc generatora.\n"
    "# Dla plikow .py / .pyc ponizszy kod zostanie uruchomiony po imporcie.\n"
    "def main():\n"
    "    print('Hello from .pyc')\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

MIT_LICENSE = '''MIT License

Copyright (c) {year}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
'''

#: szablony tresci dla generatora (wybierane liste w GUI)
GEN_PRESETS = {
    "empty": "",
    "markdown": (
        "# Tytul dokumentu\n\n"
        "Krotki opis projektu.\n\n"
        "## Instalacja\n\n"
        "```bash\npip install pakiet\n```\n\n"
        "## Uzycie\n\n"
        "1. Krok pierwszy\n"
        "2. Krok drugi\n\n"
        "## Licencja\n\nMIT\n"
    ),
    "license": MIT_LICENSE.replace("{year}", datetime.now().strftime("%Y")),
    "gitignore": (
        "__pycache__/\n*.py[cod]\n*.egg-info/\n.venv/\nvenv/\n"
        "dist/\nbuild/\n.env\n.idea/\n.vscode/\nThumbs.db\n.DS_Store\n"
    ),
}

#: mapowanie formatu na rozszerzenie pliku
FORMAT_EXTS = {
    "zip": ".zip",
    "tar": ".tar",
    "targz": ".tar.gz",
    "tarbz2": ".tar.bz2",
    "tarxz": ".tar.xz",
    "pfa": ".pfa",
}

#: mapowanie formatu na tryb tarfile
TAR_MODES = {
    "tar": "w",
    "targz": "w:gz",
    "tarbz2": "w:bz2",
    "tarxz": "w:xz",
}

SUPPORTED_HASHES = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512",
                    "sha3_256", "sha3_512", "blake2b", "blake2s", "crc32")


class PackerError(Exception):
    """Blad operacji pakowania/rozpakowywania z czytelnym komunikatem."""


class Empty:
    """Obiekt 'atrapy' logera - wygodne w CLI i w testach."""

    def log(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None


def emit(logger, message: str):
    """Bezpieczne logowanie - dziala z Loggerem GUI, CLI i atrapa."""
    log = getattr(logger, "log", None)
    if callable(log):
        log(message)


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise PackerError("__cancelled__")


def _make_progress(progress_cb):
    def report(done, total, message=""):
        if progress_cb is None:
            return
        pct = 100 if total <= 0 else int(done * 100 / total)
        try:
            progress_cb(pct, message)
        except TypeError:
            progress_cb(pct)
    return report


def human_size(num: float) -> str:
    """'1536' -> '1.5 KB'."""
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0 or unit == "TB":
            return ("%d %s" if unit == "B" else "%.1f %s") % (num, unit)
        num /= 1024.0
    return "%.1f TB" % num


def human_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return "%d ms" % int(seconds * 1000)
    if seconds < 60:
        return "%.1f s" % seconds
    minutes, sec = divmod(int(seconds), 60)
    return "%d min %02d s" % (minutes, sec)


def unique_path(path: str) -> str:
    """Zwraca nieistniejaca sciezke (dopisuje ' (1)', ' (2)' itd.)."""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    suffix = ""
    if ext.lower() in (".gz", ".bz2", ".xz"):
        root2, ext2 = os.path.splitext(root)
        if ext2.lower() == ".tar":
            root, ext, suffix = root2, ext2 + ext, ""
    i = 1
    while True:
        candidate = "%s (%d)%s%s" % (root, i, ext, suffix)
        if not os.path.exists(candidate):
            return candidate
        i += 1


def normalize_relative(path: str) -> str:
    """Ujednolica separator na '/' i czysci nazwe wpisu archiwum.

    Usuwa '.' oraz poczatkowe '/', ale zostawia elementy '..' - ich obecnosc
    sygnalizuje probe ataku Zip Slip i jest odrzucana przez safe_join().
    """
    value = str(path or "").replace("\\", "/")
    value = value.lstrip("/")
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if any(len(part) > 1 and part[1] == ":" for part in parts):
        # sciezka absolutna Windows ('C:/...') - traktujemy jako proba wyjscia
        return ".."
    return "/".join(parts)


def safe_join(base_dir: str, relative_name: str) -> str:
    """Laczy baze z nazwa wpisu, gwarantujac ze wynik zostaje w base_dir."""
    rel = normalize_relative(relative_name)
    if not rel:
        raise PackerError("invalid entry name: %r" % (relative_name,))
    base_abs = os.path.abspath(base_dir)
    target = os.path.abspath(os.path.join(base_abs, *rel.split("/")))
    if os.path.commonpath([base_abs, target]) != base_abs:
        raise PackerError("Zip Slip blocked: %r" % (relative_name,))
    return target


def detect_format(path: str) -> str:
    """Rozpoznaje format archiwum po zawartosci, a dopiero potem po rozszerzeniu."""
    try:
        with open(path, "rb") as f:
            sig = f.read(8)
    except OSError:
        sig = b""
    if sig.startswith(b"PK\x03\x04") or sig.startswith(b"PK\x05\x06"):
        return "zip"
    if sig.startswith(b"PFA2"):
        return "pfa"
    if sig.startswith(b"PFA1"):
        return "pfa"
    if sig.startswith(b"\x1f\x8b"):
        return "targz"
    if sig.startswith(b"BZh"):
        return "tarbz2"
    if sig.startswith(b"\xfd7zXZ\x00"):
        return "tarxz"
    try:
        with tarfile.open(path, "r:"):
            return "tar"
    except (tarfile.TarError, OSError):
        pass
    low = path.lower()
    # najpierw dwuczlonowe rozszerzenia (np. '.tar.gz'), potem pojedyncze
    for fmt, ext in sorted(FORMAT_EXTS.items(), key=lambda kv: len(kv[1]), reverse=True):
        if low.endswith(ext):
            return fmt
    if low.endswith((".tgz",)):
        return "targz"
    if low.endswith((".tbz2", ".tbz")):
        return "tarbz2"
    if low.endswith((".txz",)):
        return "tarxz"
    return "unknown"


def ensure_archive_ext(path: str, fmt: str) -> str:
    """Dopina poprawne rozszerzenie, jesli go brak (zamienia tez obce rozszerzenia)."""
    ext = FORMAT_EXTS.get(fmt)
    if not ext:
        return path
    low = path.lower()
    accepted = {ext}
    if fmt == "targz":
        accepted |= {".tgz"}
    elif fmt == "tarbz2":
        accepted |= {".tbz2", ".tbz"}
    elif fmt == "tarxz":
        accepted |= {".txz"}
    if any(low.endswith(a) for a in accepted):
        return path
    base, cur_ext = os.path.splitext(path)
    if cur_ext.lower() in (FORMAT_EXTS[k] for k in FORMAT_EXTS):
        return base + ext
    return path + ext


@contextmanager
def open_zip(path: str, mode: str, password: str | None = None,
             compression: str = "deflate", level: int | None = None,
             append: bool = False):
    """Otwiera ZIP; dla hasla uzywa AES-256 (pyzipper), a bez - biblioteki standardowej."""
    pyzipper = None
    if password:
        try:
            import pyzipper  # type: ignore
        except ImportError:
            pyzipper = None
            raise PackerError(
                "AES-256 (haslo) wymaga modulu 'pyzipper'. Zainstaluj: "
                "pip install pyzipper"
            )
    if pyzipper is not None:
        if append and os.path.exists(path):
            mode = "a"
        zp = pyzipper.AESZipFile(path, mode, compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES)
        if password:
            zp.setpassword(password.encode("utf-8") if isinstance(password, str) else password)
        zp.setencryption(pyzipper.WZ_AES, nbits=256)
        try:
            yield zp
        finally:
            zp.close()
        return

    if append and os.path.exists(path):
        mode = "a"
    comp = zipfile.ZIP_STORED if compression == "stored" else zipfile.ZIP_DEFLATED
    kwargs = {"compression": comp}
    if level is not None and compression != "stored":
        kwargs["compresslevel"] = max(0, min(9, int(level)))
    with zipfile.ZipFile(path, mode, **kwargs) as zf:
        yield zf


@contextmanager
def open_tar(path: str, mode: str, fmt: str = "tar"):
    """Otwiera archiwum tar z odpowiednim trybem kompresji."""
    if mode.startswith("w") and fmt in TAR_MODES:
        mode = TAR_MODES[fmt]
    with tarfile.open(path, mode) as tf:
        yield tf


def _tar_extract_member(tf: tarfile.TarFile, member: tarfile.TarInfo,
                        output_folder: str, overwrite: bool = True) -> str:
    """Bezpieczne rozpakowanie pojedynczego wpisu tar (bez wyjscia poza folder)."""
    if member.issym() or member.islnk():
        raise PackerError("links in tar archives are not extracted: %s" % member.name)
    target = safe_join(output_folder, member.name)
    if member.isdir():
        os.makedirs(target, exist_ok=True)
        return target
    if not member.isfile():
        return target
    if not overwrite and os.path.exists(target):
        return target
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    src = tf.extractfile(member)
    if src is None:
        return target
    with src, open(target, "wb") as out:
        shutil.copyfileobj(src, out, 1024 * 256)
    try:
        os.utime(target, (member.mtime, member.mtime))
    except (OSError, OverflowError, ValueError):
        pass
    if os.name != "nt":
        try:
            os.chmod(target, member.mode & 0o777)
        except OSError:
            pass
    return target


def _zip_extract_entry(zf, info, output_folder: str, password: str | None,
                       overwrite: bool = True) -> str:
    """Bezpieczne rozpakowanie pojedynczego wpisu ZIP."""
    if info.is_dir():
        os.makedirs(safe_join(output_folder, info.filename), exist_ok=True)
        return ""
    target = safe_join(output_folder, info.filename)
    if not overwrite and os.path.exists(target):
        return target
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    try:
        if password and getattr(zf, "setpassword", None):
            zf.setpassword(password.encode("utf-8"))
        src = zf.open(info, pwd=password.encode("utf-8") if password else None)
    except RuntimeError as ex:
        raise PackerError("encrypted entry %s: %s" % (info.filename, ex))
    with src, open(target, "wb") as out:
        shutil.copyfileobj(src, out, 1024 * 256)
    try:
        dt = datetime(*info.date_time).timestamp()
        os.utime(target, (dt, dt))
    except (OSError, OverflowError, ValueError):
        pass
    return target


def iter_files(root: str, patterns: list | None = None, skip_hidden: bool = True,
               follow_symlinks: bool = False):
    """Rekurencyjnie zwraca pliki z katalogu (filtr rozszerzen/wzorcow)."""
    root = os.path.abspath(root)
    norm = [p.lower().lstrip("*").strip() for p in (patterns or []) if p.strip()]
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        if skip_hidden:
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d != "__pycache__"]
            filenames = [f for f in filenames if not f.startswith(".")]
        dirnames.sort()
        for name in sorted(filenames):
            if norm:
                low = name.lower()
                if not any(low.endswith(p) for p in norm):
                    continue
            yield os.path.join(dirpath, name)


# =====================================================================
#  Logger
# =====================================================================

class Logger:
    """Loguje do widgetu Qt (liczba wywolan moze pochodzic z watku roboczego)."""

    MAX_BLOCKS = 5000

    def __init__(self, widget: QPlainTextEdit | None = None):
        self.widget = widget
        self.lock = threading.Lock()
        self.history = []

    def log(self, msg: str):
        msg = str(msg)
        with self.lock:
            self.history.append(msg)
            if len(self.history) > 20000:
                del self.history[:10000]
        if self.widget is None:
            if msg:
                print(msg, flush=True)
            return
        with self.lock:
            append = getattr(self.widget, "appendPlainText", None)
            if callable(append):
                append(msg)

    # aliasy dla wygody
    info = log

    def error(self, msg: str):
        self.log(settings.t("error") + ": " + str(msg))

    def clear(self):
        with self.lock:
            self.history.clear()
            if self.widget is not None:
                clear_fn = getattr(self.widget, "clear", None)
                if callable(clear_fn):
                    clear_fn()


# =====================================================================
#  Generator plikow
# =====================================================================

PY_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""{module} - plik wygenerowany przez {app}."""

import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("Hello from {module}! Arguments:", argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

C_TEMPLATE = (
    "#include <stdio.h>\n\n"
    "int main(void) {\n"
    "    printf(\"Hello from C!\\n\");\n"
    "    return 0;\n"
    "}\n"
)

CPP_TEMPLATE = (
    "#include <iostream>\n\n"
    "int main() {\n"
    "    std::cout << \"Hello from C++!\" << std::endl;\n"
    "    return 0;\n"
    "}\n"
)


class FileGenerator:
    """Tworzy rozne rodzaje plikow (tekst, binarny, .pyc, C, C++, RAW, JSON, MD)."""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Empty()

    # -- pomocnicze ---------------------------------------------------
    @staticmethod
    def _ensure_dir(folder: str):
        if not folder:
            raise PackerError("no output folder")
        os.makedirs(folder, exist_ok=True)

    @staticmethod
    def _ext(ext: str, default: str = "") -> str:
        ext = (ext or "").strip()
        if not ext:
            return default
        if not ext.startswith("."):
            ext = "." + ext
        return ext

    def _done(self, path: str) -> str:
        self.logger.log(settings.t("generated") + path)
        return path

    # -- generatory ---------------------------------------------------
    def generate_text_file(self, folder: str, name: str, ext: str, content: str) -> str:
        self._ensure_dir(folder)
        name = name or "file"
        path = os.path.join(folder, name + self._ext(ext, ".txt"))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content or "")
        return self._done(path)

    def generate_binary_file(self, folder: str, name: str, ext: str, size: int) -> str:
        self._ensure_dir(folder)
        size = int(size)
        if size <= 0:
            raise PackerError(settings.t("invalid_size"))
        name = name or "binary"
        path = os.path.join(folder, name + self._ext(ext, ".bin"))
        with open(path, "wb") as f:
            written = 0
            while written < size:
                chunk = min(1024 * 1024, size - written)
                f.write(os.urandom(chunk))
                written += chunk
        return self._done(path)

    def generate_pyc(self, folder: str, name: str, code: str, keep_source: bool = True) -> str:
        self._ensure_dir(folder)
        name = name or "module"
        py_path = os.path.join(folder, name + ".py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(code or "")
        pyc_path = py_path + "c"
        py_compile.compile(py_path, cfile=pyc_path, doraise=True)
        if not keep_source:
            try:
                os.remove(py_path)
            except OSError:
                pass
        return self._done(pyc_path)

    def generate_python_script(self, folder: str, name: str, code: str = "") -> str:
        self._ensure_dir(folder)
        name = name or "script"
        path = os.path.join(folder, name + ".py")
        content = code or PY_SCRIPT_TEMPLATE.format(
            module=name, app="%s v%s" % (__app_name__, __version__))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return self._done(path)

    def generate_c_file(self, folder: str, name: str, content: str = "") -> str:
        self._ensure_dir(folder)
        path = os.path.join(folder, (name or "main") + ".c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content or C_TEMPLATE)
        return self._done(path)

    def generate_cpp_file(self, folder: str, name: str, content: str = "") -> str:
        self._ensure_dir(folder)
        path = os.path.join(folder, (name or "main") + ".cpp")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content or CPP_TEMPLATE)
        return self._done(path)

    def generate_raw_image(self, folder: str, name: str, width: int, height: int,
                           pattern: str = "gradient") -> str:
        """8-bitowy obraz RAW; wzory: gradient, noise, checker, xr, plasma."""
        self._ensure_dir(folder)
        width = max(1, int(width))
        height = max(1, int(height))
        path = os.path.join(folder, (name or "image") + ".raw")
        if pattern == "noise":
            data = os.urandom(width * height)
        elif pattern == "checker":
            data = bytearray(width * height)
            cell = 16
            for y in range(height):
                row = y // cell
                base = y * width
                for x in range(0, width, cell):
                    value = 230 if ((x // cell) + row) % 2 else 30
                    end = min(width, x + cell)
                    data[base + x:base + end] = bytes([value]) * (end - x)
        elif pattern == "xr":
            data = bytearray(width * height)
            for y in range(height):
                v = int(255 * (y / max(1, height - 1)))
                data[y * width:(y + 1) * width] = bytes([v]) * width
        elif pattern == "plasma":
            data = bytearray(width * height)
            wdt = max(1, width - 1)
            hgt = max(1, height - 1)
            idx = 0
            for y in range(height):
                fy = y / hgt
                for x in range(width):
                    fx = x / wdt
                    value = 127 + 127 * math.sin(fx * math.pi * 3) * math.cos(fy * math.pi * 2)
                    data[idx] = int(max(0, min(255, value)))
                    idx += 1
        else:
            data = bytearray(width * height)
            wdt = max(1, width - 1)
            for y in range(height):
                row = bytearray(int(255 * (x / wdt)) for x in range(width))
                data[y * width:(y + 1) * width] = row
        with open(path, "wb") as f:
            f.write(data)
        return self._done(path)

    def generate_json_file(self, folder: str, name: str, content: str = "") -> str:
        self._ensure_dir(folder)
        path = os.path.join(folder, (name or "data") + ".json")
        if content.strip():
            try:
                payload = json.loads(content)
            except ValueError:
                raise PackerError("invalid JSON")
        else:
            payload = {
                "generated": datetime.now().isoformat(timespec="seconds"),
                "tool": "%s %s" % (__app_name__, __version__),
                "items": [],
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return self._done(path)

    def generate_markdown_file(self, folder: str, name: str, content: str = "") -> str:
        self._ensure_dir(folder)
        path = os.path.join(folder, (name or "README") + ".md")
        text = content.strip() or (
            "# %s\n\n%s\n\n## Opis\n\n- [ ] punkt 1\n- [ ] punkt 2\n\n"
            "```python\nprint('Hello')\n```\n" % (name or "Dokument",
                                                  datetime.now().strftime("%Y-%m-%d"))
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return self._done(path)


# =====================================================================
#  Pakowanie
# =====================================================================

@dataclass
class PackResult:
    """Podsumowanie operacji pakowania."""
    path: str
    added: int = 0
    replaced: int = 0
    skipped: int = 0
    size_before: int = 0
    size_after: int = 0
    errors: list = field(default_factory=list)
    entries: int = 0

    @property
    def ratio(self) -> float:
        if not self.size_before:
            return 0.0
        return 100.0 * (1 - (self.size_after / float(self.size_before)))


class PackerCore:
    """Tworzy archiwa ZIP/TAR/PFA z opcjami kompresji, filtrowania i szyfrowania."""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Empty()

    # -- zbieranie plikow ---------------------------------------------
    def _iter_files_recursive(self, root_folder, filter_exts, ignore_hidden=True,
                              follow_symlinks=False):
        """Zgodnosc wsteczna: generuje pliki z filtrem rozszerzen (.txt;.c)."""
        patterns = None
        if filter_exts:
            patterns = list(filter_exts)
            if patterns and not any(p.startswith(".") or p.startswith("*")
                                    for p in patterns):
                patterns = ["." + p for p in patterns]
        yield from iter_files(root_folder, patterns, ignore_hidden, follow_symlinks)

    @staticmethod
    def collect_files(files, folders, patterns=None, skip_hidden=True,
                      follow_symlinks=False, logger=None) -> list:
        """Scala liste plikow i folderow (rekurencyjnie) w jedna liste bez duplikatow."""
        result, seen = [], set()

        def add(path):
            real = os.path.abspath(path)
            if real in seen:
                return
            if not os.path.isfile(real):
                if logger is not None:
                    emit(logger, "%s: %s" % (settings.t("file_not_exist"), path))
                return
            seen.add(real)
            result.append(real)

        for f in files or []:
            f = (f or "").strip().strip('"')
            if f:
                add(os.path.expanduser(f))
        for folder in folders or []:
            folder = (folder or "").strip().strip('"')
            if not folder:
                continue
            folder = os.path.expanduser(folder)
            if not os.path.isdir(folder):
                if logger is not None:
                    emit(logger, "%s: %s" % (settings.t("folder_not_exist"), folder))
                continue
            for path in iter_files(folder, patterns, skip_hidden, follow_symlinks):
                add(path)
        return result

    @staticmethod
    def arcname_for(path: str, bases: list, keep_relative: bool = True) -> str:
        """Nazwa wpisu w archiwum - zachowuje structure folderow, gdy to mozliwe."""
        path = os.path.abspath(path)
        best = None
        for base in bases or []:
            base = os.path.abspath(base)
            if best is None or len(base) > len(best):
                if path == base or path.startswith(base + os.sep):
                    best = base
        if keep_relative:
            if best:
                rel = os.path.relpath(path, best)
                if rel != os.pardir and not rel.startswith(os.pardir + os.sep):
                    return normalize_relative(rel)
            # plik nie lezy w zadnej z baz - zachowujemy wspolny fragment sciezki
            bases = [os.path.abspath(b) for b in (bases or []) if b]
            anchor = os.path.commonpath(bases + [path]) if bases else os.path.dirname(path)
            if anchor and os.path.isdir(anchor):
                rel = os.path.relpath(path, anchor)
                if rel != os.pardir and not rel.startswith(os.pardir + os.sep):
                    return normalize_relative(rel)
        return normalize_relative(os.path.basename(path))

    # -- ZIP ----------------------------------------------------------
    def pack_zip(self, files, archive_path, progress_cb=None, compression="deflate",
                 level=None, password=None, bases=None, keep_relative=True,
                 append=False, cancel_event=None) -> PackResult:
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if not files:
            raise PackerError(settings.t("no_files"))
        queue = [(f, self.arcname_for(f, bases, keep_relative)) for f in files]
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        total = len(queue) + (1 if append else 0)
        step = 0
        emit(self.logger, "ZIP: " + archive_path)

        with open_zip(archive_path, "w", password=password, compression=compression,
                      level=level, append=append) as zf:
            existing = set(zf.namelist())
            for path, arcname in queue:
                _check_cancel(cancel_event)
                step += 1
                try:
                    size = os.path.getsize(path)
                    result.size_before += size
                    zf.write(path, arcname)
                    if arcname in existing:
                        result.replaced += 1
                    else:
                        result.added += 1
                        existing.add(arcname)
                except OSError as ex:
                    result.skipped += 1
                    result.errors.append("%s: %s" % (path, ex))
                    emit(self.logger, "%s: %s" % (settings.t("error"), ex))
                report(step, total, arcname)

        result.size_after = os.path.getsize(archive_path)
        result.entries = result.added + result.replaced
        emit(self.logger, settings.t("packed") + archive_path)
        emit(self.logger, "%s %s (%s -> %s, -%0.1f%%)" % (
            settings.t("total_size"), human_size(result.size_after),
            human_size(result.size_before), human_size(result.size_after),
            result.ratio))
        return result

    # -- TAR ----------------------------------------------------------
    def pack_tar(self, files, archive_path, mode="w", progress_cb=None, fmt=None,
                 bases=None, keep_relative=True, password=None, level=None,
                 cancel_event=None, **_ignored) -> PackResult:
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if not files:
            raise PackerError(settings.t("no_files"))
        fmt = fmt or {v: k for k, v in TAR_MODES.items()}.get(mode, "tar")
        queue = [(f, self.arcname_for(f, bases, keep_relative)) for f in files]
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        total = len(queue) + (1 if password else 0)
        step = 0
        emit(self.logger, "TAR: " + archive_path)

        with open_tar(archive_path, mode, fmt) as tf:
            for path, arcname in queue:
                _check_cancel(cancel_event)
                step += 1
                try:
                    result.size_before += os.path.getsize(path)
                    tf.add(path, arcname, recursive=False)
                    result.added += 1
                except OSError as ex:
                    result.skipped += 1
                    result.errors.append("%s: %s" % (path, ex))
                report(step, total, arcname)

        if password:
            # archiwa tar nie obsluguja szyfrowania - dodatkowa, opcjonalna warstwa
            # nie jest tu stosowana (uzyj formatu PFA lub ZIP z AES-256)
            emit(self.logger, "TAR: encryption not supported, archive left unencrypted")
        result.entries = result.added
        result.size_after = os.path.getsize(archive_path)
        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_tar_gz(self, files, archive_path, progress_cb=None, **kwargs) -> PackResult:
        return self.pack_tar(files, archive_path, mode="w:gz", fmt="targz",
                             progress_cb=progress_cb, **kwargs)

    def pack_tar_bz2(self, files, archive_path, progress_cb=None, **kwargs) -> PackResult:
        return self.pack_tar(files, archive_path, mode="w:bz2", fmt="tarbz2",
                             progress_cb=progress_cb, **kwargs)

    def pack_tar_xz(self, files, archive_path, progress_cb=None, **kwargs) -> PackResult:
        return self.pack_tar(files, archive_path, mode="w:xz", fmt="tarxz",
                             progress_cb=progress_cb, **kwargs)

    # -- dyspozytor ---------------------------------------------------
    def pack(self, files, archive_path, fmt="zip", progress_cb=None,
             keywords=None, **kwargs) -> PackResult:
        """Uniwersalna funkcja pakowania: fmt = zip|tar|targz|tarbz2|tarxz|pfa."""
        if keywords is not None:
            keywords = set(keywords)
            kwargs = {k: v for k, v in kwargs.items() if k in keywords}
        fmt = (fmt or "zip").lower()
        archive_path = ensure_archive_ext(archive_path, fmt)
        if not kwargs.get("append") and os.path.exists(archive_path):
            backup = archive_path + ".bak"
            try:
                shutil.copy2(archive_path, backup)
                emit(self.logger, "backup: " + backup)
            except OSError as ex:
                emit(self.logger, "backup failed: %s" % ex)
        if fmt == "zip":
            return self.pack_zip(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt in TAR_MODES:
            return self.pack_tar(files, archive_path, mode=TAR_MODES[fmt], fmt=fmt,
                                 progress_cb=progress_cb, **kwargs)
        if fmt == "pfa":
            pfa = PFAFormat(self.logger)
            return pfa.create_pfa(files, archive_path,
                                  progress_cb=progress_cb,
                                  password=kwargs.get("password"),
                                  bases=kwargs.get("bases"),
                                  keep_relative=kwargs.get("keep_relative", True),
                                  cancel_event=kwargs.get("cancel_event"))
        raise PackerError("unsupported format: %s" % fmt)


# =====================================================================
#  Rozpakowywanie
# =====================================================================

@dataclass
class ExtractResult:
    """Podsumowanie rozpakowywania."""
    fmt: str = ""
    extracted: int = 0
    skipped: int = 0
    overwritten: int = 0
    blocked: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    output_folder: str = ""
    bytes_written: int = 0


class UnpackerCore:
    """Rozpoznaje format i bezpiecznie rozpakowuje archiwa."""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Empty()

    def _is_zip(self, path):
        try:
            with open(path, "rb") as f:
                sig = f.read(4)
            return sig.startswith(b"PK")
        except OSError:
            return False

    def _detect_format(self, path):
        return detect_format(path)

    def detect_format(self, path):
        return detect_format(path)

    # -- lista zawartosci ---------------------------------------------
    @staticmethod
    def _list_entries(archive_path, fmt, password=None):
        """Zwraca liste slownikow: name, size, date, encrypted, is_dir."""
        entries = []
        if fmt == "zip":
            kw = {}
            if password:
                try:
                    import pyzipper  # type: ignore
                    zf = pyzipper.AESZipFile(archive_path, "r")
                    zf.setpassword(password.encode("utf-8") if isinstance(password, str) else password)
                    kw["zf"] = zf
                except ImportError:
                    kw["zf"] = zipfile.ZipFile(archive_path, "r")
            else:
                kw["zf"] = zipfile.ZipFile(archive_path, "r")
            with kw["zf"] as zf:
                for info in zf.infolist():
                    entries.append({
                        "name": info.filename,
                        "size": info.file_size,
                        "date": tuple(info.date_time),
                        "encrypted": bool(info.flag_bits & 0x1),
                        "is_dir": info.is_dir(),
                    })
        elif fmt in TAR_MODES:
            with open_tar(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    entries.append({
                        "name": member.name,
                        "size": member.size,
                        "date": time.localtime(member.mtime)[:6],
                        "encrypted": False,
                        "is_dir": member.isdir(),
                        "is_link": member.issym() or member.islnk(),
                    })
        elif fmt == "pfa":
            with PFAFormat(Empty()) as pfa:
                for entry in pfa.read_entries(archive_path, password=password):
                    entries.append({
                        "name": entry.name,
                        "size": entry.size,
                        "date": (tuple(time.localtime(entry.mtime)[:6])
                                 if entry.mtime else ()),
                        "encrypted": entry.encrypted,
                        "is_dir": False,
                        "sha256": entry.sha256,
                    })
        return entries

    def list_contents(self, archive_path, password=None):
        """Zgodnosc wsteczna: zwraca ((nazwa, rozmiar), format)."""
        if not os.path.exists(archive_path):
            raise PackerError(settings.t("file_not_exist"))
        fmt = detect_format(archive_path)
        if fmt == "unknown":
            emit(self.logger, settings.t("error") + ": " + settings.t("unknown_format"))
            return [], fmt
        entries = self._list_entries(archive_path, fmt, password)
        contents = [(e["name"], e["size"]) for e in entries if not e["is_dir"]]
        return contents, fmt

    def entries(self, archive_path, password=None):
        """Pelen opis wpisow."""
        if not os.path.exists(archive_path):
            raise PackerError(settings.t("file_not_exist"))
        fmt = detect_format(archive_path)
        if fmt == "unknown":
            raise PackerError(settings.t("unknown_format"))
        return self._list_entries(archive_path, fmt, password), fmt

    # -- rozpakowywanie -----------------------------------------------
    def unpack_auto(self, archive_path, output_folder, selected=None,
                    progress_cb=None, password=None, overwrite=True,
                    cancel_event=None) -> ExtractResult:
        if not os.path.exists(archive_path):
            raise PackerError(settings.t("file_not_exist"))
        fmt = detect_format(archive_path)
        if fmt == "unknown":
            raise PackerError(settings.t("unknown_format"))
        os.makedirs(output_folder, exist_ok=True)
        result = ExtractResult(fmt=fmt, output_folder=output_folder)
        report = _make_progress(progress_cb)

        entries = self._list_entries(archive_path, fmt, password)
        wanted = None
        if selected is not None:
            wanted = {normalize_relative(s) for s in selected}
        files = [e for e in entries
                 if not e["is_dir"] and (wanted is None or normalize_relative(e["name"]) in wanted)]
        total = len(files)

        emit(self.logger, "Unpack %s: %s" % (fmt.upper(), archive_path))

        def extract_zip(zf):
            by_name = {}
            for info in zf.infolist():
                by_name[normalize_relative(info.filename)] = info
            for i, entry in enumerate(files, 1):
                _check_cancel(cancel_event)
                info = by_name.get(normalize_relative(entry["name"]))
                if info is None:
                    result.errors.append(settings.t("unknown_entry") + ": " + entry["name"])
                    continue
                target_exists = False
                try:
                    target = safe_join(output_folder, info.filename)
                    target_exists = os.path.exists(target)
                except PackerError as ex:
                    result.blocked.append(str(ex))
                    emit(self.logger, "%s: %s" % (settings.t("error"), ex))
                    continue
                try:
                    _zip_extract_entry(zf, info, output_folder, password, overwrite)
                except (RuntimeError, NotImplementedError) as ex:
                    if entry["encrypted"] or "password" in str(ex).lower():
                        raise PackerError(settings.t("need_password") if not password
                                          else settings.t("wrong_password"))
                    raise
                except (zipfile.BadZipFile, zlib.error) as ex:
                    raise PackerError(settings.t("wrong_password") + " (%s)" % ex)
                result.extracted += 1
                result.bytes_written += entry["size"]
                result.overwritten += 1 if (target_exists and overwrite) else 0
                report(i, total, entry["name"])

        def extract_tar(tf):
            members = {}
            for member in tf.getmembers():
                members[normalize_relative(member.name)] = member
            for i, entry in enumerate(files, 1):
                _check_cancel(cancel_event)
                member = members.get(normalize_relative(entry["name"]))
                if member is None:
                    result.errors.append(settings.t("unknown_entry") + ": " + entry["name"])
                    continue
                target_exists = False
                try:
                    target_exists = os.path.exists(safe_join(output_folder, member.name))
                    _tar_extract_member(tf, member, output_folder, overwrite)
                except PackerError as ex:
                    result.blocked.append(str(ex))
                    emit(self.logger, "%s: %s" % (settings.t("error"), ex))
                    continue
                except (tarfile.TarError, OSError) as ex:
                    result.errors.append("%s: %s" % (member.name, ex))
                    emit(self.logger, "%s: %s" % (settings.t("error"), ex))
                    continue
                result.extracted += 1
                result.bytes_written += entry["size"]
                result.overwritten += 1 if (target_exists and overwrite) else 0
                report(i, total, member.name)

        if fmt == "zip":
            opener = zipfile.ZipFile
            if password:
                try:
                    import pyzipper  # type: ignore
                    opener = pyzipper.AESZipFile
                except ImportError:
                    opener = zipfile.ZipFile
            try:
                with opener(archive_path, "r") as zf:
                    extract_zip(zf)
            except zipfile.BadZipFile:
                raise PackerError(settings.t("archive_damaged").format(archive_path))
        elif fmt in TAR_MODES:
            with open_tar(archive_path, "r:*") as tf:
                extract_tar(tf)
        elif fmt == "pfa":
            with PFAFormat(self.logger) as pfa:
                res = pfa.unpack_pfa(archive_path, output_folder, selected=selected,
                                     progress_cb=progress_cb, password=password,
                                     overwrite=overwrite, cancel_event=cancel_event)
                result.extracted = res.extracted
                result.bytes_written = res.bytes_written
                result.overwritten = res.overwritten
                result.blocked.extend(res.blocked)
                result.errors.extend(res.errors)

        emit(self.logger, settings.t("unpacked") + output_folder)
        return result

    # -- test integralnosci -------------------------------------------
    def test_archive(self, archive_path, password=None, progress_cb=None) -> tuple:
        """Sprawdza CRC wszystkich wpisow. Zwraca (ok, problem, liczba_plikow)."""
        fmt = detect_format(archive_path)
        if fmt == "unknown":
            return False, settings.t("unknown_format"), 0
        report = _make_progress(progress_cb)
        count = 0
        if fmt == "zip":
            opener = zipfile.ZipFile
            if password:
                try:
                    import pyzipper  # type: ignore
                    opener = pyzipper.AESZipFile
                except ImportError:
                    opener = zipfile.ZipFile
            try:
                with opener(archive_path, "r") as zf:
                    infos = [i for i in zf.infolist() if not i.is_dir()]
                    if password:
                        zf.setpassword(password.encode("utf-8"))
                    for i, info in enumerate(infos, 1):
                        try:
                            if password or (info.flag_bits & 0x1):
                                with zf.open(info) as f:
                                    while f.read(1024 * 256):
                                        pass
                        except RuntimeError as ex:
                            return False, "%s (%s)" % (settings.t("wrong_password"), ex), count
                        count += 1
                        report(i, len(infos), info.filename)
                    if not password:
                        bad = zf.testzip()
                        if bad:
                            return False, "CRC error: %s" % bad, count
            except (zipfile.BadZipFile, zlib.error, OSError) as ex:
                return False, str(ex), count
            return True, "", count
        if fmt in TAR_MODES:
            with open_tar(archive_path, "r:*") as tf:
                members = [m for m in tf.getmembers() if m.isfile()]
                for i, member in enumerate(members, 1):
                    src = tf.extractfile(member)
                    if src is None:
                        continue
                    remaining = member.size
                    while remaining > 0:
                        chunk = src.read(min(1024 * 256, remaining))
                        if not chunk:
                            return False, "truncated: %s" % member.name, count
                        remaining -= len(chunk)
                    count += 1
                    report(i, len(members), member.name)
            return True, "", count
        if fmt == "pfa":
            with PFAFormat(self.logger) as pfa:
                return pfa.verify_pfa(archive_path, password=password,
                                      progress_cb=progress_cb)
        return False, settings.t("unknown_format"), 0


# =====================================================================
#  Format PFA (Pro File Archive)
# ---------------------------------------------------------------------
#  PFA1 (zgodnosc wsteczna, format oryginalny):
#     "PFA1" | uint32 count | count * ( uint32 name_len | name | uint32 size | data )
#
#  PFA2 (nowy format z manifestem, opcjonalnym szyfrowaniem AES-256-GCM):
#     "PFA2" | uint16 flags | uint8 kdf | uint32 iterations | uint16 salt_len | salt
#            | uint32 manifest_len | manifest | count * ( uint32 size | data )
#     flags bit 0 -> dane zaszyfrowane
#     klucz = PBKDF2-HMAC-SHA256(password, salt, iterations); nonce 12B jako prefiks.
#     Manifest (binarny): uint32 count | count * ( uint16 name_len | name |
#            uint64 offset | int64 mtime | uint32 mode | uint8 enc | 32B sha256 )
#     Dla danych zaszyfrowanych sha256 odnosi sie do jawnych danych.
# =====================================================================

PFA_MAGIC_V1 = b"PFA1"
PFA_MAGIC_V2 = b"PFA2"
PFA_FLAG_ENCRYPTED = 0x0001
PFA_FLAG_DEFLATE = 0x0002      # wszystkie wpisy sa skompresowane zlib-em
PFA_ENTRY_ENCRYPTED = 0x01     # bity w polu 'enc' wpisu manifestu
PFA_ENTRY_COMPRESSED = 0x02
PFA_PBKDF2_ITERATIONS = 200_000
PFA_SALT_LEN = 16
PFA_NONCE_LEN = 12
PFA_TAG_LEN = 16

#: wpis manifestu (bez nazwy i hasha):
#:   uint64 offset | int64 mtime | uint32 size | uint8 encrypted | uint32 mode
#: Kodowanie reczne (int.to_bytes) zamiast struct - wyniki sa jednoznaczne
#: niezaleznie od wersji Pythona i jej kodow formatu.
PFA_ENTRY_SIZE = 8 + 8 + 4 + 1 + 4


def _int_bytes(value: int, length: int, signed: bool = False) -> bytes:
    """Stala liczba bajtow niezaleznie od wartosci (bez wyrownania do slowa).

    Rzutowanie przez int() jest konieczne - dla float kodowanie zalezy od
    wartosci i moze zmienic szerokosc pola.
    """
    raw = int(value).to_bytes(length, "little", signed=signed)
    if len(raw) != length:
        raise PackerError("value %r does not fit in %d bytes" % (value, length))
    return raw


def _pack_entry(offset: int, mtime: int, size: int, encrypted: int, mode: int) -> bytes:
    return (_int_bytes(offset, 8) + _int_bytes(mtime, 8, signed=True)
            + _int_bytes(size, 4) + bytes([int(encrypted) & 0xFF])
            + _int_bytes(mode, 4))


def _unpack_entry(raw: bytes, pos: int) -> tuple:
    offset = int.from_bytes(raw[pos:pos + 8], "little", signed=False)
    mtime = int.from_bytes(raw[pos + 8:pos + 16], "little", signed=True)
    size = int.from_bytes(raw[pos + 16:pos + 20], "little", signed=False)
    encrypted = raw[pos + 20]
    mode = int.from_bytes(raw[pos + 21:pos + 25], "little", signed=False)
    return offset, size, mtime, mode, encrypted  # kolejnoĹ›Ä‡ zgodna z _parse_manifest


@dataclass
class PFAEntry:
    name: str
    offset: int
    size: int
    mtime: float
    mode: int = 0o644
    encrypted: bool = False
    sha256: str = ""
    data_offset: int = 0
    compressed: bool = False

    @property
    def size_human(self) -> str:
        return human_size(self.size)


def _aes_cipher(key: bytes, nonce: bytes, tag: bytes | None = None):
    """Tworzy AES-GCM ciphertext (tag=None) lub deszyfrujacy (tag podany)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise PackerError(
            "Szyfrowanie PFA wymaga modulu 'cryptography'. "
            "Zainstaluj: pip install cryptography"
        )
    aes = AESGCM(key)
    return aes, nonce, tag


class PFAFormat:
    """Wlasny format archiwum: manifest + opcjonalne szyfrowanie AES-256-GCM."""

    MAGIC = PFA_MAGIC_V1          # zgodnosc wsteczna (tworzymy juz PFA2)

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Empty()

    # -- klucz --------------------------------------------------------
    @staticmethod
    def _derive_key(password: str | bytes, salt: bytes, iterations: int) -> bytes:
        if isinstance(password, str):
            password = password.encode("utf-8")
        return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, dklen=32)

    # -- odczyt naglowka ----------------------------------------------
    @staticmethod
    def read_header(f) -> dict:
        f.seek(0)
        magic = f.read(4)
        if magic == PFA_MAGIC_V1:
            return {"version": 1, "magic": magic, "encrypted": False,
                    "manifest_offset": 4, "manifest_len": 0}
        if magic == PFA_MAGIC_V2:
            head = f.read(7)
            flags = int.from_bytes(head[0:2], "little")
            kdf = head[2]
            iterations = int.from_bytes(head[3:7], "little")
            salt_len = int.from_bytes(f.read(2), "little")
            salt = f.read(salt_len)
            manifest_len = int.from_bytes(f.read(4), "little")
            return {
                "version": 2,
                "magic": magic,
                "flags": flags,
                "kdf": kdf,
                "iterations": iterations,
                "salt": salt,
                "manifest_len": manifest_len,
                "manifest_offset": f.tell(),
                "encrypted": bool(flags & PFA_FLAG_ENCRYPTED),
            }
        raise PackerError("invalid PFA")

    @staticmethod
    def _parse_manifest(raw: bytes) -> list:
        entries = []
        pos = 0
        count = int.from_bytes(raw[pos:pos + 4], "little")
        pos += 4
        for _ in range(count):
            name_len = int.from_bytes(raw[pos:pos + 2], "little")
            pos += 2
            name = raw[pos:pos + name_len].decode("utf-8")
            pos += name_len
            offset, size, mtime, mode, enc = _unpack_entry(raw, pos)
            pos += PFA_ENTRY_SIZE
            sha = raw[pos:pos + 32]
            pos += 32
            entries.append(PFAEntry(
                name=name, offset=offset, size=size, mtime=mtime, mode=mode,
                encrypted=bool(enc & PFA_ENTRY_ENCRYPTED), sha256=sha.hex(),
                compressed=bool(enc & PFA_ENTRY_COMPRESSED)))
        return entries

    def _read_manifest(self, f, header, password):
        f.seek(header["manifest_offset"])
        raw = f.read(header["manifest_len"])
        if header.get("encrypted"):
            if not password:
                raise PackerError(settings.t("need_password"))
            key = self._derive_key(password, header["salt"], header["iterations"])
            if len(raw) < PFA_NONCE_LEN + PFA_TAG_LEN:
                raise PackerError(settings.t("wrong_password"))
            nonce, ciphertext, tag = (raw[:PFA_NONCE_LEN],
                                      raw[PFA_NONCE_LEN:-PFA_TAG_LEN],
                                      raw[-PFA_TAG_LEN:])
            aes, nonce, tag = _aes_cipher(key, nonce, tag)
            try:
                raw = aes.decrypt(nonce, ciphertext + tag, PFA_MAGIC_V2)
            except Exception:
                raise PackerError(settings.t("wrong_password"))
        entries = self._parse_manifest(raw)
        # offsety w manifescie liczone sa od poczatku bloku danych, ktory
        # zaczyna sie dokladnie za manifestem
        data_base = f.tell()
        for entry in entries:
            entry.data_offset = data_base + entry.offset
        return raw, entries

    def read_entries(self, archive_path, password: str | None = None) -> list:
        """Odczyt wpisow zwracajacy obiekty PFAEntry."""
        with open(archive_path, "rb") as f:
            header = self.read_header(f)
            if header["version"] == 1:
                count = struct.unpack("<I", f.read(4))[0]
                result = []
                offset = f.tell()
                for _ in range(count):
                    name_len = struct.unpack("<I", f.read(4))[0]
                    name = f.read(name_len).decode("utf-8", "replace")
                    size = struct.unpack("<I", f.read(4))[0]
                    result.append(PFAEntry(name=name, offset=offset, size=size,
                                           mtime=0.0, data_offset=f.tell()))
                    f.seek(size, os.SEEK_CUR)
                    offset = f.tell()
                return result
            return self._read_manifest(f, header, password)[1]

    # -- tworzenie ----------------------------------------------------
    def create_pfa(self, files, archive_path, progress_cb=None,
                   password: str | None = None, bases=None, keep_relative=True,
                   level: int = 6, cancel_event=None) -> PackResult:
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if not files:
            raise PackerError(settings.t("no_files"))
        packed = PackerCore(self.logger)
        queue = []
        seen = set()
        for path in files:
            name = packed.arcname_for(path, bases, keep_relative)
            if not name:
                name = os.path.basename(path)
            base, ext = os.path.splitext(name)
            i = 1
            while name in seen:
                name = "%s (%d)%s" % (base, i, ext)
                i += 1
            seen.add(name)
            queue.append((path, name))

        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        total = len(queue)
        report = _make_progress(progress_cb)
        result = PackResult(path=archive_path)
        emit(self.logger, "PFA: " + archive_path)

        level = max(0, min(9, int(level or 0)))
        salt = os.urandom(PFA_SALT_LEN)
        key = self._derive_key(password, salt, PFA_PBKDF2_ITERATIONS) if password else None
        flags = PFA_FLAG_ENCRYPTED if password else 0
        if level:
            flags |= PFA_FLAG_DEFLATE

        # 1) przetworz pliki: nazwa, dane (kompresja/szyfrowanie) i hash
        records = []
        offset = 0
        for i, (path, name) in enumerate(queue, 1):
            _check_cancel(cancel_event)
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError as ex:
                result.skipped += 1
                result.errors.append("%s: %s" % (path, ex))
                continue
            plain_size = len(data)
            digest = hashlib.sha256(data).hexdigest()
            payload = zlib.compress(data, level) if level else data
            entry_flags = PFA_ENTRY_COMPRESSED if level else 0
            if key is not None:
                nonce = os.urandom(PFA_NONCE_LEN)
                aes, nonce, _ = _aes_cipher(key, nonce)
                payload = nonce + aes.encrypt(nonce, payload, PFA_MAGIC_V2)
                entry_flags |= PFA_ENTRY_ENCRYPTED
            # kazdy wpis poprzedzony jest 4-bajtowym polem dlugosci payloadu
            start = offset
            offset += 4 + len(payload)
            records.append({
                "name": name, "offset": start, "size": plain_size,
                "mtime": os.path.getmtime(path), "mode": 0o644,
                "enc": entry_flags, "sha256": digest,
                "payload": payload,
            })
            result.size_before += plain_size
            report(i, total, name)

        # 2) manifest
        manifest = [_int_bytes(len(records), 4)]
        for rec in records:
            name_bytes = rec["name"].encode("utf-8")
            manifest.append(_int_bytes(len(name_bytes), 2) + name_bytes)
            manifest.append(_pack_entry(rec["offset"], int(rec["mtime"]),
                                        rec["size"], rec["enc"], rec["mode"]))
            manifest.append(bytes.fromhex(rec["sha256"]))
        raw_manifest = b"".join(manifest)
        if key is not None:
            nonce = os.urandom(PFA_NONCE_LEN)
            aes, nonce, _ = _aes_cipher(key, nonce)
            raw_manifest = (nonce + aes.encrypt(nonce, raw_manifest, PFA_MAGIC_V2))

        # 3) zapis
        with open(archive_path, "wb") as out:
            out.write(PFA_MAGIC_V2)
            out.write(_int_bytes(flags, 2) + b"\x01" + _int_bytes(PFA_PBKDF2_ITERATIONS, 4))
            out.write(_int_bytes(len(salt), 2) + salt)
            out.write(_int_bytes(len(raw_manifest), 4))
            out.write(raw_manifest)
            for rec in records:
                _check_cancel(cancel_event)
                out.write(_int_bytes(len(rec["payload"]), 4))
                out.write(rec["payload"])

        result.added = len(records)
        result.entries = len(records)
        result.size_after = os.path.getsize(archive_path)
        emit(self.logger, settings.t("packed") + archive_path)
        emit(self.logger, "%s %s (%s -> %s)" % (
            settings.t("total_size"), human_size(result.size_after),
            human_size(result.size_before), human_size(result.size_after)))
        return result

    # -- rozpakowywanie -----------------------------------------------
    def unpack_pfa(self, archive_path, output_folder, selected=None, progress_cb=None,
                   password: str | None = None, overwrite: bool = True,
                   cancel_event=None) -> ExtractResult:
        os.makedirs(output_folder, exist_ok=True)
        result = ExtractResult(fmt="pfa", output_folder=output_folder)
        report = _make_progress(progress_cb)
        emit(self.logger, "Unpack PFA: " + archive_path)

        with open(archive_path, "rb") as f:
            header = self.read_header(f)
            if header["version"] == 1:
                return self._unpack_v1(f, output_folder, selected, report, result,
                                       cancel_event)
            _, entries = self._read_manifest(f, header, password)
            key = None
            if header.get("encrypted"):
                key = self._derive_key(password, header["salt"], header["iterations"])
            wanted = None
            if selected is not None:
                wanted = {normalize_relative(s) for s in selected}
            todo = [e for e in entries if wanted is None or e.name in wanted]
            for i, entry in enumerate(todo, 1):
                _check_cancel(cancel_event)
                try:
                    target = safe_join(output_folder, entry.name)
                except PackerError as ex:
                    result.blocked.append(str(ex))
                    continue
                existed = os.path.exists(target)
                if existed and not overwrite:
                    result.skipped += 1
                    continue
                f.seek(entry.data_offset)
                size = int.from_bytes(f.read(4), "little")
                payload = f.read(size)
                if len(payload) != size:
                    raise PackerError("truncated entry: %s" % entry.name)
                if entry.encrypted:
                    if key is None:
                        if not password:
                            raise PackerError(settings.t("need_password"))
                        key = self._derive_key(password, header["salt"], header["iterations"])
                    nonce, body, tag = (payload[:PFA_NONCE_LEN],
                                        payload[PFA_NONCE_LEN:-PFA_TAG_LEN],
                                        payload[-PFA_TAG_LEN:])
                    aes, nonce, tag = _aes_cipher(key, nonce, tag)
                    try:
                        payload = aes.decrypt(nonce, body + tag, PFA_MAGIC_V2)
                    except Exception:
                        raise PackerError(settings.t("wrong_password"))
                if entry.compressed:
                    try:
                        payload = zlib.decompress(payload)
                    except zlib.error:
                        raise PackerError("corrupted entry: %s" % entry.name)
                if hashlib.sha256(payload).hexdigest() != entry.sha256:
                    raise PackerError("checksum mismatch: %s" % entry.name)
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                with open(target, "wb") as out:
                    out.write(payload)
                if entry.mtime:
                    try:
                        os.utime(target, (entry.mtime, entry.mtime))
                    except (OSError, OverflowError, ValueError):
                        pass
                result.extracted += 1
                result.overwritten += 1 if existed else 0
                result.bytes_written += len(payload)
                report(i, len(todo), entry.name)

        emit(self.logger, settings.t("unpacked") + output_folder)
        return result

    def _unpack_v1(self, f, output_folder, selected, report, result, cancel_event):
        count = struct.unpack("<I", f.read(4))[0]
        wanted = None
        if selected is not None:
            wanted = {normalize_relative(s) for s in selected}
        for i in range(count):
            _check_cancel(cancel_event)
            name_len = struct.unpack("<I", f.read(4))[0]
            name = f.read(name_len).decode("utf-8")
            size = struct.unpack("<I", f.read(4))[0]
            data = f.read(size)
            if wanted is not None and normalize_relative(name) not in wanted:
                continue
            try:
                target = safe_join(output_folder, name)
            except PackerError as ex:
                result.blocked.append(str(ex))
                continue
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "wb") as out:
                out.write(data)
            result.extracted += 1
            result.bytes_written += len(data)
            report(i + 1, count, name)
        emit(self.logger, settings.t("unpacked") + output_folder)
        return result

    def verify_pfa(self, archive_path, password=None, progress_cb=None):
        return self.verify(archive_path, password=password, progress_callback=progress_cb)

    def verify(self, archive_path, password=None, progress_callback=None):
        """Weryfikuje manifest i sumy SHA-256 wszystkich wpisow."""
        report = _make_progress(progress_callback)
        with open(archive_path, "rb") as f:
            header = self.read_header(f)
            if header["version"] == 1:
                entries = self.read_entries(archive_path)
                return True, "PFA1", len(entries)
            _, entries = self._read_manifest(f, header, password)
            key = None
            if header.get("encrypted"):
                if not password:
                    return False, settings.t("need_password"), 0
                key = self._derive_key(password, header["salt"], header["iterations"])
            for i, entry in enumerate(entries, 1):
                f.seek(entry.data_offset)
                size = int.from_bytes(f.read(4), "little")
                payload = f.read(size)
                if entry.encrypted and key is not None:
                    nonce, body, tag = (payload[:PFA_NONCE_LEN],
                                        payload[PFA_NONCE_LEN:-PFA_TAG_LEN],
                                        payload[-PFA_TAG_LEN:])
                    aes, nonce, tag = _aes_cipher(key, nonce, tag)
                    try:
                        payload = aes.decrypt(nonce, body + tag, PFA_MAGIC_V2)
                    except Exception:
                        return False, settings.t("wrong_password"), i - 1
                if entry.compressed:
                    try:
                        payload = zlib.decompress(payload)
                    except zlib.error as ex:
                        return False, "corrupted entry: %s (%s)" % (entry.name, ex), i - 1
                if hashlib.sha256(payload).hexdigest() != entry.sha256:
                    return False, "checksum mismatch: %s" % entry.name, i - 1
                report(i, len(entries), entry.name)
        return True, "", len(entries)

    # -- API wspolne z UnpackerCore / SecurityCore ---------------------
    def unpack_auto(self, archive_path, output_folder, selected=None, progress_cb=None,
                    password=None, overwrite=True, cancel_event=None) -> ExtractResult:
        """Zgodny interfejs z UnpackerCore.unpack_auto (tylko format PFA)."""
        if detect_format(archive_path) != "pfa":
            return UnpackerCore(self.logger).unpack_auto(
                archive_path, output_folder, selected=selected, progress_cb=progress_cb,
                password=password, overwrite=overwrite, cancel_event=cancel_event)
        return self.unpack_pfa(archive_path, output_folder, selected=selected,
                               progress_cb=progress_cb, password=password,
                               overwrite=overwrite, cancel_event=cancel_event)

    def entries(self, archive_path, password=None):
        """Lista wpisow PFA w formacie slownikow (jak UnpackerCore.entries)."""
        result = []
        for entry in self.read_entries(archive_path, password=password):
            result.append({
                "name": entry.name, "size": entry.size,
                "date": tuple(time.localtime(entry.mtime)[:6]) if entry.mtime else (),
                "encrypted": entry.encrypted, "is_dir": False,
                "sha256": entry.sha256,
            })
        return result, "pfa"

    def test_archive(self, archive_path, password=None, progress_cb=None):
        return self.verify_pfa(archive_path, password=password, progress_cb=progress_cb)

    def hash_file(self, path, algo="sha256"):
        return hash_file(path, algo)

    def crc32_file(self, path):
        return crc32_of_file(path)

    # -- API wspolne z PackerCore --------------------------------------
    def pack(self, files, archive_path, fmt="pfa", progress_cb=None, **kwargs) -> PackResult:
        """Tworzy archiwum PFA (zgodny interfejs z PackerCore.pack)."""
        archive_path = ensure_archive_ext(archive_path, "pfa")
        return self.create_pfa(
            files, archive_path,
            progress_cb=progress_cb,
            password=kwargs.get("password"),
            bases=kwargs.get("bases"),
            keep_relative=kwargs.get("keep_relative", True),
            level=kwargs.get("level", 6),
            cancel_event=kwargs.get("cancel_event"))

    # -- kontekst ------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


# =====================================================================
#  Bezpieczenstwo: sumy kontrolne i inspekcja plikow
# =====================================================================

def crc32_of_file(path: str, chunk_size=1024 * 1024) -> str:
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            crc = zlib.crc32(chunk, crc)
    return "%08x" % (crc & 0xFFFFFFFF)


def hash_file(path: str, algo: str = "sha256", chunk_size=1024 * 1024) -> str:
    algo = (algo or "sha256").lower()
    if algo == "crc32":
        return crc32_of_file(path, chunk_size)
    try:
        h = hashlib.new(algo)
    except ValueError:
        raise PackerError("unknown algorithm: %s" % algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


class SecurityCore:
    """Hashe plikow/katalogow, porownywanie z oczekiwanym hashem, CRC32."""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Empty()

    def hash_file(self, path: str, algo: str = "sha256") -> str:
        if not os.path.isfile(path):
            raise PackerError(settings.t("file_not_exist") + ": " + str(path))
        digest = hash_file(path, algo)
        emit(self.logger, "%s %s = %s" % (algo.upper(), path, digest))
        return digest

    def crc32_file(self, path: str) -> str:
        if not os.path.isfile(path):
            raise PackerError(settings.t("file_not_exist") + ": " + str(path))
        res = crc32_of_file(path)
        emit(self.logger, "CRC32 %s = %s" % (path, res))
        return res

    def hash_directory(self, folder: str, algo: str = "sha256",
                       progress_cb=None) -> dict:
        """Liczy hashe wszystkich plikow katalogu -> {sciezka_wzgledna: hash}."""
        if not os.path.isdir(folder):
            raise PackerError(settings.t("folder_not_exist"))
        files = list(iter_files(folder, None, skip_hidden=True))
        report = _make_progress(progress_cb)
        result = {}
        for i, path in enumerate(files, 1):
            rel = os.path.relpath(path, folder).replace("\\", "/")
            try:
                result[rel] = hash_file(path, algo)
            except (OSError, PackerError) as ex:
                result[rel] = "ERROR: %s" % ex
            report(i, len(files), rel)
        emit(self.logger, "%s: %d file(s) -> %s" % (algo.upper(), len(files), folder))
        return result

    def hash_archive(self, archive_path: str, algo: str = "sha256") -> dict:
        """Hashe wszystkich wpisow archiwum bez rozpakowywania."""
        fmt = detect_format(archive_path)
        result = {}
        if fmt == "zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    h = hashlib.new(algo)
                    with zf.open(info) as f:
                        for chunk in iter(lambda: f.read(1024 * 256), b""):
                            h.update(chunk)
                    result[info.filename] = h.hexdigest()
        elif fmt in TAR_MODES:
            with open_tar(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    h = hashlib.new(algo)
                    src = tf.extractfile(member)
                    if src is None:
                        continue
                    for chunk in iter(lambda: src.read(1024 * 256), b""):
                        h.update(chunk)
                    result[member.name] = h.hexdigest()
        elif fmt == "pfa":
            result = {e.name: e.sha256 for e in PFAFormat(self.logger).entries(archive_path)}
        else:
            raise PackerError(settings.t("unknown_format"))
        return result

    @staticmethod
    def compare(expected: str, actual: str) -> bool:
        return (expected or "").strip().lower() == (actual or "").strip().lower()


# =====================================================================
#  Inspekcja plikow (magic bytes, .pyc, podglad tekstu)
# =====================================================================

MAGIC_SIGNATURES = [
    (b"PK\x03\x04", "ZIP archive"),
    (b"PK\x05\x06", "empty ZIP archive"),
    (b"\x1f\x8b", "GZIP compressed"),
    (b"BZh", "BZIP2 compressed"),
    (b"\xfd7zXZ\x00", "XZ compressed"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!\x1a\x07", "RAR archive"),
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    (b"BM", "BMP image"),
    (b"%PDF-", "PDF document"),
    (b"PFA1", "PFA archive v1"),
    (b"PFA2", "PFA archive v2"),
    (b"\xfe\xed\xfa\xce", "Mach-O (32-bit)"),
    (b"\xcf\xfa\xed\xfe", "Mach-O (64-bit)"),
    (b"MZ", "Windows executable (PE)"),
    (b"\x7fELF", "ELF executable"),
    (b"SQLite format 3\x00", "SQLite database"),
    (b"\xd0\xcf\x11\xe0", "OLE2 (doc/xls)"),
    (b"ID3", "MP3 audio (ID3)"),
    (b"OggS", "OGG media"),
    (b"RIFF", "RIFF (WAV/AVI)"),
    (b"ftyp", "MP4 media"),
]


def sniff_magic(path: str) -> str:
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return ""
    if path.lower().endswith((".pyc", ".pyo")):
        return "Python compiled bytecode"
    for sig, name in MAGIC_SIGNATURES:
        if sig == b"ftyp":
            if head[4:8] == b"ftyp":
                return name
            continue
        if head.startswith(sig):
            return name
    return "unknown / raw data"


def is_probably_text(path: str, sample: int = 4096) -> bool:
    try:
        with open(path, "rb") as f:
            data = f.read(sample)
    except OSError:
        return False
    if not data:
        return True
    if b"\x00" in data:
        return False
    printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    return printable / float(len(data)) > 0.85


def describe_pyc(path: str) -> dict:
    """Odczytuje naglowek pliku .pyc (magic, wersja, znacznik czasu / hash)."""
    info = {"path": path}
    with open(path, "rb") as f:
        magic = f.read(4)
        flags = struct.unpack("<I", f.read(4))[0]
        info["magic"] = magic.hex()
        info["flags"] = flags
        if flags & 0x1:
            info["source_hash"] = f.read(8).hex()
        else:
            info["mtime"] = datetime.fromtimestamp(struct.unpack("<I", f.read(4))[0])
            info["source_size"] = struct.unpack("<I", f.read(4))[0]
    info["python"] = sys.version.split()[0]
    try:
        import importlib.util
        if importlib.util.MAGIC_NUMBER == magic:
            info["compatible"] = True
        else:
            info["compatible"] = False
    except Exception:
        pass
    return info


def creation_time(st: os.stat_result) -> float:
    """Data utworzenia pliku.

    Na Windows i macOS dostepny jest st_birthtime; na pozostalych systemach
    akceptujemy konwencje: brak pola w ogole lub wartosc 0 (brak danych).
    """
    for attr in ("st_birthtime", "st_birthtime_ns"):
        value = getattr(st, attr, None)
        if value:
            return value / 1e9 if attr.endswith("_ns") else value
    return st.st_ctime  # systemy bez informacji o utworzeniu pliku


def file_info(path: str) -> dict:
    """Pelen opis pliku: rozmiar, daty, typ, hash, podglad."""
    st = os.stat(path)
    info = {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "size": st.st_size,
        "size_human": human_size(st.st_size),
        "created": datetime.fromtimestamp(creation_time(st)),
        "modified": datetime.fromtimestamp(st.st_mtime),
        "type": sniff_magic(path),
        "is_text": is_probably_text(path),
        "readonly": not os.access(path, os.W_OK),
    }
    try:
        info["sha256"] = hash_file(path, "sha256")
        info["crc32"] = crc32_of_file(path)
    except OSError:
        pass
    if is_probably_text(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                info["preview"] = f.read(4000)
        except OSError:
            info["preview"] = ""
    return info


# =====================================================================
#  Watki robocze (GUI nie zamarza podczas dlugich operacji)
# =====================================================================

# Qt jest opcjonalne dla CLI - klase GUI definiujemy tylko, gdy Qt jest dostepne.
if QT_AVAILABLE:

  class WorkerSignals(QObject):
    progress = Signal(int)
    progress_text = Signal(int, str)
    finished = Signal()
    error = Signal(str)
    result = Signal(object)


  class BaseWorker(QThread):
    """Baza dla watkow: postep, anulowanie, obsluga wyjatkow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals()
        self.cancel_event = threading.Event()
        self._last_emit = 0.0
        self._last_pct = -1

    def cancel(self):
        self.cancel_event.set()

    def report(self, percent: int, message: str = ""):
        now = time.monotonic()
        percent = max(0, min(100, int(percent)))
        if message and (now - self._last_emit > 0.05 or percent == 100):
            self._last_emit = now
            self.signals.progress_text.emit(percent, message)
        if percent != self._last_pct:
            self._last_pct = percent
            self.signals.progress.emit(percent)

    def finish(self):
        self.signals.finished.emit()

    def fail(self, ex: Exception):
        if isinstance(ex, PackerError) and str(ex) == "__cancelled__":
            self.signals.error.emit(settings.t("cancelled"))
            return
        if isinstance(ex, PackerError):
            self.signals.error.emit(str(ex))
            return
        self.signals.error.emit("%s\n%s" % (ex, traceback.format_exc(limit=3)))


  class PackWorker(BaseWorker):
    def __init__(self, packer, files, fmt, archive_path, options=None, parent=None):
        super().__init__(parent)
        self.packer = packer
        self.files = files
        self.fmt = fmt
        self.archive_path = archive_path
        self.options = dict(options or {})

    def run(self):
        try:
            self.options["progress_cb"] = self.report
            self.options["cancel_event"] = self.cancel_event
            result = self.packer.pack(self.files, self.archive_path, self.fmt,
                                      **self.options)
            self.signals.result.emit(result)
        except Exception as ex:  # noqa: BLE001 - pokazujemy kazdy blad uzytkownikowi
            self.fail(ex)
        finally:
            self.finish()


  class UnpackWorker(BaseWorker):
    def __init__(self, unpacker, archive_path, output_folder, selected,
                 password=None, overwrite=True, parent=None):
        super().__init__(parent)
        self.unpacker = unpacker
        self.archive_path = archive_path
        self.output_folder = output_folder
        self.selected = selected
        self.password = password
        self.overwrite = overwrite

    def run(self):
        try:
            result = self.unpacker.unpack_auto(
                self.archive_path, self.output_folder, selected=self.selected,
                progress_cb=self.report, password=self.password,
                overwrite=self.overwrite, cancel_event=self.cancel_event)
            self.signals.result.emit(result)
        except Exception as ex:  # noqa: BLE001
            self.fail(ex)
        finally:
            self.finish()


  class PFACreateWorker(PackWorker):
    """Zgodnosc wsteczna - tworzenie PFA przez PackWorkera."""


  class PFAUnpackWorker(UnpackWorker):
    def __init__(self, pfa, archive_path, output_folder, password=None, parent=None):
        super().__init__(pfa, archive_path, output_folder, None, password, True, parent)


  class ListWorker(BaseWorker):
    """Wczytywanie zawartosci archiwum w tle."""

    def __init__(self, unpacker, archive_path, password=None, parent=None):
        super().__init__(parent)
        self.unpacker = unpacker
        self.archive_path = archive_path
        self.password = password

    def run(self):
        try:
            result = self.unpacker.entries(self.archive_path, self.password)
            self.signals.result.emit(result)
        except Exception as ex:  # noqa: BLE001
            self.fail(ex)
        finally:
            self.finish()


  class HashWorker(BaseWorker):
    """Haszowanie pliku, katalogu lub archiwum w tle."""

    def __init__(self, security, target, algo="sha256", mode="file", parent=None):
        super().__init__(parent)
        self.security = security
        self.target = target
        self.algo = algo
        self.mode = mode

    def run(self):
        try:
            if self.mode == "dir":
                result = self.security.hash_directory(self.target, self.algo,
                                                      progress_cb=self.report)
            elif self.mode == "archive":
                result = self.security.hash_archive(self.target, self.algo)
            else:
                self.report(50, os.path.basename(self.target))
                result = self.security.hash_file(self.target, self.algo)
            self.report(100)
            self.signals.result.emit(result)
        except Exception as ex:  # noqa: BLE001
            self.fail(ex)
        finally:
            self.finish()


  class TestArchiveWorker(BaseWorker):
    """Test integralnosci archiwum (CRC / SHA-256)."""

    def __init__(self, unpacker, archive_path, password=None, parent=None):
        super().__init__(parent)
        self.unpacker = unpacker
        self.archive_path = archive_path
        self.password = password

    def run(self):
        try:
            ok, problem, count = self.unpacker.test_archive(
                self.archive_path, self.password, progress_cb=self.report)
            self.signals.result.emit((ok, problem, count))
        except Exception as ex:  # noqa: BLE001
            self.fail(ex)
        finally:
            self.finish()
#  Pomocnicze widgety GUI
# =====================================================================

if QT_AVAILABLE:

  _ICON_COLORS = {
    "add": "#4ec9b0",
    "remove": "#f48771",
    "folder": "#dcb67a",
    "file": "#75beff",
    "archive": "#c586c0",
    "run": "#89d185",
    "hash": "#dcdcaa",
    "search": "#9cdcfe",
    "clear": "#808080",
}


  def build_icon(kind: str, color: str | None = None) -> QIcon:
    """Rysuje prosta ikone wektorowo (bez zewnetrznych plikow graficznych)."""
    color = color or _ICON_COLORS.get(kind, "#75beff")
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidth(3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if kind == "add":
        painter.drawLine(16, 6, 16, 26)
        painter.drawLine(6, 16, 26, 16)
    elif kind == "remove":
        painter.drawLine(7, 7, 25, 25)
        painter.drawLine(25, 7, 7, 25)
    elif kind in ("folder", "archive"):
        if kind == "folder":
            painter.drawRoundedRect(4, 10, 24, 16, 3, 3)
            painter.drawLine(4, 10, 13, 10)
            painter.drawLine(13, 10, 16, 7)
        else:
            painter.drawRoundedRect(6, 4, 20, 24, 3, 3)
            painter.drawLine(9, 4, 9, 28)
            painter.drawLine(9, 12, 26, 12)
    elif kind == "file":
        painter.drawRoundedRect(8, 4, 16, 24, 2, 2)
        painter.drawLine(12, 12, 20, 12)
        painter.drawLine(12, 17, 20, 17)
        painter.drawLine(12, 22, 17, 22)
    elif kind == "run":
        painter.drawLine(9, 6, 25, 16)
        painter.drawLine(25, 16, 9, 26)
        painter.drawLine(9, 26, 9, 6)
    elif kind == "hash":
        painter.drawLine(11, 5, 9, 27)
        painter.drawLine(21, 5, 19, 27)
        painter.drawLine(5, 12, 27, 12)
        painter.drawLine(4, 20, 26, 20)
    elif kind == "search":
        painter.drawEllipse(5, 5, 15, 15)
        painter.drawLine(19, 19, 27, 27)
    elif kind == "clear":
        painter.drawLine(8, 8, 24, 24)
        painter.drawLine(24, 8, 8, 24)
    else:
        painter.drawRoundedRect(6, 6, 20, 20, 4, 4)
    painter.end()
    return QIcon(pix)


  def load_image(path: str, width: int = 48, height: int = 48) -> QPixmap:
    """Wczytuje obraz z pliku i skaluje go do zadanych wymiarow z zachowaniem jakosci."""
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    if os.path.exists(full_path):
        pix = QPixmap(full_path)
        if not pix.isNull():
            return pix.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    return QPixmap()
    return QIcon(pix)





  class DropLineEdit(QLineEdit):
    """Pole tekstowe przyjmujace przeciagniete pliki/foldery."""
    pathsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.pathsDropped.emit(paths)
        else:
            super().dropEvent(event)


  class PathRow(QWidget):
    """Etykieta + sciezka + przycisk 'Przegladaj' + opcjonalny drop."""

    pathChanged = Signal(str)
    dropped = Signal(list)

    MODES = {
        "folder": "folder",
        "save": "save",
        "open": "open",
        "any": "any",
    }

    def __init__(self, label_text: str, mode: str = "open", parent=None,
                 placeholder: str = ""):
        super().__init__(parent)
        self.mode = mode
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel(label_text)
        self.label.setMinimumWidth(110)
        self.edit = DropLineEdit()
        if placeholder:
            self.edit.setPlaceholderText(placeholder)
        self.button = QPushButton(settings.t("browse"))
        layout.addWidget(self.label)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)
        self.button.clicked.connect(self.browse)
        self.edit.textChanged.connect(self.pathChanged.emit)
        self.edit.pathsDropped.connect(self._on_drop)

    def _on_drop(self, paths):
        if paths:
            self.edit.setText(paths[0])
            self.dropped.emit(paths)

    def browse(self, *_):
        start = self.text() or settings.default_dir or os.path.expanduser("~")
        if os.path.isfile(start):
            start = os.path.dirname(start)
        if self.mode == "folder":
            path = QFileDialog.getExistingDirectory(self, self.label.text(), start)
        elif self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, self.label.text(), start)
        elif self.mode == "any":
            path = QFileDialog.getExistingDirectory(self, self.label.text(), start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.label.text(), start)
        if path:
            self.edit.setText(path)
            settings.default_dir = os.path.dirname(path) if os.path.isfile(path) else path

    def text(self) -> str:
        return self.edit.text().strip().strip('"')

    def set_text(self, value: str):
        self.edit.setText(value or "")

    def bare_edit(self) -> QLineEdit:
        return self.edit



# =====================================================================
#  Okna dialogowe
# =====================================================================

  class ArchiveTreeDialog(QDialog):
      """Okno informacji o archiwum: wpisy, rozmiary, daty, hashe, typ szyfrowania."""

      def __init__(self, archive_path: str, entries, fmt: str, parent=None):
          super().__init__(parent)
          self.setWindowTitle("%s - %s" % (settings.t("info_title"), os.path.basename(archive_path)))
          self.resize(820, 480)
          layout = QVBoxLayout(self)

          summary = QLabel("%s: %s | %s: %d | %s: %s" % (
              fmt.upper(), archive_path, settings.t("files"), len(entries),
              settings.t("total_size"), human_size(sum(e["size"] for e in entries))))
          summary.setWordWrap(True)
          layout.addWidget(summary)

          self.table = QTableWidget(len(entries), 5)
          self.table.setHorizontalHeaderLabels([
              settings.t("files"), settings.t("total_size"), "Date", "Enc", "SHA-256 / CRC"])
          self.table.verticalHeader().setVisible(False)
          self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
          self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
          for row, entry in enumerate(entries):
              date = "/".join("%02d" % v for v in entry.get("date") or []) or "-"
              values = [entry["name"], human_size(entry["size"]), date,
                        "AES-256" if entry.get("encrypted") else "-",
                        entry.get("sha256") or "-"]
              for col, value in enumerate(values):
                  item = QTableWidgetItem(str(value))
                  if col == 1:
                      item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                  self.table.setItem(row, col, item)
          self.table.resizeColumnsToContents()
          self.table.horizontalHeader().setStretchLastSection(True)
          self.table.setSortingEnabled(True)
          layout.addWidget(self.table, 1)

          buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
          copy_btn = buttons.addButton(settings.t("copy"), QDialogButtonBox.ButtonRole.ActionRole)
          copy_btn.clicked.connect(self.copy_selected)
          buttons.rejected.connect(self.reject)
          buttons.accepted.connect(self.accept)
          layout.addWidget(buttons)

      def copy_selected(self):
          rows = sorted({i.row() for i in self.table.selectedIndexes()})
          text = "\n".join(self.table.item(r, 0).text() for r in rows)
          QApplication.clipboard().setText(text)


  class ShortcutsDialog(QDialog):
      """Okno pomocy ze skrotami klawiaturowymi."""

      def __init__(self, parent=None):
          super().__init__(parent)
          self.setWindowTitle(settings.t("shortcut_help_title"))
          self.resize(420, 360)
          layout = QVBoxLayout(self)
          view = QTextBrowser()
          view.setHtml(settings.t("shortcut_help"))
          layout.addWidget(view)
          buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
          buttons.rejected.connect(self.reject)
          layout.addWidget(buttons)


  class AboutDialog(QDialog):
      """Okno 'O programie' z informacjami o autorze."""

      def __init__(self, parent=None):
          super().__init__(parent)
          self.setWindowTitle(settings.t("about"))
          self.resize(600, 450)
          layout = QVBoxLayout(self)
          layout.setSpacing(16)
          layout.setContentsMargins(20, 20, 20, 20)
          
          top_layout = QHBoxLayout()
          top_layout.setSpacing(20)
          
          app_icon = QLabel()
          app_pixmap = load_image("docs/app.png", 120, 120)
          if not app_pixmap.isNull():
            app_icon.setPixmap(app_pixmap)
            app_icon.setStyleSheet("border: 2px solid #3c3c3c; border-radius: 8px; padding: 8px;")
          
          top_layout.addWidget(app_icon)
          
          view = QTextBrowser()
          view.setHtml(settings.t("about_text").format(
              name=__app_name__, ver=__version__, py=sys.version.split()[0],
              qt=QT_VERSION, platform=sys.platform))
          view.setOpenExternalLinks(True)
          view.setStyleSheet("""
              QTextBrowser {
                  background-color: #2d2d2d;
                  color: #d4d4d4;
                  border: 1px solid #3c3c3c;
                  border-radius: 8px;
                  padding: 12px;
              }
              QTextBrowser a {
                  color: #4fc1ff;
                  text-decoration: none;
              }
              QTextBrowser a:hover {
                  text-decoration: underline;
              }
          """)
          top_layout.addWidget(view, 1)
          
          layout.addLayout(top_layout)
          
          author_box = QGroupBox(settings.t("about_author"))
          author_box.setStyleSheet("""
              QGroupBox {
                  color: #9cdcfe;
                  font-weight: bold;
                  border: 1px solid #3c3c3c;
                  border-radius: 8px;
                  margin-top: 10px;
                  padding-top: 10px;
              }
              QGroupBox::title {
                  subcontrol-origin: margin;
                  left: 10px;
                  padding: 0 5px;
              }
          """)
          author_layout = QVBoxLayout(author_box)
          
          author_text = QLabel()
          author_text.setTextFormat(Qt.TextFormat.RichText)
          author_text.setOpenExternalLinks(True)
          author_text.setWordWrap(True)
          author_text.setText(
              "<b>{0}:</b> Sebastian Januchowski<br>"
              "<b>{1}:</b> polsoft.ITS™<br>"
              "<b>{2}:</b> <a href='mailto:polsoft.its@mail.com'>polsoft.its@mail.com</a><br>"
              "<b>{3}:</b> <a href='https://github.com/polsoft-it'>https://github.com/polsoft-it</a>".format(
                  settings.t("about_name"),
                  settings.t("about_company"),
                  settings.t("about_email"),
                  settings.t("about_github")
              )
          )
          author_text.setStyleSheet("""
              QLabel {
                  color: #d4d4d4;
                  padding: 8px;
              }
              QLabel a {
                  color: #4fc1ff;
                  text-decoration: none;
              }
              QLabel a:hover {
                  text-decoration: underline;
              }
          """)
          author_layout.addWidget(author_text)
          
          layout.addWidget(author_box)
          self.author_box = author_box
          self.author_text = author_text
          
          buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
          buttons.setStyleSheet("""
              QDialogButtonBox QPushButton {
                  min-width: 100px;
                  padding: 8px 16px;
                  border-radius: 4px;
              }
          """)
          buttons.rejected.connect(self.reject)
          layout.addWidget(buttons)


  if QT_AVAILABLE:
      class Notifier:
          """Powiadomienia w pasku statusu (zamiast modalnych okien).

          Komunikat pojawia sie na 6 sekund w prawym rogu paska statusu i trafia
          do logu. Nie blokuje watku roboczego ani uzytkownika.
          """

          STYLES = {
              "success": "color:#89d185;",
              "error": "color:#f48771;",
              "info": "color:#9cdcfe;",
          }

          def __init__(self, status_bar, log_callback=None):
              self.label = QLabel("")
              self.label.setVisible(False)
              self.log = log_callback or (lambda _m: None)
              status_bar.addPermanentWidget(self.label)
              self._timer = QTimer()
              self._timer.setSingleShot(True)
              self._timer.timeout.connect(self._clear)

          def notify(self, title: str, message: str, kind: str = "info"):
              self.label.setStyleSheet(self.STYLES.get(kind, self.STYLES["info"]))
              self.label.setText(message if not title else "%s: %s" % (title, message))
              self.label.setVisible(True)
              self.log(message)
              self._timer.start(6000)

          def _clear(self):
              self.label.clear()
              self.label.setVisible(False)


# koniec sekcji GUI (definicje Qt pomijane, gdy PySide6 jest niedostepne)


if QT_AVAILABLE:
    class ProgressOverlay(QWidget):
        """Banner postepu nad logiem z mozliwoscia anulowania."""

        cancelRequested = Signal()

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.label = QLabel("")
            self.label.setStyleSheet("color:#9cdcfe;")
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            self.bar.setMaximumHeight(18)
            self.button = QToolButton()
            self.button.setText("X")
            self.button.setToolTip(settings.t("cancelled"))
            self.button.clicked.connect(self.cancelRequested.emit)
            layout.addWidget(self.label, 1)
            layout.addWidget(self.bar, 2)
            layout.addWidget(self.button)
            self.hide()

        def start(self, text: str):
            self.label.setText(text)
            self.bar.setValue(0)
            self.show()

        def update_progress(self, percent: int, message: str = ""):
            self.bar.setValue(percent)
            if message:
                self.label.setText(message)

        def stop(self):
            self.hide()


# =====================================================================
#  Glowne okno aplikacji
# =====================================================================

if QT_AVAILABLE:

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.worker = None
            self.workers = []
            self.archive_entries = []
            self.archive_fmt = "unknown"
            self.pack_items = []
            self.last_generated = ""
            self.idle_dialogs = []


            self.setWindowTitle(settings.t("app_title"))
            window_icon_pixmap = load_image("docs/file2.png", 256, 256)
            if not window_icon_pixmap.isNull():
                self.setWindowIcon(QIcon(window_icon_pixmap))
            else:
                self.setWindowIcon(build_icon("archive"))

            self.logger = Logger()
            self.generator = FileGenerator(self.logger)
            self.packer = PackerCore(self.logger)
            self.unpacker = UnpackerCore(self.logger)
            self.security = SecurityCore(self.logger)
            self.pfa = PFAFormat(self.logger)

            central = QWidget()
            self.setCentralWidget(central)
            root = QVBoxLayout(central)
            root.setContentsMargins(8, 8, 8, 8)

            self._title_label = QLabel(settings.t("app_title"))
            self._title_label.setObjectName("TitleLabel")
            self._version_label = QLabel("v" + __version__)
            self._version_label.setObjectName("HintLabel")
            
            title_icon = QLabel()
            title_pixmap = load_image("docs/app.png", 64, 64)
            if not title_pixmap.isNull():
                title_icon.setPixmap(title_pixmap)
            
            title_layout = QHBoxLayout()
            title_layout.addWidget(self._title_label)
            title_layout.addWidget(self._version_label)
            title_layout.setSpacing(8)
            
            header = QHBoxLayout()
            header.addWidget(title_icon)
            header.addLayout(title_layout)
            header.addStretch(1)
            root.addLayout(header)

            self.tabs = QTabWidget()
            root.addWidget(self.tabs, 3)

            splitter = QSplitter(Qt.Orientation.Vertical)
            log_box = QGroupBox(settings.t("log"))
            log_layout = QVBoxLayout(log_box)
            log_tools = QHBoxLayout()
            self.btn_clear_log = QPushButton(settings.t("clear_log"))
            self.btn_clear_log.setIcon(build_icon("clear"))
            self.btn_clear_log.clicked.connect(self.clear_log)
            self.btn_save_log = QPushButton(settings.t("save_log"))
            self.btn_save_log.clicked.connect(self.save_log)
            log_tools.addStretch(1)
            log_tools.addWidget(self.btn_clear_log)
            log_tools.addWidget(self.btn_save_log)
            log_layout.addLayout(log_tools)
            self.log_widget = QPlainTextEdit()
            self.log_widget.setReadOnly(True)
            self.log_widget.setMaximumBlockCount(Logger.MAX_BLOCKS)
            self.logger.widget = self.log_widget
            log_layout.addWidget(self.log_widget, 1)
            self.overlay = ProgressOverlay()
            self.overlay.cancelRequested.connect(self.cancel_operation)
            log_layout.addWidget(self.overlay)
            splitter.addWidget(log_box)
            self.log_box = log_box
            self.splitter = splitter
            splitter.setSizes([170])
            root.addWidget(splitter, 2)

            self.status_label = QLabel(settings.t("status_ready"))
            self.status_bar = self.statusBar()
            self.status_bar.addWidget(self.status_label, 1)
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFixedWidth(260)
            self.status_bar.addPermanentWidget(self.progress_bar)
            self.notify = Notifier(self.status_bar, self.log)

            self.build_generate_tab()
            self.build_pack_tab()
            self.build_unpack_tab()
            self.build_security_tab()
            self.build_settings_tab()

            self.create_actions()
            self.connect_signals()
            self.refresh_language()
            self.apply_theme()

            self.setAcceptDrops(True)
            self.tabs.setAcceptDrops(True)

            self.adjustSize()

        # -----------------------------------------------------------------
        #  Zakladka 1: Generator
        # -----------------------------------------------------------------
        def build_generate_tab(self):
            w = QWidget()
            layout = QVBoxLayout(w)

            self.gen_folder_row = PathRow(settings.t("output_folder"), "folder")
            layout.addWidget(self.gen_folder_row)
            self.gen_folder_edit = self.gen_folder_row.edit
            if settings.default_dir and os.path.isdir(settings.default_dir):
                self.gen_folder_edit.setText(settings.default_dir)

            form = QFormLayout()
            self.gen_name_edit = QLineEdit("sample")
            self.gen_ext_edit = QLineEdit("txt")
            self.gen_size_spin = QSpinBox()
            self.gen_size_spin.setRange(1, 2_147_483_647)
            self.gen_size_spin.setValue(1024)
            self.gen_size_spin.setSingleStep(1024)
            self.gen_width_spin = QSpinBox()
            self.gen_width_spin.setRange(1, 16384)
            self.gen_width_spin.setValue(256)
            self.gen_height_spin = QSpinBox()
            self.gen_height_spin.setRange(1, 16384)
            self.gen_height_spin.setValue(256)
            self.gen_pattern_combo = QComboBox()
            for value in ("gradient", "xr", "noise", "checker", "plasma"):
                self.gen_pattern_combo.addItem(value, value)
            self.gen_preset_combo = QComboBox()
            for value in ("empty", "markdown", "license", "gitignore"):
                self.gen_preset_combo.addItem(value, value)
            self.gen_preset_combo.currentIndexChanged.connect(self._on_preset_changed)
            self.gen_keep_source = QCheckBox(settings.t("confirmed"))
            self.gen_keep_source.setChecked(True)

            row_name = QHBoxLayout()
            row_name.addWidget(self.gen_name_edit, 2)
            row_name.addWidget(QLabel(settings.t("file_ext")))
            row_name.addWidget(self.gen_ext_edit, 1)
            row_group = QWidget()
            row_group.setLayout(row_name)
            form.addRow(settings.t("file_name"), row_group)

            row_bin = QHBoxLayout()
            row_bin.addWidget(QLabel(settings.t("bin_size")))
            row_bin.addWidget(self.gen_size_spin, 1)
            row_bin.addWidget(QLabel(settings.t("preset_label")))
            row_bin.addWidget(self.gen_preset_combo, 1)
            bin_group = QWidget()
            bin_group.setLayout(row_bin)
            form.addRow(settings.t("btn_generate_bin"), bin_group)

            row_raw = QHBoxLayout()
            row_raw.addWidget(QLabel("W"))
            row_raw.addWidget(self.gen_width_spin, 1)
            row_raw.addWidget(QLabel("H"))
            row_raw.addWidget(self.gen_height_spin, 1)
            row_raw.addWidget(self.gen_pattern_combo, 2)
            raw_group = QWidget()
            raw_group.setLayout(row_raw)
            form.addRow(settings.t("btn_generate_raw"), raw_group)
            layout.addLayout(form)

            self.gen_code_label = QLabel(settings.t("code_area"))
            layout.addWidget(self.gen_code_label)
            self.gen_code_edit = QPlainTextEdit()
            self.gen_code_edit.setPlaceholderText("Content of the generated file...")
            self.gen_code_edit.setPlainText(DEFAULT_GEN_CODE)
            self.gen_code_edit.setTabStopDistance(32)
            layout.addWidget(self.gen_code_edit, 1)

            buttons = QGridLayout()
            self.gen_buttons = []
            specs = [
                ("btn_generate_text", self.do_generate_text, "file"),
                ("btn_generate_bin", self.do_generate_bin, "file"),
                ("btn_generate_pyc", self.do_generate_pyc, "run"),
                ("btn_generate_script", self.do_generate_script, "run"),
                ("btn_generate_c", self.do_generate_c, "file"),
                ("btn_generate_cpp", self.do_generate_cpp, "file"),
                ("btn_generate_raw", self.do_generate_raw, "file"),
                ("btn_generate_json", self.do_generate_json, "file"),
                ("btn_generate_markdown", self.do_generate_markdown, "file"),
            ]
            for index, (key, handler, icon) in enumerate(specs):
                button = QPushButton(settings.t(key))
                button.setIcon(build_icon(icon))
                button.clicked.connect(handler)
                buttons.addWidget(button, index // 3, index % 3)
            layout.addLayout(buttons)

            last_row = QHBoxLayout()
            self.btn_open_generated = QPushButton(settings.t("open_in_editor"))
            self.btn_open_generated.setEnabled(False)
            self.btn_open_generated.clicked.connect(self.open_generated)
            self.btn_reveal_generated = QPushButton(settings.t("cmd_reveal"))
            self.btn_reveal_generated.setEnabled(False)
            self.btn_reveal_generated.clicked.connect(self.reveal_generated)
            last_row.addWidget(self.btn_open_generated)
            last_row.addWidget(self.btn_reveal_generated)
            last_row.addStretch(1)
            layout.addLayout(last_row)

            self.tabs.addTab(w, settings.t("tab_generate"))

        def _on_preset_changed(self, _index):
            preset = self.gen_preset_combo.currentData()
            content = GEN_PRESETS.get(preset)
            if content is None:
                return
            self.gen_code_edit.setPlainText(content)

        # -----------------------------------------------------------------
        #  Zakladka 2: Pakowanie
        # -----------------------------------------------------------------
        def build_pack_tab(self):
            w = QWidget()
            layout = QVBoxLayout(w)

            source_box = QGroupBox(settings.t("group_source"))
            source_layout = QVBoxLayout(source_box)
            hint = QLabel(settings.t("drag_hint"))
            hint.setObjectName("HintLabel")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            source_layout.addWidget(hint)

            self.pack_list = QListWidget()
            self.pack_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.pack_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.pack_list.customContextMenuRequested.connect(self.pack_list_menu)
            self.pack_list.itemSelectionChanged.connect(self.update_pack_summary)
            source_layout.addWidget(self.pack_list, 1)

            tools = QHBoxLayout()
            self.btn_add_files = QPushButton(settings.t("add_files"))
            self.btn_add_files.setIcon(build_icon("add"))
            self.btn_add_files.clicked.connect(self.pick_pack_items)
            self.btn_add_folder = QPushButton(settings.t("add_folder"))
            self.btn_add_folder.setIcon(build_icon("folder"))
            self.btn_add_folder.clicked.connect(self.add_pack_folder)
            self.btn_remove = QPushButton(settings.t("remove"))
            self.btn_remove.setIcon(build_icon("remove"))
            self.btn_remove.clicked.connect(self.remove_pack_items)
            self.btn_clear_items = QPushButton(settings.t("clear"))
            self.btn_clear_items.clicked.connect(self.clear_pack_items)
            self.pack_summary = QLabel("")
            self.pack_summary.setObjectName("HintLabel")
            for button in (self.btn_add_files, self.btn_add_folder, self.btn_remove,
                           self.btn_clear_items):
                tools.addWidget(button)
            tools.addStretch(1)
            tools.addWidget(self.pack_summary)
            source_layout.addLayout(tools)

            filters = QHBoxLayout()
            self.pack_filter_edit = QLineEdit()
            self.pack_filter_edit.setPlaceholderText(settings.t("pattern_help"))
            self.pack_skip_hidden = QCheckBox(settings.t("scan_hidden"))
            self.pack_skip_hidden.setChecked(settings.skip_hidden)
            self.pack_keep_rel = QCheckBox(settings.t("include_root"))
            self.pack_keep_rel.setChecked(settings.keep_relative)
            filters.addWidget(QLabel(settings.t("filter")))
            filters.addWidget(self.pack_filter_edit, 1)
            filters.addWidget(self.pack_skip_hidden)
            filters.addWidget(self.pack_keep_rel)
            source_layout.addLayout(filters)
            layout.addWidget(source_box, 3)

            out_box = QGroupBox(settings.t("group_output"))
            out_layout = QGridLayout(out_box)
            self.pack_archive_row = PathRow(settings.t("archive_path"), "save")
            out_layout.addWidget(self.pack_archive_row, 0, 0, 1, 3)
            self.pack_archive_edit = self.pack_archive_row.edit
            self.pack_archive_edit.setReadOnly(False)

            self.pack_format_combo = QComboBox()
            for value in ("zip", "tar", "targz", "tarbz2", "tarxz", "pfa"):
                self.pack_format_combo.addItem(value, value)
            self.pack_format_combo.setCurrentIndex(
                max(0, self.pack_format_combo.findData(settings.last_format)))
            self.pack_format_combo.currentIndexChanged.connect(self.on_pack_format_change)
            out_layout.addWidget(QLabel(settings.t("archive_format")), 1, 0)
            out_layout.addWidget(self.pack_format_combo, 1, 1)

            self.pack_level_spin = QSpinBox()
            self.pack_level_spin.setRange(0, 9)
            self.pack_level_spin.setValue(int(settings.compression_level))
            out_layout.addWidget(QLabel(settings.t("compression_level")), 1, 2)
            out_layout.addWidget(self.pack_level_spin, 1, 3)

            self.pack_password_edit = QLineEdit()
            self.pack_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.pack_password_edit.setPlaceholderText(settings.t("password_optional"))
            self.pack_password2_edit = QLineEdit()
            self.pack_password2_edit.setEchoMode(QLineEdit.EchoMode.Password)
            out_layout.addWidget(QLabel(settings.t("password")), 2, 0)
            out_layout.addWidget(self.pack_password_edit, 2, 1, 1, 2)
            out_layout.addWidget(self.pack_password2_edit, 2, 3)

            self.pack_append_check = QCheckBox(settings.t("add_to_archive"))
            self.pack_follow_check = QCheckBox(settings.t("follow_symlinks"))
            self.pack_follow_check.setChecked(settings.follow_symlinks)
            out_layout.addWidget(self.pack_append_check, 3, 0, 1, 2)
            out_layout.addWidget(self.pack_follow_check, 3, 2, 1, 2)

            actions = QHBoxLayout()
            self.btn_pack = QPushButton(settings.t("create_archive"))
            self.btn_pack.setIcon(build_icon("archive"))
            self.btn_pack.clicked.connect(self.do_pack)
            actions.addStretch(1)
            actions.addWidget(self.btn_pack)
            out_layout.addLayout(actions, 4, 0, 1, 4)
            layout.addWidget(out_box, 2)

            self.tabs.addTab(w, settings.t("tab_pack"))
            self.pack_keep_rel.toggled.connect(self._on_keep_rel_toggled)

        def _on_keep_rel_toggled(self, _value):
            settings.keep_relative = self.pack_keep_rel.isChecked()

        def on_pack_format_change(self, _index):
            fmt = self.pack_format_combo.currentData()
            path = self.pack_archive_edit.text().strip()
            if path:
                base = path
                for ext in sorted(FORMAT_EXTS.values(), key=len, reverse=True):
                    if base.lower().endswith(ext):
                        base = base[:-len(ext)]
                        break
                self.pack_archive_edit.setText(base + FORMAT_EXTS.get(fmt, ""))
            settings.last_format = fmt

        # -----------------------------------------------------------------
        #  Zakladka 3: Rozpakowywanie
        # -----------------------------------------------------------------
        def build_unpack_tab(self):
            w = QWidget()
            layout = QVBoxLayout(w)

            top = QGridLayout()
            self.unpack_archive_row = PathRow(settings.t("select_archive"), "open")
            self.unpack_archive_edit = self.unpack_archive_row.edit
            self.unpack_archive_edit.setAcceptDrops(True)
            self.unpack_archive_row.dropped.connect(self.on_archive_dropped)
            top.addWidget(self.unpack_archive_row, 0, 0, 1, 3)

            self.unpack_output_row = PathRow(settings.t("extract_to"), "folder")
            self.unpack_output_folder_edit = self.unpack_output_row.edit
            top.addWidget(self.unpack_output_row, 1, 0, 1, 3)

            self.unpack_password_edit = QLineEdit()
            self.unpack_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.unpack_password_edit.setPlaceholderText(settings.t("password_optional"))
            top.addWidget(QLabel(settings.t("password")), 2, 0)
            top.addWidget(self.unpack_password_edit, 2, 1, 1, 2)
            self.unpack_overwrite_check = QCheckBox(settings.t("overwrite_existing"))
            self.unpack_overwrite_check.setChecked(True)
            top.addWidget(self.unpack_overwrite_check, 3, 0, 1, 2)
            layout.addLayout(top)

            self.archive_contents_label = QLabel(settings.t("archive_contents"))
            layout.addWidget(self.archive_contents_label)
            self.archive_info_label = QLabel("")
            self.archive_info_label.setObjectName("HintLabel")
            layout.addWidget(self.archive_info_label)
            self.archive_status_label = QLabel("")
            self.archive_status_label.setObjectName("HintLabel")
            layout.addWidget(self.archive_status_label)

            self.unpack_list_widget = QListWidget()
            self.unpack_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.unpack_list_widget.setSortingEnabled(True)
            layout.addWidget(self.unpack_list_widget, 1)

            filter_row = QHBoxLayout()
            self.unpack_filter_edit = QLineEdit()
            self.unpack_filter_edit.setPlaceholderText(settings.t("filter"))
            self.unpack_filter_edit.textChanged.connect(self.filter_archive_entries)
            filter_row.addWidget(self.unpack_filter_edit, 1)
            self.btn_select_all = QPushButton(settings.t("select_all"))
            self.btn_select_all.clicked.connect(self.select_all_entries)
            self.btn_select_none = QPushButton(settings.t("select_none"))
            self.btn_select_none.clicked.connect(lambda: self.unpack_list_widget.clearSelection())
            filter_row.addWidget(self.btn_select_all)
            filter_row.addWidget(self.btn_select_none)
            layout.addLayout(filter_row)

            buttons = QHBoxLayout()
            self.btn_load_archive = QPushButton(settings.t("load_archive"))
            self.btn_load_archive.setIcon(build_icon("search"))
            self.btn_load_archive.clicked.connect(self.load_archive_contents)
            self.btn_test_archive = QPushButton(settings.t("verify_archive"))
            self.btn_test_archive.setIcon(build_icon("hash"))
            self.btn_test_archive.clicked.connect(self.test_archive)
            self.btn_unpack_all = QPushButton(settings.t("extract_all"))
            self.btn_unpack_all.setIcon(build_icon("folder"))
            self.btn_unpack_all.clicked.connect(self.do_unpack_all)
            self.btn_unpack_selected = QPushButton(settings.t("extract_selected"))
            self.btn_unpack_selected.clicked.connect(self.do_unpack_selected)
            self.btn_archive_info = QPushButton(settings.t("info_title"))
            self.btn_archive_info.clicked.connect(self.show_archive_info)
            for button in (self.btn_load_archive, self.btn_test_archive, self.btn_unpack_all,
                           self.btn_unpack_selected, self.btn_archive_info):
                buttons.addWidget(button)
            layout.addLayout(buttons)

            self.tabs.addTab(w, settings.t("tab_unpack"))

        def on_archive_dropped(self, paths):
            path = paths[0]
            if os.path.isdir(path):
                return
            self.unpack_archive_edit.setText(path)
            if not self.unpack_output_folder_edit.text().strip():
                name = os.path.basename(path)
                for ext in ARCHIVE_EXTS:
                    if name.lower().endswith(ext):
                        name = name[:-len(ext)]
                        break
                self.unpack_output_folder_edit.setText(os.path.join(os.path.dirname(path), name))
            self.load_archive_contents()

        # -----------------------------------------------------------------
        #  Zakladka 4: Bezpieczenstwo
        # -----------------------------------------------------------------
        def build_security_tab(self):
            w = QWidget()
            layout = QVBoxLayout(w)

            hash_box = QGroupBox(settings.t("group_hash"))
            hl = QGridLayout(hash_box)
            self.sec_file_row = PathRow(settings.t("hash_file"), "open")
            self.sec_file_edit = self.sec_file_row.edit
            hl.addWidget(self.sec_file_row, 0, 0, 1, 4)

            self.sec_algo_combo = QComboBox()
            for algo in SUPPORTED_HASHES:
                self.sec_algo_combo.addItem(algo.upper(), algo)
            self.sec_algo_combo.setCurrentIndex(max(0, self.sec_algo_combo.findData("sha256")))
            hl.addWidget(QLabel(settings.t("hash_algo")), 1, 0)
            hl.addWidget(self.sec_algo_combo, 1, 1)
            self.btn_hash = QPushButton(settings.t("hash_file"))
            self.btn_hash.setIcon(build_icon("hash"))
            self.btn_hash.clicked.connect(self.do_hash_file)
            self.btn_hash_dir = QPushButton(settings.t("hash_multi"))
            self.btn_hash_dir.clicked.connect(self.do_hash_dir)
            self.btn_hash_archive = QPushButton(settings.t("group_archive"))
            self.btn_hash_archive.clicked.connect(self.do_hash_archive)
            hl.addWidget(self.btn_hash, 1, 2)
            hl.addWidget(self.btn_hash_dir, 1, 3)
            hl.addWidget(self.btn_hash_archive, 2, 2)
            self.btn_crc = QPushButton("CRC32")
            self.btn_crc.clicked.connect(self.do_crc_file)
            hl.addWidget(self.btn_crc, 2, 3)

            hl.addWidget(QLabel(settings.t("hash_result")), 2, 0)
            self.sec_result_edit = QLineEdit()
            self.sec_result_edit.setReadOnly(True)
            hl.addWidget(self.sec_result_edit, 2, 1)

            hl.addWidget(QLabel(settings.t("compare")), 3, 0)
            self.sec_expected_edit = QLineEdit()
            self.sec_expected_edit.setPlaceholderText("hex digest...")
            hl.addWidget(self.sec_expected_edit, 3, 1)
            self.sec_compare_label = QLabel("")
            hl.addWidget(self.sec_compare_label, 3, 2, 1, 2)
            self.sec_expected_edit.textChanged.connect(self.update_hash_compare)

            tools = QHBoxLayout()
            self.btn_copy_hash = QPushButton(settings.t("copy"))
            self.btn_copy_hash.clicked.connect(
                lambda: QApplication.clipboard().setText(self.sec_result_edit.text()))
            self.btn_save_hash = QPushButton(settings.t("save"))
            self.btn_save_hash.clicked.connect(self.save_hash_results)
            self.btn_inspect = QPushButton(settings.t("inspect"))
            self.btn_inspect.clicked.connect(self.inspect_file)
            tools.addWidget(self.btn_copy_hash)
            tools.addWidget(self.btn_save_hash)
            tools.addWidget(self.btn_inspect)
            tools.addStretch(1)
            hl.addLayout(tools, 4, 0, 1, 4)
            layout.addWidget(hash_box)

            pfa_box = QGroupBox(settings.t("group_pfa"))
            pl = QGridLayout(pfa_box)
            self.pfa_file_row = PathRow(settings.t("pfa_file"), "open")
            self.pfa_file_edit = self.pfa_file_row.edit
            pl.addWidget(self.pfa_file_row, 0, 0, 1, 3)
            self.pfa_files_row = PathRow(settings.t("select_files"), "open")
            pl.addWidget(self.pfa_files_row, 1, 0, 1, 3)
            self.pfa_password_edit = QLineEdit()
            self.pfa_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.pfa_password_edit.setPlaceholderText(settings.t("password_optional"))
            pl.addWidget(QLabel(settings.t("password")), 2, 0)
            pl.addWidget(self.pfa_password_edit, 2, 1, 1, 2)
            pfa_buttons = QHBoxLayout()
            self.btn_pfa_create = QPushButton(settings.t("pfa_create"))
            self.btn_pfa_create.setIcon(build_icon("archive"))
            self.btn_pfa_create.clicked.connect(self.do_pfa_create)
            self.btn_pfa_unpack = QPushButton(settings.t("pfa_unpack"))
            self.btn_pfa_unpack.clicked.connect(self.do_pfa_unpack)
            self.btn_pfa_verify = QPushButton(settings.t("verify_archive"))
            self.btn_pfa_verify.clicked.connect(self.do_pfa_verify)
            pfa_buttons.addStretch(1)
            pfa_buttons.addWidget(self.btn_pfa_create)
            pfa_buttons.addWidget(self.btn_pfa_unpack)
            pfa_buttons.addWidget(self.btn_pfa_verify)
            pl.addLayout(pfa_buttons, 3, 0, 1, 3)
            layout.addWidget(pfa_box)
            layout.addStretch(1)

            self.tabs.addTab(w, settings.t("tab_security"))

        # -----------------------------------------------------------------
        #  Zakladka 5: Ustawienia
        # -----------------------------------------------------------------
        def build_settings_tab(self):
            w = QWidget()
            layout = QVBoxLayout(w)

            appearance = QGroupBox(settings.t("group_appearance"))
            al = QGridLayout(appearance)
            self.lang_combo = QComboBox()
            self.lang_combo.addItem("Polski", "pl")
            self.lang_combo.addItem("English", "en")
            self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(settings.language)))
            self.theme_check = QCheckBox(settings.t("appearance_qss"))
            self.theme_check.setChecked(bool(settings.dark_theme))
            self.modal_check = QCheckBox(settings.t("modal_dialogs"))
            self.modal_check.setChecked(bool(settings.modal_dialogs))
            self.default_dir_row = PathRow(settings.t("appearance_default_dir"), "folder")
            self.default_dir_row.set_text(settings.default_dir)
            self.zoom_label = QLabel(settings.t("font_size"))
            self.zoom_spin = QSpinBox()
            self.zoom_spin.setRange(7, 20)
            self.zoom_spin.setValue(int(self.font().pointSize() or 10))
            al.addWidget(QLabel(settings.t("language")), 0, 0)
            al.addWidget(self.lang_combo, 0, 1)
            al.addWidget(self.theme_check, 0, 2)
            al.addWidget(self.modal_check, 1, 0, 1, 2)
            al.addWidget(self.default_dir_row, 1, 0, 1, 3)
            al.addWidget(self.zoom_label, 2, 0)
            al.addWidget(self.zoom_spin, 2, 1)
            layout.addWidget(appearance)

            about = QGroupBox(settings.t("group_about"))
            bl = QVBoxLayout(about)
            self.about_label = QLabel()
            self.about_label.setWordWrap(True)
            bl.addWidget(self.about_label)
            about_buttons = QHBoxLayout()
            self.btn_shortcuts = QPushButton(settings.t("shortcut_help_title"))
            self.btn_shortcuts.clicked.connect(lambda: ShortcutsDialog(self).exec())
            self.btn_settings_path = QPushButton(settings.t("settings_path"))
            self.btn_settings_path.clicked.connect(self.show_settings_path)
            self.btn_save_settings = QPushButton(settings.t("save_settings"))
            self.btn_save_settings.clicked.connect(self.save_settings)
            self.btn_open_log_folder = QPushButton(settings.t("open_folder"))
            self.btn_open_log_folder.clicked.connect(
                lambda: self.open_path(os.path.dirname(settings.path)))
            for button in (self.btn_shortcuts, self.btn_settings_path,
                           self.btn_save_settings, self.btn_open_log_folder):
                about_buttons.addWidget(button)
            about_buttons.addStretch(1)
            bl.addLayout(about_buttons)
            layout.addWidget(about)
            layout.addStretch(1)

            self.tabs.addTab(w, settings.t("tab_settings"))

        # -----------------------------------------------------------------
        #  Akcje, menu i skroty
        # -----------------------------------------------------------------
        def create_actions(self):
            self.act_add_files = QAction(build_icon("add"), settings.t("add_files"), self)
            self.act_add_files.setShortcut(QKeySequence("Ctrl+O"))
            self.act_add_files.triggered.connect(self.pick_pack_items)

            self.act_add_folder = QAction(build_icon("folder"), settings.t("add_folder"), self)
            self.act_add_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
            self.act_add_folder.triggered.connect(self.add_pack_folder)

            self.act_pack = QAction(build_icon("archive"), settings.t("create_archive"), self)
            self.act_pack.setShortcut(QKeySequence("Ctrl+E"))
            self.act_pack.triggered.connect(self.do_pack)

            self.act_unpack = QAction(build_icon("folder"), settings.t("extract_all"), self)
            self.act_unpack.setShortcut(QKeySequence("Ctrl+U"))
            self.act_unpack.triggered.connect(self.do_unpack_all)

            self.act_generate = QAction(build_icon("file"), settings.t("group_generator"), self)
            self.act_generate.setShortcut(QKeySequence("Ctrl+G"))
            self.act_generate.triggered.connect(self.do_generate_text)

            self.act_hash = QAction(build_icon("hash"), settings.t("hash_file"), self)
            self.act_hash.setShortcut(QKeySequence("Ctrl+Shift+H"))
            self.act_hash.triggered.connect(self.do_hash_file)

            self.act_test = QAction(settings.t("verify_archive"), self)
            self.act_test.setShortcut(QKeySequence("F5"))
            self.act_test.triggered.connect(self.test_archive)

            self.act_clear_log = QAction(settings.t("clear_log"), self)
            self.act_clear_log.setShortcut(QKeySequence("Ctrl+L"))
            self.act_clear_log.triggered.connect(self.clear_log)

            self.act_save_log = QAction(settings.t("save_log"), self)
            self.act_save_log.setShortcut(QKeySequence("Ctrl+S"))
            self.act_save_log.triggered.connect(self.save_log)

            self.act_quit = QAction(settings.t("quit"), self)
            self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
            self.act_quit.triggered.connect(self.close)

            menu_file = self.menuBar().addMenu(settings.t("menu_file"))
            menu_file.addAction(self.act_add_files)
            menu_file.addAction(self.act_add_folder)
            menu_file.addSeparator()
            menu_file.addAction(self.act_save_log)
            menu_file.addAction(self.act_quit)
            self.menu_file = menu_file

            menu_tools = self.menuBar().addMenu(settings.t("menu_tools"))
            menu_tools.addAction(self.act_generate)
            menu_tools.addAction(self.act_pack)
            menu_tools.addAction(self.act_unpack)
            menu_tools.addAction(self.act_hash)
            menu_tools.addAction(self.act_test)
            menu_tools.addSeparator()
            self.act_open_generated = QAction(settings.t("open_in_editor"), self)
            self.act_open_generated.setShortcut(QKeySequence("Ctrl+R"))
            self.act_open_generated.triggered.connect(self.open_generated)
            menu_tools.addAction(self.act_open_generated)
            self.menu_tools = menu_tools

            menu_view = self.menuBar().addMenu(settings.t("menu_view"))
            self.act_clear_log_2 = menu_view.addAction(self.act_clear_log)
            self.menu_view = menu_view
            lang_group = QActionGroup(self)
            self.lang_actions = {}
            for code in ("pl", "en"):
                act = QAction(code.upper(), self, checkable=True)
                act.setChecked(settings.language == code)
                act.triggered.connect(lambda _checked=False, c=code: self.set_language(c))
                lang_group.addAction(act)
                menu_view.addAction(act)
                self.lang_actions[code] = act

            menu_help = self.menuBar().addMenu(settings.t("menu_help"))
            self.act_shortcuts = QAction(settings.t("shortcut_help_title"), self)
            self.act_shortcuts.setShortcut(QKeySequence("F1"))
            self.act_shortcuts.triggered.connect(lambda: ShortcutsDialog(self).exec())
            menu_help.addAction(self.act_shortcuts)
            menu_help.addSeparator()
            self.act_about = QAction(settings.t("about"), self)
            self.act_about.triggered.connect(lambda: AboutDialog(self).exec())
            menu_help.addAction(self.act_about)
            self.menu_help = menu_help

            for index in range(5):
                shortcut = QShortcut(QKeySequence("Ctrl+%d" % (index + 1)), self)
                shortcut.activated.connect(lambda i=index: self.tabs.setCurrentIndex(i))
            QShortcut(QKeySequence(Qt.Key.Key_Delete), self.pack_list).activated.connect(
                self.remove_pack_items)

        def connect_signals(self):
            self.lang_combo.currentIndexChanged.connect(
                lambda _i: self.set_language(self.lang_combo.currentData()))
            self.theme_check.toggled.connect(self.on_theme_toggled)
            self.modal_check.toggled.connect(self.on_modal_toggled)
            self.default_dir_row.pathChanged.connect(self._on_default_dir_changed)
            self.zoom_spin.valueChanged.connect(self.on_zoom_changed)

        # -----------------------------------------------------------------
        #  Jezyk / motyw / pomoc
        # -----------------------------------------------------------------
        def set_language(self, code: str):
            if code not in LANG:
                return
            for action in self.lang_actions.values():
                action.setChecked(action.text().lower() == code)
            settings.language = code
            index = self.lang_combo.findData(code)
            if index != self.lang_combo.currentIndex():
                self.lang_combo.blockSignals(True)
                self.lang_combo.setCurrentIndex(index)
                self.lang_combo.blockSignals(False)
            self.refresh_language()

        def _apply_retranslate(self):
            for index in range(5):
                self.tabs.setTabText(index, settings.t([
                    "tab_generate", "tab_pack", "tab_unpack", "tab_security", "tab_settings"][index]))
            self.gen_folder_row.label.setText(settings.t("output_folder"))
            self.gen_code_label.setText(settings.t("code_area"))
            self.pack_summary.setText(self.pack_summary.text())
            self.archive_contents_label.setText(settings.t("archive_contents"))
            self.zoom_label.setText(settings.t("font_size"))
            self.unpack_archive_row.label.setText(settings.t("select_archive"))
            self.unpack_output_row.label.setText(settings.t("extract_to"))
            self.sec_file_row.label.setText(settings.t("hash_file"))
            self.pfa_file_row.label.setText(settings.t("pfa_file"))
            self.pfa_files_row.label.setText(settings.t("select_files"))
            self.default_dir_row.label.setText(settings.t("appearance_default_dir"))
            self.btn_load_archive.setText(settings.t("load_archive"))
            self.btn_test_archive.setText(settings.t("verify_archive"))
            self.btn_unpack_all.setText(settings.t("extract_all"))
            self.btn_unpack_selected.setText(settings.t("extract_selected"))
            self.btn_archive_info.setText(settings.t("info_title"))
            self.btn_add_files.setText(settings.t("add_files"))
            self.btn_add_folder.setText(settings.t("add_folder"))
            self.btn_remove.setText(settings.t("remove"))
            self.btn_clear_items.setText(settings.t("clear"))
            self.btn_pack.setText(settings.t("create_archive"))
            self.pack_append_check.setText(settings.t("add_to_archive"))
            self.pack_follow_check.setText(settings.t("follow_symlinks"))
            self.pack_skip_hidden.setText(settings.t("scan_hidden"))
            self.pack_keep_rel.setText(settings.t("include_root"))
            self.unpack_overwrite_check.setText(settings.t("overwrite_existing"))
            self.btn_hash.setText(settings.t("hash_file"))
            self.btn_hash_dir.setText(settings.t("hash_multi"))
            self.btn_pfa_create.setText(settings.t("pfa_create"))
            self.btn_pfa_unpack.setText(settings.t("pfa_unpack"))
            self.btn_pfa_verify.setText(settings.t("verify_archive"))
            self.btn_inspect.setText(settings.t("inspect"))
            self.btn_open_generated.setText(settings.t("open_in_editor"))
            self.btn_reveal_generated.setText(settings.t("cmd_reveal"))
            self.btn_copy_hash.setText(settings.t("copy"))
            self.btn_save_hash.setText(settings.t("save"))
            self.btn_select_all.setText(settings.t("select_all"))
            self.btn_select_none.setText(settings.t("select_none"))
            self.theme_check.setText(settings.t("appearance_qss"))
            self.modal_check.setText(settings.t("modal_dialogs"))
            self.btn_shortcuts.setText(settings.t("shortcut_help_title"))
            self.btn_settings_path.setText(settings.t("settings_path"))
            self.btn_save_settings.setText(settings.t("save_settings"))
            self.btn_open_log_folder.setText(settings.t("open_folder"))
            self.btn_clear_log.setText(settings.t("clear_log"))
            self.btn_save_log.setText(settings.t("save_log"))
            self.pack_filter_edit.setPlaceholderText(settings.t("pattern_help"))
            self.unpack_filter_edit.setPlaceholderText(settings.t("filter"))
            self.gen_code_edit.setPlaceholderText(settings.t("code_area"))
            self.about_label.setText(settings.t("about_text").format(
                name=__app_name__, ver=__version__, py=sys.version.split()[0],
                qt=QT_VERSION, platform=sys.platform))
            self.unpack_archive_row.button.setIcon(build_icon("search"))

        def refresh_language(self):
            self.setWindowTitle(settings.t("app_title"))
            self._title_label.setText(settings.t("app_title"))
            self.menu_file.setTitle(settings.t("menu_file"))
            self.menu_tools.setTitle(settings.t("menu_tools"))
            self.menu_view.setTitle(settings.t("menu_view"))
            self.menu_help.setTitle(settings.t("menu_help"))
            self.act_shortcuts.setText(settings.t("shortcut_help_title"))
            self.act_about.setText(settings.t("about"))
            self.act_add_files.setText(settings.t("add_files"))
            self.act_add_folder.setText(settings.t("add_folder"))
            self.act_pack.setText(settings.t("create_archive"))
            self.act_unpack.setText(settings.t("extract_all"))
            self.act_generate.setText(settings.t("group_generator"))
            self.act_hash.setText(settings.t("hash_file"))
            self.act_test.setText(settings.t("verify_archive"))
            self.act_clear_log.setText(settings.t("clear_log"))
            self.act_save_log.setText(settings.t("save_log"))
            self.act_quit.setText(settings.t("quit"))
            self.act_open_generated.setText(settings.t("open_in_editor"))
            self._apply_retranslate()
            self.update_pack_summary()
            self.update_archive_info_label()

        def on_theme_toggled(self, enabled: bool):
            settings.dark_theme = bool(enabled)
            self.apply_theme()

        def on_modal_toggled(self, enabled: bool):
            settings.modal_dialogs = bool(enabled)

        def apply_theme(self):
            self.setStyleSheet(load_stylesheet() if settings.dark_theme else "")

        def _on_default_dir_changed(self, value: str):
            settings.default_dir = value

        def on_zoom_changed(self, size: int):
            font = self.font()
            font.setPointSize(int(size))
            self.setFont(font)

        def show_settings_path(self):
            QMessageBox.information(self, settings.t("settings_path"),
                                    "%s\n\n%s" % (settings.path, settings.t("save_settings")))

        def save_settings(self):
            settings.dark_theme = self.theme_check.isChecked()
            settings.default_dir = self.default_dir_row.text()
            settings.language = settings.language
            if settings.save():
                self.log(settings.t("save_settings") + ": " + settings.path)
            else:
                self.log(settings.t("error") + ": " + settings.path)

        # -----------------------------------------------------------------
        #  Log i status
        # -----------------------------------------------------------------
        def log(self, message: str):
            self.logger.log(message)

        def clear_log(self):
            self.logger.clear()
            self.log_widget.clear()

        def save_log(self):
            path, _ = QFileDialog.getSaveFileName(
                self, settings.t("save_log"),
                os.path.join(settings.default_dir or os.path.expanduser("~"), "zipps-log.txt"),
                "Text (*.txt);;All (*)")
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.log_widget.toPlainText())
                self.log(settings.t("save") + ": " + path)
            except OSError as ex:
                self.log(settings.t("error") + ": " + str(ex))

        def set_status(self, text: str):
            self.status_label.setText(text)

        def open_path(self, path: str):
            if not path or not os.path.exists(path):
                return
            try:
                if os.name == "nt":
                    os.startfile(path)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            except OSError as ex:
                self.log(settings.t("error") + ": " + str(ex))

        # -----------------------------------------------------------------
        #  Drag and drop na oknie glownym
        # -----------------------------------------------------------------
        def dragEnterEvent(self, event: QDragEnterEvent):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                super().dragEnterEvent(event)

        def dropEvent(self, event: QDropEvent):
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
            if not paths:
                return
            event.acceptProposedAction()
            self.handle_dropped_paths(paths)

        def handle_dropped_paths(self, paths):
            files = [p for p in paths if os.path.isfile(p)]
            folders = [p for p in paths if os.path.isdir(p)]
            archives = [p for p in files if p.lower().endswith(ARCHIVE_EXTS)]
            plain = [p for p in files if p not in archives]

            if plain or folders:
                self.add_pack_items(plain + folders)
                self.tabs.setCurrentIndex(1)
            if archives:
                self.unpack_archive_edit.setText(archives[0])
                self.on_archive_dropped([archives[0]])
                if not plain and not folders:
                    self.tabs.setCurrentIndex(2)

        # -----------------------------------------------------------------
        #  Generator - akcje
        # -----------------------------------------------------------------
        def _gen_folder(self) -> str:
            folder = self.gen_folder_row.text()
            if not folder:
                folder = settings.default_dir or os.path.expanduser("~")
                self.gen_folder_row.set_text(folder)
            return folder

        def _report_generated(self, path: str):
            self.last_generated = path
            self.progress_bar.setValue(100)
            self.set_status(settings.t("done", os.path.basename(path)))
            self._update_generated_buttons()

        def _update_generated_buttons(self):
            has_file = bool(self.last_generated) and os.path.exists(self.last_generated)
            self.btn_open_generated.setEnabled(has_file)
            self.btn_reveal_generated.setEnabled(has_file)

        def open_generated(self):
            """Otwiera ostatnio wygenerowany plik w domyslnej aplikacji."""
            if self.last_generated and os.path.exists(self.last_generated):
                self.open_path(self.last_generated)
            else:
                self.log(settings.t("error") + ": " + settings.t("file_not_exist"))

        def reveal_generated(self):
            """Pokazuje ostatnio wygenerowany plik w Eksploratorze."""
            if self.last_generated and os.path.exists(self.last_generated):
                self.reveal_in_explorer(self.last_generated)
            else:
                self.log(settings.t("error") + ": " + settings.t("file_not_exist"))

        def do_generate_text(self):
            self._guard(self._do_generate_text)

        def _do_generate_text(self):
            try:
                path = self.generator.generate_text_file(
                    self._gen_folder(), self.gen_name_edit.text(), self.gen_ext_edit.text(),
                    self.gen_code_edit.toPlainText())
                self._report_generated(path)
            except (OSError, PackerError) as ex:
                self.log(settings.t("error") + ": " + str(ex))

        def do_generate_bin(self):
            def run():
                try:
                    path = self.generator.generate_binary_file(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_ext_edit.text() or "bin", self.gen_size_spin.value())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_pyc(self):
            def run():
                try:
                    path = self.generator.generate_pyc(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_code_edit.toPlainText(), self.gen_keep_source.isChecked())
                    self._report_generated(path)
                except (OSError, PackerError, py_compile.PyCompileError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_script(self):
            def run():
                try:
                    path = self.generator.generate_python_script(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_code_edit.toPlainText())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_c(self):
            def run():
                try:
                    path = self.generator.generate_c_file(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_code_edit.toPlainText())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_cpp(self):
            def run():
                try:
                    path = self.generator.generate_cpp_file(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_code_edit.toPlainText())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_raw(self):
            def run():
                try:
                    path = self.generator.generate_raw_image(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_width_spin.value(), self.gen_height_spin.value(),
                        self.gen_pattern_combo.currentData())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_json(self):
            def run():
                try:
                    path = self.generator.generate_json_file(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_code_edit.toPlainText())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_markdown(self):
            def run():
                try:
                    path = self.generator.generate_markdown_file(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_code_edit.toPlainText())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        # -----------------------------------------------------------------
        #  Wspolne: ochrona przed rownoleglymi operacjami
        # -----------------------------------------------------------------
        def is_busy(self) -> bool:
            return self.worker is not None and self.worker.isRunning()

        def _guard(self, func) -> bool:
            if self.is_busy():
                self.log(settings.t("busy"))
                return False
            func()
            return True

        def run_worker(self, worker: BaseWorker, on_result, start_text: str,
                       status_key: str = "status_working") -> BaseWorker:
            """Uruchamia watek roboczy i podlacza sygnaly do GUI."""
            self.worker = worker
            self.workers.append(worker)
            self.progress_bar.setValue(0)
            self.set_status(settings.t(status_key))
            self.overlay.start(start_text)
            worker.signals.progress.connect(self.progress_bar.setValue)
            worker.signals.progress_text.connect(self.overlay.update_progress)
            worker.signals.result.connect(on_result)
            worker.signals.error.connect(self.on_worker_error)
            worker.signals.finished.connect(self.on_worker_finished)
            worker.start()
            return worker

        def cancel_operation(self):
            if self.worker is not None:
                self.worker.cancel()
                self.log(settings.t("cancelled"))

        def on_worker_error(self, message: str):
            self.log(settings.t("error") + ": " + message)
            self.set_status(settings.t("status_error"))
            if message == settings.t("need_password") or "haslo" in message.lower():
                self._ask_for_password_hint()

        def _ask_for_password_hint(self):
            self.log(settings.t("need_password"))

        def on_worker_finished(self):
            self.overlay.stop()
            if self.worker is not None and self.worker in self.workers:
                self.workers.remove(self.worker)
            self.worker = None
            if self.progress_bar.value() < 100:
                self.progress_bar.setValue(0)
            # komunikaty zebrane w trakcie pracy watku pokazujemy po jego konczeniu
            if self.idle_dialogs:
                QTimer.singleShot(0, self.flush_dialogs)

        # -----------------------------------------------------------------
        #  Pakowanie - lista plikow
        # -----------------------------------------------------------------
        def pick_pack_items(self):
            start = settings.default_dir or os.path.expanduser("~")
            files, _ = QFileDialog.getOpenFileNames(self, settings.t("add_files"), start)
            if files:
                self.add_pack_items(files)

        def add_pack_folder(self):
            start = settings.default_dir or os.path.expanduser("~")
            folder = QFileDialog.getExistingDirectory(self, settings.t("add_folder"), start)
            if folder:
                self.add_pack_items([folder])

        def _parse_patterns(self) -> list:
            raw = self.pack_filter_edit.text().strip()
            if not raw:
                return None
            patterns = []
            for part in raw.replace(",", ";").split(";"):
                part = part.strip().lower()
                if not part:
                    continue
                if "*" not in part:
                    part = "*" + (part if part.startswith(".") else "*" + part)
                patterns.append(part)
            return patterns

        def add_pack_items(self, paths):
            paths = [p for p in paths if p]
            for path in paths:
                if settings.default_dir == "" and path:
                    settings.default_dir = path if os.path.isdir(path) else os.path.dirname(path)
            folders = [p for p in paths if os.path.isdir(p)]
            direct_files = [p for p in paths if os.path.isfile(p)]
            collected = self.packer.collect_files(
                direct_files, folders, self._parse_patterns(),
                self.pack_skip_hidden.isChecked(), self.pack_follow_check.isChecked(),
                logger=self.logger)
            known = {item for item in self.pack_items}
            added = 0
            for path in collected:
                if path in known:
                    continue
                known.add(path)
                self.pack_items.append(path)
                item = QListWidgetItem(self._decorate_item(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                self.pack_list.addItem(item)
                added += 1
            self.log("%s: %d" % (settings.t("add_files"), added))
            self.update_pack_summary()
            self.auto_suggest_archive()

        @staticmethod
        def _decorate_item(path: str) -> str:
            try:
                size = human_size(os.path.getsize(path))
            except OSError:
                size = "?"
            return "%s    (%s)" % (os.path.basename(path), size)

        def remove_pack_items(self):
            rows = sorted({self.pack_list.row(i) for i in self.pack_list.selectedItems()},
                          reverse=True)
            if not rows:
                return
            for row in rows:
                item = self.pack_list.takeItem(row)
                path = item.data(Qt.ItemDataRole.UserRole)
                if path in self.pack_items:
                    self.pack_items.remove(path)
            self.update_pack_summary()

        def clear_pack_items(self):
            self.pack_list.clear()
            self.pack_items.clear()
            self.update_pack_summary()

        def update_pack_summary(self):
            total = 0
            for path in self.pack_items:
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
            text = settings.t("items_count", len(self.pack_items), human_size(total))
            self.pack_summary.setText(text)
            selected = len(self.pack_list.selectedItems())
            if selected:
                self.pack_summary.setText(text + " | %s: %d" % (settings.t("result"), selected))

        def pack_list_menu(self, position):
            menu = QMenu(self)
            act_remove = menu.addAction(build_icon("remove"), settings.t("cmd_remove"))
            act_copy = menu.addAction(settings.t("cmd_copy_path"))
            act_reveal = menu.addAction(settings.t("cmd_reveal"))
            item = self.pack_list.itemAt(position)
            chosen = menu.exec(self.pack_list.mapToGlobal(position))
            if chosen is None or item is None:
                return
            path = item.data(Qt.ItemDataRole.UserRole)
            if chosen is act_remove:
                self.remove_pack_items()
            elif chosen is act_copy:
                QApplication.clipboard().setText(path)
            elif chosen is act_reveal:
                self.reveal_in_explorer(path)

        def reveal_in_explorer(self, path: str):
            """Pokazuje plik w Eksploratorze Windows (lub otwiera folder)."""
            try:
                if os.name == "nt":
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", path])
                else:
                    self.open_path(os.path.dirname(path))
            except OSError as ex:
                self.log(settings.t("error") + ": " + str(ex))

        def auto_suggest_archive(self, force: bool = False):
            if (self.pack_archive_edit.text().strip() and not force) or not self.pack_items:
                return
            base = settings.default_dir or os.path.dirname(self.pack_items[0])
            fmt = self.pack_format_combo.currentData() or "zip"
            self.pack_archive_edit.setText(os.path.join(base, "archive" + FORMAT_EXTS[fmt]))

        # -----------------------------------------------------------------
        #  Pakowanie - wykonanie
        # -----------------------------------------------------------------
        def _pack_options(self) -> dict:
            fmt = self.pack_format_combo.currentData()
            password = self.pack_password_edit.text() or None
            if password and password != self.pack_password2_edit.text():
                raise PackerError(settings.t("password_mismatch"))
            if fmt in ("tar", "targz", "tarbz2", "tarxz") and password:
                self.log("TAR: encryption not supported - archive will be stored unencrypted")
            bases = sorted({os.path.dirname(p) for p in self.pack_items},
                           key=len) or [settings.default_dir or os.getcwd()]
            level = self.pack_level_spin.value()
            return {
                "bases": bases,
                "keep_relative": self.pack_keep_rel.isChecked(),
                "password": password,
                "level": level,
                "compression": "stored" if level == 0 else "deflate",
                "append": self.pack_append_check.isChecked() and fmt == "zip",
            }

        def do_pack(self):
            def run():
                try:
                    options = self._pack_options()
                except PackerError as ex:
                    self.log(settings.t("error") + ": " + str(ex))
                    return
                if not self.pack_items:
                    self.log(settings.t("error") + ": " + settings.t("no_files"))
                    return
                fmt = self.pack_format_combo.currentData()
                archive_path = self.pack_archive_edit.text().strip()
                if not archive_path:
                    self.auto_suggest_archive(force=True)
                    archive_path = self.pack_archive_edit.text().strip()
                archive_path = ensure_archive_ext(os.path.expanduser(archive_path), fmt)
                self.pack_archive_edit.setText(archive_path)
                if fmt == "zip" and options.get("append"):
                    if not os.path.exists(archive_path):
                        self.log("ZIP: append requested but archive does not exist - creating new")
                        options["append"] = False
                settings.compression_level = self.pack_level_spin.value()
                settings.keep_relative = self.pack_keep_rel.isChecked()
                settings.follow_symlinks = self.pack_follow_check.isChecked()
                settings.last_format = fmt
                settings.save()
                worker = PackWorker(self.packer, list(self.pack_items), fmt, archive_path,
                                    options, self)
                self.run_worker(worker, self._on_pack_done, settings.t("status_packing"),
                                "status_packing")
            self._guard(run)

        def _on_pack_done(self, result):
            if result is None:
                return
            self.log("%s%s | %d -> %s | -%0.1f%%" % (
                settings.t("total_size"), "", result.entries, human_size(result.size_after),
                result.ratio))
            self.set_status(settings.t("done", os.path.basename(result.path)))
            self.progress_bar.setValue(100)
            if os.path.exists(result.path):
                self.unpack_archive_edit.setText(result.path)

        # -----------------------------------------------------------------
        #  Rozpakowywanie
        # -----------------------------------------------------------------
        def _password_for(self) -> str | None:
            return self.unpack_password_edit.text() or None

        def load_archive_contents(self):
            path = self.unpack_archive_row.text()
            if not path:
                self.log(settings.t("error") + ": " + settings.t("select_archive"))
                return
            if not os.path.exists(path):
                self.log(settings.t("error") + ": " + settings.t("file_not_exist"))
                return
            if not self.unpack_output_folder_edit.text().strip():
                self.on_archive_dropped([path])
            worker = ListWorker(self.unpacker, path, self._password_for(), self)
            worker.signals.result.connect(self._fill_archive_list)
            worker.signals.error.connect(self.on_worker_error)
            self.run_worker(worker, lambda _r: None, "%s: %s" % (
                settings.t("load_archive"), os.path.basename(path)))

        def _fill_archive_list(self, payload):
            entries, fmt = payload
            self.archive_entries = entries
            self.archive_fmt = fmt
            self.unpack_list_widget.setSortingEnabled(False)
            self.unpack_list_widget.clear()
            self.archive_status_label.setText("")
            for entry in entries:
                text = "%s    (%s)" % (entry["name"], human_size(entry["size"]))
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, entry["name"])
                item.setToolTip(entry["name"])
                if not entry.get("encrypted"):
                    pass
                self.unpack_list_widget.addItem(item)
            self.unpack_list_widget.setSortingEnabled(True)
            self.update_archive_info_label()
            self.log("%s: %d (%s)" % (settings.t("archive_contents"), len(entries), fmt.upper()))
            self.progress_bar.setValue(100)
            self.set_status(settings.t("done", fmt.upper()))

        def update_archive_info_label(self):
            if not self.archive_entries:
                self.archive_info_label.setText("")
                return
            total = sum(e["size"] for e in self.archive_entries)
            encrypted = any(e.get("encrypted") for e in self.archive_entries)
            self.archive_info_label.setText("%s | %s: %d | %s: %s%s" % (
                self.archive_fmt.upper(), settings.t("files"), len(self.archive_entries),
                settings.t("total_size"), human_size(total),
                " | AES-256" if encrypted else ""))

        def filter_archive_entries(self, text: str):
            needle = (text or "").lower()
            for row in range(self.unpack_list_widget.count()):
                item = self.unpack_list_widget.item(row)
                item.setHidden(bool(needle) and needle not in item.text().lower())

        def select_all_entries(self):
            for row in range(self.unpack_list_widget.count()):
                item = self.unpack_list_widget.item(row)
                if not item.isHidden():
                    item.setSelected(True)

        def _get_selected_entries(self):
            selected_items = self.unpack_list_widget.selectedItems()
            if not selected_items:
                return None
            return [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]

        def do_unpack_all(self):
            self._start_unpack(selected=None)

        def do_unpack_selected(self):
            def run():
                selected = self._get_selected_entries()
                if not selected:
                    self.log(settings.t("error") + ": " + settings.t("extract_selected"))
                    return
                self._start_unpack(selected=selected)
            self._guard(run)

        def _start_unpack(self, selected=None):
            if self.is_busy():
                self.log(settings.t("busy"))
                return
            archive_path = self.unpack_archive_row.text()
            output_folder = self.unpack_output_row.text()
            if not archive_path:
                self.log(settings.t("error") + ": " + settings.t("select_archive"))
                return
            if not output_folder:
                self.log(settings.t("error") + ": " + settings.t("output_folder"))
                return
            os.makedirs(output_folder, exist_ok=True)
            settings.default_dir = output_folder
            worker = UnpackWorker(self.unpacker, archive_path, output_folder, selected,
                                  password=self._password_for(),
                                  overwrite=self.unpack_overwrite_check.isChecked(), parent=self)
            self.run_worker(worker, self._on_unpack_done, settings.t("status_unpacking"),
                            "status_unpacking")

        def _on_unpack_done(self, result):
            if result is None:
                return
            self.progress_bar.setValue(100)
            self.set_status(settings.t("done", result.output_folder))
            if result.blocked:
                self.log("%s: %d" % (settings.t("error"), len(result.blocked)))
            self.log("%s: %d | %s" % (settings.t("files"), result.extracted,
                                      human_size(result.bytes_written)))

        def test_archive(self):
            def run():
                path = self.unpack_archive_row.text()
                if not path:
                    path = self.unpack_archive_row.text()
                if not path:
                    self.log(settings.t("error") + ": " + settings.t("select_archive"))
                    return
                worker = TestArchiveWorker(self.unpacker, path,
                                           self._password_for(), self)
                self.run_worker(worker, self._on_test_done, settings.t("status_testing"),
                                "status_testing")
            self._guard(run)

        def _on_test_done(self, payload):
            ok, problem, count = payload
            if ok:
                message = settings.t("archive_ok", count, "OK")
                self.log(message)
                self.set_status(settings.t("status_done"))
                self.set_archive_size(count, human_size(self._archive_size_bytes()))
                self.idle_dialogs.append(("success", settings.t("group_archive_tools"), message))
            else:
                message = settings.t("archive_damaged", problem)
                self.log(message)
                self.set_status(settings.t("status_error"))
                self.idle_dialogs.append(("error", settings.t("group_archive_tools"), message))
            self.flush_dialogs()

        def _archive_size_bytes(self) -> int:
            try:
                return os.path.getsize(self.unpack_archive_row.text())
            except OSError:
                return 0

        def set_archive_size(self, count: int, size_text: str):
            """Dopisuje do etykiety archiwum skrot i czas weryfikacji."""
            self.archive_status_label.setText("%s: %d | %s | %s" % (
                settings.t("files"), count, size_text,
                datetime.now().strftime("%H:%M:%S")))

        # -- okna komunikatow (domyslnie modalne, opcjonalnie w logu) ------
        def queue_dialog(self, kind: str, title: str, message: str):
            """Kolejkuje komunikat; pokazuje go zaraz po zakonczeniu watku."""
            self.idle_dialogs.append((kind, title, message))
            if not self.is_busy():
                self.flush_dialogs()

        def flush_dialogs(self):
            if self.is_busy():
                return
            pending, self.idle_dialogs = self.idle_dialogs, []
            for kind, title, message in pending:
                if settings.modal_dialogs:
                    if kind == "error":
                        QMessageBox.warning(self, title, message)
                    else:
                        QMessageBox.information(self, title, message)
                else:
                    self.notify.notify(title, message, kind)

        def _drain_pending_dialogs(self):
            self.flush_dialogs()

        def show_archive_info(self):
            path = self.unpack_archive_row.text()
            if not path or not os.path.exists(path):
                self.log(settings.t("error") + ": " + settings.t("select_archive"))
                return
            try:
                entries, fmt = self.unpacker.entries(path, self._password_for())
            except PackerError as ex:
                self.log(settings.t("error") + ": " + str(ex))
                return
            ArchiveTreeDialog(path, entries, fmt, self).exec()

        # -----------------------------------------------------------------
        #  Bezpieczenstwo
        # -----------------------------------------------------------------
        def _hash_target(self) -> str:
            return self.sec_file_row.text()

        def do_hash_file(self):
            def run():
                path = self._hash_target()
                if not os.path.isfile(path):
                    self.log(settings.t("error") + ": " + settings.t("file_not_exist"))
                    return
                worker = HashWorker(self.security, path, self.sec_algo_combo.currentData(),
                                    "file", self)
                self.run_worker(worker, self._on_hash_done, settings.t("status_hashing"),
                                "status_hashing")
            self._guard(run)

        def do_hash_dir(self):
            def run():
                folder = os.path.dirname(self._hash_target()) if os.path.isfile(
                    self._hash_target()) else self._hash_target()
                if not folder or not os.path.isdir(folder):
                    folder = QFileDialog.getExistingDirectory(
                        self, settings.t("hash_multi"), settings.default_dir or "")
                if not folder:
                    return
                worker = HashWorker(self.security, folder,
                                    self.sec_algo_combo.currentData(), "dir", self)
                self.run_worker(worker, self._on_hash_dir_done, settings.t("status_hashing"),
                                "status_hashing")
            self._guard(run)

        def do_crc_file(self):
            def run():
                path = self._hash_target()
                if not os.path.isfile(path):
                    self.log(settings.t("error") + ": " + settings.t("file_not_exist"))
                    return
                value = self.security.crc32_file(path)
                self.sec_result_edit.setText(value)
                self.update_hash_compare()
            self._guard(run)

        def do_hash_archive(self):
            def run():
                path = self.unpack_archive_row.text()
                if not path or not os.path.exists(path):
                    self.log(settings.t("error") + ": " + settings.t("select_archive"))
                    return
                worker = HashWorker(self.security, path,
                                    self.sec_algo_combo.currentData(), "archive", self)
                self.run_worker(worker, self._on_hash_dir_done, settings.t("status_hashing"),
                                "status_hashing")
            self._guard(run)

        def _on_hash_done(self, digest):
            self.sec_result_edit.setText(digest)
            self.update_hash_compare()
            self.progress_bar.setValue(100)

        def _on_hash_dir_done(self, mapping):
            self.progress_bar.setValue(100)
            if isinstance(mapping, dict):
                lines = ["%s  %s" % (value, name) for name, value in sorted(mapping.items())]
                self.log("\n".join(lines[:200]))
                self.log("%s: %d" % (settings.t("files"), len(mapping)))

        def update_hash_compare(self):
            expected = self.sec_expected_edit.text().strip()
            actual = self.sec_result_edit.text().strip()
            if not expected or not actual:
                self.sec_compare_label.setText("")
                return
            if SecurityCore.compare(expected, actual):
                self.sec_compare_label.setText(settings.t("hash_match"))
                self.sec_compare_label.setStyleSheet("color:#89d185;")
            else:
                self.sec_compare_label.setText(settings.t("hash_mismatch"))
                self.sec_compare_label.setStyleSheet("color:#f48771;")

        def save_hash_results(self):
            path, _ = QFileDialog.getSaveFileName(
                self, settings.t("save"),
                os.path.join(settings.default_dir or os.path.expanduser("~"),
                             "hashes.sha256"), "Text (*.txt *.sha256);;All (*)")
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.log_widget.toPlainText())
                self.log(settings.t("save") + ": " + path)
            except OSError as ex:
                self.log(settings.t("error") + ": " + str(ex))

        def inspect_file(self):
            path = self._hash_target()
            if not os.path.isfile(path):
                self.log(settings.t("error") + ": " + settings.t("file_not_exist"))
                return
            try:
                info = file_info(path)
            except OSError as ex:
                self.log(settings.t("error") + ": " + str(ex))
                return
            lines = [
                "%s: %s" % (settings.t("file_name"), info["name"]),
                "%s: %s (%d B)" % (settings.t("total_size"), info["size_human"], info["size"]),
                "Type: %s" % info["type"],
                "SHA-256: %s" % info.get("sha256", "-"),
                "CRC32: %s" % info.get("crc32", "-"),
            ]
            if path.lower().endswith((".pyc", ".pyo")):
                try:
                    pyc = describe_pyc(path)
                    lines.append("Magic: %s" % pyc.get("magic"))
                    lines.append("Python: %s" % pyc.get("python"))
                    lines.append("Compatible: %s" % pyc.get("compatible"))
                    if "source_hash" in pyc:
                        lines.append("Source hash: %s" % pyc["source_hash"])
                    if "mtime" in pyc:
                        lines.append("Source mtime: %s" % pyc["mtime"])
                    disasm = self._disassemble_pyc(path)
                    if disasm:
                        lines.append("\n" + disasm)
                except Exception as ex:  # noqa: BLE001
                    lines.append("Pyc error: %s" % ex)
            if info.get("preview"):
                lines.append("\n--- preview ---\n" + info["preview"][:2000])
            QMessageBox.information(self, settings.t("info_title"), "\n".join(lines))

        @staticmethod
        def _disassemble_pyc(path: str) -> str:
            """Podglad instrukcji bajtowych pliku .pyc (bez uruchamiania kodu)."""
            try:
                import dis
                import marshal
                import importlib.util
                with open(path, "rb") as f:
                    data = f.read()
                header = 16 if importlib.util.MAGIC_NUMBER == data[:4] else 12
                code = marshal.loads(data[header:])
                import io
                out = io.StringIO()
                dis.dis(code, file=out)
                return out.getvalue()[:4000]
            except Exception:
                return ""

        # -----------------------------------------------------------------
        #  PFA (wlasne archiwum)
        # -----------------------------------------------------------------
        def _pfa_password(self) -> str | None:
            return self.pfa_password_edit.text() or None

        def do_pfa_create(self):
            def run():
                files = []
                current = self.pfa_files_row.text()
                if current:
                    files = [p.strip() for p in current.split(";") if p.strip()]
                if not files:
                    files = list(self.pack_items)
                if not files:
                    chosen, _ = QFileDialog.getOpenFileNames(
                        self, settings.t("select_files"), settings.default_dir or "")
                    files = chosen
                if not files:
                    self.log(settings.t("error") + ": " + settings.t("no_files"))
                    return
                target = self.pfa_file_row.text().strip()
                if not target:
                    base_dir = settings.default_dir or os.path.dirname(files[0]) or os.getcwd()
                    target, _ = QFileDialog.getSaveFileName(
                        self, settings.t("pfa_create"),
                        os.path.join(base_dir, "archive.pfa"),
                        "PFA (*.pfa);;All (*)")
                    if not target:
                        # uzytkownik anulowal okno wyboru - zapisujemy obok plikow
                        target = os.path.join(base_dir, "archive.pfa")
                target = os.path.abspath(target)
                target = ensure_archive_ext(target, "pfa")
                self.pfa_file_row.set_text(target)
                worker = PackWorker(self.pfa, [f.strip().strip('"') for f in files], "pfa",
                                    target, {"password": self._pfa_password(),
                                             "bases": [os.path.dirname(os.path.abspath(
                                                 f.strip().strip('"'))) for f in files]},
                                    self)
                self.run_worker(worker, self._on_pack_done, settings.t("status_packing"),
                                "status_packing")
            self._guard(run)

        def do_pfa_unpack(self):
            def run():
                archive_path = self.pfa_file_row.text()
                if not archive_path or not os.path.exists(archive_path):
                    self.log(settings.t("error") + ": " + settings.t("pfa_file"))
                    return
                output_folder = self.unpack_output_row.text()
                if not output_folder:
                    output_folder = os.path.splitext(archive_path)[0]
                    self.unpack_output_row.set_text(output_folder)
                os.makedirs(output_folder, exist_ok=True)
                worker = UnpackWorker(self.pfa, archive_path, output_folder, None,
                                      password=self._pfa_password(),
                                      overwrite=self.unpack_overwrite_check.isChecked(),
                                      parent=self)
                self.run_worker(worker, self._on_unpack_done, settings.t("status_unpacking"),
                                "status_unpacking")
            self._guard(run)

        def do_pfa_verify(self):
            def run():
                archive_path = self.pfa_file_row.text()
                if not archive_path or not os.path.exists(archive_path):
                    self.log(settings.t("error") + ": " + settings.t("pfa_file"))
                    return
                worker = TestArchiveWorker(self.unpacker, archive_path,
                                           self._pfa_password(), self)
                self.run_worker(worker, self._on_test_done, settings.t("status_testing"),
                                "status_testing")
            self._guard(run)

        # -----------------------------------------------------------------
        #  Zamkniecie aplikacji
        # -----------------------------------------------------------------
        def closeEvent(self, event):
            if self.is_busy():
                answer = QMessageBox.question(
                    self, settings.t("app_title"), settings.t("status_working"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
                for worker in list(self.workers):
                    worker.cancel()
                    worker.wait(3000)
                    worker.deleteLater()
                self.workers.clear()
            settings.dark_theme = self.theme_check.isChecked()
            settings.default_dir = self.default_dir_row.text() or settings.default_dir
            settings.save()
            event.accept()


# =====================================================================
#  Interfejs wiersza polecen (CLI)
# =====================================================================

def _cli_progress(percent: int, message: str = ""):
    width = 28
    filled = int(width * percent / 100)
    bar = "#" * filled + "-" * (width - filled)
    sys.stdout.write("\r[%s] %3d%% %s\033[K" % (bar, percent, message[:60]))
    sys.stdout.flush()
    if percent >= 100:
        sys.stdout.write("\n")


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ZIPps.py",
        description="%s v%s - generator plikow, pakowanie, rozpakowywanie i hashe." % (
            __app_name__, __version__),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Przyklady:\n"
            "  python ZIPps.py                     # uruchamia GUI\n"
            "  python ZIPps.py pack src -o out/backup.zip --format zip\n"
            "  python ZIPps.py pack a.txt b/ -o data.pfa --password secret\n"
            "  python ZIPps.py unpack out/backup.zip -d restored/\n"
            "  python ZIPps.py list out/backup.zip\n"
            "  python ZIPps.py hash file.bin --algo sha256\n"
            "  python ZIPps.py info file.bin\n"
        ))
    sub = parser.add_subparsers(dest="command")

    p_pack = sub.add_parser("pack", help="pakuj pliki/foldery do archiwum")
    p_pack.add_argument("paths", nargs="+", help="pliki i/lub foldery")
    p_pack.add_argument("-o", "--output", required=True, help="sciezka archiwum")
    p_pack.add_argument("-f", "--format", default=None,
                        choices=["zip", "tar", "targz", "tarbz2", "tarxz", "pfa"],
                        help="format (domyslnie z rozszerzenia)")
    p_pack.add_argument("--password", default=None, help="haslo (ZIP AES-256 / PFA)")
    p_pack.add_argument("--level", type=int, default=6, help="poziom kompresji 0-9")
    p_pack.add_argument("--filter", default=None, help="wzorce, np. '*.py;*.txt'")
    p_pack.add_argument("--flat", action="store_true", help="bez struktury folderow")
    p_pack.add_argument("--include-hidden", action="store_true")
    p_pack.add_argument("--append", action="store_true", help="dopisz do istniejacego ZIP")
    p_pack.add_argument("-q", "--quiet", action="store_true")

    p_unpack = sub.add_parser("unpack", help="rozpakuj archiwum")
    p_unpack.add_argument("archive", help="sciezka archiwum")
    p_unpack.add_argument("-d", "--dest", default=None, help="folder docelowy")
    p_unpack.add_argument("--password", default=None)
    p_unpack.add_argument("--only", nargs="+", default=None, help="wybrane wpisy")
    p_unpack.add_argument("--no-overwrite", action="store_true")
    p_unpack.add_argument("-q", "--quiet", action="store_true")

    p_list = sub.add_parser("list", help="lista zawartosci archiwum")
    p_list.add_argument("archive")
    p_list.add_argument("--password", default=None)
    p_list.add_argument("--json", action="store_true")

    p_hash = sub.add_parser("hash", help="policz sume kontrolna")
    p_hash.add_argument("path")
    p_hash.add_argument("-a", "--algo", default="sha256", choices=list(SUPPORTED_HASHES))
    p_hash.add_argument("--compare", default=None, help="oczekiwany hash")
    p_hash.add_argument("--csv", action="store_true", help="format 'hash *sciezka'")
    p_hash.add_argument("-q", "--quiet", action="store_true", help="tylko wynik")

    p_info = sub.add_parser("info", help="informacje o pliku")
    p_info.add_argument("path")
    p_info.add_argument("--json", action="store_true")

    p_test = sub.add_parser("test", help="test integralnosci archiwum")
    p_test.add_argument("archive")
    p_test.add_argument("--password", default=None)
    p_test.add_argument("-q", "--quiet", action="store_true")

    p_gen = sub.add_parser("gen", help="wygeneruj plik")
    p_gen.add_argument("kind", choices=["text", "bin", "pyc", "py", "c", "cpp", "raw",
                                        "json", "md"])
    p_gen.add_argument("name", help="nazwa pliku (bez rozszerzenia)")
    p_gen.add_argument("-d", "--dir", default=".")
    p_gen.add_argument("-s", "--size", type=int, default=1024, help="rozmiar bin / WxH")
    p_gen.add_argument("--height", type=int, default=None)
    p_gen.add_argument("--content", default="")

    p_gui = sub.add_parser("gui", help="uruchom interfejs graficzny")
    p_gui.add_argument("paths", nargs="*", help="pliki/foldery do wczytania")

    sub.add_parser("settings", help="pokaz sciezke pliku ustawien")
    return parser


def cli_cmd_settings(args, logger, progress) -> int:
    """Wypisz sciezke pliku ustawien."""
    print(settings.path)
    return 0


def cli_cmd_pack(args, logger, progress) -> int:
    """Pakowanie plikow i folderow do archiwum."""
    packer = PackerCore(logger)
    patterns = None
    if args.filter:
        patterns = [p.strip() for p in args.filter.replace(",", ";").split(";") if p.strip()]
    files = packer.collect_files(
        [p for p in args.paths if os.path.isfile(p)],
        [p for p in args.paths if os.path.isdir(p)],
        patterns, not args.include_hidden)
    if not files:
        print("No files to pack.", file=sys.stderr)
        return 2
    fmt = args.format or detect_format(args.output)
    if fmt == "unknown":
        fmt = "zip"
    bases = [p for p in args.paths if os.path.isdir(p)] or \
            sorted({os.path.dirname(f) for f in files}, key=len)
    result = packer.pack(files, args.output, fmt, progress_cb=progress,
                         bases=bases, keep_relative=not args.flat,
                         level=args.level, password=args.password,
                         append=args.append)
    print("%s: %s (%d entries, %s)" % (settings.t("packed"), result.path,
                                       result.entries, human_size(result.size_after)))
    return 0


def cli_cmd_unpack(args, logger, progress) -> int:
    """Rozpakowanie archiwum (format wykrywany automatycznie)."""
    unpacker = UnpackerCore(logger)
    dest = args.dest or os.path.splitext(os.path.basename(args.archive))[0] or "extracted"
    result = unpacker.unpack_auto(args.archive, dest, selected=args.only,
                                  progress_cb=progress, password=args.password,
                                  overwrite=not args.no_overwrite)
    print("%s: %s (%d files, blocked: %d)" % (settings.t("unpacked"), result.output_folder,
                                              result.extracted, len(result.blocked)))
    return 0


def cli_cmd_list(args, logger, progress) -> int:
    """Lista zawartosci archiwum (tekst lub JSON)."""
    unpacker = UnpackerCore(logger)
    entries, fmt = unpacker.entries(args.archive, args.password)
    if args.json:
        print(json.dumps(entries, indent=2, default=str))
        return 0
    print("%s: %s" % (fmt.upper(), args.archive))
    total = 0
    for entry in entries:
        total += entry["size"]
        flags = "E" if entry.get("encrypted") else " "
        print("%s %10s  %s" % (flags, human_size(entry["size"]), entry["name"]))
    print("%d entries, %s" % (len(entries), human_size(total)))
    return 0


def cli_cmd_hash(args, logger, progress) -> int:
    """Suma kontrolna pliku lub katalogu, opcjonalnie z porownaniem."""
    expected = (args.compare or "").strip()
    if args.compare is not None and not expected:
        print("Podany --compare jest pusty - nie ma czego porownywac.", file=sys.stderr)
        return 2
    if os.path.isdir(args.path):
        if expected:
            print("--compare dziala tylko dla pojedynczego pliku, nie dla katalogu: %s"
                  % args.path, file=sys.stderr)
            return 2
        security = SecurityCore(logger)
        mapping = security.hash_directory(args.path, args.algo)
        for name, value in sorted(mapping.items()):
            print("%s  %s%s%s" % (value, "*" if args.csv else "", name, "" if args.csv else "  "))
        return 0
    digest = hash_file(args.path, args.algo)
    print("%s  %s%s" % (digest, "*" if args.csv else "", args.path) if args.csv
          else "%s %s = %s" % (args.algo.upper(), args.path, digest))
    if expected:
        ok = SecurityCore.compare(expected, digest)
        print(settings.t("hash_match") if ok else settings.t("hash_mismatch"))
        return 0 if ok else 3
    return 0


def cli_cmd_info(args, logger, progress) -> int:
    """Informacje o pliku (wersja tekstowa lub JSON)."""
    data = file_info(args.path)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    for key, value in data.items():
        if key == "preview":
            continue
        print("%-10s %s" % (key + ":", value))
    return 0


def cli_cmd_test(args, logger, progress) -> int:
    """Test integralnosci archiwum."""
    unpacker = UnpackerCore(logger)
    ok, problem, count = unpacker.test_archive(args.archive, args.password,
                                               progress_cb=progress)
    if ok:
        print(settings.t("archive_ok", count, "OK"))
        return 0
    print(settings.t("archive_damaged", problem), file=sys.stderr)
    return 1


def cli_cmd_gen(args, logger, progress) -> int:
    """Generowanie przykladowego pliku wybranego rodzaju."""
    gen = FileGenerator(logger)
    kind = args.kind
    if kind == "text":
        print(gen.generate_text_file(args.dir, args.name, "txt",
                                     args.content or "Hello from ZIPps!\n"))
    elif kind == "bin":
        print(gen.generate_binary_file(args.dir, args.name, "bin", args.size))
    elif kind == "pyc":
        print(gen.generate_pyc(args.dir, args.name,
                               args.content or "print('Hello from .pyc')"))
    elif kind == "py":
        print(gen.generate_python_script(args.dir, args.name, args.content))
    elif kind == "c":
        print(gen.generate_c_file(args.dir, args.name, args.content))
    elif kind == "cpp":
        print(gen.generate_cpp_file(args.dir, args.name, args.content))
    elif kind == "raw":
        width = args.size
        height = args.height or args.size
        print(gen.generate_raw_image(args.dir, args.name, width, height))
    elif kind == "json":
        print(gen.generate_json_file(args.dir, args.name, args.content))
    elif kind == "md":
        print(gen.generate_markdown_file(args.dir, args.name, args.content))
    else:
        print("Nieznany rodzaj pliku: %s" % kind, file=sys.stderr)
        return 2
    return 0


#: mapa nazwa podkomendy -> funkcja obslugujaca (args, logger, progress) -> int
CLI_COMMANDS = {
    "pack": cli_cmd_pack,
    "unpack": cli_cmd_unpack,
    "list": cli_cmd_list,
    "hash": cli_cmd_hash,
    "info": cli_cmd_info,
    "test": cli_cmd_test,
    "gen": cli_cmd_gen,
    "settings": cli_cmd_settings,
}


def cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_cli_parser()
    args = parser.parse_args(argv)
    if args.command in (None, "gui"):
        return run_gui(getattr(args, "paths", []) or [])

    handler = CLI_COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    quiet = bool(getattr(args, "quiet", False))
    logger = Empty() if quiet else Logger()
    # w trybie -q nie rysujemy paska postepu (nie zasmieca wyjscia i logow)
    progress = None if quiet else _cli_progress
    return handler(args, logger, progress)


# =====================================================================
#  Uruchomienie GUI
# =====================================================================

def create_application(argv: Optional[Sequence[str]] = None):
    """Tworzy (lub zwraca istniejaca) aplikacje Qt; wymaga dostepnego PySide6."""
    require_qt()
    app = QApplication.instance() or QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ZIPps")
    if settings.dark_theme:
        try:
            app.setStyle("Fusion")
        except Exception as ex:  # noqa: BLE001 - styl to opcja, nie krytyczna funkcja
            Logger().error("Nie udalo sie ustawic stylu Fusion: %s" % ex)
        # arkusz stylow wczytywany dopiero przy starcie GUI (nie przy imporcie)
        stylesheet = load_stylesheet()
        if stylesheet:
            app.setStyleSheet(stylesheet)
    return app


def run_gui(paths: Optional[Sequence[str]] = None) -> int:
    """Uruchamia GUI. Bez PySide6 rzuca RuntimeError z instrukcja instalacji."""
    require_qt()
    app = create_application(sys.argv)
    window = MainWindow()
    window.show()
    if paths:
        QTimer.singleShot(100, lambda: window.handle_dropped_paths(list(paths)))
    return app.exec()


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        try:
            return run_gui()
        except QtUnavailableError as ex:
            print(ex, file=sys.stderr)
            return 1
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
