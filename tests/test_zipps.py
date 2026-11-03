"""Testy jednostkowe dla ZIPps (uruchomienie: python -m unittest discover -s tests)."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ZIPps


def run_cli(argv):
    """Uruchamia cli_main(argv) i zwraca (kod wyjscia, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = ZIPps.cli_main(argv)
        except SystemExit as exc:  # argparse przy blednych argumentach
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def make_file(self, name="sample.txt", content=b"hello ZIPps\n"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(content)
        return path


class FileInfoTests(TempDirTestCase):
    def test_reports_basic_metadata(self):
        path = self.make_file("info.txt", b"abc")
        info = ZIPps.file_info(path)

        self.assertEqual(os.path.abspath(path), info["path"])
        self.assertEqual("info.txt", info["name"])
        self.assertEqual(3, info["size"])
        self.assertTrue(info["is_text"])
        self.assertIn("preview", info)
        self.assertEqual("abc", info["preview"].strip())

    def test_includes_sha256_and_crc32(self):
        path = self.make_file("hashed.txt", b"12345")
        info = ZIPps.file_info(path)

        self.assertEqual(ZIPps.hash_file(path, "sha256"), info["sha256"])
        self.assertEqual(ZIPps.crc32_of_file(path), info["crc32"])

    def test_binary_file_has_no_preview(self):
        path = self.make_file("bin.dat", bytes(range(256)) * 8)
        info = ZIPps.file_info(path)

        self.assertFalse(info["is_text"])
        self.assertNotIn("preview", info)


class HashFileTests(TempDirTestCase):
    def test_matches_hashlib(self):
        import hashlib

        data = b"content for hashing"
        path = self.make_file("hash.bin", data)

        for algo in ("md5", "sha1", "sha256", "sha512"):
            with self.subTest(algo=algo):
                expected = hashlib.new(algo, data).hexdigest()
                self.assertEqual(expected, ZIPps.hash_file(path, algo))

    def test_algo_name_is_case_insensitive(self):
        path = self.make_file("case.txt", b"x")
        self.assertEqual(ZIPps.hash_file(path, "sha256"),
                         ZIPps.hash_file(path, "SHA256"))

    def test_crc32_is_eight_hex_chars(self):
        path = self.make_file("crc.txt", b"abc")
        value = ZIPps.hash_file(path, "crc32")
        self.assertEqual(8, len(value))
        int(value, 16)  # rzuca, jesli to nie hex

    def test_unknown_algorithm_raises_packer_error(self):
        path = self.make_file("bad.txt", b"x")
        with self.assertRaises(ZIPps.PackerError):
            ZIPps.hash_file(path, "no-such-algo")

    def test_missing_file_raises_oserror(self):
        with self.assertRaises(OSError):
            ZIPps.hash_file(os.path.join(self.tmp, "missing.txt"))


class ArchiveRoundTripTests(TempDirTestCase):
    def _make_inputs(self):
        a = self.make_file("a.txt", b"alpha\n")
        b = self.make_file("b.txt", b"bravo\n")
        return [a, b]

    def test_zip_pack_then_list_and_unpack(self):
        files = self._make_inputs()
        archive = os.path.join(self.tmp, "out.zip")

        packer = ZIPps.PackerCore(ZIPps.Empty())
        result = packer.pack(files, archive, "zip")
        self.assertTrue(os.path.isfile(archive))
        self.assertEqual(2, result.entries)

        unpacker = ZIPps.UnpackerCore(ZIPps.Empty())
        entries, fmt = unpacker.entries(archive)
        self.assertEqual("zip", fmt)
        self.assertEqual(2, len(entries))
        self.assertEqual(
            {"a.txt", "b.txt"},
            {os.path.basename(e["name"]) for e in entries},
        )

        dest = os.path.join(self.tmp, "restored")
        extract = unpacker.unpack_auto(archive, dest)
        self.assertEqual(2, extract.extracted)
        with open(os.path.join(dest, "a.txt"), "rb") as fh:
            self.assertEqual(b"alpha\n", fh.read())

    def test_archive_passes_integrity_test(self):
        files = self._make_inputs()
        archive = os.path.join(self.tmp, "check.zip")
        ZIPps.PackerCore(ZIPps.Empty()).pack(files, archive, "zip")

        ok, problem, count = ZIPps.UnpackerCore(ZIPps.Empty()).test_archive(archive)
        self.assertTrue(ok, msg=problem)
        self.assertEqual(2, count)

    def test_selected_files_only(self):
        files = self._make_inputs()
        archive = os.path.join(self.tmp, "subset.zip")
        packer = ZIPps.PackerCore(ZIPps.Empty())
        unpacker = ZIPps.UnpackerCore(ZIPps.Empty())
        packer.pack(files, archive, "zip")

        dest = os.path.join(self.tmp, "only_a")
        result = unpacker.unpack_auto(archive, dest, selected=["a.txt"])
        self.assertEqual(1, result.extracted)

    def test_detect_format_from_extension(self):
        self.assertEqual("zip", ZIPps.detect_format("data.zip"))
        self.assertEqual("targz", ZIPps.detect_format("data.tar.gz"))
        self.assertEqual("7z", ZIPps.detect_format("data.7z"))

    def test_7z_pack_then_list_and_unpack(self):
        if not ZIPps.PY7ZR_AVAILABLE:
            self.skipTest("py7zr not available")
        files = self._make_inputs()
        archive = os.path.join(self.tmp, "out.7z")

        packer = ZIPps.PackerCore(ZIPps.Empty())
        result = packer.pack(files, archive, "7z")
        self.assertTrue(os.path.isfile(archive))
        self.assertEqual(2, result.entries)

        unpacker = ZIPps.UnpackerCore(ZIPps.Empty())
        entries, fmt = unpacker.entries(archive)
        self.assertEqual("7z", fmt)
        self.assertEqual(2, len(entries))
        self.assertEqual(
            {"a.txt", "b.txt"},
            {os.path.basename(e["name"]) for e in entries},
        )

        dest = os.path.join(self.tmp, "restored")
        extract = unpacker.unpack_auto(archive, dest)
        self.assertEqual(2, extract.extracted)
        with open(os.path.join(dest, "a.txt"), "rb") as fh:
            self.assertEqual(b"alpha\n", fh.read())

    def test_7z_archive_passes_integrity_test(self):
        if not ZIPps.PY7ZR_AVAILABLE:
            self.skipTest("py7zr not available")
        files = self._make_inputs()
        archive = os.path.join(self.tmp, "check.7z")
        ZIPps.PackerCore(ZIPps.Empty()).pack(files, archive, "7z")

        ok, problem, count = ZIPps.UnpackerCore(ZIPps.Empty()).test_archive(archive)
        self.assertTrue(ok, msg=problem)
        self.assertEqual(2, count)


class CliDispatchTests(TempDirTestCase):
    def test_settings_returns_zero(self):
        code, out, _err = run_cli(["settings"])
        self.assertEqual(0, code)
        self.assertTrue(out.strip())

    def test_hash_exit_zero_on_success(self):
        path = self.make_file("cli.txt", b"payload")
        code, out, _err = run_cli(["hash", path])
        self.assertEqual(0, code)
        self.assertIn("SHA256", out)

    def test_hash_compare_matches_returns_zero(self):
        path = self.make_file("cmp.txt", b"payload")
        digest = ZIPps.hash_file(path, "sha256")
        code, _out, _err = run_cli(["hash", path, "--compare", digest])
        self.assertEqual(0, code)

    def test_hash_compare_mismatch_returns_three(self):
        path = self.make_file("cmp2.txt", b"payload")
        code, _out, _err = run_cli(["hash", path, "--compare", "0" * 64])
        self.assertEqual(3, code)

    def test_hash_blank_compare_returns_two(self):
        path = self.make_file("cmp3.txt", b"payload")
        code, _out, err = run_cli(["hash", path, "--compare", "   "])
        self.assertEqual(2, code)
        self.assertIn("compare", err)

    def test_hash_directory_with_compare_returns_two(self):
        code, _out, err = run_cli(["hash", self.tmp, "--compare", "abc"])
        self.assertEqual(2, code)
        self.assertIn("katalogu", err)

    def test_info_json_returns_zero(self):
        path = self.make_file("inf.json", b"{}")
        code, out, _err = run_cli(["info", path, "--json"])
        self.assertEqual(0, code)
        self.assertIn('"name"', out)

    def test_list_returns_zero(self):
        path = self.make_file("l.txt", b"x")
        archive = os.path.join(self.tmp, "list.zip")
        ZIPps.PackerCore(ZIPps.Empty()).pack([path], archive, "zip")

        code, out, _err = run_cli(["list", archive])
        self.assertEqual(0, code)
        self.assertIn("ZIP", out)

    def test_test_command_on_valid_archive_returns_zero(self):
        path = self.make_file("t.txt", b"x")
        archive = os.path.join(self.tmp, "t.zip")
        ZIPps.PackerCore(ZIPps.Empty()).pack([path], archive, "zip")

        code, _out, _err = run_cli(["test", archive])
        self.assertEqual(0, code)

    def test_gen_text_creates_file(self):
        code, out, _err = run_cli(
            ["gen", "text", "generated", "-d", self.tmp, "--content", "hi"]
        )
        self.assertEqual(0, code)
        self.assertTrue(out.strip())
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "generated.txt")))

    def test_unknown_gen_kind_returns_two(self):
        args = type("Args", (), {
            "kind": "bogus", "dir": self.tmp, "name": "x",
            "size": 1, "height": None, "content": "",
        })()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = ZIPps.cli_cmd_gen(args, ZIPps.Empty(), None)
        self.assertEqual(2, code)
        self.assertIn("bogus", err.getvalue())


if __name__ == "__main__":
    unittest.main()
