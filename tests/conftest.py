import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ZIPps  # noqa: E402


@pytest.fixture
def tmp_tree(tmp_path):
    """Katalog tymczasowy z przykladowymi plikami do testow CLI."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.txt").write_text("hello world\n", encoding="utf-8")
    (src / "data.bin").write_bytes(bytes(range(256)) * 4)
    sub = src / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested\n", encoding="utf-8")
    return src


@pytest.fixture
def run_cli():
    """Wywolanie cli_main z parsowaniem argumentow (bez GUI)."""
    def _run(argv):
        return ZIPps.cli_main(argv)
    return _run


@pytest.fixture
def quiet():
    return ["-q"]
