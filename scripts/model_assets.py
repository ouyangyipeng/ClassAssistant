"""Fetch hash-pinned small runtime assets before freezing the backend."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api-service"))

import httpx  # noqa: E402

from classfox.downloads import download_asset  # noqa: E402
from classfox.model_catalog import CATALOG, runtime_asset  # noqa: E402


async def prepare() -> None:
    destination = ROOT / "api-service" / "model-assets"
    assets = [CATALOG["sensevoice-small"].files[-1], runtime_asset()]
    async with httpx.AsyncClient(trust_env=False) as client:
        for asset in assets:
            print(f"Verify bundled resource: {asset.filename}", flush=True)
            await download_asset(client, asset, destination / asset.filename, lambda count: None)


if __name__ == "__main__":
    asyncio.run(prepare())
