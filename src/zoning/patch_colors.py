#!/usr/bin/env python3
"""
patch_colors.py — Actualiza los colores del visualizador a la paleta CS2 oficial.
Uso: cd src && uv run patch_colors.py
"""
import re
from pathlib import Path

HTML_PATH = Path("../visualizer/index.html")

# Mapa de colores: nombre de zona → nuevo color CS2
CS2_COLORS = {
    # Residencial
    "res_high":      "#2E7D32",  # Verde oscuro
    "res_med":       "#4CAF50",  # Verde medio
    "res_low":       "#8BC34A",  # Verde claro
    # Comercial
    "com_high":      "#0277BD",  # Azul oscuro
    "com_low":       "#29B6F6",  # Azul claro
    "retail":        "#00BCD4",  # Celeste
    # Otros
    "office":        "#00ACC1",  # Turquesa
    "industrial":    "#FFC107",  # Amarillo ámbar
    "mixed":         "#00E5FF",  # Cian
    "mixed_res_com": "#80DEEA",  # Cian claro
    "prk_surface":   "#90A4AE",  # Gris claro
    "prk_ramp":      "#546E7A",  # Gris oscuro
}


def patch_html(html: str) -> str:
    """
    Reemplaza asignaciones de color en el JS del visualizador.

    Estrategias en orden de especificidad:
    1. Patrones: 'zone_key': '#XXXXXX' (objeto JS de colores)
    2. Patrones: "zone_key": "#XXXXXX" (comillas dobles)
    3. Patrones density inline: zone === 'high' ? '#XXXXXX'
    """
    patched = html
    total_replacements = 0

    for zone_key, new_color in CS2_COLORS.items():
        # Estrategia 1: 'zone_key': '#XXXXXX'
        pattern1 = rf"('{re.escape(zone_key)}')\s*:\s*'#[0-9A-Fa-f]{{6}}'"
        replacement1 = rf"\1: '{new_color}'"
        result1, n1 = re.subn(pattern1, replacement1, patched)
        patched = result1
        total_replacements += n1

        # Estrategia 2: "zone_key": "#XXXXXX"
        pattern2 = rf'("{re.escape(zone_key)}")\s*:\s*"#[0-9A-Fa-f]{{6}}"'
        replacement2 = rf'\1: "{new_color}"'
        result2, n2 = re.subn(pattern2, replacement2, patched)
        patched = result2
        total_replacements += n2

    # Estrategia 3: densidades residenciales inline (high/medium/low)
    density_colors = {
        "high":   CS2_COLORS["res_high"],
        "medium": CS2_COLORS["res_med"],
        "low":    CS2_COLORS["res_low"],
    }
    for density, color in density_colors.items():
        pattern3 = rf"(zone\s*===\s*['\"{density}['\"])\s*\?\s*['\"]#[0-9A-Fa-f]{{6}}['\"]"
        # More conservative: only replace standalone density ternaries
        pattern3b = rf"(['\"]){re.escape(density)}\1\s*:\s*['\"]#[0-9A-Fa-f]{{6}}['\"]"
        replacement3b = rf"'{density}': '{color}'"
        result3b, n3b = re.subn(pattern3b, replacement3b, patched)
        patched = result3b
        total_replacements += n3b

    return patched, total_replacements


def main():
    if not HTML_PATH.exists():
        print(f"Error: no se encuentra {HTML_PATH}")
        print(f"Asegúrate de ejecutar desde el directorio src/")
        return

    original = HTML_PATH.read_text(encoding="utf-8")
    patched, count = patch_html(original)

    if count == 0 or patched == original:
        print("AVISO: No se encontraron patrones de color que reemplazar automáticamente.")
        print("El visualizador puede usar una estructura de colores diferente.")
        print("\nColores CS2 objetivo — reemplaza manualmente en visualizer/index.html:")
        print("-" * 50)
        for k, v in CS2_COLORS.items():
            print(f"  {k:<16} → {v}")
        print("\nBusca en el HTML patrones como ZONE_COLORS, zoneColors, o definiciones")
        print("de color hardcodeadas junto a los nombres de zona.")
        return

    # Backup
    backup = HTML_PATH.with_suffix(".html.bak")
    backup.write_text(original, encoding="utf-8")
    print(f"Backup guardado en: {backup}")

    HTML_PATH.write_text(patched, encoding="utf-8")
    print(f"Colores actualizados. Reemplazos realizados: {count}")
    print("\nColores CS2 aplicados:")
    for k, v in CS2_COLORS.items():
        print(f"  {k:<16} → {v}")


if __name__ == "__main__":
    main()
