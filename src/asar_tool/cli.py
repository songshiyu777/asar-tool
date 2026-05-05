"""Command-line interface for asar-tool."""

import argparse
import sys
import textwrap
from pathlib import Path

from .parser import AsarParser


def _fmt_size(n: int) -> str:
    if n >= 1024 * 1024 * 1024:
        return f"{n / (1024**3):.1f} GB"
    if n >= 1024 * 1024:
        return f"{n / (1024**2):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n:,} B"


def cmd_info(asar: AsarParser, args):
    info = asar.get_info()
    print(f"File         : {info.path}")
    print(f"Archive size : {_fmt_size(info.file_size)}")
    print(f"Files        : {info.file_count:,}")
    print(f"Unpacked size: {_fmt_size(info.total_unpacked_size)}")
    print(f"Integrity    : {'yes' if info.has_integrity else 'no'}")
    if info.integrity_config:
        ic = info.integrity_config
        print(f"  Algorithm  : {ic.get('algorithm', '?')}")
        print(f"  Hash       : {ic.get('hash', '?')[:16]}...")
        block_size = ic.get("blockSize", 0)
        if block_size:
            print(f"  Block size : {_fmt_size(block_size)}")
        block_count = ic.get("blockSize") and len(ic.get("blocks", []))
        if block_count:
            print(f"  Blocks     : {block_count}")


def cmd_list(asar: AsarParser, args):
    files = asar.list_files()
    if not files:
        print("(empty archive)")
        return

    if args.pattern:
        files = asar.search(args.pattern)
        if not files:
            print(f"No files matching '{args.pattern}'")
            return

    if args.long:
        print(f"{'Size':>10s}  {'Path'}")
        print("-" * 80)
    for f in files:
        if args.long:
            print(f"{_fmt_size(f.size):>10s}  {f.path}")
        else:
            print(f.path)

    if args.long and not args.pattern:
        print("-" * 80)
        print(f"{_fmt_size(asar.get_info().total_unpacked_size):>10s}  ({len(files)} files)")


def cmd_extract(asar: AsarParser, args):
    dest = Path(args.output)
    if args.path:
        asar.extract(args.path, dest)
        print(f"Extracted: {args.path}")
    else:
        asar.extract_all(dest)
        files = asar.list_files()
        print(f"Extracted {len(files)} files to {dest.absolute()}")


def cmd_search(asar: AsarParser, args):
    results = asar.search(args.pattern)
    if not results:
        print(f"No files matching '{args.pattern}'")
        return
    print(f"{len(results)} matches:")
    for f in results:
        print(f"  {_fmt_size(f.size):>10s}  {f.path}")


def cmd_cat(asar: AsarParser, args):
    try:
        data = asar.read_file(args.path)
        sys.stdout.buffer.write(data)
    except KeyError:
        print(f"File not found: {args.path}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="asar-tool",
        description="Inspect, list, and extract Electron ASAR archives.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
          asar-tool info app.asar
          asar-tool list app.asar
          asar-tool list --long app.asar
          asar-tool search main app.asar
          asar-tool extract app.asar -o output/
          asar-tool extract app.asar path/to/file.js -o output/
          asar-tool cat app.asar package.json
        """),
    )
    parser.add_argument("--version", action="version", version="asar-tool 0.1.0")

    sub = parser.add_subparsers(dest="command", help="Available commands")
    sub.required = True

    # info
    p = sub.add_parser("info", help="Show archive overview")
    p.add_argument("file", type=Path, help="Path to .asar file")
    p.set_defaults(func=cmd_info)

    # list
    p = sub.add_parser("list", help="List files in archive")
    p.add_argument("file", type=Path, help="Path to .asar file")
    p.add_argument("-l", "--long", action="store_true", help="Show file sizes")
    p.add_argument("-p", "--pattern", type=str, default=None,
                   help="Filter by filename pattern")
    p.set_defaults(func=cmd_list)

    # extract
    p = sub.add_parser("extract", help="Extract files from archive")
    p.add_argument("file", type=Path, help="Path to .asar file")
    p.add_argument("path", type=str, nargs="?", default=None,
                   help="Specific file to extract (omit for all)")
    p.add_argument("-o", "--output", type=str, required=True,
                   help="Destination directory")
    p.set_defaults(func=cmd_extract)

    # search
    p = sub.add_parser("search", help="Search for files by name")
    p.add_argument("pattern", type=str, help="Search pattern (case-insensitive)")
    p.add_argument("file", type=Path, help="Path to .asar file")
    p.set_defaults(func=cmd_search)

    # cat
    p = sub.add_parser("cat", help="Print a file from archive to stdout")
    p.add_argument("path", type=str, help="Internal file path")
    p.add_argument("file", type=Path, help="Path to .asar file")
    p.set_defaults(func=cmd_cat)

    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    try:
        with AsarParser(args.file) as asar:
            args.func(asar, args)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error: not a valid ASAR archive — {e}", file=sys.stderr)
        sys.exit(1)
    except EOFError as e:
        print(f"Error reading archive: {e}", file=sys.stderr)
        sys.exit(1)


# For import in main error case
import json
