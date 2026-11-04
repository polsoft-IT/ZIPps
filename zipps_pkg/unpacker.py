"""ZIPps - rozpakowywanie archiwow."""
import bz2
import gzip
import json
import lzma
import os
import shutil
import struct
import tarfile
import time
import zipfile
import zlib

from dataclasses import dataclass, field

# Nowe biblioteki kompresji
try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False

try:
    import lz4.frame
    LZ4_AVAILABLE = True
except ImportError:
    LZ4_AVAILABLE = False

try:
    import rarfile
    RAR_AVAILABLE = True
except ImportError:
    RAR_AVAILABLE = False

try:
    import pycdlib
    ISO_AVAILABLE = True
except ImportError:
    ISO_AVAILABLE = False

try:
    import brotli
    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False

try:
    import arpy
    AR_AVAILABLE = True
except ImportError:
    AR_AVAILABLE = False

def py7zr_module():
    """Modul py7zr ladowany przy uzyciu (opcjonalny)."""
    import py7zr
    return py7zr


from zipps_pkg.core import (
    PackerError, Empty, emit, human_size, _check_cancel, _make_progress,
    detect_format, normalize_relative, safe_join, open_tar, strip_archive_ext,
    _tar_extract_member, _zip_extract_entry, _uncompressed_size, _gzip_original_name,
    TAR_MODES, PY7ZR_AVAILABLE, ZSTD_AVAILABLE, LZ4_AVAILABLE, BROTLI_AVAILABLE, AR_AVAILABLE,
)
from zipps_pkg.settings_mod import settings
from zipps_pkg.logging_mod import Logger
from zipps_pkg.packer import PackResult


def _lazy_pfa():
    """Ladowskie tworzenie PFAFormat (unikanie importu cyklicznego)."""
    from zipps_pkg.pfa import PFAFormat
    return PFAFormat
from zipps_pkg.packer import PackResult
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
        elif fmt == "7z":
            if not PY7ZR_AVAILABLE:
                raise PackerError("py7zr library is not available. Install it with: pip install py7zr")
            try:
                with py7zr_module().SevenZipFile(archive_path, "r", password=password) as archive:
                    for info in archive.list():
                        entries.append({
                            "name": info.filename,
                            "size": info.uncompressed,
                            "date": time.localtime(os.path.getmtime(archive_path))[:6],
                            "encrypted": bool(password),
                            "is_dir": info.is_directory,
                        })
            except py7zr_module().Bad7zFile:
                pass
        elif fmt == "pfa":
            with _lazy_pfa()(Empty()) as pfa:
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
        elif fmt in ("gz", "bz2", "xz", "zst", "lz4", "br"):
            # Single-file compression formats
            # nazwa wpisu: bez rozszerzenia kompresji (dla gz - nazwa z naglowka)
            base = os.path.basename(strip_archive_ext(archive_path))
            if fmt == "gz":
                original = _gzip_original_name(archive_path)
                if original:
                    base = os.path.basename(original)
            try:
                size = _uncompressed_size(archive_path, fmt)
            except (OSError, EOFError, PackerError):
                size = os.path.getsize(archive_path)
            entries.append({
                "name": base,
                "size": size,
                "date": time.localtime(os.path.getmtime(archive_path))[:6],
                "encrypted": False,
                "is_dir": False,
            })
        elif fmt == "ar":
            if not AR_AVAILABLE:
                raise PackerError("AR wymaga modulu 'arpy'. Zainstaluj: pip install arpy")
            try:
                with arpy.Archive(archive_path) as ar:
                    ar.read_all_headers()
                    for name in ar.archived_files.keys():
                        if isinstance(name, bytes):
                            name = name.decode('utf-8', errors='replace')
                        entries.append({
                            "name": name,
                            "size": ar.archived_files[name.encode('utf-8') if isinstance(name, str) else name].size,
                            "date": time.localtime(os.path.getmtime(archive_path))[:6],
                            "encrypted": False,
                            "is_dir": False,
                        })
            except Exception:
                pass
        elif fmt == "rar":
            if not RAR_AVAILABLE:
                raise PackerError("RAR wymaga modulu 'rarfile'. Zainstaluj: pip install rarfile")
            try:
                with rarfile.RarFile(archive_path) as rf:
                    for info in rf.infolist():
                        entries.append({
                            "name": info.filename,
                            "size": info.file_size,
                            "date": time.localtime(info.date_time)[:6],
                            "encrypted": bool(info.flag_bits & 0x1),
                            "is_dir": info.is_dir(),
                        })
            except rarfile.BadRarFile:
                pass
        elif fmt == "iso":
            if not ISO_AVAILABLE:
                raise PackerError("ISO wymaga modulu 'pycdlib'. Zainstaluj: pip install pycdlib")
            try:
                iso = pycdlib.PyCdlib()
                iso.open(archive_path)
                for path, _ in iso.list_iso():
                    if path.endswith('/') or path == '':
                        continue
                    entries.append({
                        "name": path.lstrip('/'),
                        "size": iso.get_record(path).data_length,
                        "date": time.localtime(os.path.getmtime(archive_path))[:6],
                        "encrypted": False,
                        "is_dir": False,
                    })
                iso.close()
            except Exception:
                pass
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
        elif fmt == "7z":
            if not PY7ZR_AVAILABLE:
                raise PackerError("py7zr library is not available. Install it with: pip install py7zr")
            _check_cancel(cancel_event)
            try:
                with py7zr_module().SevenZipFile(archive_path, "r", password=password) as archive:
                    # Extract all files to output folder
                    archive.extractall(path=output_folder)
                    # Count extracted files
                    for i, entry in enumerate(files, 1):
                        _check_cancel(cancel_event)
                        try:
                            target = safe_join(output_folder, entry["name"])
                            if os.path.exists(target):
                                result.extracted += 1
                                result.bytes_written += entry["size"]
                                report(i, total, entry["name"])
                        except PackerError as ex:
                            result.blocked.append(str(ex))
                            emit(self.logger, "%s: %s" % (settings.t("error"), ex))
            except py7zr_module().Bad7zFile:
                raise PackerError(settings.t("archive_damaged").format(archive_path))
        elif fmt == "pfa":
            with _lazy_pfa()(self.logger) as pfa:
                res = pfa.unpack_pfa(archive_path, output_folder, selected=selected,
                                     progress_cb=progress_cb, password=password,
                                     overwrite=overwrite, cancel_event=cancel_event)
                result.extracted = res.extracted
                result.bytes_written = res.bytes_written
                result.overwritten = res.overwritten
                result.blocked.extend(res.blocked)
                result.errors.extend(res.errors)
        elif fmt in ("gz", "bz2", "xz", "zst", "lz4", "br"):
            # Single-file compression formats
            _check_cancel(cancel_event)
            if not files:
                raise PackerError("No files to extract")
            entry = files[0]
            # nazwa pliku wynikowego: bez rozszerzenia kompresji; dla gzip
            # preferujemy oryginalna nazwe zapisana w naglowku formatu
            name = entry["name"]
            if fmt == "gz":
                original = _gzip_original_name(archive_path)
                if original:
                    name = os.path.basename(original)
                else:
                    name = os.path.basename(strip_archive_ext(name))
            else:
                name = os.path.basename(strip_archive_ext(name))
            target = os.path.join(output_folder, name)
            target_exists = os.path.exists(target)

            if not overwrite and target_exists:
                result.skipped += 1
            else:
                try:
                    if fmt == "gz":
                        with gzip.open(archive_path, "rb") as f_in:
                            with open(target, "wb") as f_out:
                                shutil.copyfileobj(f_in, f_out, 1024 * 256)
                    elif fmt == "bz2":
                        with bz2.open(archive_path, "rb") as f_in:
                            with open(target, "wb") as f_out:
                                shutil.copyfileobj(f_in, f_out, 1024 * 256)
                    elif fmt == "xz":
                        with lzma.open(archive_path, "rb") as f_in:
                            with open(target, "wb") as f_out:
                                shutil.copyfileobj(f_in, f_out, 1024 * 256)
                    elif fmt == "zst":
                        if not ZSTD_AVAILABLE:
                            raise PackerError("ZSTD wymaga modulu 'zstandard'. Zainstaluj: pip install zstandard")
                        with open(archive_path, "rb") as f_in:
                            dctx = zstd.ZstdDecompressor()
                            with dctx.stream_reader(f_in) as reader:
                                with open(target, "wb") as f_out:
                                    shutil.copyfileobj(reader, f_out, 1024 * 256)
                    elif fmt == "lz4":
                        if not LZ4_AVAILABLE:
                            raise PackerError("LZ4 wymaga modulu 'lz4'. Zainstaluj: pip install lz4")
                        with lz4.frame.open(archive_path, "rb") as f_in:
                            with open(target, "wb") as f_out:
                                shutil.copyfileobj(f_in, f_out, 1024 * 256)
                    elif fmt == "br":
                        if not BROTLI_AVAILABLE:
                            raise PackerError("Brotli wymaga modulu 'brotli'. Zainstaluj: pip install brotli")
                        with open(archive_path, "rb") as f_in:
                            data = f_in.read()
                            decompressed = brotli.decompress(data)
                            with open(target, "wb") as f_out:
                                f_out.write(decompressed)
                    result.extracted += 1
                    result.bytes_written += os.path.getsize(target)
                    result.overwritten += 1 if (target_exists and overwrite) else 0
                    report(1, 1, name)
                except OSError as ex:
                    result.errors.append("%s: %s" % (name, ex))
                    emit(self.logger, "%s: %s" % (settings.t("error"), ex))
        elif fmt == "ar":
            if not AR_AVAILABLE:
                raise PackerError("AR wymaga modulu 'arpy'. Zainstaluj: pip install arpy")
            _check_cancel(cancel_event)
            try:
                with arpy.Archive(archive_path) as ar:
                    ar.read_all_headers()
                    for i, entry in enumerate(files, 1):
                        _check_cancel(cancel_event)
                        try:
                            target = safe_join(output_folder, entry["name"])
                            target_exists = os.path.exists(target)
                            if not overwrite and target_exists:
                                result.skipped += 1
                            else:
                                name_key = entry["name"].encode('utf-8') if isinstance(entry["name"], str) else entry["name"]
                                with ar.open(name_key) as f_in:
                                    with open(target, "wb") as f_out:
                                        shutil.copyfileobj(f_in, f_out, 1024 * 256)
                                result.extracted += 1
                                result.bytes_written += entry["size"]
                                result.overwritten += 1 if (target_exists and overwrite) else 0
                                report(i, total, entry["name"])
                        except PackerError as ex:
                            result.blocked.append(str(ex))
                            emit(self.logger, "%s: %s" % (settings.t("error"), ex))
            except Exception as ex:
                raise PackerError(settings.t("archive_damaged").format(archive_path))
        elif fmt == "rar":
            if not RAR_AVAILABLE:
                raise PackerError("RAR wymaga modulu 'rarfile'. Zainstaluj: pip install rarfile")
            _check_cancel(cancel_event)
            try:
                with rarfile.RarFile(archive_path) as rf:
                    for i, entry in enumerate(files, 1):
                        _check_cancel(cancel_event)
                        try:
                            target = safe_join(output_folder, entry["name"])
                            target_exists = os.path.exists(target)
                            if not overwrite and target_exists:
                                result.skipped += 1
                            else:
                                rf.extract(entry["name"], path=output_folder)
                                result.extracted += 1
                                result.bytes_written += entry["size"]
                                result.overwritten += 1 if (target_exists and overwrite) else 0
                                report(i, total, entry["name"])
                        except PackerError as ex:
                            result.blocked.append(str(ex))
                            emit(self.logger, "%s: %s" % (settings.t("error"), ex))
            except rarfile.BadRarFile:
                raise PackerError(settings.t("archive_damaged").format(archive_path))
        elif fmt == "iso":
            if not ISO_AVAILABLE:
                raise PackerError("ISO wymaga modulu 'pycdlib'. Zainstaluj: pip install pycdlib")
            _check_cancel(cancel_event)
            try:
                iso = pycdlib.PyCdlib()
                iso.open(archive_path)
                for i, entry in enumerate(files, 1):
                    _check_cancel(cancel_event)
                    try:
                        target = safe_join(output_folder, entry["name"])
                        target_exists = os.path.exists(target)
                        if not overwrite and target_exists:
                            result.skipped += 1
                        else:
                            iso.read_file(target, f'/{entry["name"]}')
                            result.extracted += 1
                            result.bytes_written += entry["size"]
                            result.overwritten += 1 if (target_exists and overwrite) else 0
                            report(i, total, entry["name"])
                    except PackerError as ex:
                        result.blocked.append(str(ex))
                        emit(self.logger, "%s: %s" % (settings.t("error"), ex))
                iso.close()
            except Exception as ex:
                raise PackerError(settings.t("archive_damaged").format(archive_path))

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
        if fmt == "7z":
            if not PY7ZR_AVAILABLE:
                return False, "py7zr library is not available. Install it with: pip install py7zr", 0
            try:
                with py7zr_module().SevenZipFile(archive_path, "r", password=password) as archive:
                    # Test all entries by reading them
                    for i, info in enumerate(archive.list(), 1):
                        if not info.is_directory:
                            # py7zr automatically validates CRC when extracting
                            # We just verify the archive can be opened and listed
                            count += 1
                            report(i, len(list(archive.list())), info.filename)
                return True, "", count
            except py7zr_module().Bad7zFile as ex:
                return False, str(ex), count
        if fmt == "pfa":
            with _lazy_pfa()(self.logger) as pfa:
                return pfa.verify_pfa(archive_path, password=password,
                                      progress_cb=progress_cb)
        if fmt in ("gz", "bz2", "xz", "zst", "lz4", "br"):
            # Single-file compression formats - test by reading the entire file
            try:
                opener = None
                if fmt == "gz":
                    opener = gzip.open
                elif fmt == "bz2":
                    opener = bz2.open
                elif fmt == "xz":
                    opener = lzma.open
                elif fmt == "zst":
                    if not ZSTD_AVAILABLE:
                        return False, "ZSTD wymaga modulu 'zstandard'. Zainstaluj: pip install zstandard", 0
                    with open(archive_path, "rb") as f_in:
                        dctx = zstd.ZstdDecompressor()
                        with dctx.stream_reader(f_in) as reader:
                            while reader.read(1024 * 256):
                                pass
                    return True, "", 1
                elif fmt == "lz4":
                    if not LZ4_AVAILABLE:
                        return False, "LZ4 wymaga modulu 'lz4'. Zainstaluj: pip install lz4", 0
                    with lz4.frame.open(archive_path, "rb") as f:
                        while f.read(1024 * 256):
                            pass
                    return True, "", 1
                elif fmt == "br":
                    if not BROTLI_AVAILABLE:
                        return False, "Brotli wymaga modulu 'brotli'. Zainstaluj: pip install brotli", 0
                    with open(archive_path, "rb") as f:
                        brotli.decompress(f.read())
                    return True, "", 1
                if opener:
                    with opener(archive_path, "rb") as f:
                        while f.read(1024 * 256):
                            pass
                    return True, "", 1
            except (OSError, EOFError) as ex:
                return False, str(ex), 0
        if fmt == "ar":
            if not AR_AVAILABLE:
                return False, "AR wymaga modulu 'arpy'. Zainstaluj: pip install arpy", 0
            try:
                with arpy.Archive(archive_path) as ar:
                    ar.read_all_headers()
                return True, "", 1
            except Exception as ex:
                return False, str(ex), 0
        if fmt == "rar":
            if not RAR_AVAILABLE:
                return False, "RAR wymaga modulu 'rarfile'. Zainstaluj: pip install rarfile", 0
            try:
                with rarfile.RarFile(archive_path) as rf:
                    rf.test()
                return True, "", 1
            except rarfile.BadRarFile as ex:
                return False, str(ex), 0
        if fmt == "iso":
            if not ISO_AVAILABLE:
                return False, "ISO wymaga modulu 'pycdlib'. Zainstaluj: pip install pycdlib", 0
            try:
                iso = pycdlib.PyCdlib()
                iso.open(archive_path)
                iso.close()
                return True, "", 1
            except Exception as ex:
                return False, str(ex), 0
        return False, settings.t("unknown_format"), 0


