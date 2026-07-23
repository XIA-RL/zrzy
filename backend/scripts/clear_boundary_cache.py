#!/usr/bin/env python3
"""清空预导出的边界 GeoJSON 缓存，避免旧的同名区多边界结果残留。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES_DIR = ROOT / "data" / "boundaries"


def main() -> int:
    if not BOUNDARIES_DIR.exists():
        print(f"[SKIP] {BOUNDARIES_DIR} 不存在")
        return 0
    files = list(BOUNDARIES_DIR.glob("*.geojson"))
    for path in files:
        path.unlink()
    print(f"[DONE] deleted {len(files)} geojson cache files from {BOUNDARIES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
