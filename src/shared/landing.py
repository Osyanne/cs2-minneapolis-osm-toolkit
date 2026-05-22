"""Generador de landing page (visualizer/index.html) desde cities.json + manifests."""
import argparse
import html
import json
from pathlib import Path

from shared.registry import load_cities, load_manifest


MODULE_LABELS = {
    "zoning": "Zoning",
    "vial": "Vial",
    "services": "Servicios",
}

REPO_URL = "https://github.com/Osyanne/CitiesSkylines2-osm-toolkit"
ISSUE_NEW_URL = f"{REPO_URL}/issues/new?template=city-request.yml"
PATREON_URL = "https://www.patreon.com/c/CS2OSMToolkit"

# Region display names for pills (slug → label)
REGION_LABELS = {
    "all": "All",
    "north-america": "North America",
    "europe": "Europe",
    "south-america": "South America",
    "asia": "Asia",
    "africa": "Africa",
    "oceania": "Oceania",
    "other": "Other",
}


def _format_count(n: int) -> str:
    """Format feature count humanizado: 12345 → '12.3k', 1500000 → '1.5M'."""
    n = max(0, n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def country_to_flag(code: str | None) -> str:
    """ISO 3166-1 alpha-2 code → flag emoji via regional indicator chars.

    Returns empty string for falsy or invalid input (graceful fallback for
    cities without a country_code field).
    """
    if not code or len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c.upper()) - ord("A")) for c in code)


COUNTRY_TO_REGION = {
    # North America
    "USA": "north-america",
    "Canada": "north-america",
    "Mexico": "north-america",
    # Europe
    "Netherlands": "europe",
    "Norway": "europe",
    "Romania": "europe",
    "Germany": "europe",
    "France": "europe",
    "UK": "europe",
    "Spain": "europe",
    "Italy": "europe",
    "Portugal": "europe",
    # South America
    "Brazil": "south-america",
    "Argentina": "south-america",
    "Chile": "south-america",
    "Colombia": "south-america",
    # Asia (placeholder for future)
    "Japan": "asia",
    "China": "asia",
    "South Korea": "asia",
}


def region_counts(cities: dict) -> dict[str, int]:
    """Count cities per region for filter pills. Always includes 'all' key."""
    counts = {"all": len(cities)}
    for entry in cities.values():
        region = COUNTRY_TO_REGION.get(entry["country"], "other")
        counts[region] = counts.get(region, 0) + 1
    return counts


def _read_version_short(default: str = "v3.4") -> str:
    """Reads major.minor from pyproject.toml. Falls back to default on any error.

    Note: pyproject.toml lives at src/pyproject.toml — `parents[1]` from
    `src/shared/landing.py` resolves to `src/`.
    """
    try:
        import tomllib  # Python 3.11+
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        full = data["project"]["version"]  # e.g. "3.4.0"
        parts = full.split(".")
        return f"v{parts[0]}.{parts[1]}"
    except Exception:
        return default


def build_stats(cities: dict, manifests: dict) -> dict:
    """Compute 4 stats for the hero banner."""
    total_features = 0
    for slug, manifest in manifests.items():
        if not manifest:
            continue
        for mod in manifest.get("modules", {}).values():
            total_features += mod.get("features", 0)
    return {
        "cities_count": len(cities),
        "features_total": _format_count(total_features),
        "countries_count": len(set(c["country"] for c in cities.values())),
        "version": _read_version_short(),
    }


def _card_html(slug: str, entry: dict, manifest: dict | None) -> str:
    """Generate the <a class='card'> for one city."""
    name = html.escape(entry["display_name"])
    country = html.escape(entry["country"])
    country_code = entry.get("country_code", "")
    tagline = html.escape(entry["tagline"])
    flag = country_to_flag(country_code)
    region = COUNTRY_TO_REGION.get(entry["country"], "other")

    # Precomputed lowercase search index (avoids client-side toLowerCase per keystroke)
    search_index = html.escape(
        f"{entry['display_name']} {entry['country']} {entry['tagline']}".lower()
    )

    # Module dots — fixed order: zoning, vial, services
    if manifest is None or not manifest.get("modules"):
        mods_html = (
            '<span class="mod off" aria-label="Zoning not available"></span>'
            '<span class="mod off" aria-label="Vial not available"></span>'
            '<span class="mod off" aria-label="Services not available"></span>'
        )
        total = 0
    else:
        present = manifest.get("modules", {})
        labels = {
            "zoning": "Zoning",
            "vial": "Vial",
            "services": "Services",
        }
        dot_pieces = []
        for key in ("zoning", "vial", "services"):
            label = labels[key]
            if key in present:
                dot_pieces.append(
                    f'<span class="mod" aria-label="{label} available"></span>'
                )
            else:
                dot_pieces.append(
                    f'<span class="mod off" aria-label="{label} not available"></span>'
                )
        mods_html = "".join(dot_pieces)
        total = sum(d.get("features", 0) for d in present.values())

    flag_html = f"{flag} " if flag else ""

    return (
        f'<a href="map.html?city={html.escape(slug)}" class="card"'
        f' data-region="{region}"'
        f' data-search="{search_index}">'
        f'<div class="thumb">'
        f'<img loading="lazy" src="assets/thumbnails/{html.escape(slug)}.png"'
        f' alt="Zoning map of {name}">'
        f'</div>'
        f'<div class="body">'
        f'<h4>{name}</h4>'
        f'<div class="loc">{flag_html}{country}</div>'
        f'<div class="tag">{tagline}</div>'
        f'<div class="meta">'
        f'<div class="modules">{mods_html}</div>'
        f'<span class="count">{_format_count(total)}</span>'
        f'</div>'
        f'</div>'
        f'</a>'
    )


def _build_pills_html(cities: dict) -> str:
    """Generate the filter pill buttons. 'all' is always active by default."""
    counts = region_counts(cities)
    # Always include 'all' first
    pills = [("all", counts["all"])]
    # Then any region present (in defined order)
    for slug in ("north-america", "europe", "south-america", "asia", "africa", "oceania", "other"):
        if slug in counts:
            pills.append((slug, counts[slug]))
    pieces = []
    for i, (slug, count) in enumerate(pills):
        active = ' class="active" aria-pressed="true"' if i == 0 else ' aria-pressed="false"'
        label = REGION_LABELS.get(slug, slug.title())
        pieces.append(
            f'<button{active} data-region="{slug}">{label} · {count}</button>'
        )
    return "\n        ".join(pieces)


def build_landing_html(cities: dict, manifests: dict) -> str:
    """Build the complete landing HTML."""
    cards = "\n".join(
        _card_html(slug, entry, manifests.get(slug))
        for slug, entry in cities.items()
    )
    stats = build_stats(cities, manifests)
    pills_html = _build_pills_html(cities)

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CS2 OSM Toolkit — Real-world cities for your CS2 builds</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/landing.css">
</head>
<body>
  <div class="wrap">
    <nav class="top">
      <div class="brand">
        <div class="logo">🏙</div>
        CS2 OSM Toolkit
        <span class="ver">{stats["version"]}</span>
      </div>
      <div class="links">
        <a href="{REPO_URL}#readme" data-secondary>Docs</a>
        <a href="{REPO_URL}/blob/main/METHODOLOGY.md" data-secondary>Methodology</a>
        <a href="{REPO_URL}" data-tertiary>GitHub</a>
        <a href="{PATREON_URL}" class="cta">Support →</a>
      </div>
    </nav>

    <section class="hero">
      <a class="badge" href="{REPO_URL}#roadmap"><span class="dot"></span> v3.5 — Browser generator in development</a>
      <h1>OpenStreetMap zoning<br>for <span class="grad">Cities: Skylines 2</span> builders.</h1>
      <p class="lede">Real-world cities, ready to import. Open data, open source, zero friction. Browse {stats["cities_count"]} curated maps or request your own.</p>
      <div class="ctas">
        <a href="#gallery" class="primary">Browse cities ↓</a>
        <a href="{ISSUE_NEW_URL}" class="secondary" target="_blank" rel="noopener">Request your city</a>
      </div>

      <div class="stats" role="list" aria-label="Project stats">
        <div role="listitem"><strong>{stats["cities_count"]}</strong><span>Cities</span></div>
        <div role="listitem"><strong>{stats["features_total"]}</strong><span>Features</span></div>
        <div role="listitem"><strong>{stats["countries_count"]}</strong><span>Countries</span></div>
        <div role="listitem"><strong>{stats["version"]}</strong><span>Version</span></div>
      </div>
    </section>

    <section id="gallery">
      <h2 class="sr-only">Featured cities</h2>
      <div class="filter-bar">
        <label class="sr-only" for="search">Search cities</label>
        <div class="filter-pills" role="group" aria-label="Filter by region">
        {pills_html}
        </div>
        <div class="search">
          <input id="search" type="search" placeholder="Search cities…" autocomplete="off">
        </div>
      </div>

      <div class="grid">
{cards}
        <a class="card request" href="{ISSUE_NEW_URL}" target="_blank" rel="noopener">
          <svg class="plus" viewBox="0 0 24 24" width="32" height="32" stroke="currentColor" stroke-width="1.5" fill="none" aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          <h4>Request your city</h4>
          <p>Open an issue with your bbox and we'll add it to the collection.</p>
          <span class="cta">Open issue template →</span>
        </a>
      </div>

      <div id="empty-state" class="empty-state">
        <p>No cities match. Try a different filter, or <a href="{ISSUE_NEW_URL}" target="_blank" rel="noopener">request your city →</a></p>
      </div>
    </section>

    <footer>
      <div>MIT licensed · OSM data © OpenStreetMap contributors · Built by <a href="https://github.com/Osyanne">@Osyanne</a></div>
      <div class="right">
        <a href="{REPO_URL}">GitHub</a>
        <a href="{PATREON_URL}" class="patreon-link">Patreon</a>
        <a href="{ISSUE_NEW_URL}" target="_blank" rel="noopener">Request a city</a>
      </div>
    </footer>
  </div>

  <script>
  (() => {{
    const cards = document.querySelectorAll('.card[data-region]');
    const pills = document.querySelectorAll('.filter-pills button');
    const search = document.getElementById('search');
    const empty = document.getElementById('empty-state');
    let region = 'all', query = '';
    function apply() {{
      let visible = 0;
      cards.forEach(c => {{
        const okRegion = region === 'all' || c.dataset.region === region;
        const okQuery = !query || c.dataset.search.includes(query);
        const show = okRegion && okQuery;
        c.style.display = show ? '' : 'none';
        if (show) visible++;
      }});
      empty.classList.toggle('visible', visible === 0);
    }}
    pills.forEach(p => p.addEventListener('click', () => {{
      pills.forEach(x => {{
        x.classList.toggle('active', x === p);
        x.setAttribute('aria-pressed', x === p ? 'true' : 'false');
      }});
      region = p.dataset.region;
      apply();
    }}));
    search.addEventListener('input', e => {{
      query = e.target.value.toLowerCase().trim();
      apply();
    }});
  }})();
  </script>
</body>
</html>
'''


def main():
    parser = argparse.ArgumentParser(
        description="Generate landing index.html from cities.json + manifests"
    )
    parser.add_argument(
        "--cities-file", default=None,
        help="Path a cities.json (default: <repo_root>/cities.json)",
    )
    parser.add_argument(
        "--visualizer-root", default=None,
        help="Path a visualizer/ (default: <repo_root>/visualizer)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Path al index.html de salida (default: <visualizer_root>/index.html)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    cities_file = Path(args.cities_file) if args.cities_file else repo_root / "cities.json"
    vis_root = Path(args.visualizer_root) if args.visualizer_root else repo_root / "visualizer"
    out_path = Path(args.out) if args.out else vis_root / "index.html"

    cities = load_cities(cities_file)
    manifests = {slug: load_manifest(vis_root, slug) for slug in cities}

    html_content = build_landing_html(cities, manifests)
    out_path.write_text(html_content, encoding="utf-8")

    # Copiar cities.json a visualizer/ — necesario porque GH Pages sirve
    # solo desde /visualizer (no puede acceder a ../cities.json).
    # El root cities.json sigue siendo source of truth; este es deployment artifact.
    deployed_registry = vis_root / "cities.json"
    deployed_registry.write_text(
        json.dumps(cities, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Landing generada: {out_path}")
    print(f"Registro deployado: {deployed_registry}")
    print(f"Cities incluidas: {sorted(cities.keys())}")
