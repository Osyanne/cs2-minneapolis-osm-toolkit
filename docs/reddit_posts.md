# Reddit Post Drafts

> Author: u/Kingleyend (Reddit) / Osyanne (GitHub)
> Post these AFTER creating the GitHub repo and uploading screenshots.
> Replace `[SCREENSHOT: ...]` placeholders with actual image uploads.

---

## v3.0 — UPDATE POSTS (post 2026-05-15)

These are the current posts to use. They build on v1.0 with the work done across Sessions 1.5-1.7. The v1.0 posts below are kept for history.

---

### Post A — r/CitiesSkylines2 [PRIMARY TARGET]

**Title (pick one):**
```
[OC] I rewrote my OpenStreetMap → CS2 zoning tool — now 81k polygons across all 11 official CS2 zones (Minneapolis 1:1, free + open source)
```

OR more conversational:
```
[Tool] Free zoning reference map: real Minneapolis as the 11 official CS2 zones (now with 81k polygons after a major rewrite)
```

**Body:**

---

Hey r/CitiesSkylines2!

A few weeks ago I posted a small GIS tool that pulled zoning data from OpenStreetMap for my Minneapolis 1:1 build. It was useful but rough — only ~1,500 polygons, generic density categories, and the Overpass queries timed out half the time.

**I went back and rewrote it.** Sharing v3.0 now because the difference is night and day.

### What changed

| | v1.0 | v3.0 |
|---|---|---|
| Total polygons | ~1,500 | **81,732** |
| Zone categories | 10 generic | **All 11 official CS2 zones** |
| Pan/zoom feel | Slow | Smooth (Canvas renderer) |
| Loading time | 10-15 min | <2 seconds (prebuilt mode) |
| Mixed Housing detection | n/a | Spatial join (123 polygons) |

### The 11 CS2 zones, mapped from OSM

- **Residential (6):** Low Density Housing, Medium Density Row Housing, Medium Density Housing, **Mixed Housing**, Low Rent Housing, High Density Housing
- **Commercial (2):** Low Density Business, High Density Business
- **Offices (2):** Low Density Offices, High Density Offices
- **Industrial (1):** Industrial Manufacturing

Plus Surface Parking + Parking Structure for visual reference (not technically a CS2 zone).

For Mixed Housing specifically I had to use an Overpass spatial join — `way["building"="apartments"](around.comm:5)` — because in OSM the shops are tagged as separate nodes inside the apartment polygon, not on the building way itself. The naive query found 3 polygons. The spatial join found 123.

### Why this might be useful

Use it as a reference while building. Each polygon is colored by its real CS2 zone type so you can:
- See which corridors should be commercial vs residential
- Place Mixed Housing where it actually exists IRL (Hennepin, Nicollet, Lyn-Lake)
- Get the suburban → urban density gradient right

### Lessons from the rewrite (might save you time)

I also tried augmenting OSM with **Microsoft's USBuildingFootprints** (5M+ buildings detected from satellite imagery) to fill suburban gaps where OSM doesn't tag every house. **It didn't work**: the classifier got confused by big individual buildings (a Target store ≈ 13,000 m²) and started coloring neighboring houses as commercial within a 500m radius. The script is still in the repo with a caveat — if anyone wants to fix the classification logic (use only `landuse=*` polygons as anchors, tighten radius to 100m), it's there as a starting point.

### Tech stack

- Python + Overpass API (no API keys, no PostGIS, no QGIS)
- Leaflet.js with Canvas renderer
- CartoDB Dark Matter basemap (matches CS2 editor aesthetic)
- Total install: 5 minutes

[SCREENSHOT: preview_full.png]
[SCREENSHOT: preview_downtown.png]

**Repo:** https://github.com/Osyanne/cs2-minneapolis-zoning

Works for any city — just change the bbox. Adapted to NYC, LA, etc. in ~2 minutes. Methodology doc walks through every design decision (why 7 source queries instead of 1, the spatial join syntax gotcha, the tier-based hiding for performance, etc.).

Happy to answer questions. Hoping someone takes this and runs with it for their own 1:1 build.

---

### Post B — r/CitiesSkylines [BROADER AUDIENCE]

Same content as Post A, but adapted slightly to acknowledge both CS1 and CS2 audience. Either cross-post Post A or use this title:

**Title:**
```
[OC] Open-source tool that turns OpenStreetMap data into CS2 zoning reference maps (Minneapolis demo, works for any city)
```

Body: same as Post A.

---

### Post C — r/openstreetmap [TECHNICAL AUDIENCE]

**Title:**
```
Pipeline for classifying OSM landuse + building data into urban zoning categories — Cities Skylines 2 mapping use case, but generic [OC]
```

**Body:**

---

Sharing an open-source project that might interest folks here. I'm using Overpass API for a city-building game (Cities Skylines 2) but the pipeline is general enough for any urban analysis where you want to bucket OSM polygons by zoning type.

### Technical bits

**1. Spatial join for mixed-use detection.** OSM commonly tags commercial POIs (shops, restaurants) as separate nodes inside an apartment building's polygon, not on the way itself. To detect mixed-use buildings, I use:

```overpass
[out:json][timeout:120];
(
  node["shop"](bbox);
  node["amenity"~"^(restaurant|cafe|bar|pub|fast_food)$"](bbox);
)->.comm;
(
  way["building"="apartments"](around.comm:5);
  way["building"="residential"](around.comm:5);
);
out body geom;
```

Note the **named set** syntax (`->.comm`). I initially used `(around:5)` with the implicit `_` set — returned 0 results consistently. After using the explicit named set, the same query returns 123 polygons in Minneapolis.

**2. Element-ID dedup across categories.** OSM has overlapping semantics (downtown blocks are tagged both `landuse=commercial` and `building=office`). Processing queries in priority order and maintaining a global `seen_ids` set prevents stacked polygons.

**3. Footprint area heuristic.** To distinguish "block-scale" landuse polygons (~50,000 m²) from "individual buildings" (~150 m²), I compute area via equirectangular projection at the centroid + shoelace. Sufficient at urban scale.

**4. Multi-endpoint retry.** Rotates across 3 Overpass endpoints + corsproxy.io fallback + 3 retries × 2s/4s/8s backoff. Handles transient overload but NOT silent empty responses (Overpass returning 200 with `{"elements": []}`) — this is a known weakness.

### Output

13-category JS data file + Leaflet visualizer with Canvas renderer. 81k polygons render smoothly.

### Caveat I want to flag

I also tried augmenting with Microsoft's USBuildingFootprints (5M+ buildings from satellite imagery). It works mechanically but the classification logic is broken: using individual buildings ≥3,000 m² as classification anchors pulls nearby houses into wrong categories. The right fix is to use ONLY `landuse=*` polygons as anchors. Script is in the repo with a caveat — would love a contributor to fix it.

**Repo:** https://github.com/Osyanne/cs2-minneapolis-zoning

The methodology doc has 13 sections walking through every decision. Feedback welcome.

---

## v1.0 — ORIGINAL POSTS (history, used at v1.0 release)

---

## Post 1 — r/CitiesSkylines + r/CitiesSkylinesModding

**Title:**
```
I built a free GIS tool to extract real-world zoning data from OpenStreetMap for CS2 maps — Minneapolis 1:1 v1.0 [OC]
```

**Body:**

---

Hey r/CitiesSkylines!

After months of work on my Minneapolis 1:1 recreation in CS2, I've open-sourced the GIS pipeline I built to generate the zoning layer. Figured the community might find it useful.

**What it does:**
Pulls real zoning polygons directly from OpenStreetMap (Overpass API) and classifies them into CS2-native zone types automatically:

| Real World                    | CS2 Zone                                    |
|-------------------------------|---------------------------------------------|
| landuse=residential + ≥5 fl.  | North American High Density Residential     |
| landuse=residential + ≥3 fl.  | North American Medium Density Residential   |
| landuse=residential (default) | North American Low Density Residential      |
| landuse=commercial + ≥4 fl.   | North American High Density Commercial      |
| landuse=commercial (default)  | North American Low Density Commercial       |
| landuse=retail                | North American Retail Hub                   |
| landuse=industrial            | North American Industrial Zone              |
| amenity=parking + multi-storey| Parking Garage / Ramp                       |
| amenity=parking (default)     | Surface Parking Lot                         |
| building=office               | Office / Government Building                |
| landuse=mixed                 | Mixed-Use Development                       |

**What's included in the repo:**
- Python extraction script (runs in ~15 minutes)
- Interactive Leaflet.js visualizer with dark map (CartoDB Dark Matter)
- Full methodology explaining every design decision
- Guide to adapt it to ANY city, not just Minneapolis

**Tech stack:** Python + uv, Overpass API, Leaflet.js. All 100% free, no API keys.

**Coverage:** Full city of Minneapolis + immediate borders (~44.86,-93.38 to 45.05,-93.17)

[SCREENSHOT: preview_full.png]
[SCREENSHOT: preview_downtown.png]

GitHub: https://github.com/Osyanne/cs2-minneapolis-zoning

Happy to answer questions about the methodology or help anyone adapt this to their own city. The density thresholds (≥5 floors = high density) were calibrated specifically for Minneapolis — other cities may need adjustment.

---

## Post 2 — r/gis

**Title:**
```
Free pipeline: OpenStreetMap → Leaflet.js zoning visualizer, built for Cities Skylines 2 but works for any urban analysis [OC]
```

**Body:**

---

Sharing a small open-source project that might interest the OSM/GIS community.

I needed real zoning data for a 1:1 recreation of Minneapolis in Cities: Skylines 2. Instead of using proprietary city GIS portals, I built a pipeline entirely on top of OpenStreetMap via the Overpass API.

**Technical highlights:**

1. **Sequential queries, not one mega-query**
   Splitting by category (residential/commercial/industrial/etc.) avoids the 504 timeouts that kill large bbox queries on public Overpass instances.

2. **Two-pass density classification**
   First pass: index all `building:levels` tags from apartment footprints.
   Second pass: when classifying `landuse=residential` polygons, look up the max floor count from buildings within each polygon to infer density. Simple but effective without needing spatial joins.

3. **Multi-endpoint rotation with exponential backoff**
   Rotates across 4 community Overpass endpoints (overpass-api.de, kumi.systems, openstreetmap.ru, maps.mail.ru) with 3s/6s/12s backoff. Practically eliminates failures on large bboxes.

4. **Zero dependencies beyond Python + requests**
   No PostGIS, no QGIS, no GeoPandas. Everything runs in a single script.

**Output:** A JavaScript data file with classified polygon arrays, rendered via Leaflet.js on a CartoDB Dark Matter basemap. The dark basemap is intentional — it mirrors the CS2 map editor aesthetic.

[SCREENSHOT: preview_full.png]

GitHub: https://github.com/Osyanne/cs2-minneapolis-zoning

The pipeline should work for any city with decent OSM coverage. Methodology doc explains all the classification decisions and edge cases.

---

## Post 3 — r/openstreetmap

**Title:**
```
I used Overpass API to extract and classify zoning data for a 1:1 city recreation in Cities Skylines 2 — full pipeline open sourced [OC]
```

**Body:**

---

Sharing a small open-source project that might interest the OSM/GIS community.

I needed real zoning data for a 1:1 recreation of Minneapolis in Cities: Skylines 2. Instead of using proprietary city GIS portals, I built a pipeline entirely on top of OpenStreetMap via the Overpass API.

**Technical highlights:**

1. **Sequential queries, not one mega-query**
   Splitting by category (residential/commercial/industrial/etc.) avoids the 504 timeouts that kill large bbox queries on public Overpass instances.

2. **Two-pass density classification**
   First pass: index all `building:levels` tags from apartment footprints.
   Second pass: when classifying `landuse=residential` polygons, look up the max floor count from buildings within each polygon to infer density. Simple but effective without needing spatial joins.

3. **Multi-endpoint rotation with exponential backoff**
   Rotates across 4 community Overpass endpoints (overpass-api.de, kumi.systems, openstreetmap.ru, maps.mail.ru) with 3s/6s/12s backoff. Practically eliminates failures on large bboxes.

4. **Zero dependencies beyond Python + requests**
   No PostGIS, no QGIS, no GeoPandas. Everything runs in a single script.

**Output:** A JavaScript data file with classified polygon arrays, rendered via Leaflet.js on a CartoDB Dark Matter basemap. The dark basemap is intentional — it mirrors the CS2 map editor aesthetic.

[SCREENSHOT: preview_full.png]

GitHub: https://github.com/Osyanne/cs2-minneapolis-zoning

The pipeline should work for any city with decent OSM coverage. Methodology doc explains all the classification decisions and edge cases.

---

## Posting checklist

- [ ] GitHub repo is public and accessible
- [ ] Screenshots uploaded to the repo (so Reddit image embeds work from GitHub)
- [ ] Preview images show in the repo README
- [ ] Post to r/CitiesSkylines first (largest audience)
- [ ] Cross-post to r/CitiesSkylinesModding
- [ ] Post separately (not cross-post) to r/gis and r/openstreetmap with adapted text
- [ ] Reply to comments within first hour for visibility boost
