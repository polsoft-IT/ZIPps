"""ZIPps - interfejs wiersza polecen."""
import argparse
import json
import os
import sys

from typing import Optional, Sequence

from zipps_pkg.version import __version__, __app_name__
from zipps_pkg.core import (
    PackerError, Empty, emit, human_size, detect_format, SUPPORTED_HASHES,
)
from zipps_pkg.settings_mod import settings
from zipps_pkg.logging_mod import Logger
from zipps_pkg.generator import FileGenerator
from zipps_pkg.packer import PackerCore
from zipps_pkg.unpacker import UnpackerCore
from zipps_pkg.security import SecurityCore, file_info, hash_file

# Import GUI function if available
try:
    from zipps_pkg.gui import run_gui
except ImportError:
    run_gui = None

# =====================================================================
#  Interfejs wiersza polecen (CLI)
# =====================================================================

def _cli_progress(percent: int, message: str = "") -> None:
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
                        choices=["zip", "tar", "targz", "tarbz2", "tarxz", "tarzst", "tarlz4", "tarbr",
                                 "gz", "bz2", "xz", "zst", "lz4", "br", "ar", "7z", "pfa"],
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
    p_gen.add_argument("kind", choices=["text", "bin", "pyc", "py", "c", "cpp", "h", "raw",
                                        "json", "md", "dat", "img", "blob"])
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
        print(settings.t("cli_no_files"), file=sys.stderr)
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
    handler = _GEN_KINDS.get(args.kind)
    if handler is None:
        msg = settings.t("unknown_gen_kind") % args.kind
        try:
            logger.error(msg)
        except Exception:  # noqa: BLE001 - logger moze byc atrapa
            pass
        print(msg, file=sys.stderr)
        return 2
    print(handler(gen, args))
    return 0


#: mapa rodzaju pliku -> funkcja (gen, args) -> sciezka utworzonego pliku
_GEN_KINDS = {
    "text": lambda gen, args: gen.generate_text_file(
        args.dir, args.name, "txt", args.content or "Hello from ZIPps!\n"),
    "bin": lambda gen, args: gen.generate_binary_file(
        args.dir, args.name, "bin", args.size),
    "pyc": lambda gen, args: gen.generate_pyc(
        args.dir, args.name, args.content or "print('Hello from .pyc')"),
    "py": lambda gen, args: gen.generate_python_script(
        args.dir, args.name, args.content),
    "c": lambda gen, args: gen.generate_c_file(args.dir, args.name, args.content),
    "cpp": lambda gen, args: gen.generate_cpp_file(args.dir, args.name, args.content),
    "h": lambda gen, args: gen.generate_h_file(args.dir, args.name, args.content),
    "raw": lambda gen, args: gen.generate_raw_image(
        args.dir, args.name, args.size, args.height or args.size),
    "json": lambda gen, args: gen.generate_json_file(args.dir, args.name, args.content),
    "md": lambda gen, args: gen.generate_markdown_file(args.dir, args.name, args.content),
    "dat": lambda gen, args: gen.generate_dat_file(args.dir, args.name, args.size),
    "img": lambda gen, args: gen.generate_img_file(args.dir, args.name, args.size),
    "blob": lambda gen, args: gen.generate_blob_file(args.dir, args.name, args.size),
}


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
        if run_gui is None:
            print("GUI is not available - PySide6 is not installed.")
            return 1
        return run_gui(getattr(args, "paths", []) or [])

    handler = CLI_COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    quiet = bool(getattr(args, "quiet", False))
    logger = Empty() if quiet else Logger()
    # w trybie -q nie rysujemy paska postepu (nie zasmieca wyjscia i logow)
    progress = None if quiet else _cli_progress
    logger.log("ZIPps v%s started (CLI)" % __version__)
    return handler(args, logger, progress)

