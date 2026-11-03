"""ZIPps - interfejs graficzny (PySide6); opcjonalny."""
import os
import sys
import threading
import time
import subprocess
import traceback

from zipps_pkg.version import __version__, __app_name__
import json
import math
import py_compile

from typing import Optional, Sequence

from zipps_pkg.core import (
    PackerError, Empty, emit, human_size, detect_format, ensure_archive_ext,
    strip_archive_ext, archive_file_filter, normalize_relative,
    SUPPORTED_HASHES, ARCHIVE_EXTS, FORMAT_EXTS, GEN_PRESETS, DEFAULT_GEN_CODE,
)
from zipps_pkg.settings_mod import LANG, Settings, settings, config_path
from zipps_pkg.logging_mod import Logger
from zipps_pkg.generator import FileGenerator
from zipps_pkg.packer import PackResult, PackerCore
from zipps_pkg.unpacker import ExtractResult, UnpackerCore
from zipps_pkg.pfa import PFAFormat
from zipps_pkg.security import (SecurityCore, file_info, describe_pyc,
                                hash_file)


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
        QTextBrowser, QTableWidget, QTableWidgetItem, QFrame
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

# =====================================================================
#  Styl interfejsu
# =====================================================================

#: sciezka pliku ze stylem QSS (wczytywany leniwie przy starcie GUI)
QSS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "style.qss")


def load_stylesheet() -> str:
    """Wczytuje arkusz stylow z pliku style.qss (pusty napis, gdy plik nie istnieje)."""
    try:
        with open(QSS_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as ex:
        Logger().error("Nie udalo sie wczytac %s: %s" % (QSS_PATH, ex))
        return ""


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
    full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
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
                 placeholder: str = "", file_filter: str = ""):
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
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
            path, _ = QFileDialog.getSaveFileName(self, self.label.text(), start,
                                                  self.file_filter)
        elif self.mode == "any":
            path = QFileDialog.getExistingDirectory(self, self.label.text(), start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.label.text(), start,
                                                  self.file_filter)
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
      """Okno pomocy ze skrotami klawiaturowymi (motyw-aware)."""

      # doklejany blok CSS - nadpisuje kolory z wbudowanego HTML tak, aby
      # okno wygladalo dobrze w jasnym i ciemnym motywie.
      # Uwaga: renderer HTML Qt nie wspiera qlineargradient - uzywamy
      # jednolitych kolorow i selektorow o wyzszej specyficznosci,
      # aby nadpisac style wbudowane w tlumaczenie.
      THEME_CSS_LIGHT = """
          table td .shortcut, span.shortcut {
              background-color: #eef3f8; border: 1px solid #b6c6d8;
              border-bottom: 2px solid #9fb3c8;
              border-radius: 5px; padding: 3px 10px;
              font-family: 'Consolas','Courier New',monospace;
              font-weight: bold; font-size: 12px; color: #1b6ec2;
              min-width: 110px; display: inline-block; text-align: center; }
          td .desc, .desc { color: #2c3e50; font-size: 13px; }
          div.category, .category {
              background-color: #3498db; color: #ffffff;
              padding: 6px 12px; border-radius: 5px;
              margin-top: 18px; margin-bottom: 8px;
              font-size: 13px; font-weight: bold; letter-spacing: 0.3px; }
          td { padding: 7px 10px; border-bottom: 1px solid #e9ecef; }
          h2 { color: #2c3e50; }
      """
      THEME_CSS_DARK = """
          table td .shortcut, span.shortcut {
              background-color: #33383d; border: 1px solid #5a636b;
              border-bottom: 2px solid #6e7a84;
              border-radius: 5px; padding: 3px 10px;
              font-family: 'Consolas','Courier New',monospace;
              font-weight: bold; font-size: 12px; color: #4fc1ff;
              min-width: 110px; display: inline-block; text-align: center; }
          td .desc, .desc { color: #d4d4d4; font-size: 13px; }
          div.category, .category {
              background-color: #09477a; color: #ffffff;
              padding: 6px 12px; border-radius: 5px;
              margin-top: 18px; margin-bottom: 8px;
              font-size: 13px; font-weight: bold; letter-spacing: 0.3px; }
          td { padding: 7px 10px; border-bottom: 1px solid #3c3c3c; }
          h2 { color: #d4d4d4; }
      """

      def __init__(self, parent=None):
          super().__init__(parent)
          self.setWindowTitle(settings.t("shortcut_help_title"))
          self.resize(440, 520)
          self.setMinimumSize(400, 420)
          self.setModal(True)

          dark = bool(getattr(settings, "dark_theme", False))
          theme_css = self.THEME_CSS_DARK if dark else self.THEME_CSS_LIGHT

          layout = QVBoxLayout(self)
          layout.setContentsMargins(16, 16, 16, 16)
          layout.setSpacing(12)

          # Naglowek z ikona
          header = QHBoxLayout()
          icon_label = QLabel()
          icon_pixmap = load_image("docs/file2.png", 48, 48)
          if not icon_pixmap.isNull():
              icon_label.setPixmap(icon_pixmap)
          title_label = QLabel("⌨️  " + settings.t("shortcut_help_title"))
          title_label.setStyleSheet(
              "font-size: 18px; font-weight: bold; color: %s;" % ("#d4d4d4" if dark else "#2c3e50"))
          header.addWidget(icon_label)
          header.addWidget(title_label)
          header.addStretch(1)
          layout.addLayout(header)

          # Separator
          line = QFrame()
          line.setFrameShape(QFrame.Shape.HLine)
          line.setFrameShadow(QFrame.Shadow.Sunken)
          line.setStyleSheet("background-color: %s;" % ("#3c3c3c" if dark else "#bdc3c7"))
          layout.addWidget(line)

          # Widok HTML - usuwamy wbudowany blok <style> (zaszyte jasne kolory)
          # i wstawiamy wlasny, zgodny z motywem
          import re as _re
          html = _re.sub(r"<style>.*?</style>", "", settings.t("shortcut_help"),
                         count=1, flags=_re.DOTALL | _re.IGNORECASE)
          # naglowek okna juz pokazuje tytul - usuwamy duplikat z tresci HTML
          html = _re.sub(r"<h2>.*?</h2>", "", html, count=1,
                         flags=_re.DOTALL | _re.IGNORECASE)
          view = QTextBrowser()
          view.setHtml("<style>%s</style>%s" % (theme_css, html))
          view.setOpenExternalLinks(False)
          if dark:
              view.setStyleSheet("""
                  QTextBrowser { background-color: #252526; color: #d4d4d4;
                      border: 1px solid #3c3c3c; border-radius: 8px; padding: 12px; }
              """)
          else:
              view.setStyleSheet("""
                  QTextBrowser { background-color: #f8f9fa; color: #2c3e50;
                      border: 1px solid #dee2e6; border-radius: 8px; padding: 12px; }
              """)
          layout.addWidget(view, 1)

          # Przycisk zamykania
          buttons = QHBoxLayout()
          buttons.addStretch(1)
          close_btn = QPushButton(settings.t("close"))
          close_btn.setMinimumWidth(110)
          if dark:
              close_btn.setStyleSheet("""
                  QPushButton {
                      background-color: #0e639c; color: white; border: none;
                      padding: 8px 28px; border-radius: 5px; font-weight: bold; }
                  QPushButton:hover { background-color: #1177bb; }
                  QPushButton:pressed { background-color: #0a4f80; }
              """)
          else:
              close_btn.setStyleSheet("""
                  QPushButton {
                      background-color: #3498db; color: white; border: none;
                      padding: 8px 28px; border-radius: 5px; font-weight: bold; }
                  QPushButton:hover { background-color: #2980b9; }
                  QPushButton:pressed { background-color: #21618c; }
              """)
          close_btn.clicked.connect(self.accept)
          buttons.addWidget(close_btn)
          layout.addLayout(buttons)


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
            log_layout.addWidget(self.log_widget, 1)

            # Logger po utworzeniu widgetu logu
            self.logger = Logger(self.log_widget)
            self.generator = FileGenerator(self.logger)
            self.packer = PackerCore(self.logger)
            self.unpacker = UnpackerCore(self.logger)
            self.security = SecurityCore(self.logger)
            self.pfa = PFAFormat(self.logger)

            self.overlay = ProgressOverlay()
            self.overlay.cancelRequested.connect(self.cancel_operation)
            log_layout.addWidget(self.overlay)
            self.log_box = log_box

            # Log start message
            self.logger.log("ZIPps v%s started (GUI)" % __version__)

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

            # Log jako ostatnia zakladka (kolejnosc indeksow: Generator=0 ... Log=5)
            self.tabs.addTab(log_box, settings.t("log"))

            self.create_actions()
            self.connect_signals()
            self.refresh_language()
            self.apply_theme()

            self.setAcceptDrops(True)
            self.tabs.setAcceptDrops(True)

            if settings.remember_window and settings.window_geometry:
                try:
                    x, y, w_, h_ = (int(v) for v in settings.window_geometry.split(","))
                    self.setGeometry(x, y, w_, h_)
                except (ValueError, TypeError):
                    pass
            else:
                self.adjustSize()

            # Minimum okna = faktyczne minimum layoutu (minimumSizeHint),
            # dzieki czemu okno jest najmniejsze z mozliwych, a nic nie jest
            # ucinane ani zakrywane. sizeHint() byl zdecydowanie za duzy.
            def _apply_compact_size():
                hint = central.layout().minimumSize() + QSize(
                    2 * 8, 2 * 8 + self.menuBar().height() + self.statusBar().height())
                self.setMinimumSize(hint)
                if not settings.window_geometry:
                    self.resize(hint)
                elif self.width() < hint.width() or self.height() < hint.height():
                    self.resize(max(self.width(), hint.width()),
                                max(self.height(), hint.height()))
            QTimer.singleShot(0, _apply_compact_size)

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
                ("btn_generate_h", self.do_generate_h, "file"),
                ("btn_generate_raw", self.do_generate_raw, "file"),
                ("btn_generate_dat", self.do_generate_dat, "file"),
                ("btn_generate_img", self.do_generate_img, "file"),
                ("btn_generate_blob", self.do_generate_blob, "file"),
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
            self.pack_archive_row = PathRow(settings.t("archive_path"), "save",
                                            file_filter=archive_file_filter())
            out_layout.addWidget(self.pack_archive_row, 0, 0, 1, 3)
            self.pack_archive_edit = self.pack_archive_row.edit
            self.pack_archive_edit.setReadOnly(False)

            self.pack_format_combo = QComboBox()
            # czytelne etykiety z tlumaczen (np. "ZIP (.zip)") zamiast kodow formatu
            self._format_labels = {
                "zip": "format_zip", "tar": "format_tar",
                "targz": "format_targz", "tarbz2": "format_tarbz2",
                "tarxz": "format_tarxz", "gz": "format_gz",
                "bz2": "format_bz2", "xz": "format_xz",
                "7z": "format_7z", "pfa": "format_pfa",
            }
            for value in ("zip", "tar", "targz", "tarbz2", "tarxz",
                          "gz", "bz2", "xz", "7z", "pfa"):
                self.pack_format_combo.addItem(settings.t(self._format_labels[value]), value)
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
            # Initialize format-dependent UI state
            self.on_pack_format_change(self.pack_format_combo.currentIndex())

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
            # Disable append checkbox for non-ZIP formats
            self.pack_append_check.setEnabled(fmt == "zip")
            if fmt != "zip":
                self.pack_append_check.setChecked(False)
            # Disable password for formats that don't support encryption
            supports_encryption = fmt in ("zip", "pfa")
            self.pack_password_edit.setEnabled(supports_encryption)
            self.pack_password2_edit.setEnabled(supports_encryption)
            if not supports_encryption:
                self.pack_password_edit.clear()
                self.pack_password2_edit.clear()
            settings.last_format = fmt

        # -----------------------------------------------------------------
        #  Zakladka 3: Rozpakowywanie
        # -----------------------------------------------------------------
        def build_unpack_tab(self):
            w = QWidget()
            layout = QVBoxLayout(w)

            top = QGridLayout()
            self.unpack_archive_row = PathRow(settings.t("select_archive"), "open",
                                              file_filter=archive_file_filter())
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
                name = strip_archive_ext(os.path.basename(path))
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
            self.sec_file_row = PathRow(settings.t("hash_file"), "open",
                                        file_filter=archive_file_filter())
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
            self.pfa_file_row = PathRow(settings.t("pfa_file"), "open",
                                        file_filter=archive_file_filter("pfa"))
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
            self.remember_window_check = QCheckBox(settings.t("remember_window"))
            self.remember_window_check.setChecked(bool(settings.remember_window))
            self.remember_paths_check = QCheckBox(settings.t("remember_last_paths"))
            self.remember_paths_check.setChecked(bool(settings.remember_last_paths))
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
            al.addWidget(self.remember_window_check, 1, 2)
            al.addWidget(self.remember_paths_check, 2, 0, 1, 2)
            al.addWidget(self.default_dir_row, 3, 0, 1, 3)
            al.addWidget(self.zoom_label, 4, 0)
            al.addWidget(self.zoom_spin, 4, 1)
            layout.addWidget(appearance)

            # --- Zachowanie ---
            behavior = QGroupBox(settings.t("group_behavior"))
            bl = QGridLayout(behavior)
            self.confirm_pack_check = QCheckBox(settings.t("confirm_before_pack"))
            self.confirm_pack_check.setChecked(bool(settings.confirm_before_pack))
            self.confirm_unpack_check = QCheckBox(settings.t("confirm_before_unpack"))
            self.confirm_unpack_check.setChecked(bool(settings.confirm_before_unpack))
            self.confirm_exit_check = QCheckBox(settings.t("confirm_exit_busy"))
            self.confirm_exit_check.setChecked(bool(settings.confirm_exit_busy))
            self.auto_open_check = QCheckBox(settings.t("auto_open_output"))
            self.auto_open_check.setChecked(bool(settings.auto_open_output))
            self.sound_check = QCheckBox(settings.t("sound_alerts"))
            self.sound_check.setChecked(bool(settings.sound_alerts))
            self.verify_after_pack_check = QCheckBox(settings.t("verify_after_pack"))
            self.verify_after_pack_check.setChecked(bool(settings.verify_after_pack))
            self.date_name_check = QCheckBox(settings.t("date_in_archive_name"))
            self.date_name_check.setChecked(bool(settings.date_in_archive_name))
            bl.addWidget(self.confirm_pack_check, 0, 0)
            bl.addWidget(self.confirm_unpack_check, 0, 1)
            bl.addWidget(self.confirm_exit_check, 1, 0)
            bl.addWidget(self.auto_open_check, 1, 1)
            bl.addWidget(self.sound_check, 2, 0)
            bl.addWidget(self.verify_after_pack_check, 2, 1)
            bl.addWidget(self.date_name_check, 3, 0, 1, 2)

            overwrite_row = QHBoxLayout()
            overwrite_row.addWidget(QLabel(settings.t("overwrite_mode")))
            self.overwrite_combo = QComboBox()
            for label_key, value in (("overwrite_ask", "ask"), ("overwrite_always", "always"),
                                     ("overwrite_skip", "skip"), ("overwrite_rename", "rename")):
                self.overwrite_combo.addItem(settings.t(label_key), value)
            idx = self.overwrite_combo.findData(settings.overwrite_policy)
            self.overwrite_combo.setCurrentIndex(max(0, idx))
            overwrite_row.addWidget(self.overwrite_combo, 1)
            bl.addLayout(overwrite_row, 4, 0, 1, 2)
            layout.addWidget(behavior)

            # --- Log i bezpieczenstwo ---
            tools_box = QGroupBox(settings.t("group_hash"))
            tl = QGridLayout(tools_box)
            self.log_file_check = QCheckBox(settings.t("log_to_file"))
            self.log_file_check.setChecked(bool(settings.log_to_file))
            self.timestamp_check = QCheckBox(settings.t("timestamp_log"))
            self.timestamp_check.setChecked(bool(settings.timestamp_log))
            self.hash_upper_check = QCheckBox(settings.t("hash_uppercase"))
            self.hash_upper_check.setChecked(bool(settings.hash_uppercase))
            tl.addWidget(self.log_file_check, 0, 0)
            tl.addWidget(self.timestamp_check, 0, 1)
            tl.addWidget(self.hash_upper_check, 0, 2)
            tl.addWidget(QLabel(settings.t("log_max_lines")), 1, 0)
            self.log_lines_spin = QSpinBox()
            self.log_lines_spin.setRange(100, 100000)
            self.log_lines_spin.setSingleStep(500)
            self.log_lines_spin.setValue(int(settings.log_max_lines))
            tl.addWidget(self.log_lines_spin, 1, 1)
            tl.addWidget(QLabel(settings.t("default_hash_algo")), 2, 0)
            self.hash_algo_combo = QComboBox()
            for algo in SUPPORTED_HASHES:
                self.hash_algo_combo.addItem(algo.upper(), algo)
            hidx = self.hash_algo_combo.findData(settings.default_hash_algo)
            self.hash_algo_combo.setCurrentIndex(max(0, hidx))
            tl.addWidget(self.hash_algo_combo, 2, 1)
            layout.addWidget(tools_box)

            # --- Wydajnosc ---
            perf = QGroupBox(settings.t("group_performance"))
            pl_ = QGridLayout(perf)
            pl_.addWidget(QLabel(settings.t("chunk_size")), 0, 0)
            self.chunk_spin = QSpinBox()
            self.chunk_spin.setRange(16, 4096)
            self.chunk_spin.setSingleStep(64)
            self.chunk_spin.setValue(int(settings.chunk_size_kb))
            self.chunk_spin.setSuffix(" KB")
            pl_.addWidget(self.chunk_spin, 0, 1)
            pl_.addWidget(QLabel(settings.t("parallel_workers")), 0, 2)
            self.workers_spin = QSpinBox()
            self.workers_spin.setRange(1, 16)
            self.workers_spin.setValue(int(settings.parallel_workers))
            pl_.addWidget(self.workers_spin, 0, 3)
            pl_.setColumnStretch(4, 1)
            layout.addWidget(perf)

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
            self.btn_reset_settings = QPushButton(settings.t("reset_all"))
            self.btn_reset_settings.clicked.connect(self.reset_settings)
            self.btn_open_log_folder = QPushButton(settings.t("open_folder"))
            self.btn_open_log_folder.clicked.connect(
                lambda: self.open_path(os.path.dirname(settings.path)))
            for button in (self.btn_shortcuts, self.btn_settings_path,
                           self.btn_save_settings, self.btn_reset_settings,
                           self.btn_open_log_folder):
                about_buttons.addWidget(button)
            about_buttons.addStretch(1)
            bl.addLayout(about_buttons)
            layout.addWidget(about)
            layout.addStretch(1)

            self.tabs.addTab(w, settings.t("tab_settings"))

        def reset_settings(self):
            answer = QMessageBox.question(
                self, settings.t("reset_all"), settings.t("reset_confirm"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            for key, value in Settings.DEFAULTS.items():
                setattr(settings, key, value)
            settings.save()
            self.apply_theme()
            self.refresh_language()
            self.log(settings.t("reset_all") + " - " + settings.t("settings_saved"))

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

            for index in range(6):
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
            for index in range(6):
                self.tabs.setTabText(index, settings.t([
                    "tab_generate", "tab_pack", "tab_unpack", "tab_security",
                    "tab_settings", "log"][index]))
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
            # etykiety formatow w combo pakowania (czytelne nazwy z tlumaczen)
            if getattr(self, "_format_labels", None):
                current = self.pack_format_combo.currentData()
                self.pack_format_combo.blockSignals(True)
                for index in range(self.pack_format_combo.count()):
                    fmt = self.pack_format_combo.itemData(index)
                    label_key = self._format_labels.get(fmt)
                    if label_key:
                        self.pack_format_combo.setItemText(index, settings.t(label_key))
                self.pack_format_combo.blockSignals(False)
                if current is not None:
                    idx = self.pack_format_combo.findData(current)
                    if idx >= 0:
                        self.pack_format_combo.setCurrentIndex(idx)
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

        def _collect_settings_ui(self):
            """Przenosi stan widgetow zakladki Ustawienia do obiektu settings."""
            settings.dark_theme = self.theme_check.isChecked()
            settings.default_dir = self.default_dir_row.text()
            settings.modal_dialogs = self.modal_check.isChecked()
            settings.remember_window = self.remember_window_check.isChecked()
            settings.remember_last_paths = self.remember_paths_check.isChecked()
            settings.confirm_before_pack = self.confirm_pack_check.isChecked()
            settings.confirm_before_unpack = self.confirm_unpack_check.isChecked()
            settings.confirm_exit_busy = self.confirm_exit_check.isChecked()
            settings.auto_open_output = self.auto_open_check.isChecked()
            settings.sound_alerts = self.sound_check.isChecked()
            settings.verify_after_pack = self.verify_after_pack_check.isChecked()
            settings.date_in_archive_name = self.date_name_check.isChecked()
            settings.overwrite_policy = self.overwrite_combo.currentData() or "ask"
            settings.log_to_file = self.log_file_check.isChecked()
            settings.timestamp_log = self.timestamp_check.isChecked()
            settings.hash_uppercase = self.hash_upper_check.isChecked()
            settings.log_max_lines = self.log_lines_spin.value()
            settings.default_hash_algo = self.hash_algo_combo.currentData() or "sha256"
            settings.chunk_size_kb = self.chunk_spin.value()
            settings.parallel_workers = self.workers_spin.value()

        def save_settings(self):
            self._collect_settings_ui()
            if settings.save():
                self.log(settings.t("settings_saved") + ": " + settings.path)
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

        def do_generate_h(self):
            def run():
                try:
                    path = self.generator.generate_h_file(
                        self._gen_folder(), self.gen_name_edit.text(),
                        self.gen_code_edit.toPlainText())
                    self._report_generated(path)
                except (OSError, PackerError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_dat(self):
            def run():
                try:
                    size = int(self.gen_size_edit.text() or "1024")
                    path = self.generator.generate_dat_file(
                        self._gen_folder(), self.gen_name_edit.text(), size)
                    self._report_generated(path)
                except (OSError, PackerError, ValueError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_img(self):
            def run():
                try:
                    size = int(self.gen_size_edit.text() or "1024")
                    path = self.generator.generate_img_file(
                        self._gen_folder(), self.gen_name_edit.text(), size)
                    self._report_generated(path)
                except (OSError, PackerError, ValueError) as ex:
                    self.log(settings.t("error") + ": " + str(ex))
            self._guard(run)

        def do_generate_blob(self):
            def run():
                try:
                    size = int(self.gen_size_edit.text() or "1024")
                    path = self.generator.generate_blob_file(
                        self._gen_folder(), self.gen_name_edit.text(), size)
                    self._report_generated(path)
                except (OSError, PackerError, ValueError) as ex:
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
            if fmt in ("tar", "targz", "tarbz2", "tarxz", "gz", "bz2", "xz") and password:
                self.log("%s: encryption not supported - archive will be stored unencrypted" % fmt.upper())
            bases = sorted({os.path.dirname(p) for p in self.pack_items},
                           key=len) or [settings.default_dir or os.getcwd()]
            level = self.pack_level_spin.value()
            return {
                "bases": bases,
                "keep_relative": self.pack_keep_rel.isChecked(),
                "password": password,
                "level": level,
                "compression": "stored" if level == 0 else "deflate",
                "append": self.pack_append_check.isChecked() and fmt == "zip",  # Only ZIP supports append
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
                if settings.confirm_exit_busy:
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
            try:
                self._collect_settings_ui()
            except AttributeError:
                pass
            if settings.remember_window:
                g = self.geometry()
                settings.window_geometry = "%d,%d,%d,%d" % (g.x(), g.y(), g.width(), g.height())
            else:
                settings.window_geometry = ""
            settings.save()
            self.logger.log("ZIPps v%s closed" % __version__)
            event.accept()



# =====================================================================
#  Uruchomienie GUI
# =====================================================================

def create_application(argv: Optional[Sequence[str]] = None) -> QApplication:
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


# =====================================================================
#  Wymagania Qt / pomocnicze dla modulu GUI
# =====================================================================

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

