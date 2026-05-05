"""Electron ASAR archive parser — handles both standard and integrity-protected formats."""

import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple, Union


@dataclass
class FileEntry:
    path: str
    size: int
    offset: int
    executable: bool = False
    integrity: Optional[Dict] = None

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def dirname(self) -> str:
        return os.path.dirname(self.path)


@dataclass
class AsarInfo:
    path: Path
    file_size: int
    file_count: int
    total_unpacked_size: int
    has_integrity: bool
    integrity_config: Optional[Dict] = None


class AsarParser:
    """Parser for Electron ASAR archives.

    Usage:
        with AsarParser("app.asar") as asar:
            for entry in asar.list_files():
                print(f"{entry.path}  ({entry.size:,} bytes)")
            asar.extract_all("output_dir/")
            data = asar.read_file("path/to/file.js")
    """

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._file: Optional[BinaryIO] = None
        self._header: Dict[str, Any] = {}
        self._files: List[FileEntry] = []
        self._integrity_config: Optional[Dict] = None
        self._base_offset: int = 0  # offset past header where file data starts

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    def open(self):
        self._file = open(self.path, "rb")
        self._parse()

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    def _read(self, offset: int, size: int) -> bytes:
        self._file.seek(offset)
        data = self._file.read(size)
        if len(data) < size:
            raise EOFError(
                f"Short read at offset 0x{offset:X}: "
                f"expected {size} bytes, got {len(data)}"
            )
        return data

    @property
    def file_size(self) -> int:
        return os.path.getsize(self.path)

    def _parse(self):
        total_size = self.file_size
        if total_size < 4:
            raise ValueError("File too small to be an ASAR archive")

        # Read potential header size
        first4 = struct.unpack("<I", self._read(0, 4))[0]

        # Try standard format: first 4 bytes = JSON header size
        header_size = first4
        json_start = 4

        # Heuristic: if header_size is absurdly large, try 16-byte integrity header
        if header_size > total_size or header_size > 200 * 1024 * 1024:
            # Try the 4-uint32 extended header format
            data16 = self._read(0, 16)
            v1, v2, v3, v4 = struct.unpack("<IIII", data16)
            # The third uint32 is typically the actual header size
            if v3 > 0 and v3 < total_size and v3 < 200 * 1024 * 1024:
                header_size = v3
                json_start = 16

        # Read JSON header
        raw_json = self._read(json_start, header_size)
        # Strip trailing null bytes / padding
        raw_json = raw_json.rstrip(b"\x00")
        header = json.loads(raw_json.decode("utf-8"))
        self._header = header

        # Calculate data start (header + padding to 4 bytes)
        self._base_offset = json_start + header_size
        if self._base_offset % 4 != 0:
            self._base_offset += 4 - (self._base_offset % 4)

        # Parse file table
        self._files = []
        self._flatten_files(header.get("files", {}), "")

        # Check for integrity footer
        self._integrity_config = self._parse_integrity_footer()

    def _flatten_files(self, tree: Dict, prefix: str):
        for name, info in tree.items():
            full_path = prefix + name if not prefix else prefix + "/" + name
            if "files" in info:
                # Directory node
                self._flatten_files(info["files"], full_path)
            else:
                # File node
                offset = info.get("offset", "0")
                if isinstance(offset, str):
                    offset = int(offset)
                size = info.get("size", 0)
                if isinstance(size, str):
                    size = int(size)
                self._files.append(FileEntry(
                    path=full_path,
                    size=size,
                    offset=offset,
                    executable=info.get("executable", False),
                    integrity=info.get("integrity"),
                ))

    def _parse_integrity_footer(self) -> Optional[Dict]:
        """Try to read integrity config from end of file."""
        try:
            total = self.file_size
            # Read last 4 bytes as potential header_size
            footer_header_size = struct.unpack("<I", self._read(total - 4, 4))[0]
            if footer_header_size <= 0 or footer_header_size > total - 4:
                return None
            json_bytes = self._read(total - 4 - footer_header_size, footer_header_size)
            config = json.loads(json_bytes.decode("utf-8"))
            if "algorithm" in config and "hash" in config:
                return config
        except (ValueError, json.JSONDecodeError, EOFError, UnicodeDecodeError):
            pass
        return None

    def list_files(self) -> List[FileEntry]:
        """Return all file entries sorted by path."""
        return sorted(self._files, key=lambda f: f.path)

    def get_file(self, path: str) -> Optional[FileEntry]:
        """Get a single file entry by its internal path."""
        for f in self._files:
            if f.path == path:
                return f
        return None

    def read_file(self, path: str) -> bytes:
        """Read the contents of a single file from the archive."""
        entry = self.get_file(path)
        if entry is None:
            raise KeyError(f"File not found in archive: {path}")
        actual_offset = self._base_offset + entry.offset
        return self._read(actual_offset, entry.size)

    def extract(self, path: str, dest_dir: Union[str, Path]):
        """Extract a single file to a destination directory."""
        entry = self.get_file(path)
        if entry is None:
            raise KeyError(f"File not found in archive: {path}")
        data = self.read_file(path)
        dest = Path(dest_dir) / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if entry.executable:
            dest.chmod(dest.stat().st_mode | 0o111)

    def extract_all(self, dest_dir: Union[str, Path]):
        """Extract all files to a destination directory."""
        dest_dir = Path(dest_dir)
        for entry in self._files:
            data = self.read_file(entry.path)
            dest = dest_dir / entry.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if entry.executable:
                dest.chmod(dest.stat().st_mode | 0o111)

    def get_info(self) -> AsarInfo:
        """Return archive summary info."""
        return AsarInfo(
            path=self.path,
            file_size=self.file_size,
            file_count=len(self._files),
            total_unpacked_size=sum(f.size for f in self._files),
            has_integrity=self._integrity_config is not None,
            integrity_config=self._integrity_config,
        )

    def search(self, pattern: str) -> List[FileEntry]:
        """Search for files whose path contains the given pattern (case-insensitive)."""
        pattern_lower = pattern.lower()
        return [f for f in self._files if pattern_lower in f.path.lower()]
