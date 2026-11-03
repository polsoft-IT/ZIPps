"""ZIPps - logowanie (Logger oraz atrapa Empty)."""
import os
import threading
from datetime import datetime

from zipps_pkg.settings_mod import settings
# =====================================================================
#  Logger
# =====================================================================

class Empty:
    """Obiekt 'atrapy' logera - wygodne w CLI i w testach."""

    def log(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

class Logger:
    """Loguje do widgetu Qt oraz do pliku (liczba wywolan moze pochodzic z watku roboczego)."""

    MAX_BLOCKS = 5000

    def __init__(self, widget=None, log_file: str | None = None):
        self.widget = widget
        self.lock = threading.Lock()
        self.history = []
        self.log_file = log_file
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """Tworzy katalog dla pliku logu, jesli nie istnieje."""
        if self.log_file:
            log_dir = os.path.dirname(os.path.abspath(self.log_file))
            if log_dir and not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except OSError:
                    pass

    def _get_log_file_path(self) -> str:
        """Zwraca sciezke do pliku logu. Jesli nie ustawiono, uzywa domyslnej."""
        if self.log_file:
            return self.log_file
        # Domyślna ścieżka w katalogu ustawień użytkownika
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME")
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".config")
        log_dir = os.path.join(base, "ZIPps")
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError:
                return ""
        return os.path.join(log_dir, "ZIPps.log")

    def _write_to_file(self, msg: str):
        """Zapisuje wiadomosc do pliku logu."""
        log_path = self._get_log_file_path()
        if not log_path:
            return
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg}\n")
        except OSError:
            pass

    def log(self, msg: str):
        msg = str(msg)
        with self.lock:
            self.history.append(msg)
            if len(self.history) > 20000:
                del self.history[:10000]
        # Zapisz do pliku logu
        self._write_to_file(msg)
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


