"""ZIPps - sumy kontrolne i inspekcja plikow."""
import hashlib
import os
import struct
import sys
import zlib
from datetime import datetime

from zipps_pkg.core import (
    PackerError, Empty, emit, human_size, _make_progress, detect_format,
    iter_files, open_tar, FORMAT_EXTS, TAR_MODES,
)
from zipps_pkg.settings_mod import settings
from zipps_pkg.logging_mod import Logger, Empty
from zipps_pkg.packer import PackerCore

# =====================================================================
#  Bezpieczenstwo: sumy kontrolne i inspekcja plikow
# =====================================================================

def crc32_of_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            crc = zlib.crc32(chunk, crc)
    return "%08x" % (crc & 0xFFFFFFFF)


def hash_file(path: str, algo: str = "sha256", chunk_size: int = 1024 * 1024) -> str:
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

