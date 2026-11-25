"""Shared constants for the RAPIDA one-pager app."""
import json
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PKG_DIR / "template"
SCHEMA_PATH = TEMPLATE_DIR / "rapida-feed.schema.json"
# Natural Earth 1:50m countries (public domain), simplified to ~1 km: neighbours and sea on the map
WORLD_COUNTRIES = PKG_DIR / "data" / "countries.parquet"
COUNTRY_NAMES = PKG_DIR / "data" / "country_names.json"   # {ISO3: {en, fr, es}}

CRISIS_TYPES = {"flood": "Flood (single-level polygon)",
                "earthquake": "Earthquake (shakemap with intensity levels)",
                "admin": "List of admin units (no hazard polygon)"}
LANGS = {"en": "English", "fr": "Français", "es": "Español"}
THEMES = {"approved": "Approved layout", "clean": "Clean (tile) layout"}

GEOGRAPHIC = "EPSG:4326"
EQUAL_AREA = "EPSG:6933"            # areas in km²

# ---- map look (agreed spec) ----
COLORS = dict(
    flood="#ec1551", affected="#0991d7", affected_fill="#e5e6ea", selected_fill="#bcdcf7",
    land="#f0f0f1", land_edge="#dadadd", country_edge="#c8c8cc", sea="#e1f1fa", neighbour="#ffffff",
    locator_land="#eff0f1", locator_edge="#d3d3d6", locator_fill="#3f8fd8", epicentre="#222222",
)
# Intensity colours from the agreed scale (perceived shaking / potential damage chart).
# Half steps are grouped down (6.5 -> VI). Classes 1-3 share the "≤III" colour.
MMI_COLORS = {1: "#306fc2", 2: "#306fc2", 3: "#306fc2", 4: "#d6fdfe", 5: "#b0f95b",
              6: "#fefd7d", 7: "#ec612e", 8: "#e94227", 9: "#ac2e1a", 10: "#a32c18"}
MMI_EDGE = {c: "#7fb3c9" if c == 4 else col for c, col in MMI_COLORS.items()}   # IV is near-white: thin blue edge
MMI_SHAKING = {"en": {3: "Weak", 4: "Light", 5: "Moderate", 6: "Strong", 7: "Very strong", 8: "Severe", 9: "Violent", 10: "Extreme"},
               "fr": {3: "Faible", 4: "Léger", 5: "Modéré", 6: "Fort", 7: "Très fort", 8: "Sévère", 9: "Violent", 10: "Extrême"},
               "es": {3: "Débil", 4: "Leve", 5: "Moderado", 6: "Fuerte", 7: "Muy fuerte", 8: "Severo", 9: "Violento", 10: "Extremo"}}
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X+"}
MMI_MIN_SHOWN = 4                  # default: bands below IV are not drawn (step 8 can change it)
MMI_ALPHA = 0.8

# Map window per layout, in poster units (the page is 1414 x 2000). The map image is drawn at 2 px per unit,
# in exactly the window's shape, so nothing is cropped. Overlay boxes (locator, legend, chip) mirror the CSS.
MAP_DPI = 200
MAP_PAD = 0.12                     # padding around the affected area
MAP_MIN_WIDTH_KM = 100             # never zoom closer than this
LEGEND_H = 0.13                    # legend + scale strip at the bottom (fraction of the window height)
LAYOUTS = {
    # approved theme, map inside the page margins and clear of the key-figures column (default)
    "approved_framed": dict(w=863, h=728, side=26, top_t=56, top_t_left=56, top_b=359, pw=184, ph=273,
                            lw=273, lh=184, ltop_b=448, chip="center", hidden_left=0.0),
    # approved theme as originally designed: map runs to the right page edge, its left strip under the text column
    "approved_bleed": dict(w=974, h=728, side=26, top_t=56, top_t_left=56, top_b=359, pw=184, ph=273,
                           lw=273, lh=184, ltop_b=448, chip="center", hidden_left=60 / 974),
    "clean": dict(w=888, h=664, side=22, top_t=22, top_t_left=68, top_b=318, pw=168, ph=250,
                  lw=250, lh=168, ltop_b=400, chip="left", hidden_left=0.0),
}
for _k, _v in LAYOUTS.items():
    _v["name"], _v["px_w"], _v["px_h"] = _k, 2 * _v["w"], 2 * _v["h"]


def layout_for(theme, frame="framed"):
    return LAYOUTS["clean" if theme == "clean" else ("approved_bleed" if frame == "bleed" else "approved_framed")]


def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _walk_limits(node, path, out):
    if not isinstance(node, dict):
        return
    if node.get("type") == "string" and "maxLength" in node:
        out[path] = node["maxLength"]
    for k, sub in (node.get("properties") or {}).items():
        _walk_limits(sub, f"{path}.{k}" if path else k, out)
    items = node.get("items")
    if isinstance(items, dict):
        _walk_limits(items, f"{path}[]", out)


def char_limits():
    """{'meta.title': 34, 'key_messages[].text': 165, ...} read from the feed schema."""
    out = {}
    _walk_limits(schema(), "", out)
    return out


LIMITS = char_limits()
