"""ZIPps - rdzen: wyjatki, pomocnicze funkcje, wykrywanie formatow."""
import os
import sys
import json
import math
import stat
import shutil
import struct
import zlib
import gzip
import bz2
import lzma
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

#: py7zr dla obslugi formatu 7z
try:
    import py7zr
    PY7ZR_AVAILABLE = True
except ImportError:
    PY7ZR_AVAILABLE = False

# =====================================================================
#  Funkcje pomocnicze
# =====================================================================

ARCHIVE_EXTS = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2",
                ".tar.xz", ".txz", ".gz", ".bz2", ".xz", ".pfa")

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
    "gz": ".gz",
    "bz2": ".bz2",
    "xz": ".xz",
    "7z": ".7z",
    "pfa": ".pfa",
}

#: mapowanie formatu na tryb tarfile
TAR_MODES = {
    "tar": "w",
    "targz": "w:gz",
    "tarbz2": "w:bz2",
    "tarxz": "w:xz",
}

#: mapowanie formatu na modul kompresji
COMPRESS_MODES = {
    "gz": gzip,
    "bz2": bz2,
    "xz": lzma,
}

#: dodatkowe, alternatywne rozszerzenia tych samych formatow (bez FORMAT_EXTS)
ALTERNATE_EXTS = (".tgz", ".tbz2", ".tbz", ".txz")

#: wszystkie rozszerzenia archiwow znane aplikacji (do filtra plikow i drag&drop)
ALL_ARCHIVE_EXTS = tuple(sorted(set(FORMAT_EXTS.values()) | set(ALTERNATE_EXTS),
                                key=len, reverse=True))


def strip_archive_ext(name: str) -> str:
    """Zdejmuje rozszerzenia archiwum ('a.tar.gz' -> 'a', 'a.zip' -> 'a').

    Dekompresyjne przyrosty (.gz/.bz2/.xz) zdejmowane wielokrotnie, aby
    'a.tar.gz' dalo nazwe folderu wyjsciowego 'a', a nie 'a.tar'.
    """
    low = (name or "").lower()
    changed = True
    while changed:
        changed = False
        for ext in ALL_ARCHIVE_EXTS:
            if low.endswith(ext):
                name = name[:-len(ext)]
                low = low[:-len(ext)]
                changed = ext in (".gz", ".bz2", ".xz")
                break
    return name


def _gzip_original_name(path: str) -> str:
    """Odczytuje oryginalna nazwe pliku z naglowka gzip (pole FNAME), jesli jest."""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            if len(head) < 10 or head[:2] != b"\x1f\x8b":
                return ""
            flags = head[3]
            if not flags & 0x08:  # brak pola FNAME
                return ""
            # po naglowku: opcjonalne pola dodatkowe, potem nazwa zakonczona NUL
            if flags & 0x04:
                extra_len = int.from_bytes(f.read(2), "little")
                f.seek(extra_len, os.SEEK_CUR)
            raw = b""
            while True:
                byte = f.read(1)
                if not byte or byte == b"\x00":
                    break
                raw += byte
        return raw.decode("utf-8", "replace") if raw else ""
    except OSError:
        return ""


def _uncompressed_size(path: str, fmt: str) -> int:
    """Rozmiar danych po rozpakowaniu (gzip: z ostatnich 4B, bz2/xz: przez strumien)."""
    if fmt == "gz":
        # ostatnie 4 bajty pliku gzip to rozmiar danych jawnych (mod 2^32)
        with open(path, "rb") as f:
            f.seek(-4, os.SEEK_END)
            raw_size = int.from_bytes(f.read(4), "little")
        return raw_size
    opener = {"bz2": bz2.open, "xz": lzma.open}.get(fmt)
    if opener is None:
        return os.path.getsize(path)
    total = 0
    with opener(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
    return total


def archive_file_filter(fmt: str | None = None) -> str:
    """Filtr plikow dla okien dialogowych Qt (np. 'Archives (*.zip *.tar ...)').

    Z fmt ogranicza liste do jednego formatu, bez - pokazuje wszystkie
    obslugiwane archiwa plus pozycje 'All files'.
    """
    if fmt and fmt in FORMAT_EXTS:
        exts = {FORMAT_EXTS[fmt]}
        exts |= {a for a in ALTERNATE_EXTS if a.startswith(FORMAT_EXTS[fmt][:4])}
        name = "%s archive" % fmt.upper()
    else:
        exts = set(ALL_ARCHIVE_EXTS)
        name = "Archives"
    pattern = " ".join("*" + e for e in sorted(exts))
    return "%s (%s);;All files (*)" % (name, pattern)


SUPPORTED_HASHES = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512",
                    "sha3_256", "sha3_512", "blake2b", "blake2s", "crc32")


def _fix_default_hash_algo(settings):
    """Korekta wczytanego ustawienia (wywolywana z settings_mod po inicie)."""
    if settings.default_hash_algo not in SUPPORTED_HASHES:
        settings.default_hash_algo = "sha256"


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
    """Rozpoznaje format archiwum po zawartosci (magic bytes), a dopiero potem po rozszerzeniu."""
    sig = b""
    if os.path.exists(path):
        # Read magic bytes for format detection
        try:
            with open(path, "rb") as f:
                sig = f.read(10)  # Read more bytes for better detection
        except OSError:
            sig = b""

    # ZIP (PK header)
    if sig.startswith(b"PK\x03\x04") or sig.startswith(b"PK\x05\x06") or sig.startswith(b"PK\x07\x08"):
        return "zip"

    # PFA custom format
    if sig.startswith(b"PFA2") or sig.startswith(b"PFA1"):
        return "pfa"

    # GZIP (standalone or tar.gz)
    if sig.startswith(b"\x1f\x8b"):
        low = path.lower()
        # Check if it's tar.gz by extension
        if low.endswith((".tar.gz", ".tgz")):
            return "targz"
        # Could also be nested .tar.gz.gz - handle that case
        if low.count(".tar") > 0 and low.endswith(".gz"):
            return "targz"
        return "gz"

    # BZIP2 (standalone or tar.bz2)
    if sig.startswith(b"BZh"):
        low = path.lower()
        if low.endswith((".tar.bz2", ".tbz2", ".tbz")):
            return "tarbz2"
        return "bz2"

    # 7-Zip archive
    if sig.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"

    # XZ/LZMA (standalone or tar.xz)
    if sig.startswith(b"\xfd7zXZ\x00"):
        low = path.lower()
        if low.endswith((".tar.xz", ".txz")):
            return "tarxz"
        return "xz"

    # Try to open as tar (plain tar files don't have a magic header)
    try:
        with tarfile.open(path, "r:"):
            return "tar"
    except (tarfile.TarError, OSError):
        pass

    # Fallback to extension-based detection
    low = path.lower()
    # Check multi-part extensions first (longer first)
    for fmt, ext in sorted(FORMAT_EXTS.items(), key=lambda kv: len(kv[1]), reverse=True):
        if low.endswith(ext):
            return fmt

    # Alternative extensions for compressed tar
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
    # Accepted extensions for this format (including alternatives)
    accepted = {ext}
    alternatives = {
        "targz": {".tgz"},
        "tarbz2": {".tbz2", ".tbz"},
        "tarxz": {".txz"},
    }
    if fmt in alternatives:
        accepted |= alternatives[fmt]

    # If already has correct extension, return as-is
    if any(low.endswith(a) for a in accepted):
        return path

    # Remove any existing archive extension
    base = path
    # Try to strip multi-part extensions first (e.g., .tar.gz)
    for ext_to_remove in sorted(FORMAT_EXTS.values(), key=len, reverse=True):
        if low.endswith(ext_to_remove):
            base = path[:-len(ext_to_remove)]
            break
    else:
        # Try single extension
        _, cur_ext = os.path.splitext(path)
        if cur_ext.lower() in (FORMAT_EXTS[k] for k in FORMAT_EXTS):
            base = path[:-len(cur_ext)]

    return base + ext


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


