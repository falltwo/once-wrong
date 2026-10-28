"""建立知識庫：

    python -m once_wrong.kb.build config/manuals.json --out data/kb

手冊更新時重跑一次即可；審核時只讀 data/kb，不再解析 PDF。
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

from once_wrong.kb.store import build, load_manifest, save


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(description="建立填報手冊知識庫")
    parser.add_argument("manifest", help="手冊清單，例如 config/manuals.json")
    parser.add_argument("--root", default=".", help="手冊路徑的基準資料夾，預設目前資料夾")
    parser.add_argument("--out", default="data/kb", help="輸出資料夾")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    missing = [m.path for m in manifest if not (Path(args.root) / m.path).exists()]
    if missing:
        print("找不到手冊：\n  " + "\n  ".join(missing), file=sys.stderr)
        return 2

    passages = build(manifest, args.root)
    out = save(passages, args.out)

    counts = Counter((p.product, p.kind.value) for p in passages)
    print(f"共 {len(passages)} 段，寫入 {out}")
    for (product, kind), n in sorted(counts.items()):
        print(f"  {product:<6} {kind:<11} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
