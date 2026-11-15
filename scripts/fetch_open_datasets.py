"""Offline auth-free downloader fetching open Earth, Moon, and Mars grids into data/raw/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from isotopos.etl.sources.open_dataset_manifest import OPEN_DATASET_MANIFEST, DatasetAsset  # noqa: E402


def download_asset(client: httpx.Client, asset: DatasetAsset, raw_dir: Path, force: bool = False) -> None:
    """Download one manifest asset idempotently with atomic temp-file replacement."""
    dest = asset.resolve(raw_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not force and dest.exists() and dest.stat().st_size >= asset.min_bytes:
        print(f"  [cached] {asset.rel_path} ({dest.stat().st_size / 1e6:.2f} MB)")
        return

    tmp_path = dest.with_suffix(dest.suffix + ".part")
    print(f"  [fetch]  {asset.key} -> {asset.rel_path} ...")
    with client.stream("GET", asset.url) as resp:
        resp.raise_for_status()
        with tmp_path.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=262_144):
                fh.write(chunk)

    size = tmp_path.stat().st_size
    if size < asset.min_bytes:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded {asset.key} from {asset.url} was smaller than expected ({size} < {asset.min_bytes} bytes)."
        )
    tmp_path.replace(dest)
    print(f"  [ok]     {asset.rel_path} ({size / 1e6:.2f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch auth-free open planetary & terrestrial grids into data/raw/.")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw", help="Destination data/raw directory.")
    parser.add_argument("--scope", choices=("all", "earth", "moon", "mars"), default="all")
    parser.add_argument("--force", action="store_true", help="Re-download files even if cached.")
    args = parser.parse_args()

    assets = [
        a for a in OPEN_DATASET_MANIFEST if args.scope == "all" or a.scope == args.scope
    ]
    print(f"Fetching {len(assets)} open dataset assets into {args.raw_dir} (scope={args.scope})...")
    with httpx.Client(
        timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0),
        follow_redirects=True,
        headers={"User-Agent": "iso-topos-etl/1.0 (+https://github.com/isotopos)"},
    ) as client:
        for asset in assets:
            download_asset(client, asset, args.raw_dir, force=args.force)

    print("All requested open dataset assets are present.")


if __name__ == "__main__":
    main()
