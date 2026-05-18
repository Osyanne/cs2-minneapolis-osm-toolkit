# Adapting This Pipeline to Other Cities

This pipeline is city-agnostic. Any city with reasonable OpenStreetMap coverage can be processed in under 20 minutes. If you haven't set up Python and uv yet, start with [QUICKSTART.md](QUICKSTART.md) — it walks through the full install from zero.

---

## Step 1: Find Your City's Bounding Box

You need four coordinates in `south,west,north,east` order — a rectangle that covers your city.

**Option A — bboxfinder.com (easiest for beginners):**

Go to [bboxfinder.com](http://bboxfinder.com/), zoom to your city, and draw a rectangle. The coordinates appear at the bottom of the page in the correct format. Copy them.

**Option B — Nominatim:**

Search your city on [nominatim.openstreetmap.org](https://nominatim.openstreetmap.org/). The result page shows a bounding box, or use the API directly:

    https://nominatim.openstreetmap.org/search?q=Chicago,IL,USA&format=json&limit=1

The response includes `"boundingbox": ["south", "north", "west", "east"]`. Note that Nominatim returns south, **north**, west, east — you need to reorder to south, **west**, north, east for these extractors.

**Option C — bbox-mcp-server (if you use AI tools):**

If you have the bbox-mcp-server set up, ask your AI assistant: "What is the bounding box for Chicago, IL?" See [bbox-mcp-server.md](bbox-mcp-server.md) for setup.

**Example bboxes:**

| City | Bounding Box |
|------|--------------|
| Minneapolis, MN | `44.86,-93.38,45.05,-93.17` |
| Saint Paul, MN | `44.88,-93.20,45.03,-92.99` |
| Madison, WI | `43.05,-89.50,43.15,-89.30` |
| Chicago, IL | `41.64,-87.94,42.02,-87.52` |
| Portland, OR | `45.43,-122.84,45.65,-122.47` |
| Austin, TX | `30.10,-97.97,30.52,-97.56` |
| Denver, CO | `39.61,-105.11,39.91,-104.60` |
| Sacramento, CA | `38.50,-121.55,38.65,-121.45` |
| Buenos Aires, AR | `-34.71,-58.55,-34.53,-58.34` |
| Berlin, DE | `52.35,13.10,52.65,13.78` |
| Tokyo (23 wards), JP | `35.53,139.55,35.82,139.92` |
| Amsterdam, NL | `52.30,4.78,52.43,5.02` |

Keep bboxes reasonably sized. A city's urban core (not the entire metro region) is usually the right scope. Very large bboxes will time out the Overpass API or produce files too large to be useful in the visualizer.

---

## Step 2: Run the Extractors

Open a terminal inside the `src/` folder. If you haven't done `uv sync` yet, do that first.

**Important (v3.3):** The CLI requires either `--city <slug>` (looks up bbox from `cities.json` registry) or `--bbox X --slug Y` together (escape hatch). Running `--bbox` alone errors out. Pick the slug you want your city to have under `visualizer/cities/<slug>/`.

**Zoning (building polygons classified into CS2 zone types):**

    uv run extract-zoning --bbox "south,west,north,east" --slug your_slug

This is the slowest extractor — 1–5 minutes depending on city size and how busy the Overpass servers are. It downloads building data and classifies each polygon into one of the 11 CS2 zone types.

Output: `visualizer/cities/your_slug/datos_zonificacion.js`

**Road network (roads classified into CS2 road categories):**

    uv run extract-vial --bbox "south,west,north,east" --slug your_slug

Usually under a minute. Classifies all OSM `highway=*` ways into the 6 CS2 road categories.

Output: `visualizer/cities/your_slug/datos_vial.js`

**Services (hospitals, schools, fire stations, parks, police/admin):**

    uv run extract-services --bbox "south,west,north,east" --slug your_slug

Usually under a minute. Returns points and polygons for 5 service buckets aligned to CS2's service tabs.

Output: `visualizer/cities/your_slug/datos_servicios.js`

You can run all three for the same slug, or just the ones you need. Each extract updates the city's `manifest.json` preserving other modules already generated.

**Example for Madison, WI:**

    uv run extract-zoning --bbox "43.05,-89.50,43.15,-89.30" --slug madison
    uv run extract-vial --bbox "43.05,-89.50,43.15,-89.30" --slug madison
    uv run extract-services --bbox "43.05,-89.50,43.15,-89.30" --slug madison

(Note: `madison` is already in `cities.json`. To use it without `--bbox`, simply run `uv run extract-zoning --city madison`.)

---

## Step 3: Open the Visualizer

Run `uv run generate-landing` once to add your new city to the landing page. Then go to the `visualizer/` folder and double-click `index.html` — your city will appear as a card in the gallery. Click it to open `map.html?city=your_slug`. The map centers automatically using the bbox/center from your extraction.

If the map appears blank or shows an error, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Step 4: Calibrate Density Thresholds (if needed)

The density thresholds in the zoning classifier were tuned for Minneapolis. They may not be a perfect fit for your city.

Open your city's visualizer and compare against Google Maps or local knowledge. Look at areas you know well:

- **Too much high-density (red) in suburban areas?** The `building:levels` threshold is too low. Raise it in `src/zoning/classifiers.py`.
- **Dense downtown showing as low-density (green)?** Lower the high-density threshold.
- **Everything classified as low-density?** Your city likely has sparse `building:levels` data in OSM. See the coverage section below.

The relevant thresholds are in `src/zoning/classifiers.py` in the `classify_residential()` function:

    if (effective_levels >= 5   # raise or lower for high density
            or residential_subtype in ("apartments", "condominium", "condo")):
        return "high"

    if (effective_levels >= 3   # raise or lower for medium density
            or building_type in ("terrace", "dormitory", "townhouse")
            ...):
        return "medium"

**For European cities:** residential buildings tend to be denser at lower floor counts than US cities. You may get better results lowering these thresholds by 1–2 floors. A 4-floor Paris apartment block should probably classify as high density, not medium.

**For US Sun Belt cities:** low `building:levels` coverage is common even in dense areas. If most buildings are coming out as low-density, check OSM coverage first before adjusting thresholds.

---

## OSM Coverage Gaps Will Affect Your Output

This is worth being upfront about. OSM is a volunteer-built map, and coverage varies significantly by region.

The toolkit works best for cities where contributors have mapped:
- Building footprints with `building:levels` tags (for density classification)
- `landuse=residential/commercial/industrial` polygons (for broad zone classification)
- Amenity and facility tags (`amenity=hospital`, `leisure=park`, etc.) for services

Cities with strong OSM communities — most of North America, Western Europe, Japan, Australia — usually produce good results. Cities with sparser coverage may produce fewer polygons and coarser classification.

Longfellow and some inner-ring Minneapolis neighborhoods are a good example: even with good US city coverage, some blocks have missing `building:levels` data, which causes those buildings to fall through to low-density classification even when they're clearly not.

**Check your city's coverage** at [osmstats.neis-one.org](https://osmstats.neis-one.org/). If the edit and contributor counts are low, expect sparse output.

The best fix is contributing to OSM for your area — it improves the map for everyone, not just this tool. The OSM wiki has tutorials for beginners.

---

## A Note on Zoning vs. Land Use

This toolkit classifies buildings using OSM land use tags and building attributes, not actual municipal zoning data. These are related but not the same thing. What OSM tags as "residential" matches what CS2 calls residential zone, but the exact density breakdown is an approximation based on floor counts and building types — not a direct read from your city's zoning code. For a reference layer while building in CS2, this is accurate enough. For anything requiring legal zoning data, consult your municipality's GIS portal.

---

## Common Errors

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for fixes for Overpass timeouts, empty output, uv errors, and visualizer issues.
