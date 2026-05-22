# Landing Redesign — Design Spec

> **Date:** 2026-05-22
> **Status:** Design approved — implementation pending
> **Author:** Imanol Miranda (`@Osyanne`)
> **Repo:** `CitiesSkylines2-osm-toolkit`
> **Predecessor:** v3.4.0 (PBF migration shipped 2026-05-20)
> **Touches:** `src/shared/landing.py`, `visualizer/assets/landing.css` (new), `cities.json`

---

## 1. Summary

Rediseño visual completo de la landing page (`visualizer/index.html`) generada por `src/shared/landing.py`. Pasa de un grid de 10 cards muy simple (header + grid + footer) a una landing con personalidad estilo Linear/Cal.com: hero con badge animado + headline gradient + stats banner, filter bar con pills por región + search, grid de 3 columnas con cards más ricas (flag emoji, module dots, count en monospace), footer minimal con link discreto a Patreon.

**Por qué ahora:** la landing actual se siente "básica" y desperdicia el valor que tiene la colección (10 ciudades, 855k features, 5 países). El polish visual eleva la percepción del proyecto sin acoplar nada al modelo de monetización (que sigue abierto).

**Por qué este shape (open-source con personalidad):** explorados 3 estilos en mockups HTML reales (`docs/mockups/landing-redesign/{editorial,open-source,cs2-gaming}.html`). Usuario eligió **open-source-con-personalidad** sobre editorial-magazine y sobre CS2-gaming-blueprint. Razones:
- Es la dirección más **versátil** ante modelos de negocio futuros (Modelo A freemium o Modelo B SaaS Pro separado — ver §11).
- Patrón visual conocido (Linear/Cal.com/Plane) → navegación familiar.
- Equilibrio entre "proyecto serio" y "se respira open-source con gusto".
- Permite stats banner como social proof natural sin sentirse marketing-y.

---

## 2. Strategic context (deferred)

El usuario sigue indeciso sobre el modelo de monetización a largo plazo:

- **Modelo A — Freemium en la misma página:** descarga del bundle/GeoJSON requiere pago, browsing es gratis.
- **Modelo B — Dos productos separados:** landing gratis se mantiene como funnel/showcase; SaaS Pro (Phase 4) vive en producto separado con auth + billing.

El spec de v3.5 (`docs/specs/2026-05-18-osm2cs-generator-design.md`) asume Modelo B: *"if a future SaaS Pro tier ships, the free tool stays available as the entry point"*. Pero no es irrevocable.

**Decisión clave para este rediseño:** el polish visual es **invariante al modelo elegido**. Diseñamos para el estado actual (free + 10 ciudades + v3.5 in development) con dos *future-compat slots* que permiten ambos paths sin reescribir (§11).

---

## 3. Decisiones tomadas

| # | Decisión | Valor elegido | Alternativas descartadas | Razón |
|---|----------|---------------|--------------------------|-------|
| D1 | Dirección visual | Open-source con personalidad (Linear/Cal.com) | Editorial-magazine, CS2-gaming-blueprint | Versatilidad + balance serio/comunidad |
| D2 | Accent color | `#5e6ad2` (purple Linear) | Azul OSM `#2563eb`, Naranja CS2 `#f59e0b` | Usuario eligió púrpura del mockup |
| D3 | Stats banner — 4to slot | Versión actual (`v3.4`) | "100% Free", "Open Source", "MIT" | Refuerza "activamente mantenido" sin redundar con header/footer |
| D4 | Filtros + search | Incluidos en v1 | Diferir a 15-20 ciudades | Usuario pidió tenerlos listos ahora para no volver luego |
| D5 | Patreon CTA | Header `[Support →]` + footer `[Patreon]` lavender | Solo footer (más muted) | Moderate intensity, no pushy |
| D6 | Grid columns desktop | 3 columnas | 4 columnas | Más respiro, cards más legibles |
| D7 | Card huérfano fila final | "Request your city" card (col-span-2) | Dejar vacío, o expand última card | Convierte dead space en conversion path |
| D8 | Thumbs faltantes (NY, Sacramento, Fayetteville) | **In scope** — generar en este trabajo | Diferir a follow-up | Usuario pidió cerrarlo ahora + memoria persistente para no volver a olvidar |
| D9 | Thumbnails markup | `<img loading="lazy">` con wrapper `.thumb` | `background-image` actual | Lazy loading + a11y alt text + SEO |
| D10 | CSS organization | Extraer a `visualizer/assets/landing.css` | Mantener inline en `landing.py` | ~250 líneas no caben legibles en template Python |
| D11 | Region mapping | En código `landing.py` (no en `cities.json`) | Campo `region` por ciudad | Cambios raros y centralizados; evita tocar JSON |
| D12 | Country flag | Helper Python desde `country_code` ISO | Hardcoded emojis en HTML | Generar emoji desde código ISO es estándar y compacto |

---

## 4. Design tokens

### Colores

| Token | Valor | Uso |
|-------|-------|-----|
| `--bg` | `#0e0e10` | Fondo base |
| `--bg-elevated` | `linear-gradient(180deg, #18181b 0%, #0f0f12 100%)` | Cards, stats banner |
| `--border` | `rgba(255,255,255,0.06)` | Separadores |
| `--border-hover` | `rgba(94,106,210,0.4)` | Borde de card en hover |
| `--text` | `#fafafa` | Texto principal |
| `--text-muted` | `#a0a0a8` | Subtítulos, tags |
| `--text-dim` | `#71717a` | Labels, captions |
| `--accent` | `#5e6ad2` | Acento (Linear purple) |
| `--accent-soft` | `#c4b5fd` | Gradientes, badges, link Patreon |
| `--hero-glow` | `radial-gradient(circle, rgba(94,106,210,0.15) 0%, transparent 65%)` | Glow detrás del headline |

### Tipografía

- **Display + UI:** Inter (400/500/600/700) — vía Google Fonts con `preconnect`
- **Monospace:** JetBrains Mono (400/500) — version tags, feature counts, technical labels
- **Hero headline:** `clamp(2.5rem, 5vw, 3.8rem)`, `letter-spacing: -0.03em`, `font-weight: 600`
- **Body:** base `1rem` / `16px`, `line-height: 1.5`
- **Fallback stack:** `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- **Font subset:** `latin` (suficiente para ES + EN)
- **font-display:** `swap` (default en Google Fonts)

### Spacing & geometría

- Base de 4px
- Layout `max-width: 1280px`, padding outer `2rem` (desktop) / `1rem` (mobile)
- Card radius: `10px` · Pill radius: `999px` · Input/button radius: `6–8px`
- Card hover shadow: `0 12px 24px -8px rgba(94,106,210,0.15)`

---

## 5. Architecture

### Files affected

```
src/shared/
  └── landing.py                      ← reescribe template HTML + _card_html()
                                         + COUNTRY_TO_REGION + country_to_flag()

visualizer/assets/
  ├── landing.css                     ← NEW (~250 líneas extraídas)
  └── thumbnails/
      ├── fayetteville_nc.png         ← NEW (generar)
      ├── sacramento.png              ← NEW (generar)
      └── new_york.png                ← NEW (generar)

cities.json                           ← agregar campo country_code por ciudad
visualizer/cities.json                ← se regenera vía landing.py (deployed mirror)
```

### `landing.py` changes

1. **Eliminar CSS inline** del template — solo dejar `<link rel="stylesheet" href="assets/landing.css">`
2. **Reescribir template HTML** — nuevo markup con `<nav>`, `<section class="hero">`, `<div class="stats">`, `.filter-bar`, `.grid`, `<footer>`
3. **Helpers nuevos:**
   ```python
   COUNTRY_TO_REGION = {
       "USA": "north-america",
       "Canada": "north-america",
       "Mexico": "north-america",
       "Netherlands": "europe",
       "Norway": "europe",
       "Romania": "europe",
       "Brazil": "south-america",
       "Argentina": "south-america",
       # Extender cuando se agreguen países nuevos
   }

   def country_to_flag(code: str) -> str:
       """ISO 3166-1 alpha-2 → emoji flag. Empty string si code vacío."""
       if not code:
           return ""
       return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code.upper())

   def build_stats(cities: dict, manifests: dict) -> dict:
       """Computa los 4 stats del banner."""
       total_features = sum(
           sum(d.get("features", 0) for d in m.get("modules", {}).values())
           for m in manifests.values() if m
       )
       return {
           "cities_count": len(cities),
           "features_total": _format_count(total_features),
           "countries_count": len(set(c["country"] for c in cities.values())),
           "version": _read_version_short(),  # ej. "v3.4" — ver helper abajo
       }

   def _read_version_short(default: str = "v3.4") -> str:
       """Lee versión major.minor desde pyproject.toml. Fallback al default."""
       try:
           import tomllib  # py3.11+
           pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
           data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
           full = data["project"]["version"]  # ej. "3.4.0"
           parts = full.split(".")
           return f"v{parts[0]}.{parts[1]}"
       except Exception:
           return default

   def region_counts(cities: dict) -> dict:
       """Count de ciudades por region. Returns {'all': 10, 'north-america': 6, ...}"""
       counts = {"all": len(cities)}
       for c in cities.values():
           region = COUNTRY_TO_REGION.get(c["country"], "other")
           counts[region] = counts.get(region, 0) + 1
       return counts
   ```

4. **`_card_html()` reescribir:**
   - Wrapper `<a class="card" data-region="..." data-search="...">`
   - `data-region` viene de `COUNTRY_TO_REGION.get(country, "other")`
   - `data-search` = `f"{name.lower()} {country.lower()} {tagline.lower()}"` (precomputado para velocidad de filtering JS)
   - Inner: `<div class="thumb"><img loading="lazy" src="..." alt="Zoning map of {name}"></div>` + body con h4 + flag+loc + tag + meta (modules + count)
   - Module dots: 3 `<span class="mod {on|off}">` con `aria-label` apropiado

### `cities.json` schema extension

Agregar campo opcional `country_code` (ISO 3166-1 alpha-2):

```diff
   "minneapolis": {
     "display_name": "Minneapolis, MN",
     "country": "USA",
+    "country_code": "US",
     "bbox": [...],
     ...
   }
```

Mapeo a aplicar:
- USA → `US`, Netherlands → `NL`, Norway → `NO`, Romania → `RO`, Brazil → `BR`

Si `country_code` falta o está vacío, `country_to_flag()` retorna string vacío → la card simplemente no muestra flag (graceful degrade).

### Existing tests impact

- `tests/shared/test_landing.py` (si existe) — actualizar snapshot/golden si compara HTML string exacto
- Si no existe, agregar test mínimo que verifique:
  - Output válido HTML
  - 10 cards generadas
  - Stats banner contiene el count correcto
  - `_card_html` con manifest vacío genera "Sin datos" badge (caso edge actual)

---

## 6. Section-by-section spec

### 6.1 Header / nav bar

```
[🏙 CS2 OSM Toolkit  v3.4.0]                    [Docs] [Methodology] [GitHub] [Support →]
```

- Logo: cuadrito 26×26 con gradient `linear-gradient(135deg, #5e6ad2, #8b5cf6)` + emoji 🏙
- Brand: Inter 600 / 0.95rem
- Version tag: JetBrains Mono / 0.7rem, fondo `rgba(255,255,255,0.05)`, padding `0.15rem 0.45rem`, border-radius 4px
- Links: muted color, hover → blanco, transition 0.15s
- "Support →" CTA: bg blanco, text `#0e0e10`, padding `0.45rem 0.9rem`, border-radius 6px, link a Patreon
- No sticky

### 6.2 Hero section

```
              [● v3.5 — Browser generator in development]    ← badge pill con dot pulsing

           OpenStreetMap zoning
        for Cities: Skylines 2 builders.    ← gradient purple en parte resaltada

      Real-world cities, ready to import. Open data,
      open source, zero friction. Browse 10 curated
              maps or request your own.

              [Browse cities ↓]  [Request your city]
```

- Background: `--hero-glow` radial centrado arriba
- Badge: pill `padding 0.35rem 0.85rem`, border `rgba(94,106,210,0.3)`, color `#c4b5fd`. Contiene dot `width: 6px` con `box-shadow: 0 0 8px var(--accent)` y `animation: pulse 2s infinite`
- Headline: dos líneas, gradient en línea 2 segmento "Cities: Skylines 2 builders." via `background-clip: text`
- Lede: `max-width: 560px`, color muted, `font-size: 1.15rem`, margin centrado
- CTAs:
  - Primario "Browse cities ↓": bg `--text` (blanco), text `--bg`, padding `0.7rem 1.4rem`, border-radius 8px, href `#gallery`
  - Secundario "Request your city": bg transparent, border `rgba(255,255,255,0.1)`, padding mismo, href issue template
- Smooth scroll global: `html { scroll-behavior: smooth; }`

### 6.3 Stats banner

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│      10      │     855k     │      5       │     v3.4     │
│    CITIES    │   FEATURES   │  COUNTRIES   │   VERSION    │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

- Border `rgba(255,255,255,0.08)`, border-radius 12px
- Background: `linear-gradient(180deg, rgba(255,255,255,0.02), transparent)`
- Grid 4-col, divisores verticales `rgba(255,255,255,0.06)`
- Números: JetBrains Mono 500 / 1.8rem / `letter-spacing: -0.02em`
- Labels: uppercase, `letter-spacing: 0.1em`, color dim, font-size 0.75rem
- Padding `1.5rem 0`
- Computed server-side desde `cities.json` + manifests (ver §5 `build_stats`)

### 6.4 Filter bar

```
[All · 10] [North America · 6] [Europe · 3] [South America · 1]    [⌕ Search cities…]
```

- Layout flex space-between, align-items center, margin-bottom 1.5rem
- **Pills (4):** `<button class="pill" data-region="...">{label} · {count}</button>`
  - Inactivo: bg `rgba(255,255,255,0.04)`, border subtle, color muted
  - Activo: bg `#fafafa`, color `#0e0e10`, border `#fafafa`
  - `aria-pressed="true|false"`
  - Counts vienen de `region_counts()` server-side
- **Search:**
  - `<input type="search" id="search" placeholder="Search cities…">`
  - Width 220px desktop
  - Ícono `⌕` posicionado absolutely a la izquierda con `::before`
  - `<label class="sr-only" for="search">Search cities</label>`
  - `:focus-within` → border accent

### 6.5 Card grid

- `<section id="gallery">` (anchor target del CTA hero); contiene `<h2 class="sr-only">Featured cities</h2>` para que screenreaders tengan landmark heading
- Grid: 3 columnas desktop, 1rem gap
- **Anatomía de card:**
  ```html
  <a class="card" href="map.html?city=minneapolis"
     data-region="north-america"
     data-search="minneapolis, mn usa ciudad hero — fully featured">
    <div class="thumb">
      <img loading="lazy" src="assets/thumbnails/minneapolis.png"
           alt="Zoning map of Minneapolis, MN">
    </div>
    <div class="body">
      <h4>Minneapolis, MN</h4>
      <div class="loc">🇺🇸 USA</div>
      <div class="tag">Ciudad hero — fully featured, zoning + vial + servicios</div>
      <div class="meta">
        <div class="modules">
          <span class="mod on" aria-label="Zoning available"></span>
          <span class="mod on" aria-label="Vial available"></span>
          <span class="mod on" aria-label="Services available"></span>
        </div>
        <span class="count">295.9k</span>
      </div>
    </div>
  </a>
  ```
- Hover: `translateY(-2px)` + border-hover + box-shadow purple glow
- Thumb gradient overlay: `::after` con `linear-gradient(180deg, transparent 50%, rgba(15,15,18,0.6) 100%)`
- Module dots: 5px diameter, on = `--accent` + glow, off = `rgba(255,255,255,0.1)`
- Count: JetBrains Mono 0.72rem, color muted

### 6.6 "Request your city" card (último slot)

- Mismo container que cards normales pero `class="card request-card"` con `grid-column: span 2`
- Border dashed `var(--text-dim)`
- Padding generoso, centrado
- Contenido (íconos via SVG inline, no Unicode glyphs — más portable):
  ```html
  <svg class="plus" viewBox="0 0 24 24" width="32" height="32" stroke="currentColor"
       stroke-width="1.5" fill="none">
    <line x1="12" y1="5" x2="12" y2="19"/>
    <line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
  <h4>Request your city</h4>
  <p>Open an issue with your bbox and we'll add it</p>
  <span class="cta">Open issue template →</span>
  ```
- Hover: border solid + color accent

### 6.7 Empty state (filter no matches)

- `<div id="empty-state" style="display: none">` debajo del grid
- Padding 3rem, centrado, `border: 1px dashed var(--border)`, border-radius 12px
- Contenido: "No cities match. Try a different filter, or [Request your city →]"
- Mostrado por JS cuando `cards visibles === 0`

### 6.8 Footer

```
MIT licensed · OSM data © OpenStreetMap contributors · Built by @Osyanne     [GitHub] [Patreon] [Request a city]
```

- Border-top `var(--border)`, padding `2.5rem 0 3rem`
- Texto izquierda: font-size 0.82rem, color `--text-dim`
- Links derecha: gap 1.5rem
- `[Patreon]` link: color `--accent-soft` (lavender) — único hint de color

---

## 7. JavaScript

Inline al final del `<body>` antes del `</body>`. Sin dependencias.

```javascript
(() => {
  const cards = document.querySelectorAll('.card[data-region]');
  const pills = document.querySelectorAll('.pill');
  const search = document.getElementById('search');
  const empty = document.getElementById('empty-state');
  let region = 'all', query = '';

  function apply() {
    let visible = 0;
    cards.forEach(c => {
      const okRegion = region === 'all' || c.dataset.region === region;
      const okQuery = !query || c.dataset.search.includes(query);
      const show = okRegion && okQuery;
      c.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    empty.style.display = visible === 0 ? '' : 'none';
  }

  pills.forEach(p => p.addEventListener('click', () => {
    pills.forEach(x => {
      x.classList.toggle('active', x === p);
      x.setAttribute('aria-pressed', x === p ? 'true' : 'false');
    });
    region = p.dataset.region;
    apply();
  }));

  search.addEventListener('input', e => {
    query = e.target.value.toLowerCase().trim();
    apply();
  });
})();
```

Notas:
- `data-search` se precomputa server-side, evita `textContent.toLowerCase()` por card en cada keystroke
- Selector `.card[data-region]` excluye la `.request-card` (no tiene `data-region`) — siempre visible
- IIFE para no contaminar global scope

---

## 8. Responsive

| Breakpoint | Cambios |
|------------|---------|
| ≥ 1024px (desktop) | Layout completo |
| 768–1023px (tablet) | Grid 3-col mantiene, sin más cambios |
| 640–767px | Grid → 2-col; oculta "Methodology" link; "Request your city" col-span-1 |
| 480–639px | Grid → 2-col; stats banner → 2×2; filter bar → search debajo de pills (full-width) |
| < 480px | Grid → 1-col; header solo logo + GitHub + Support; hero padding 3rem |

CSS clamps en el hero manejan sizing auto. Media queries para el resto.

---

## 9. Accessibility checklist

- [ ] HTML semántico: `<nav>`, `<main>`, `<section>`, `<footer>`, `<h1>`, `<h2>`, `<h4>`
- [ ] Cards son `<a>` con `href` válido (keyboard nav nativo)
- [ ] Pills son `<button>` con `aria-pressed`
- [ ] Search input tiene `<label class="sr-only">` asociado
- [ ] Module dots tienen `aria-label` descriptivo
- [ ] Imágenes con `alt` no vacío
- [ ] Focus rings visibles solo con `:focus-visible` (no en click)
- [ ] `@media (prefers-reduced-motion: reduce)` desactiva pulse del badge + transforms en hover
- [ ] Contrast WCAG AA verificado (`#fafafa` on `#0e0e10` = 17.5:1 AAA; `#71717a` = 4.3:1 AA)
- [ ] Tab order lógico: nav → hero CTAs → pills → search → cards → footer

---

## 10. Performance

- Total page weight (above-the-fold): ~50 KB de assets críticos
- Fonts: Google Fonts con `preconnect`, `font-display: swap`, subset `latin`
- Thumbnails: `<img loading="lazy">` → solo los visibles cargan inicialmente (~1.5 MB vs 3-4 MB naive)
- CSS: extraído, cacheable via GitHub Pages headers
- JS: ~30 líneas inline, sin libs

---

## 11. Future-compatibility slots

### Slot 1 — v3.5 generator CTA

Badge del hero ya reserva el espacio:
- **Estado actual:** `[● v3.5 — Browser generator in development]` (marketing/expectation)
- **Cuando v3.5 ship:** cambiar copy a `[● Try the generator — generate any city →]` + href a `generate.html`
- **Refactor cost:** 2 líneas en `landing.py`

### Slot 2 — Modelo A paywall (si se adopta)

Per-ciudad gating:
- En `cities.json`: agregar `"tier": "free" | "pro"` por ciudad
- En `_card_html()`: si `tier === "pro"`, render badge `<span class="badge-pro">Pro</span>` en esquina del thumb
- En click handler (futuro JS): si pro + no-supporter → redirect checkout
- **CSS adicional necesario:** ~20 líneas para el badge + overlay
- **No se construye ahora**

### Slot 3 — More cities / scaling

- Region pills: agregar nuevas regiones al `COUNTRY_TO_REGION` dict cuando lleguen ciudades de Asia/África/Oceanía
- Si el grid pasa de 20 ciudades, evaluar pagination o lazy-render

---

## 12. In-scope follow-ups

### F1 — Generar los 3 thumbnails faltantes

**Incluido en el PR de este rediseño** (no como follow-up separado):

```bash
uv run generate-thumbnails  # auto-detecta NY, Sacramento, Fayetteville
```

Output esperado: 3 nuevos PNG en `visualizer/assets/thumbnails/`. Setup previo (una vez): `uv sync --group thumbnails && uv run --group thumbnails playwright install chromium`.

### F2 — Agregar `country_code` a `cities.json`

Mapping:

| `country` | `country_code` |
|-----------|----------------|
| USA | US |
| Netherlands | NL |
| Norway | NO |
| Romania | RO |
| Brazil | BR |

### F3 — Documentar en CHANGELOG

Entry para `CHANGELOG.md`:
```
## v3.4.1 — Landing redesign (2026-05-22)
- New visual identity for landing page (Linear/Cal.com inspired)
- Filter by region + search functionality
- Lazy-loaded thumbnails for better performance
- Improved accessibility (WCAG AA, reduced-motion support)
- Generated missing thumbnails for NY, Sacramento, Fayetteville
- BREAKING: `cities.json` schema gained optional `country_code` field
```

---

## 13. Out of scope (explicitly)

- Versión móvil app/PWA — defer hasta tener tracción medible
- Internacionalización del UI a inglés (tagline en español por ciudad se mantiene)
- Carousel / featured city section — deliberadamente NO incluido (era de mockup A editorial)
- Animaciones complejas (Lottie, scroll-triggered) — too token-heavy para el value que aportan
- Backend para guardar preferencias del filter (cookies/localStorage) — innecesario para 10-20 cards
- Server-rendered search index (Pagefind, etc.) — overkill, el data-search precomputado alcanza

---

## 14. Risks & open questions

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| Google Fonts down → headline se ve raro | Baja | Fallback stack robusto, `font-display: swap` |
| `cities.json` ya tiene un `country_code` con valor distinto al ISO en algún fork | Baja | Migration es additive (campo nuevo), no breaking |
| Mobile <320px se rompe | Baja | Min-width práctico es 320px; smaller no testing |
| Patreon link visible empuje al usuario lejos antes de explorar | Baja-media | Lavender soft no llama tanto vs botón; mitigable A/B futuro |

Open questions: ninguna bloqueante. Todo lo no resuelto es deferido explícitamente en §11/§13.

---

## 15. Links

- Mockups exploratorios: `docs/mockups/landing-redesign/{editorial,open-source,cs2-gaming}.html`
- v3.5 spec relacionado: `docs/specs/2026-05-18-osm2cs-generator-design.md`
- v3.4.0 PBF migration spec: `docs/superpowers/plans/2026-05-18-pbf-migration.md`
- Thumbnail generation script: `src/shared/thumbnails.py`
- Patreon: https://www.patreon.com/c/CS2OSMToolkit
- Deployed landing: https://osyanne.github.io/CitiesSkylines2-osm-toolkit/
