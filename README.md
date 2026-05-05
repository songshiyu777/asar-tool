# ASAR Tool · Electron 归档文件解包工具

> 纯 Python、零依赖的命令行工具。无需安装 Node.js，即可查看、列出、搜索和提取 Electron [ASAR](https://github.com/electron/asar) 归档文件。支持 Linux、macOS、Windows。

A **pure-Python**, **zero-dependency** CLI tool to inspect, list, search, and extract Electron [ASAR](https://github.com/electron/asar) archives. Works on **Linux, macOS, and Windows** — no Node.js required.

## Features

- **Cross-platform** — parses the binary format directly, no Electron or Node.js needed
- **Zero dependencies** — only the Python standard library
- **Supports both formats** — standard ASAR and integrity-protected archives
- **Command-line interface** with subcommands for common tasks
- **Python API** for programmatic use
- Handles large archives (tested with 98MB+ files)

## Installation

```bash
pip install git+https://github.com/songshiyu777/asar-tool.git
```

Or clone and install locally:

```bash
git clone https://github.com/songshiyu777/asar-tool.git
cd asar-tool
pip install -e .
```

## Quick Start

```bash
# Overview of an ASAR archive
asar-tool info app.asar

# List all files
asar-tool list app.asar

# List with file sizes
asar-tool list --long app.asar

# Search for files by name
asar-tool search main app.asar

# Filter file listing by pattern
asar-tool list --pattern "*.js" app.asar

# Extract everything
asar-tool extract app.asar -o output/

# Extract a single file
asar-tool extract app.asar dist-electron/main/index.js -o output/

# Print a file to stdout
asar-tool cat app.asar package.json
```

### Example output

```
$ asar-tool info app.asar

File         : app.asar
Archive size : 93.7 MB
Files        : 8,720
Unpacked size: 198.5 MB
Integrity    : yes
  Algorithm  : SHA256
  Hash       : a1b2c3d4e5f6...
  Block size : 4.0 MB
  Blocks     : 48
```

```
$ asar-tool list --long app.asar | head -10

     Size  Path
--------------------------------------------------------------------------------
 166.6 KB  dist-electron/main/index.js
    414 B  dist-electron/preload/couponPreload.js
    2.3 KB  dist-electron/preload/index.js
   2.2 MB  node_modules/electron-log/...
    ...
```

```
$ asar-tool search keygen app.asar | head -5

3 matches:
    3.2 KB  EXTRA/node_modules/asarmor/scripts/keygen.js
    8.1 KB  EXTRA/node_modules/electron-updater/out/providers/KeygenProvider.js
      ...
```

## Python API

```python
from asar_tool import AsarParser

with AsarParser("app.asar") as asar:
    # Archive info
    info = asar.get_info()
    print(f"Files: {info.file_count}, Integrity: {info.has_integrity}")

    # List all files
    for entry in asar.list_files():
        print(f"{entry.size:>10,d}  {entry.path}")

    # Read a single file
    package_json = asar.read_file("package.json")

    # Search for files
    for f in asar.search("main"):
        print(f"Found: {f.path}")

    # Extract everything
    asar.extract_all("output/")

    # Extract a specific file
    asar.extract("dist-electron/main/index.js", "output/")
```

## License

MIT — see [LICENSE](LICENSE) for details.
