#!/usr/bin/env python3
"""
Mundial 2026 — bundle data.json inside index.html → mundial-2026.html.

Used by the daily GitHub Action to keep the shareable single-file
version in sync with the auto-updated data.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def build(index_path: Path, data_path: Path, output_path: Path) -> None:
    html = index_path.read_text(encoding="utf-8")
    data = data_path.read_text(encoding="utf-8")

    fetch_block = (
        "      const res = await fetch('data.json', { cache: 'no-store' });\n"
        "      if (!res.ok) throw new Error('No se pudo cargar data.json');\n"
        "      state.data = await res.json();"
    )
    inline_block = (
        "      state.data = JSON.parse(document.getElementById('embeddedData').textContent);"
    )
    if fetch_block not in html:
        sys.exit("ERROR: fetch block not found in index.html")
    html = html.replace(fetch_block, inline_block)

    data_tag = (
        '<script id="embeddedData" type="application/json">\n'
        + data
        + "\n</script>\n  "
    )
    # Inject before the application <script> (the one starting with 'use strict')
    pattern = re.compile(r"(  <script>\s*\r?\n\s*'use strict';)", re.DOTALL)
    new_html, n = pattern.subn(data_tag + r"\1", html, count=1)
    if n != 1:
        sys.exit("ERROR: could not locate the 'use strict' anchor in index.html")

    output_path.write_text(new_html, encoding="utf-8", newline="\n")
    size_kb = output_path.stat().st_size / 1024
    print(f"Wrote {output_path.name} ({size_kb:.1f} KB)")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    build(root / "index.html", root / "data.json", root / "mundial-2026.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
