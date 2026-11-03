"""Testy CLI: pack, unpack, list, hash, info, test, gen."""
import hashlib
import json
import os

import pytest

import ZIPps


def _strip_banner(out):
    lines = out.splitlines()
    return "\n".join(l for l in lines if not l.startswith("ZIPps v"))


# --------------------------------------------------------------- pack
def test_pack_and_unpack_roundtrip_zip(tmp_path, tmp_tree, run_cli, capsys):
    archive = tmp_path / "out.zip"
    assert run_cli(["pack", str(tmp_tree), "-o", str(archive), "-q"]) == 0
    assert archive.exists() and archive.stat().st_size > 0

    dest = tmp_path / "dest"
    assert run_cli(["unpack", str(archive), "-d", str(dest), "-q"]) == 0
    assert (dest / "hello.txt").read_text(encoding="utf-8") == "hello world\n"
    assert (dest / "sub" / "nested.txt").exists()

    out = capsys.readouterr().out
    assert "files" in out


def test_pack_with_password_pfa(tmp_path, tmp_tree, run_cli):
    archive = tmp_path / "secret.pfa"
    assert run_cli(["pack", str(tmp_tree), "-o", str(archive),
                    "--password", "tajne", "-q"]) == 0
    assert archive.exists()
    # lista bez hasla powinna dzialac (nazwy sa jawne) lub rzucic blad obslugiwany
    rc = run_cli(["test", str(archive), "--password", "tajne", "-q"])
    assert rc == 0


def test_pack_filter(tmp_path, tmp_tree, run_cli):
    archive = tmp_path / "filtered.zip"
    assert run_cli(["pack", str(tmp_tree), "-o", str(archive),
                    "--filter", "*.txt", "-q"]) == 0
    entries, _ = ZIPps.UnpackerCore(ZIPps.Empty()).entries(str(archive), None)
    names = [e["name"] for e in entries]
    assert any(n.endswith("hello.txt") for n in names)
    assert not any(n.endswith("data.bin") for n in names)


# --------------------------------------------------------------- list
def test_list_text_and_json(tmp_path, tmp_tree, run_cli, capsys):
    archive = tmp_path / "a.zip"
    assert run_cli(["pack", str(tmp_tree), "-o", str(archive), "-q"]) == 0

    assert run_cli(["list", str(archive)]) == 0
    text = capsys.readouterr().out
    assert "ZIP" in text.upper()
    assert "hello.txt" in text

    assert run_cli(["list", str(archive), "--json"]) == 0
    entries = json.loads(_strip_banner(capsys.readouterr().out))
    names = [e["name"] for e in entries]
    assert any(n.endswith("hello.txt") for n in names)


def test_list_missing_archive_fails(run_cli):
    with pytest.raises((SystemExit, ZIPps.PackerError)):
        run_cli(["list", "nie-ma-takiego.zip"])


# --------------------------------------------------------------- hash
def test_hash_single_file_and_compare(tmp_path, run_cli, capsys):
    f = tmp_path / "f.bin"
    f.write_bytes(b"x" * 128)
    digest = hashlib.sha256(f.read_bytes()).hexdigest()

    assert run_cli(["hash", str(f), "--quiet"]) == 0
    assert digest in capsys.readouterr().out

    assert run_cli(["hash", str(f), "--compare", digest, "-q"]) == 0
    assert "MATCHES" in capsys.readouterr().out.upper()

    rc = run_cli(["hash", str(f), "--compare", "0" * 64, "-q"])
    assert rc == 3


def test_hash_directory(tmp_path, tmp_tree, run_cli, capsys):
    assert run_cli(["hash", str(tmp_tree), "-q"]) == 0
    out = capsys.readouterr().out
    assert "hello.txt" in out and "data.bin" in out


def test_hash_empty_compare_is_error(tmp_path, run_cli):
    f = tmp_path / "f.bin"
    f.write_bytes(b"x")
    assert run_cli(["hash", str(f), "--compare", "   "]) == 2


# --------------------------------------------------------------- info
def test_info_text_and_json(tmp_path, run_cli, capsys):
    f = tmp_path / "info.txt"
    f.write_text("abc", encoding="utf-8")
    assert run_cli(["info", str(f)]) == 0
    assert "info.txt" in capsys.readouterr().out

    assert run_cli(["info", str(f), "--json"]) == 0
    data = json.loads(_strip_banner(capsys.readouterr().out))
    assert data["size"] == 3


# --------------------------------------------------------------- test
def test_test_archive_ok_and_missing(tmp_path, tmp_tree, run_cli, capsys):
    archive = tmp_path / "t.zip"
    assert run_cli(["pack", str(tmp_tree), "-o", str(archive), "-q"]) == 0
    assert run_cli(["test", str(archive), "-q"]) == 0
    capsys.readouterr()

    rc = run_cli(["test", str(archive), "--password", "zle-haslo", "-q"])
    assert rc in (0, 1)  # zip bez hasla: nieuszkodzone; nie moze sie wywalic


# --------------------------------------------------------------- gen
def test_gen_text_and_json(tmp_path, run_cli):
    d = tmp_path / "gen"
    d.mkdir()
    assert run_cli(["gen", "text", "pozdro", "-d", str(d),
                    "--content", "hello\n"]) == 0
    assert (d / "pozdro.txt").read_text(encoding="utf-8") == "hello\n"

    assert run_cli(["gen", "json", "cfg", "-d", str(d)]) == 0
    assert (d / "cfg.json").exists()


@pytest.mark.parametrize("kind,ext", [
    ("bin", "bin"), ("py", "py"), ("c", "c"), ("cpp", "cpp"),
    ("md", "md"), ("dat", "dat"), ("img", "img"), ("blob", "blob"),
    ("raw", "raw"), ("pyc", "pyc"),
])
def test_gen_kinds(tmp_path, run_cli, kind, ext):
    d = tmp_path / "gen"
    d.mkdir()
    assert run_cli(["gen", kind, "plik", "-d", str(d), "-s", "64"]) == 0
    assert (d / ("plik." + ext)).exists()


def test_gen_raw_dimensions(tmp_path, run_cli):
    d = tmp_path / "gen"
    d.mkdir()
    assert run_cli(["gen", "raw", "obraz", "-d", str(d),
                    "-s", "8", "--height", "4"]) == 0
    assert (d / "obraz.raw").stat().st_size == 8 * 4


# --------------------------------------------------------------- main dispatch
def test_unknown_gen_kind(tmp_path, run_cli):
    rc = ZIPps.cli_cmd_gen(type("A", (), {
        "kind": "nieznany", "dir": str(tmp_path), "name": "x",
    })(), ZIPps.Empty(), None)
    assert rc == 2


def test_cli_commands_registry():
    assert set(ZIPps.CLI_COMMANDS) == {
        "pack", "unpack", "list", "hash", "info", "test", "gen", "settings"}
