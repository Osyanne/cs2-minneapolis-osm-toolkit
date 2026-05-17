"""Registro de ciudades (cities.json) + manifest per-city.

Single source of truth para qué ciudades existen y qué módulos están generados.
`cities.json` define qué ciudades son seleccionables; `manifest.json` per-city
declara qué módulos (zoning/vial/services) hay en disco para esa ciudad.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_CITY_FIELDS = {
    "display_name", "country", "bbox", "center", "zoom", "tagline", "locale",
}


class RegistryError(Exception):
    """cities.json malformado o entries inválidas."""


class CityNotFoundError(Exception):
    """Slug no presente en el registro."""


def load_cities(path: Path) -> dict[str, dict[str, Any]]:
    """Lee y valida cities.json. Devuelve dict {slug: metadata}."""
    if not Path(path).exists():
        raise RegistryError(f"cities.json no existe en {path}")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RegistryError(f"cities.json no es JSON válido: {e}") from e
    if not isinstance(data, dict):
        raise RegistryError("cities.json debe ser dict {slug: metadata}")
    for slug, entry in data.items():
        if not isinstance(entry, dict):
            raise RegistryError(f"Entry {slug!r} no es dict")
        missing = REQUIRED_CITY_FIELDS - set(entry.keys())
        if missing:
            raise RegistryError(
                f"Entry {slug!r} le faltan campos: {sorted(missing)}"
            )
        bbox = entry["bbox"]
        if not (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(isinstance(x, (int, float)) for x in bbox)
        ):
            raise RegistryError(
                f"Entry {slug!r}: bbox debe ser [s,w,n,e] de 4 floats"
            )
        s, w, n, e = bbox
        if s >= n:
            raise RegistryError(f"Entry {slug!r}: bbox inválido (south>=north)")
        if w >= e:
            raise RegistryError(f"Entry {slug!r}: bbox inválido (west>=east)")
    return data


def get_city(cities: dict, slug: str) -> dict:
    """Devuelve entry de la ciudad o lanza CityNotFoundError."""
    if slug not in cities:
        raise CityNotFoundError(
            f"Slug {slug!r} no está en el registro. "
            f"Disponibles: {sorted(cities.keys())}"
        )
    return cities[slug]


# ── Manifest IO ──────────────────────────────────────────────────────────────

VALID_MODULES = frozenset({"zoning", "vial", "services"})


def manifest_path(visualizer_root: Path, slug: str) -> Path:
    """Devuelve la ruta esperada del manifest para una ciudad."""
    return Path(visualizer_root) / "cities" / slug / "manifest.json"


def load_manifest(visualizer_root: Path, slug: str) -> dict | None:
    """Lee manifest.json de la ciudad. Devuelve None si no existe."""
    p = manifest_path(visualizer_root, slug)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RegistryError(f"manifest.json malformado para {slug}: {e}") from e


def hash_file(path: Path, length: int = 8) -> str:
    """sha256 trunco a `length` chars para cache busting (streaming)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:length]


def save_manifest_entry(
    visualizer_root: Path,
    slug: str,
    module: str,
    file_path: Path,
    features: int,
) -> dict:
    """Agrega/actualiza entry de `module` en manifest.json de la ciudad.

    Preserva entries de otros módulos. Crea directorio si no existe.
    Devuelve el manifest completo tras el merge.
    """
    if module not in VALID_MODULES:
        raise ValueError(
            f"módulo debe ser uno de {sorted(VALID_MODULES)}, no {module!r}"
        )
    manifest = load_manifest(visualizer_root, slug) or {"modules": {}}
    manifest.setdefault("modules", {})
    manifest["modules"][module] = {
        "hash": hash_file(file_path),
        "features": int(features),
    }
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    p = manifest_path(visualizer_root, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
