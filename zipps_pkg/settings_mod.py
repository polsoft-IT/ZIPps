"""ZIPps - konfiguracja i tlumaczenia."""
import json
import os

from zipps_pkg.core import _fix_default_hash_algo

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
        "btn_generate_h": "C header",
        "btn_generate_raw": "RAW image",
        "btn_generate_dat": "Data file",
        "btn_generate_img": "IMG file",
        "btn_generate_blob": "BLOB file",
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
        "format_gz": "GZIP (.gz)",
        "format_bz2": "BZIP2 (.bz2)",
        "format_xz": "XZ (.xz)",
        "format_7z": "7-Zip (.7z)",
        "format_pfa": "PFA (custom)",
        "compression_level": "Compression level",
        "include_root": "Store folder names in archive",
        "follow_symlinks": "Follow symbolic links",
        "password": "Password (AES-256 for ZIP / 7zAES for 7z / encryption for PFA)",
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
        "group_behavior": "Behaviour",
        "group_performance": "Performance and limits",
        "confirm_before_pack": "Confirm before creating archive",
        "confirm_before_unpack": "Confirm before unpacking",
        "confirm_exit_busy": "Warn when closing during operation",
        "auto_open_output": "Open output folder after operation",
        "remember_window": "Remember window size and position",
        "remember_last_paths": "Remember last used paths",
        "overwrite_mode": "Existing files",
        "overwrite_ask": "Ask each time",
        "overwrite_always": "Overwrite silently",
        "overwrite_skip": "Skip existing",
        "overwrite_rename": "Rename new file (1)",
        "sound_alerts": "Play sound when operation finishes",
        "log_to_file": "Write log to file",
        "log_max_lines": "Log buffer size (lines)",
        "timestamp_log": "Add timestamps to log entries",
        "default_hash_algo": "Default hash algorithm",
        "hash_uppercase": "Show hashes in uppercase",
        "verify_after_pack": "Verify archive right after packing",
        "date_in_archive_name": "Add date to suggested archive name",
        "chunk_size": "I/O chunk size (KB)",
        "parallel_workers": "Parallel file operations",
        "ui_language_hint": "Changes apply immediately",
        "theme_hint": "QSS dark theme",
        "reset_all": "Reset all settings",
        "reset_confirm": "Reset all settings to defaults?",
        "settings_saved": "Settings saved",
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
            "<style>"
            "body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }"
            "h2 { color: #2c3e50; margin-top: 0; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 8px; }"
            "h3 { color: #34495e; margin-top: 20px; margin-bottom: 10px; font-size: 14px; }"
            "table { border-collapse: collapse; width: 100%; margin-bottom: 15px; }"
            "td { padding: 8px 12px; border-bottom: 1px solid #ecf0f1; }"
            "tr:last-child td { border-bottom: none; }"
            ".shortcut { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; "
            "padding: 4px 10px; font-family: 'Consolas', monospace; font-weight: bold; "
            "color: #e74c3c; min-width: 120px; display: inline-block; text-align: center; }"
            ".desc { color: #34495e; }"
            ".category { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); "
            "color: white; padding: 8px 12px; border-radius: 4px; margin-top: 20px; margin-bottom: 10px; }"
            "</style>"
            "<h2>⌨️ Keyboard Shortcuts</h2>"
            "<div class='category'>📂 Navigation</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+1..6</span></td><td class='desc'>Switch between tabs</td></tr>"
            "<tr><td><span class='shortcut'>F1</span></td><td class='desc'>Show this help</td></tr>"
            "</table>"
            "<div class='category'>📦 Packing</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+O</span></td><td class='desc'>Add files (Pack tab)</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+Shift+O</span></td><td class='desc'>Add folder (Pack tab)</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+E</span></td><td class='desc'>Create archive</td></tr>"
            "<tr><td><span class='shortcut'>Del</span></td><td class='desc'>Remove selected from list</td></tr>"
            "</table>"
            "<div class='category'>📂 Unpacking</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+U</span></td><td class='desc'>Unpack all</td></tr>"
            "<tr><td><span class='shortcut'>F5</span></td><td class='desc'>Refresh / validate</td></tr>"
            "</table>"
            "<div class='category'>🛠️ Tools</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+G</span></td><td class='desc'>Generate file</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+Shift+H</span></td><td class='desc'>Hash file</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+L</span></td><td class='desc'>Clear log</td></tr>"
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
        "unknown_gen_kind": "Unknown file kind: %s",
        "cli_no_files": "No files to pack.",
    },
    "pl": {
        "app_title": "Pro File Packer Enterprise",
        "menu_file": "&Plik",
        "menu_tools": "&Narzędzia",
        "menu_view": "&Widok",
        "menu_help": "&Pomoc",
        "tab_generate": "Generator plików",
        "tab_pack": "Pakowanie",
        "tab_unpack": "Rozpakowywanie",
        "tab_security": "Bezpieczeństwo",
        "tab_settings": "Ustawienia",
        "lang_label": "Język",
        "select_files": "Wybierz pliki",
        "select_folder": "Wybierz folder",
        "select_archive": "Wybierz archiwum",
        "output_folder": "Folder wyjściowy",
        "archive_format": "Format archiwum",
        "btn_pack": "Pakuj",
        "btn_unpack": "Rozpakuj",
        "btn_generate_text": "Plik tekstowy",
        "btn_generate_bin": "Plik binarny",
        "btn_generate_pyc": "Python .pyc",
        "btn_generate_c": "Plik C",
        "btn_generate_cpp": "Plik C++",
        "btn_generate_h": "Nagłówek C",
        "btn_generate_raw": "Obraz RAW",
        "btn_generate_dat": "Plik danych",
        "btn_generate_img": "Plik IMG",
        "btn_generate_blob": "Plik BLOB",
        "btn_generate_json": "Dane JSON",
        "btn_generate_markdown": "Markdown",
        "btn_generate_script": "Skrypt Python",
        "file_name": "Nazwa pliku",
        "file_ext": "Rozszerzenie",
        "bin_size": "Rozmiar binarny (bajty)",
        "code_area": "Zawartość / kod Pythona",
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
        "pfa_create": "Utwórz archiwum PFA",
        "pfa_unpack": "Rozpakuj archiwum PFA",
        "pfa_file": "Plik PFA",
        "error": "Błąd",
        "generated": "Wygenerowano plik: ",
        "packed": "Utworzono archiwum: ",
        "unpacked": "Rozpakowano archiwum do: ",
        "drag_hint": "Przeciągnij pliki lub archiwa tutaj",
        # --- v2 ---
        "group_source": "Pliki do spakowania",
        "group_output": "Archiwum",
        "group_archive": "Archiwum",
        "group_extract": "Opcje rozpakowywania",
        "group_archive_tools": "Narzędzia archiwum",
        "group_hash": "Sumy kontrolne plików",
        "group_pfa": "Archiwa własne PFA",
        "group_appearance": "Wygląd i zachowanie",
        "group_about": "O programie",
        "group_generator": "Generator",
        "add_files": "Dodaj pliki",
        "add_folder": "Dodaj folder",
        "remove": "Usuń",
        "clear": "Wyczyść",
        "save_list": "Zapisz liste",
        "load_list": "Wczytaj liste",
        "items_count": "{0} plik(ow), {1}",
        "archive_path": "Ścieżka archiwum",
        "browse": "Przeglądaj...",
        "format_zip": "ZIP (.zip)",
        "format_tar": "TAR (.tar)",
        "format_targz": "TAR GZIP (.tar.gz)",
        "format_tarbz2": "TAR BZIP2 (.tar.bz2)",
        "format_tarxz": "TAR XZ (.tar.xz)",
        "format_gz": "GZIP (.gz)",
        "format_bz2": "BZIP2 (.bz2)",
        "format_xz": "XZ (.xz)",
        "format_7z": "7-Zip (.7z)",
        "format_pfa": "PFA (własny)",
        "compression_level": "Poziom kompresji",
        "include_root": "Zachowaj nazwy folderow w archiwum",
        "follow_symlinks": "Podazaj za dowiazaniami symbolicznymi",
        "password": "Hasło (AES-256 dla ZIP / 7zAES dla 7z / szyfrowanie PFA)",
        "confirm_password": "Powtórz hasło",
        "password_optional": "(opcjonalne)",
        "add_to_archive": "Dopisz do istniejacego archiwum",
        "create_archive": "Utwórz archiwum",
        "load_archive": "Wczytaj",
        "verify_archive": "Testuj archiwum",
        "filter": "Filtruj",
        "select_all": "Zaznacz wszystko",
        "select_none": "Odznacz wszystko",
        "folder_not_exist": "Folder nie istnieje",
        "file_not_exist": "Plik nie istnieje",
        "no_files": "Brak plików do przetworzenia",
        "invalid_size": "Nieprawidłowy rozmiar",
        "password_mismatch": "Hasla nie sa identyczne!",
        "need_password": "To archiwum jest zaszyfrowane. Podaj haslo i sprobuj ponownie.",
        "wrong_password": "Bledne haslo lub uszkodzone archiwum.",
        "unsupported_zstd": "Ta kompresja wymaga Pythona 3.14+ (ZIP_ZSTANDARD).",
        "unknown_format": "Nierozpoznany format archiwum",
        "archive_ok": "Test archiwum zakończony: {0} plik(ów), {1}",
        "archive_damaged": "Archiwum jest uszkodzone: {0}",
        "unknown_entry": "Nieznany wpis",
        "hash_multi": "Haszuj katalog",
        "compare": "Porównaj z oczekiwanym",
        "copy": "Kopiuj",
        "save": "Zapisz do pliku",
        "hash_empty": "Podaj ścieżkę pliku i oczekiwany hash",
        "hash_match": "Hash ZGODNY z oczekiwanym.",
        "hash_mismatch": "Hash NIE zgadza się z oczekiwanym!",
        "done": "Gotowe: {0}",
        "busy": "Inna operacja nadal trwa, poczekaj.",
        "status_working": "Praca...",
        "status_done": "Gotowe",
        "status_error": "Błąd",
        "status_cancelled": "Anulowano",
        "status_paths": "{0} plik(ow), {1}",
        "cancelled": "Operacja przerwana",
        "appearance_qss": "Włącz ciemny motyw (QSS)",
        "appearance_default_dir": "Domyślny folder",
        "language": "Język",
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
        "quit": "Zakończ",
        "clear_log": "Wyczysc log",
        "save_log": "Zapisz log",
        "open_in_editor": "Otwórz w edytorze",
        "open_folder": "Otwórz folder",
        "total_size": "Razem",
        "scan_hidden": "Pomijaj pliki ukryte",
        "include_dirs": "Dodawaj puste foldery",
        "files": "Pliki",
        "folder": "Folder",
        "inspect": "Sprawdź plik",
        "inspect_pyc": "Sprawdź .pyc",
        "info_title": "Informacje o pliku",
        "pattern_help": "Dozwolone wzorce: *.py, *.txt;*.md",
        "font_size": "Rozmiar czcionki",
        "modal_dialogs": "Pokazuj okna potwierdzeń (inaczej log + pasek statusu)",
        "group_behavior": "Zachowanie",
        "group_performance": "Wydajnosc i limity",
        "confirm_before_pack": "Potwierdzaj przed utworzeniem archiwum",
        "confirm_before_unpack": "Potwierdzaj przed rozpakowaniem",
        "confirm_exit_busy": "Ostrzegaj przy zamknięciu w trakcie operacji",
        "auto_open_output": "Otwieraj folder wyjsciowy po operacji",
        "remember_window": "Zapamietuj rozmiar i pozycje okna",
        "remember_last_paths": "Zapamietuj ostatnio używane ścieżki",
        "overwrite_mode": "Istniejące pliki",
        "overwrite_ask": "Pytaj za kazdym razem",
        "overwrite_always": "Nadpisuj bez pytania",
        "overwrite_skip": "Pomijaj istniejace",
        "overwrite_rename": "Zmieniaj nazwe nowego (1)",
        "sound_alerts": "Odtwarzaj dźwięk po zakończeniu operacji",
        "log_to_file": "Zapisuj log do pliku",
        "log_max_lines": "Rozmiar bufora logu (linie)",
        "timestamp_log": "Dodawaj znaczniki czasu do logu",
        "default_hash_algo": "Domyślny algorytm hashowania",
        "hash_uppercase": "Pokazuj hashe wielkimi literami",
        "verify_after_pack": "Testuj archiwum zaraz po pakowaniu",
        "date_in_archive_name": "Dodawaj datę do proponowanej nazwy archiwum",
        "chunk_size": "Rozmiar bloku I/O (KB)",
        "parallel_workers": "Równoległe operacje na plikach",
        "ui_language_hint": "Zmiany stosowane od razu",
        "theme_hint": "Ciemny motyw QSS",
        "reset_all": "Przywróć ustawienia domyślne",
        "reset_confirm": "Przywrócić wszystkie ustawienia do domyślnych?",
        "settings_saved": "Ustawienia zapisane",
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
        "cmd_copy_path": "Kopiuj ścieżkę",
        "cmd_reveal": "Pokaz w Eksploratorze",
        "cmd_remove": "Usun z listy",
        "shortcut_help_title": "Skroty klawiaturowe",
        "shortcut_help": (
            "<style>"
            "body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }"
            "h2 { color: #2c3e50; margin-top: 0; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 8px; }"
            "h3 { color: #34495e; margin-top: 20px; margin-bottom: 10px; font-size: 14px; }"
            "table { border-collapse: collapse; width: 100%; margin-bottom: 15px; }"
            "td { padding: 8px 12px; border-bottom: 1px solid #ecf0f1; }"
            "tr:last-child td { border-bottom: none; }"
            ".shortcut { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; "
            "padding: 4px 10px; font-family: 'Consolas', monospace; font-weight: bold; "
            "color: #e74c3c; min-width: 120px; display: inline-block; text-align: center; }"
            ".desc { color: #34495e; }"
            ".category { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); "
            "color: white; padding: 8px 12px; border-radius: 4px; margin-top: 20px; margin-bottom: 10px; }"
            "</style>"
            "<h2>⌨️ Skroty klawiaturowe</h2>"
            "<div class='category'>📂 Nawigacja</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+1..6</span></td><td class='desc'>Przelaczanie zakladek</td></tr>"
            "<tr><td><span class='shortcut'>F1</span></td><td class='desc'>Pokaz te pomoc</td></tr>"
            "</table>"
            "<div class='category'>📦 Pakowanie</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+O</span></td><td class='desc'>Dodaj pliki (zakladka Pakowanie)</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+Shift+O</span></td><td class='desc'>Dodaj folder (zakladka Pakowanie)</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+E</span></td><td class='desc'>Utworz archiwum</td></tr>"
            "<tr><td><span class='shortcut'>Del</span></td><td class='desc'>Usun zaznaczone z listy</td></tr>"
            "</table>"
            "<div class='category'>📂 Rozpakowywanie</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+U</span></td><td class='desc'>Rozpakuj wszystko</td></tr>"
            "<tr><td><span class='shortcut'>F5</span></td><td class='desc'>Odswiez / waliduj</td></tr>"
            "</table>"
            "<div class='category'>🛠️ Narzedzia</div>"
            "<table>"
            "<tr><td><span class='shortcut'>Ctrl+G</span></td><td class='desc'>Wygeneruj plik</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+Shift+H</span></td><td class='desc'>Haszuj plik</td></tr>"
            "<tr><td><span class='shortcut'>Ctrl+L</span></td><td class='desc'>Wyczysc log</td></tr>"
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
        "act_quit": "Zakończ",
        "unknown_gen_kind": "Nieznany rodzaj pliku: %s",
        "cli_no_files": "Brak plików do spakowania.",
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
        # --- zachowanie ---
        "confirm_before_pack": False,
        "confirm_before_unpack": False,
        "confirm_exit_busy": True,
        "auto_open_output": False,
        "remember_last_paths": True,
        "overwrite_policy": "ask",    # ask|always|skip|rename
        "sound_alerts": False,
        "verify_after_pack": False,
        "date_in_archive_name": False,
        # --- wyglad ---
        "remember_window": True,
        "window_geometry": "",        # "x,y,w,h"
        # --- log ---
        "log_to_file": True,
        "log_max_lines": 5000,
        "timestamp_log": False,
        # --- bezpieczenstwo / narzedzia ---
        "default_hash_algo": "sha256",
        "hash_uppercase": False,
        # --- wydajnosc ---
        "chunk_size_kb": 256,
        "parallel_workers": 1,
    }

    #: klucze, ktore nie sa zapisywane do pliku (stan ulotny sesji)
    VOLATILE_KEYS = ("window_geometry",)

    def __init__(self, path: str | None = None):
        self.path = path or config_path()
        for key, value in self.DEFAULTS.items():
            setattr(self, key, value)
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
                value = data[key]
                # korekta typow - chroni przed uszkodzonym/ręcznie edytowanym plikiem
                default = self.DEFAULTS[key]
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, int) and not isinstance(default, bool):
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        value = default
                setattr(self, key, value)
        if self.language not in LANG:
            self.language = self.DEFAULTS["language"]
        if self.overwrite_policy not in ("ask", "always", "skip", "rename"):
            self.overwrite_policy = "ask"
        self.chunk_size_kb = max(16, min(4096, int(self.chunk_size_kb)))
        self.parallel_workers = max(1, min(16, int(self.parallel_workers)))
        self.log_max_lines = max(100, min(100000, int(self.log_max_lines)))

    def save(self) -> bool:
        data = {key: getattr(self, key) for key in self.DEFAULTS
                if key not in self.VOLATILE_KEYS}
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
_fix_default_hash_algo(settings)
