"""Tests for ASAR parser using synthetic archives."""

import json
import struct
import tempfile
from pathlib import Path

import pytest

from asar_tool.parser import AsarParser


def _build_asar(file_contents: dict, *, integrity: bool = False) -> bytes:
    """Build a valid ASAR archive from {path: content_bytes}.

    Offsets are computed automatically.
    Pass integrity=True to append an integrity footer.
    """
    # Build file table and data section
    files = {}
    data_buf = bytearray()
    data_offset = 0

    def _add_files(tree: dict, contents: dict, prefix: str = ""):
        nonlocal data_offset
        for key, value in sorted(contents.items()):
            full_key = prefix + "/" + key if prefix else key
            if isinstance(value, dict):
                tree[key] = {"files": {}}
                _add_files(tree[key]["files"], value, full_key)
            else:
                data = value if isinstance(value, bytes) else value.encode("utf-8")
                pad_len = (4 - len(data) % 4) % 4
                tree[key] = {
                    "offset": str(data_offset),
                    "size": len(data),
                }
                data_buf.extend(data)
                data_buf.extend(b"\x00" * pad_len)
                data_offset += len(data) + pad_len

    _add_files(files, file_contents)
    header = json.dumps({"files": files}, separators=(",", ":"))
    header_bytes = header.encode("utf-8")
    header_size = len(header_bytes)

    buf = bytearray()
    buf.extend(struct.pack("<I", header_size))
    buf.extend(header_bytes)
    while len(buf) % 4 != 0:
        buf.append(0)

    buf.extend(data_buf)

    if integrity:
        ic = json.dumps(
            {"algorithm": "SHA256", "hash": "abc123def456", "blockSize": 4194304,
             "blocks": ["aaa", "bbb"]},
            separators=(",", ":"),
        )
        ic_bytes = ic.encode("utf-8")
        buf.extend(ic_bytes)
        buf.extend(struct.pack("<I", len(ic_bytes)))

    return bytes(buf)


class TestAsarParser:
    _tmp_standard = None
    _tmp_integrity = None
    path_standard = None
    path_integrity = None

    @classmethod
    def setup_class(cls):
        standard = _build_asar({
            "package.json": b'{"name":"test"}',
            "src": {
                "main.js": b"console.log(1);",
                "utils.js": b"exports.x=1;",
            },
        })
        cls._tmp_standard = tempfile.NamedTemporaryFile(suffix=".asar", delete=False)
        cls._tmp_standard.write(standard)
        cls._tmp_standard.close()
        cls.path_standard = Path(cls._tmp_standard.name)

        integrity = _build_asar({
            "package.json": b'{"name":"test2"}',
            "index.js": b"1+1;",
        }, integrity=True)
        cls._tmp_integrity = tempfile.NamedTemporaryFile(suffix=".asar", delete=False)
        cls._tmp_integrity.write(integrity)
        cls._tmp_integrity.close()
        cls.path_integrity = Path(cls._tmp_integrity.name)

    @classmethod
    def teardown_class(cls):
        for attr in ["_tmp_standard", "_tmp_integrity"]:
            tmp = getattr(cls, attr, None)
            if tmp:
                try:
                    Path(tmp.name).unlink(missing_ok=True)
                except OSError:
                    pass

    # -- Standard format tests --

    def test_parse_standard(self):
        with AsarParser(self.path_standard) as asar:
            info = asar.get_info()
            assert info.file_count == 3

    def test_list_standard(self):
        with AsarParser(self.path_standard) as asar:
            paths = {f.path for f in asar.list_files()}
            assert "package.json" in paths
            assert "src/main.js" in paths
            assert "src/utils.js" in paths

    def test_read_file_standard(self):
        with AsarParser(self.path_standard) as asar:
            data = asar.read_file("package.json")
            assert b'{"name":"test"}' in data

    def test_read_nested_file(self):
        with AsarParser(self.path_standard) as asar:
            data = asar.read_file("src/main.js")
            assert b"console.log(1);" in data

    def test_get_file_standard(self):
        with AsarParser(self.path_standard) as asar:
            f = asar.get_file("src/main.js")
            assert f is not None
            assert f.size > 0

    def test_extract_all_standard(self):
        with tempfile.TemporaryDirectory() as tmp:
            with AsarParser(self.path_standard) as asar:
                asar.extract_all(tmp)
            assert Path(tmp, "package.json").exists()
            assert Path(tmp, "src/main.js").exists()
            assert Path(tmp, "src/utils.js").exists()

    def test_extract_single(self):
        with tempfile.TemporaryDirectory() as tmp:
            with AsarParser(self.path_standard) as asar:
                asar.extract("package.json", tmp)
            assert Path(tmp, "package.json").exists()
            assert not Path(tmp, "src/main.js").exists()

    def test_extract_nested(self):
        with tempfile.TemporaryDirectory() as tmp:
            with AsarParser(self.path_standard) as asar:
                asar.extract("src/utils.js", tmp)
            assert Path(tmp, "src/utils.js").exists()
            data = Path(tmp, "src/utils.js").read_bytes()
            assert b"exports.x=1" in data

    def test_search(self):
        with AsarParser(self.path_standard) as asar:
            results = asar.search("main")
            assert len(results) == 1
            assert results[0].path == "src/main.js"

    def test_search_case_insensitive(self):
        with AsarParser(self.path_standard) as asar:
            assert len(asar.search("MAIN")) == 1
            assert len(asar.search("SRC")) == 2

    # -- Integrity format tests --

    def test_parse_integrity(self):
        with AsarParser(self.path_integrity) as asar:
            info = asar.get_info()
            assert info.file_count == 2
            assert info.has_integrity
            assert info.integrity_config["algorithm"] == "SHA256"
            assert len(info.integrity_config["blocks"]) == 2

    def test_list_integrity(self):
        with AsarParser(self.path_integrity) as asar:
            paths = {f.path for f in asar.list_files()}
            assert "package.json" in paths
            assert "index.js" in paths

    def test_read_integrity(self):
        with AsarParser(self.path_integrity) as asar:
            data = asar.read_file("index.js")
            assert b"1+1" in data

    def test_extract_all_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            with AsarParser(self.path_integrity) as asar:
                asar.extract_all(tmp)
            assert Path(tmp, "package.json").exists()
            assert Path(tmp, "index.js").exists()

    # -- Error handling --

    def test_invalid_file(self):
        with tempfile.NamedTemporaryFile(suffix=".asar", delete=False) as f:
            f.write(b"not an asar file")
            bad = Path(f.name)
        try:
            with pytest.raises((ValueError, EOFError, json.JSONDecodeError)):
                AsarParser(bad).open()
        finally:
            try:
                bad.unlink(missing_ok=True)
            except OSError:
                pass

    def test_missing_file_in_archive(self):
        with AsarParser(self.path_standard) as asar:
            with pytest.raises(KeyError):
                asar.read_file("nonexistent.js")

    def test_context_manager(self):
        with AsarParser(self.path_standard) as asar:
            assert asar._file is not None
        assert asar._file is None

    def test_info_total_size(self):
        with AsarParser(self.path_standard) as asar:
            info = asar.get_info()
            assert info.total_unpacked_size > 0
            assert info.file_size > 0
