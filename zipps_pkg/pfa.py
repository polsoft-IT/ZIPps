"""ZIPps - wlasny format PFA (manifest + AES-256-GCM)."""
import hashlib
import os
import struct
import time
import zlib

from dataclasses import dataclass

from zipps_pkg.core import (
    PackerError, Empty, emit, human_size, _check_cancel, _make_progress,
    detect_format, ensure_archive_ext, normalize_relative, safe_join,
)
from zipps_pkg.settings_mod import settings
from zipps_pkg.logging_mod import Logger
from zipps_pkg.packer import PackerCore


def _lazy_packer(logger):
    from zipps_pkg.packer import PackerCore
    return PackerCore(logger)

# PackResult/ExtractResult sa tworzone leniwie, aby uniknac importu
# cyklicznego packer <-> pfa <-> unpacker.


def _pack_result(path):
    from zipps_pkg.packer import PackResult
    return PackResult(path=path)


def _extract_result(output_folder):
    from zipps_pkg.unpacker import ExtractResult
    return ExtractResult(fmt="pfa", output_folder=output_folder)
# =====================================================================
#  Format PFA (Pro File Archive)
# ---------------------------------------------------------------------
#  PFA1 (zgodnosc wsteczna, format oryginalny):
#     "PFA1" | uint32 count | count * ( uint32 name_len | name | uint32 size | data )
#
#  PFA2 (nowy format z manifestem, opcjonalnym szyfrowaniem AES-256-GCM):
#     "PFA2" | uint16 flags | uint8 kdf | uint32 iterations | uint16 salt_len | salt
#            | uint32 manifest_len | manifest | count * ( uint32 size | data )
#     flags bit 0 -> dane zaszyfrowane
#     klucz = PBKDF2-HMAC-SHA256(password, salt, iterations); nonce 12B jako prefiks.
#     Manifest (binarny): uint32 count | count * ( uint16 name_len | name |
#            uint64 offset | int64 mtime | uint32 mode | uint8 enc | 32B sha256 )
#     Dla danych zaszyfrowanych sha256 odnosi sie do jawnych danych.
# =====================================================================

PFA_MAGIC_V1 = b"PFA1"
PFA_MAGIC_V2 = b"PFA2"
PFA_FLAG_ENCRYPTED = 0x0001
PFA_FLAG_DEFLATE = 0x0002      # wszystkie wpisy sa skompresowane zlib-em
PFA_ENTRY_ENCRYPTED = 0x01     # bity w polu 'enc' wpisu manifestu
PFA_ENTRY_COMPRESSED = 0x02
PFA_PBKDF2_ITERATIONS = 200_000
PFA_SALT_LEN = 16
PFA_NONCE_LEN = 12
PFA_TAG_LEN = 16

#: wpis manifestu (bez nazwy i hasha):
#:   uint64 offset | int64 mtime | uint32 size | uint8 encrypted | uint32 mode
#: Kodowanie reczne (int.to_bytes) zamiast struct - wyniki sa jednoznaczne
#: niezaleznie od wersji Pythona i jej kodow formatu.
PFA_ENTRY_SIZE = 8 + 8 + 4 + 1 + 4


def _int_bytes(value: int, length: int, signed: bool = False) -> bytes:
    """Stala liczba bajtow niezaleznie od wartosci (bez wyrownania do slowa).

    Rzutowanie przez int() jest konieczne - dla float kodowanie zalezy od
    wartosci i moze zmienic szerokosc pola.
    """
    raw = int(value).to_bytes(length, "little", signed=signed)
    if len(raw) != length:
        raise PackerError("value %r does not fit in %d bytes" % (value, length))
    return raw


def _pack_entry(offset: int, mtime: int, size: int, encrypted: int, mode: int) -> bytes:
    return (_int_bytes(offset, 8) + _int_bytes(mtime, 8, signed=True)
            + _int_bytes(size, 4) + bytes([int(encrypted) & 0xFF])
            + _int_bytes(mode, 4))


def _unpack_entry(raw: bytes, pos: int) -> tuple:
    offset = int.from_bytes(raw[pos:pos + 8], "little", signed=False)
    mtime = int.from_bytes(raw[pos + 8:pos + 16], "little", signed=True)
    size = int.from_bytes(raw[pos + 16:pos + 20], "little", signed=False)
    encrypted = raw[pos + 20]
    mode = int.from_bytes(raw[pos + 21:pos + 25], "little", signed=False)
    return offset, size, mtime, mode, encrypted  # kolejnoĹ›Ä‡ zgodna z _parse_manifest


@dataclass
class PFAEntry:
    name: str
    offset: int
    size: int
    mtime: float
    mode: int = 0o644
    encrypted: bool = False
    sha256: str = ""
    data_offset: int = 0
    compressed: bool = False

    @property
    def size_human(self) -> str:
        return human_size(self.size)


def _aes_cipher(key: bytes, nonce: bytes, tag: bytes | None = None):
    """Tworzy AES-GCM ciphertext (tag=None) lub deszyfrujacy (tag podany)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise PackerError(
            "Szyfrowanie PFA wymaga modulu 'cryptography'. "
            "Zainstaluj: pip install cryptography"
        )
    aes = AESGCM(key)
    return aes, nonce, tag


class PFAFormat:
    """Wlasny format archiwum: manifest + opcjonalne szyfrowanie AES-256-GCM."""

    MAGIC = PFA_MAGIC_V1          # zgodnosc wsteczna (tworzymy juz PFA2)

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Empty()

    # -- klucz --------------------------------------------------------
    @staticmethod
    def _derive_key(password: str | bytes, salt: bytes, iterations: int) -> bytes:
        if isinstance(password, str):
            password = password.encode("utf-8")
        return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, dklen=32)

    # -- odczyt naglowka ----------------------------------------------
    @staticmethod
    def read_header(f) -> dict:
        f.seek(0)
        magic = f.read(4)
        if magic == PFA_MAGIC_V1:
            return {"version": 1, "magic": magic, "encrypted": False,
                    "manifest_offset": 4, "manifest_len": 0}
        if magic == PFA_MAGIC_V2:
            head = f.read(7)
            flags = int.from_bytes(head[0:2], "little")
            kdf = head[2]
            iterations = int.from_bytes(head[3:7], "little")
            salt_len = int.from_bytes(f.read(2), "little")
            salt = f.read(salt_len)
            manifest_len = int.from_bytes(f.read(4), "little")
            return {
                "version": 2,
                "magic": magic,
                "flags": flags,
                "kdf": kdf,
                "iterations": iterations,
                "salt": salt,
                "manifest_len": manifest_len,
                "manifest_offset": f.tell(),
                "encrypted": bool(flags & PFA_FLAG_ENCRYPTED),
            }
        raise PackerError("invalid PFA")

    @staticmethod
    def _parse_manifest(raw: bytes) -> list:
        entries = []
        pos = 0
        count = int.from_bytes(raw[pos:pos + 4], "little")
        pos += 4
        for _ in range(count):
            name_len = int.from_bytes(raw[pos:pos + 2], "little")
            pos += 2
            name = raw[pos:pos + name_len].decode("utf-8")
            pos += name_len
            offset, size, mtime, mode, enc = _unpack_entry(raw, pos)
            pos += PFA_ENTRY_SIZE
            sha = raw[pos:pos + 32]
            pos += 32
            entries.append(PFAEntry(
                name=name, offset=offset, size=size, mtime=mtime, mode=mode,
                encrypted=bool(enc & PFA_ENTRY_ENCRYPTED), sha256=sha.hex(),
                compressed=bool(enc & PFA_ENTRY_COMPRESSED)))
        return entries

    def _read_manifest(self, f, header, password):
        f.seek(header["manifest_offset"])
        raw = f.read(header["manifest_len"])
        if header.get("encrypted"):
            if not password:
                raise PackerError(settings.t("need_password"))
            key = self._derive_key(password, header["salt"], header["iterations"])
            if len(raw) < PFA_NONCE_LEN + PFA_TAG_LEN:
                raise PackerError(settings.t("wrong_password"))
            nonce, ciphertext, tag = (raw[:PFA_NONCE_LEN],
                                      raw[PFA_NONCE_LEN:-PFA_TAG_LEN],
                                      raw[-PFA_TAG_LEN:])
            aes, nonce, tag = _aes_cipher(key, nonce, tag)
            try:
                raw = aes.decrypt(nonce, ciphertext + tag, PFA_MAGIC_V2)
            except Exception:
                raise PackerError(settings.t("wrong_password"))
        entries = self._parse_manifest(raw)
        # offsety w manifescie liczone sa od poczatku bloku danych, ktory
        # zaczyna sie dokladnie za manifestem
        data_base = f.tell()
        for entry in entries:
            entry.data_offset = data_base + entry.offset
        return raw, entries

    def read_entries(self, archive_path, password: str | None = None) -> list:
        """Odczyt wpisow zwracajacy obiekty PFAEntry."""
        with open(archive_path, "rb") as f:
            header = self.read_header(f)
            if header["version"] == 1:
                count = struct.unpack("<I", f.read(4))[0]
                result = []
                offset = f.tell()
                for _ in range(count):
                    name_len = struct.unpack("<I", f.read(4))[0]
                    name = f.read(name_len).decode("utf-8", "replace")
                    size = struct.unpack("<I", f.read(4))[0]
                    result.append(PFAEntry(name=name, offset=offset, size=size,
                                           mtime=0.0, data_offset=f.tell()))
                    f.seek(size, os.SEEK_CUR)
                    offset = f.tell()
                return result
            return self._read_manifest(f, header, password)[1]

    # -- tworzenie ----------------------------------------------------
    def create_pfa(self, files, archive_path, progress_cb=None,
                   password: str | None = None, bases=None, keep_relative=True,
                   level: int = 6, cancel_event=None):
        files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
        if not files:
            raise PackerError(settings.t("no_files"))
        packed = _lazy_packer(self.logger)
        queue = []
        seen = set()
        for path in files:
            name = packed.arcname_for(path, bases, keep_relative)
            if not name:
                name = os.path.basename(path)
            base, ext = os.path.splitext(name)
            i = 1
            while name in seen:
                name = "%s (%d)%s" % (base, i, ext)
                i += 1
            seen.add(name)
            queue.append((path, name))

        os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
        total = len(queue)
        report = _make_progress(progress_cb)
        result = _pack_result(archive_path)
        emit(self.logger, "PFA: " + archive_path)

        level = max(0, min(9, int(level or 0)))
        salt = os.urandom(PFA_SALT_LEN)
        key = self._derive_key(password, salt, PFA_PBKDF2_ITERATIONS) if password else None
        flags = PFA_FLAG_ENCRYPTED if password else 0
        if level:
            flags |= PFA_FLAG_DEFLATE

        # 1) przetworz pliki: nazwa, dane (kompresja/szyfrowanie) i hash
        records = []
        offset = 0
        for i, (path, name) in enumerate(queue, 1):
            _check_cancel(cancel_event)
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError as ex:
                result.skipped += 1
                result.errors.append("%s: %s" % (path, ex))
                continue
            plain_size = len(data)
            digest = hashlib.sha256(data).hexdigest()
            payload = zlib.compress(data, level) if level else data
            entry_flags = PFA_ENTRY_COMPRESSED if level else 0
            if key is not None:
                nonce = os.urandom(PFA_NONCE_LEN)
                aes, nonce, _ = _aes_cipher(key, nonce)
                payload = nonce + aes.encrypt(nonce, payload, PFA_MAGIC_V2)
                entry_flags |= PFA_ENTRY_ENCRYPTED
            # kazdy wpis poprzedzony jest 4-bajtowym polem dlugosci payloadu
            start = offset
            offset += 4 + len(payload)
            records.append({
                "name": name, "offset": start, "size": plain_size,
                "mtime": os.path.getmtime(path), "mode": 0o644,
                "enc": entry_flags, "sha256": digest,
                "payload": payload,
            })
            result.size_before += plain_size
            report(i, total, name)

        # 2) manifest
        manifest = [_int_bytes(len(records), 4)]
        for rec in records:
            name_bytes = rec["name"].encode("utf-8")
            manifest.append(_int_bytes(len(name_bytes), 2) + name_bytes)
            manifest.append(_pack_entry(rec["offset"], int(rec["mtime"]),
                                        rec["size"], rec["enc"], rec["mode"]))
            manifest.append(bytes.fromhex(rec["sha256"]))
        raw_manifest = b"".join(manifest)
        if key is not None:
            nonce = os.urandom(PFA_NONCE_LEN)
            aes, nonce, _ = _aes_cipher(key, nonce)
            raw_manifest = (nonce + aes.encrypt(nonce, raw_manifest, PFA_MAGIC_V2))

        # 3) zapis
        with open(archive_path, "wb") as out:
            out.write(PFA_MAGIC_V2)
            out.write(_int_bytes(flags, 2) + b"\x01" + _int_bytes(PFA_PBKDF2_ITERATIONS, 4))
            out.write(_int_bytes(len(salt), 2) + salt)
            out.write(_int_bytes(len(raw_manifest), 4))
            out.write(raw_manifest)
            for rec in records:
                _check_cancel(cancel_event)
                out.write(_int_bytes(len(rec["payload"]), 4))
                out.write(rec["payload"])

        result.added = len(records)
        result.entries = len(records)
        result.size_after = os.path.getsize(archive_path)
        emit(self.logger, settings.t("packed") + archive_path)
        emit(self.logger, "%s %s (%s -> %s)" % (
            settings.t("total_size"), human_size(result.size_after),
            human_size(result.size_before), human_size(result.size_after)))
        return result

    # -- rozpakowywanie -----------------------------------------------
    def unpack_pfa(self, archive_path, output_folder, selected=None, progress_cb=None,
                   password: str | None = None, overwrite: bool = True,
                   cancel_event=None):
        os.makedirs(output_folder, exist_ok=True)
        result = _extract_result(output_folder)
        report = _make_progress(progress_cb)
        emit(self.logger, "Unpack PFA: " + archive_path)

        with open(archive_path, "rb") as f:
            header = self.read_header(f)
            if header["version"] == 1:
                return self._unpack_v1(f, output_folder, selected, report, result,
                                       cancel_event)
            _, entries = self._read_manifest(f, header, password)
            key = None
            if header.get("encrypted"):
                key = self._derive_key(password, header["salt"], header["iterations"])
            wanted = None
            if selected is not None:
                wanted = {normalize_relative(s) for s in selected}
            todo = [e for e in entries if wanted is None or e.name in wanted]
            for i, entry in enumerate(todo, 1):
                _check_cancel(cancel_event)
                try:
                    target = safe_join(output_folder, entry.name)
                except PackerError as ex:
                    result.blocked.append(str(ex))
                    continue
                existed = os.path.exists(target)
                if existed and not overwrite:
                    result.skipped += 1
                    continue
                f.seek(entry.data_offset)
                size = int.from_bytes(f.read(4), "little")
                payload = f.read(size)
                if len(payload) != size:
                    raise PackerError("truncated entry: %s" % entry.name)
                if entry.encrypted:
                    if key is None:
                        if not password:
                            raise PackerError(settings.t("need_password"))
                        key = self._derive_key(password, header["salt"], header["iterations"])
                    nonce, body, tag = (payload[:PFA_NONCE_LEN],
                                        payload[PFA_NONCE_LEN:-PFA_TAG_LEN],
                                        payload[-PFA_TAG_LEN:])
                    aes, nonce, tag = _aes_cipher(key, nonce, tag)
                    try:
                        payload = aes.decrypt(nonce, body + tag, PFA_MAGIC_V2)
                    except Exception:
                        raise PackerError(settings.t("wrong_password"))
                if entry.compressed:
                    try:
                        payload = zlib.decompress(payload)
                    except zlib.error:
                        raise PackerError("corrupted entry: %s" % entry.name)
                if hashlib.sha256(payload).hexdigest() != entry.sha256:
                    raise PackerError("checksum mismatch: %s" % entry.name)
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                with open(target, "wb") as out:
                    out.write(payload)
                if entry.mtime:
                    try:
                        os.utime(target, (entry.mtime, entry.mtime))
                    except (OSError, OverflowError, ValueError):
                        pass
                result.extracted += 1
                result.overwritten += 1 if existed else 0
                result.bytes_written += len(payload)
                report(i, len(todo), entry.name)

        emit(self.logger, settings.t("unpacked") + output_folder)
        return result

    def _unpack_v1(self, f, output_folder, selected, report, result, cancel_event):
        count = struct.unpack("<I", f.read(4))[0]
        wanted = None
        if selected is not None:
            wanted = {normalize_relative(s) for s in selected}
        for i in range(count):
            _check_cancel(cancel_event)
            name_len = struct.unpack("<I", f.read(4))[0]
            name = f.read(name_len).decode("utf-8")
            size = struct.unpack("<I", f.read(4))[0]
            data = f.read(size)
            if wanted is not None and normalize_relative(name) not in wanted:
                continue
            try:
                target = safe_join(output_folder, name)
            except PackerError as ex:
                result.blocked.append(str(ex))
                continue
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "wb") as out:
                out.write(data)
            result.extracted += 1
            result.bytes_written += len(data)
            report(i + 1, count, name)
        emit(self.logger, settings.t("unpacked") + output_folder)
        return result

    def verify_pfa(self, archive_path, password=None, progress_cb=None):
        return self.verify(archive_path, password=password, progress_callback=progress_cb)

    def verify(self, archive_path, password=None, progress_callback=None):
        """Weryfikuje manifest i sumy SHA-256 wszystkich wpisow."""
        report = _make_progress(progress_callback)
        with open(archive_path, "rb") as f:
            header = self.read_header(f)
            if header["version"] == 1:
                entries = self.read_entries(archive_path)
                return True, "PFA1", len(entries)
            _, entries = self._read_manifest(f, header, password)
            key = None
            if header.get("encrypted"):
                if not password:
                    return False, settings.t("need_password"), 0
                key = self._derive_key(password, header["salt"], header["iterations"])
            for i, entry in enumerate(entries, 1):
                f.seek(entry.data_offset)
                size = int.from_bytes(f.read(4), "little")
                payload = f.read(size)
                if entry.encrypted and key is not None:
                    nonce, body, tag = (payload[:PFA_NONCE_LEN],
                                        payload[PFA_NONCE_LEN:-PFA_TAG_LEN],
                                        payload[-PFA_TAG_LEN:])
                    aes, nonce, tag = _aes_cipher(key, nonce, tag)
                    try:
                        payload = aes.decrypt(nonce, body + tag, PFA_MAGIC_V2)
                    except Exception:
                        return False, settings.t("wrong_password"), i - 1
                if entry.compressed:
                    try:
                        payload = zlib.decompress(payload)
                    except zlib.error as ex:
                        return False, "corrupted entry: %s (%s)" % (entry.name, ex), i - 1
                if hashlib.sha256(payload).hexdigest() != entry.sha256:
                    return False, "checksum mismatch: %s" % entry.name, i - 1
                report(i, len(entries), entry.name)
        return True, "", len(entries)

    # -- API wspolne z UnpackerCore / SecurityCore ---------------------
    def unpack_auto(self, archive_path, output_folder, selected=None, progress_cb=None,
                    password=None, overwrite=True, cancel_event=None):
        """Zgodny interfejs z UnpackerCore.unpack_auto (tylko format PFA)."""
        if detect_format(archive_path) != "pfa":
            return UnpackerCore(self.logger).unpack_auto(
                archive_path, output_folder, selected=selected, progress_cb=progress_cb,
                password=password, overwrite=overwrite, cancel_event=cancel_event)
        return self.unpack_pfa(archive_path, output_folder, selected=selected,
                               progress_cb=progress_cb, password=password,
                               overwrite=overwrite, cancel_event=cancel_event)

    def entries(self, archive_path, password=None):
        """Lista wpisow PFA w formacie slownikow (jak UnpackerCore.entries)."""
        result = []
        for entry in self.read_entries(archive_path, password=password):
            result.append({
                "name": entry.name, "size": entry.size,
                "date": tuple(time.localtime(entry.mtime)[:6]) if entry.mtime else (),
                "encrypted": entry.encrypted, "is_dir": False,
                "sha256": entry.sha256,
            })
        return result, "pfa"

    def test_archive(self, archive_path, password=None, progress_cb=None):
        return self.verify_pfa(archive_path, password=password, progress_cb=progress_cb)

    def hash_file(self, path, algo="sha256"):
        return hash_file(path, algo)

    def crc32_file(self, path):
        return crc32_of_file(path)

    # -- API wspolne z PackerCore --------------------------------------
    def pack(self, files, archive_path, fmt="pfa", progress_cb=None, **kwargs):
        """Tworzy archiwum PFA (zgodny interfejs z PackerCore.pack)."""
        archive_path = ensure_archive_ext(archive_path, "pfa")
        return self.create_pfa(
            files, archive_path,
            progress_cb=progress_cb,
            password=kwargs.get("password"),
            bases=kwargs.get("bases"),
            keep_relative=kwargs.get("keep_relative", True),
            level=kwargs.get("level", 6),
            cancel_event=kwargs.get("cancel_event"))

    # -- kontekst ------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

