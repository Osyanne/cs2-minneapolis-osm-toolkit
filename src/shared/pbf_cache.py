"""
pbf_cache.py
============
Geofabrik PBF download & local cache with TTL.

Resuelve regiones (e.g. 'north-america/us/minnesota') a URLs de
download.geofabrik.de, descarga el .osm.pbf y lo cachea localmente.
Re-descarga si el archivo cacheado es más viejo que TTL (default 7 días).

Uso:
    from shared.pbf_cache import ensure_pbf
    path = ensure_pbf("north-america/us/minnesota")
    # path es Path al .osm.pbf local
"""

from __future__ import annotations

from pathlib import Path

GEOFABRIK_BASE = "https://download.geofabrik.de"


class GeofabrikRegionError(ValueError):
    """Región Geofabrik inválida o no resoluble."""


def geofabrik_url(region: str) -> str:
    """
    Resuelve un identificador de región Geofabrik a URL de descarga.

    Args:
        region: Path-style region, e.g. 'north-america/us/minnesota',
            'europe/netherlands'. Acepta con o sin prefijo '/' y con o
            sin suffix '-latest.osm.pbf'.

    Returns:
        URL completa al .osm.pbf más reciente.

    Raises:
        GeofabrikRegionError: si region es vacía o None.
    """
    if not region or not isinstance(region, str):
        raise GeofabrikRegionError(f"Región vacía o no-str: {region!r}")
    cleaned = region.strip().lstrip("/")
    if cleaned.endswith("-latest.osm.pbf"):
        return f"{GEOFABRIK_BASE}/{cleaned}"
    return f"{GEOFABRIK_BASE}/{cleaned}-latest.osm.pbf"


import time

import requests

DEFAULT_TTL_SECONDS = 7 * 86400  # 7 días
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "cs2-osm-toolkit" / "pbf"
DOWNLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MiB


def _local_filename(region: str) -> str:
    """Convierte 'north-america/us/minnesota' a 'north-america-us-minnesota-latest.osm.pbf'."""
    cleaned = region.strip().lstrip("/")
    if cleaned.endswith("-latest.osm.pbf"):
        cleaned = cleaned[: -len("-latest.osm.pbf")]
    return cleaned.replace("/", "-") + "-latest.osm.pbf"


def is_fresh(path: Path, ttl_seconds: int) -> bool:
    """Returns True if path exists and was modified within ttl_seconds."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_seconds


def ensure_pbf(
    region: str,
    cache_dir: Path | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    force_refresh: bool = False,
) -> Path:
    """
    Garantiza que el .osm.pbf de `region` exista localmente y esté fresco.

    Args:
        region: Identificador Geofabrik, e.g. 'north-america/us/minnesota'.
        cache_dir: Dónde cachear. Default ~/.cache/cs2-osm-toolkit/pbf/.
        ttl_seconds: Si el archivo existe pero es más viejo que esto, re-descarga.
        force_refresh: Re-descarga incluso si está fresco.

    Returns:
        Path al .osm.pbf local.

    Raises:
        GeofabrikRegionError: si region es inválida.
        requests.HTTPError: si la descarga falla.
    """
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    target = cache_dir / _local_filename(region)

    if not force_refresh and is_fresh(target, ttl_seconds):
        print(f"[pbf_cache] cache hit: {target.name}", flush=True)
        return target

    url = geofabrik_url(region)
    print(f"[pbf_cache] downloading {url} -> {target}", flush=True)

    tmp = target.with_suffix(target.suffix + ".part")
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    total_bytes = int(response.headers.get("content-length", 0))
    written = 0
    with tmp.open("wb") as f:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            if not chunk:
                continue
            f.write(chunk)
            written += len(chunk)
            if total_bytes:
                pct = 100 * written / total_bytes
                print(
                    f"\r[pbf_cache] {written // (1024*1024)} MiB / "
                    f"{total_bytes // (1024*1024)} MiB ({pct:.0f}%)",
                    end="",
                    flush=True,
                )

    if total_bytes:
        print(flush=True)
    tmp.replace(target)
    return target
