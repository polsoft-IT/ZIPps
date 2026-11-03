"""Pro File Packer Enterprise - generator plikow, pakowanie, rozpakowywanie,
bezpieczenstwo (hashe, format PFA) oraz GUI (PySide6) i CLI.

Uruchomienie GUI:   python ZIPps.py
Uruchomienie CLI:   python ZIPps.py --help

Logika zyje w pakiecie zipps_pkg; ten plik to cienki punkt wejscia, ktory
re-eksportuje publiczne API dla zgodnosci wstecznej (testy, rozszerzenia).
"""

from zipps_pkg.version import __version__, __app_name__          # noqa: F401
from zipps_pkg.core import (                                      # noqa: F401
    PackerError, Empty, emit, human_size, human_time, unique_path,
    normalize_relative, safe_join, detect_format, ensure_archive_ext,
    strip_archive_ext, iter_files, open_zip, open_tar, _check_cancel,
    _make_progress, archive_file_filter, SUPPORTED_HASHES, ARCHIVE_EXTS,
    FORMAT_EXTS, TAR_MODES, COMPRESS_MODES, ALL_ARCHIVE_EXTS, ALTERNATE_EXTS,
    GEN_PRESETS, DEFAULT_GEN_CODE, PY7ZR_AVAILABLE,
)
from zipps_pkg.settings_mod import LANG, Settings, settings, config_path  # noqa: F401
from zipps_pkg.logging_mod import Logger                          # noqa: F401
from zipps_pkg.generator import FileGenerator                     # noqa: F401
from zipps_pkg.packer import PackResult, PackerCore               # noqa: F401
from zipps_pkg.unpacker import ExtractResult, UnpackerCore        # noqa: F401
from zipps_pkg.pfa import (PFAEntry, PFAFormat, PFA_MAGIC_V1,     # noqa: F401
                           PFA_MAGIC_V2)
from zipps_pkg.security import (SecurityCore, crc32_of_file, hash_file,   # noqa: F401
                                file_info, sniff_magic, describe_pyc,
                                is_probably_text, creation_time)
from zipps_pkg.cli import (build_cli_parser, cli_main, CLI_COMMANDS,      # noqa: F401
                           cli_cmd_pack, cli_cmd_unpack, cli_cmd_list,
                           cli_cmd_hash, cli_cmd_info, cli_cmd_test,
                           cli_cmd_gen, cli_cmd_settings, _cli_progress,
                           _GEN_KINDS)
from zipps_pkg.gui import (QT_AVAILABLE, QT_VERSION, require_qt,          # noqa: F401
                           QtUnavailableError, load_stylesheet,
                           create_application, run_gui, MainWindow)

import sys


def main(argv: list[str] | None = None) -> int:
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
