"""ZIPps - pakowanie archiwow (ZIP, TAR+, gz/bz2/xz, 7z, zstd, lz4)."""
import bz2
import gzip
import lzma
import os
import shutil

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
    detect_format, ensure_archive_ext, iter_files, normalize_relative,
    open_tar, open_zip, FORMAT_EXTS, TAR_MODES, PY7ZR_AVAILABLE,
    ZSTD_AVAILABLE, LZ4_AVAILABLE, BROTLI_AVAILABLE, AR_AVAILABLE,
)
from zipps_pkg.settings_mod import settings
from zipps_pkg.logging_mod import Logger


def _lazy_pfa():
    """Ladowskie tworzenie PFAFormat (unikanie importu cyklicznego)."""
    from zipps_pkg.pfa import PFAFormat
    return PFAFormat()
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
        if level is None:
            level = 9
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

        with open_tar(archive_path, mode, fmt, level) as tf:
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

    def pack_tar_gz(self, files, archive_path, progress_cb=None, level=None, **kwargs) -> PackResult:
        return self.pack_tar(files, archive_path, mode="w:gz", fmt="targz",
                             progress_cb=progress_cb, level=level, **kwargs)

    def pack_tar_bz2(self, files, archive_path, progress_cb=None, level=None, **kwargs) -> PackResult:
        return self.pack_tar(files, archive_path, mode="w:bz2", fmt="tarbz2",
                             progress_cb=progress_cb, level=level, **kwargs)

    def pack_tar_xz(self, files, archive_path, progress_cb=None, level=None, **kwargs) -> PackResult:
        return self.pack_tar(files, archive_path, mode="w:xz", fmt="tarxz",
                             progress_cb=progress_cb, level=level, **kwargs)

    def pack_tar_zst(self, files, archive_path, progress_cb=None, level=None,
                     cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pliki do formatu .tar.zst (tar + zstd)."""
        if not ZSTD_AVAILABLE:
            raise PackerError("ZSTD wymaga modulu 'zstandard'. Zainstaluj: pip install zstandard")
        return self.pack_tar(files, archive_path, mode="w|zstd", fmt="tarzst",
                             progress_cb=progress_cb, level=level, cancel_event=cancel_event, **kwargs)

    def pack_tar_lz4(self, files, archive_path, progress_cb=None, level=None,
                     cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pliki do formatu .tar.lz4 (tar + lz4)."""
        if not LZ4_AVAILABLE:
            raise PackerError("LZ4 wymaga modulu 'lz4'. Zainstaluj: pip install lz4")
        return self.pack_tar(files, archive_path, mode="w|lz4", fmt="tarlz4",
                             progress_cb=progress_cb, level=level, cancel_event=cancel_event, **kwargs)

    def pack_tar_br(self, files, archive_path, progress_cb=None, level=None,
                    cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pliki do formatu .tar.br (tar + brotli)."""
        if not BROTLI_AVAILABLE:
            raise PackerError("Brotli wymaga modulu 'brotli'. Zainstaluj: pip install brotli")
        # TAR + Brotli - najpierw pakujemy jako TAR, potem kompresujemy Brotli
        temp_tar = archive_path.replace(".br", ".tar")
        if archive_path.endswith(".tar.br"):
            temp_tar = archive_path[:-3]
        result = self.pack_tar(files, temp_tar, mode="w", fmt="tar",
                               progress_cb=progress_cb, cancel_event=cancel_event, **kwargs)
        _check_cancel(cancel_event)
        try:
            if level is None:
                level = 11
            level = max(0, min(11, int(level)))
            with open(temp_tar, "rb") as f_in:
                with open(archive_path, "wb") as f_out:
                    compressor = brotli.Compressor(quality=level)
                    for chunk in iter(lambda: f_in.read(1024 * 256), b""):
                        f_out.write(compressor.compress(chunk))
                    f_out.write(compressor.finish())
            result.size_after = os.path.getsize(archive_path)
            os.remove(temp_tar)
        except Exception as ex:
            if os.path.exists(temp_tar):
                os.remove(temp_tar)
            raise PackerError("TAR+Brotli pack failed: %s" % ex)
        return result

    def pack_gz(self, files, archive_path, progress_cb=None, level=None,
                cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pojedynczy plik do formatu .gz (gzip)."""
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if len(files) != 1:
            raise PackerError("GZIP supports only a single file")
        source = files[0]
        archive_path = ensure_archive_ext(archive_path, "gz")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "GZIP: " + archive_path)

        if level is None:
            level = 9
        level = max(0, min(9, int(level)))

        _check_cancel(cancel_event)
        try:
            result.size_before = os.path.getsize(source)
            with open(source, "rb") as f_in:
                with gzip.open(archive_path, "wb", compresslevel=level) as f_out:
                    shutil.copyfileobj(f_in, f_out, 1024 * 256)
            result.added = 1
            result.entries = 1
            result.size_after = os.path.getsize(archive_path)
            report(1, 1, source)
        except OSError as ex:
            result.skipped += 1
            result.errors.append("%s: %s" % (source, ex))
            emit(self.logger, "%s: %s" % (settings.t("error"), ex))

        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_bz2(self, files, archive_path, progress_cb=None, level=None,
                 cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pojedynczy plik do formatu .bz2 (bzip2)."""
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if len(files) != 1:
            raise PackerError("BZIP2 supports only a single file")
        source = files[0]
        archive_path = ensure_archive_ext(archive_path, "bz2")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "BZIP2: " + archive_path)

        if level is None:
            level = 9
        level = max(1, min(9, int(level)))

        _check_cancel(cancel_event)
        try:
            result.size_before = os.path.getsize(source)
            with open(source, "rb") as f_in:
                with bz2.open(archive_path, "wb", compresslevel=level) as f_out:
                    shutil.copyfileobj(f_in, f_out, 1024 * 256)
            result.added = 1
            result.entries = 1
            result.size_after = os.path.getsize(archive_path)
            report(1, 1, source)
        except OSError as ex:
            result.skipped += 1
            result.errors.append("%s: %s" % (source, ex))
            emit(self.logger, "%s: %s" % (settings.t("error"), ex))

        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_xz(self, files, archive_path, progress_cb=None, level=None,
                cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pojedynczy plik do formatu .xz (xz/lzma)."""
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if len(files) != 1:
            raise PackerError("XZ supports only a single file")
        source = files[0]
        archive_path = ensure_archive_ext(archive_path, "xz")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "XZ: " + archive_path)

        if level is None:
            level = 9
        level = max(0, min(9, int(level)))

        _check_cancel(cancel_event)
        try:
            result.size_before = os.path.getsize(source)
            with open(source, "rb") as f_in:
                with lzma.open(archive_path, "wb", preset=level) as f_out:
                    shutil.copyfileobj(f_in, f_out, 1024 * 256)
            result.added = 1
            result.entries = 1
            result.size_after = os.path.getsize(archive_path)
            report(1, 1, source)
        except OSError as ex:
            result.skipped += 1
            result.errors.append("%s: %s" % (source, ex))
            emit(self.logger, "%s: %s" % (settings.t("error"), ex))

        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_zst(self, files, archive_path, progress_cb=None, level=None,
                 cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pojedynczy plik do formatu .zst (zstandard)."""
        if not ZSTD_AVAILABLE:
            raise PackerError("ZSTD wymaga modulu 'zstandard'. Zainstaluj: pip install zstandard")
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if len(files) != 1:
            raise PackerError("ZSTD supports only a single file")
        source = files[0]
        archive_path = ensure_archive_ext(archive_path, "zst")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "ZSTD: " + archive_path)

        if level is None:
            level = 19
        level = max(1, min(22, int(level)))

        _check_cancel(cancel_event)
        try:
            result.size_before = os.path.getsize(source)
            cctx = zstd.ZstdCompressor(level=level)
            with open(source, "rb") as f_in:
                with open(archive_path, "wb") as f_out:
                    with cctx.stream_writer(f_out) as compressor:
                        shutil.copyfileobj(f_in, compressor, 1024 * 256)
            result.added = 1
            result.entries = 1
            result.size_after = os.path.getsize(archive_path)
            report(1, 1, source)
        except OSError as ex:
            result.skipped += 1
            result.errors.append("%s: %s" % (source, ex))
            emit(self.logger, "%s: %s" % (settings.t("error"), ex))

        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_lz4(self, files, archive_path, progress_cb=None, level=None,
                 cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pojedynczy plik do formatu .lz4."""
        if not LZ4_AVAILABLE:
            raise PackerError("LZ4 wymaga modulu 'lz4'. Zainstaluj: pip install lz4")
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if len(files) != 1:
            raise PackerError("LZ4 supports only a single file")
        source = files[0]
        archive_path = ensure_archive_ext(archive_path, "lz4")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "LZ4: " + archive_path)

        if level is None:
            level = 1
        level = max(0, min(16, int(level)))

        _check_cancel(cancel_event)
        try:
            result.size_before = os.path.getsize(source)
            with open(source, "rb") as f_in:
                with lz4.frame.open(archive_path, "wb", compression_level=level) as f_out:
                    shutil.copyfileobj(f_in, f_out, 1024 * 256)
            result.added = 1
            result.entries = 1
            result.size_after = os.path.getsize(archive_path)
            report(1, 1, source)
        except OSError as ex:
            result.skipped += 1
            result.errors.append("%s: %s" % (source, ex))
            emit(self.logger, "%s: %s" % (settings.t("error"), ex))

        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_br(self, files, archive_path, progress_cb=None, level=None,
                cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pojedynczy plik do formatu .br (Brotli)."""
        if not BROTLI_AVAILABLE:
            raise PackerError("Brotli wymaga modulu 'brotli'. Zainstaluj: pip install brotli")
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if len(files) != 1:
            raise PackerError("Brotli supports only a single file")
        source = files[0]
        archive_path = ensure_archive_ext(archive_path, "br")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "Brotli: " + archive_path)

        if level is None:
            level = 11
        level = max(0, min(11, int(level)))

        _check_cancel(cancel_event)
        try:
            result.size_before = os.path.getsize(source)
            with open(source, "rb") as f_in:
                with open(archive_path, "wb") as f_out:
                    compressor = brotli.Compressor(quality=level)
                    for chunk in iter(lambda: f_in.read(1024 * 256), b""):
                        f_out.write(compressor.compress(chunk))
                    f_out.write(compressor.finish())
            result.added = 1
            result.entries = 1
            result.size_after = os.path.getsize(archive_path)
            report(1, 1, source)
        except OSError as ex:
            result.skipped += 1
            result.errors.append("%s: %s" % (source, ex))
            emit(self.logger, "%s: %s" % (settings.t("error"), ex))

        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_ar(self, files, archive_path, progress_cb=None, bases=None,
                keep_relative=True, cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pliki do formatu .ar (biblioteki statyczne)."""
        if not AR_AVAILABLE:
            raise PackerError("AR wymaga modulu 'arpy'. Zainstaluj: pip install arpy")
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if not files:
            raise PackerError(settings.t("no_files"))

        archive_path = ensure_archive_ext(archive_path, "ar")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "AR: " + archive_path)

        queue = [(f, self.arcname_for(f, bases, keep_relative)) for f in files]
        total = len(queue)
        step = 0

        _check_cancel(cancel_event)
        try:
            with arpy.Archive(archive_path, 'w') as ar:
                for path, arcname in queue:
                    _check_cancel(cancel_event)
                    step += 1
                    try:
                        size = os.path.getsize(path)
                        result.size_before += size
                        with open(path, 'rb') as f:
                            ar.add_file(arcname.encode('utf-8'), f)
                        result.added += 1
                        report(step, total, arcname)
                    except OSError as ex:
                        result.skipped += 1
                        result.errors.append("%s: %s" % (path, ex))
                        emit(self.logger, "%s: %s" % (settings.t("error"), ex))

            result.entries = result.added
            result.size_after = os.path.getsize(archive_path)
        except Exception as ex:
            raise PackerError("AR pack failed: %s" % ex)

        emit(self.logger, settings.t("packed") + archive_path)
        return result

    def pack_7z(self, files, archive_path, progress_cb=None, level=None,
                password=None, bases=None, keep_relative=True,
                cancel_event=None, **kwargs) -> PackResult:
        """Pakuje pliki do formatu .7z (7-Zip) przy uzyciu py7zr."""
        if not PY7ZR_AVAILABLE:
            raise PackerError("py7zr library is not available. Install it with: pip install py7zr")

        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if not files:
            raise PackerError(settings.t("no_files"))

        archive_path = ensure_archive_ext(archive_path, "7z")
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        result = PackResult(path=archive_path)
        report = _make_progress(progress_cb)
        emit(self.logger, "7z: " + archive_path)

        # Kompresja level (dla 7z: 0-9, domyslnie 9)
        if level is None:
            level = 9
        level = max(0, min(9, int(level)))

        # Przygotuj listy plikow z nazwami w archiwum
        queue = [(f, self.arcname_for(f, bases, keep_relative)) for f in files]
        total = len(queue)
        step = 0

        _check_cancel(cancel_event)
        try:
            # Konfiguracja filtra kompresji
            filters = [{"id": py7zr_module().FILTER_LZMA2, "preset": level}]

            with py7zr_module().SevenZipFile(archive_path, "w", filters=filters, password=password) as archive:
                for path, arcname in queue:
                    _check_cancel(cancel_event)
                    step += 1
                    try:
                        size = os.path.getsize(path)
                        result.size_before += size
                        # py7zr expects arcname to be relative to archive root
                        archive.write(path, arcname)
                        result.added += 1
                        report(step, total, arcname)
                    except OSError as ex:
                        result.skipped += 1
                        result.errors.append("%s: %s" % (path, ex))
                        emit(self.logger, "%s: %s" % (settings.t("error"), ex))

            result.entries = result.added
            result.size_after = os.path.getsize(archive_path)
        except Exception as ex:
            raise PackerError("7z pack failed: %s" % ex)

        emit(self.logger, settings.t("packed") + archive_path)
        emit(self.logger, "%s %s (%s -> %s, -%0.1f%%)" % (
            settings.t("total_size"), human_size(result.size_after),
            human_size(result.size_before), human_size(result.size_after),
            result.ratio))
        return result

    # -- dyspozytor ---------------------------------------------------
    def pack(self, files, archive_path, fmt="zip", progress_cb=None,
             keywords=None, **kwargs) -> PackResult:
        """Uniwersalna funkcja pakowania: fmt = zip|tar|targz|tarbz2|tarxz|tarzst|tarlz4|tarbr|gz|bz2|xz|zst|lz4|br|ar|7z|pfa."""
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
        if fmt == "gz":
            return self.pack_gz(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "bz2":
            return self.pack_bz2(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "xz":
            return self.pack_xz(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "zst":
            return self.pack_zst(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "lz4":
            return self.pack_lz4(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "br":
            return self.pack_br(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "ar":
            return self.pack_ar(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "tarzst":
            return self.pack_tar_zst(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "tarlz4":
            return self.pack_tar_lz4(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "tarbr":
            return self.pack_tar_br(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "7z":
            return self.pack_7z(files, archive_path, progress_cb=progress_cb, **kwargs)
        if fmt == "pfa":
            pfa = _lazy_pfa()
            return pfa.create_pfa(files, archive_path,
                                  progress_cb=progress_cb,
                                  password=kwargs.get("password"),
                                  bases=kwargs.get("bases"),
                                  keep_relative=kwargs.get("keep_relative", True),
                                  cancel_event=kwargs.get("cancel_event"))
        raise PackerError("unsupported format: %s" % fmt)

