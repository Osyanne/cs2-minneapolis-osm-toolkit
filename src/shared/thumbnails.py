#!/usr/bin/env python3
"""
thumbnails.py — Auto-generate city card thumbnails for the visualizer landing
==============================================================================
v3.4.0 — Reemplaza el flujo manual (Playwright MCP) por un entry point CLI.

Para cada slug de cities.json que NO tenga ya un PNG en
visualizer/assets/thumbnails/<slug>.png, este script:

  1. Lanza Chromium headless via playwright.
  2. Navega a la URL deployed (o local) del map para esa ciudad.
  3. Espera a que el render termine (loading overlay desaparece).
  4. Oculta el chrome UI (header pills, layers control, attribution).
  5. Captura un screenshot 1200×800 y lo guarda en disco.

Triggers:
  - Solo missing thumbnails:    `uv run generate-thumbnails`
  - Una ciudad específica:      `uv run generate-thumbnails --city bacau_ro`
  - Forzar regen de TODAS:      `uv run generate-thumbnails --force`
  - Apuntar a server local:     `uv run generate-thumbnails --base-url http://localhost:8080`

Dependencias:
  playwright vive en el grupo [dependency-groups.thumbnails] (opt-in por peso
  del binario Chromium ~300 MB). Para correr la primera vez:

    uv sync --group thumbnails
    uv run --group thumbnails playwright install chromium
    uv run --group thumbnails generate-thumbnails

Convención de output:
  - PNG, 1200×800, type=image/png
  - filename = `<slug>.png` (mismo slug que cities.json)
  - dir = `<repo>/visualizer/assets/thumbnails/`
"""

import argparse
import sys
from pathlib import Path

from shared.registry import load_cities, get_city, CityNotFoundError, RegistryError


DEFAULT_BASE_URL = "https://osyanne.github.io/CitiesSkylines2-osm-toolkit/visualizer"
VIEWPORT_W, VIEWPORT_H = 1200, 800
# Per-city wait budget. Ciudades con dataset grande (Mpls 60 MB, Mafra ~12 MB
# con Google) requieren más settle time tras el render para que los polígonos
# canvas-renderizados aparezcan completos en el screenshot.
LOAD_TIMEOUT_MS = 120_000
SETTLE_MS = 5_000


# ── Discovery ────────────────────────────────────────────────────────────────

def discover_missing(
    cities: dict,
    out_dir: Path,
    force: bool,
    only_city: str | None,
) -> list[str]:
    """
    Decide qué slugs necesitan thumbnail.

    - Si only_city está dado: solo ese (siempre lo regenera).
    - Si force=True: todas las del registry.
    - Default: solo las que no tienen <slug>.png ya en disco.
    """
    if only_city:
        if only_city not in cities:
            raise CityNotFoundError(
                f"slug {only_city!r} no está en cities.json. "
                f"Disponibles: {sorted(cities.keys())}"
            )
        return [only_city]

    if force:
        return sorted(cities.keys())

    missing = []
    for slug in sorted(cities.keys()):
        if not (out_dir / f"{slug}.png").exists():
            missing.append(slug)
    return missing


# ── Playwright capture (lazy import — solo si hay slugs que procesar) ────────

def _hide_chrome_js() -> str:
    """JS que oculta el chrome UI del visualizer antes del screenshot."""
    return """
    () => {
      const hide = (sel) => document.querySelectorAll(sel)
        .forEach(el => el.style.display = 'none');
      hide('#loading');
      hide('header');
      hide('.leaflet-control-layers');
      hide('.leaflet-control-zoom');
      hide('.leaflet-control-attribution');
      return 'OK';
    }
    """.strip()


def _wait_for_render_js() -> str:
    """Predicate JS: true cuando el loading overlay está hidden + título cambió."""
    return """
    () => {
      const loadingEl = document.getElementById('loading');
      const titleOk = document.title.indexOf('Cargando') === -1;
      const overlayHidden = !loadingEl || loadingEl.style.display === 'none';
      return titleOk && overlayHidden;
    }
    """.strip()


def capture_thumbnails(
    slugs: list[str],
    base_url: str,
    out_dir: Path,
) -> dict[str, str]:
    """
    Captura PNG por cada slug. Returns {slug: status} con 'ok' o 'failed: <msg>'.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(
            "Error: playwright no está instalado. Corre primero:\n"
            "  uv sync --group thumbnails\n"
            "  uv run --group thumbnails playwright install chromium",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    results: dict[str, str] = {}
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
        )
        page = ctx.new_page()

        for slug in slugs:
            url = f"{base_url}/map.html?city={slug}"
            target = out_dir / f"{slug}.png"
            print(f"[{slug}] {url} → {target.name}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
                page.wait_for_function(
                    _wait_for_render_js(), timeout=LOAD_TIMEOUT_MS,
                )
                page.wait_for_timeout(SETTLE_MS)
                page.evaluate(_hide_chrome_js())
                page.wait_for_timeout(500)  # let style mutations apply
                # Mouse fuera del map para evitar tooltips parásitos
                page.mouse.move(1, 1)
                page.screenshot(path=str(target), type="png", full_page=False)
                size_kb = target.stat().st_size // 1024
                print(f"  ok → {size_kb} KB")
                results[slug] = "ok"
            except Exception as e:
                print(f"  failed: {e}", file=sys.stderr)
                results[slug] = f"failed: {e}"

        browser.close()

    return results


# ── Main CLI ─────────────────────────────────────────────────────────────────

def main():
    # Windows fix: stdout/stderr default to cp1252, which crashes on Unicode
    # arrows/checkmarks used below. Force UTF-8 if available (Python 3.7+).
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    parser = argparse.ArgumentParser(
        description="Generate city card thumbnails for the visualizer landing.",
    )
    parser.add_argument(
        "--city", default=None,
        help="Solo generar thumbnail para este slug (default: todos los missing).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerar thumbnails de TODAS las cities (sobreescribe PNGs existentes).",
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL,
        help=(
            "Base URL del visualizer. Default: GH Pages deployed. "
            "Para dev local: http://localhost:8080"
        ),
    )
    parser.add_argument(
        "--cities-file", default=None,
        help="Path a cities.json (default: <repo>/cities.json).",
    )
    parser.add_argument(
        "--out-dir", default=None,
        help="Output dir para PNGs (default: <repo>/visualizer/assets/thumbnails).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    cities_file = Path(args.cities_file) if args.cities_file else repo_root / "cities.json"
    out_dir = (
        Path(args.out_dir) if args.out_dir
        else repo_root / "visualizer" / "assets" / "thumbnails"
    )

    try:
        cities = load_cities(cities_file)
    except RegistryError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        slugs = discover_missing(cities, out_dir, args.force, args.city)
    except CityNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not slugs:
        print("Nothing to do — todas las cities ya tienen thumbnail en disk.")
        print(f"  (revisa {out_dir})")
        return

    print(f"Generating {len(slugs)} thumbnail(s) at {VIEWPORT_W}x{VIEWPORT_H}:")
    for s in slugs:
        print(f"  - {s}")
    print(f"Base URL    : {args.base_url}")
    print(f"Output dir  : {out_dir}\n")

    results = capture_thumbnails(slugs, args.base_url, out_dir)

    print("\nSummary:")
    ok = sum(1 for v in results.values() if v == "ok")
    failed = len(results) - ok
    for slug, status in results.items():
        marker = "✓" if status == "ok" else "✗"
        print(f"  {marker} {slug:<24} {status}")
    print(f"\n{ok} ok, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
