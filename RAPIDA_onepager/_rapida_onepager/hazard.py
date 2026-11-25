"""Crisis polygons: GDACS API or uploaded files.

Output of every loader is a GeoDataFrame in EPSG:4326 with columns
  hz_class  int   flood: 1 ; earthquake: whole MMI class (6.5 -> 6) ; admin list: 1
  hz_label  str   "Flooded area", "VI", ...
plus, for earthquakes, an epicentre dict.
"""
import json
import math
import re
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from .config import GEOGRAPHIC, EQUAL_AREA, ROMAN

GDACS_API = "https://www.gdacs.org/gdacsapi/api"
INTENSITY_FIELDS = ["intensity", "PARAMVALUE", "paramvalue", "mmi", "MMI", "value", "VALUE", "grid_value", "GRID_CODE"]


# ---------------------------------------------------------------- GDACS
def parse_gdacs_ref(text):
    """Accept a GDACS geometry URL, report URL, or 'EQ 1498907 [1658860]'. -> (eventtype, eventid, episodeid|None)"""
    text = (text or "").strip()
    if text.startswith("http"):
        q = {k.lower(): v[0] for k, v in parse_qs(urlparse(text).query).items()}
        et, ev, ep = q.get("eventtype"), q.get("eventid"), q.get("episodeid")
        if not (et and ev):
            raise ValueError("The GDACS link must contain eventtype= and eventid=")
        return et.upper(), int(ev), int(ep) if ep else None
    parts = re.split(r"[\s,;/]+", text)
    if len(parts) >= 2 and parts[0].upper() in ("EQ", "FL", "TC", "VO", "DR", "WF"):
        return parts[0].upper(), int(parts[1]), int(parts[2]) if len(parts) > 2 else None
    raise ValueError("Give a GDACS link, or 'EQ <eventid> [episodeid]'")


def _get_json(url, timeout=90):
    import requests
    r = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def fetch_gdacs(eventtype, eventid, episodeid=None):
    """Download the GDACS event geometry (FeatureCollection)."""
    url = f"{GDACS_API}/polygons/getgeometry?eventtype={eventtype}&eventid={eventid}"
    if episodeid:
        url += f"&episodeid={episodeid}"
    try:
        fc = _get_json(url)
    except Exception:
        if episodeid:
            raise
        # no episode given and the API wants one: take the latest from the event data
        ev = _get_json(f"{GDACS_API}/events/geteventdata?eventtype={eventtype}&eventid={eventid}")
        props = ev.get("properties", ev)
        eps = props.get("episodes") or []
        ids = [e.get("episodeid") or e.get("id") for e in eps if isinstance(e, dict)]
        episodeid = props.get("episodeid") or (max(i for i in ids if i) if any(ids) else None)
        if not episodeid:
            raise
        url = f"{GDACS_API}/polygons/getgeometry?eventtype={eventtype}&eventid={eventid}&episodeid={episodeid}"
        fc = _get_json(url)
    if isinstance(fc, dict) and "features" not in fc and "data" in fc:
        fc = fc["data"]
    return fc, url


def _is_circle(geom, center=None, tol=0.97):
    """Near-perfect circle (the GDACS 100 km buffer)."""
    if geom is None or geom.is_empty or geom.geom_type != "Polygon":
        return False
    g = gpd.GeoSeries([geom], crs=GEOGRAPHIC).to_crs(EQUAL_AREA).iloc[0]
    if g.length == 0:
        return False
    circ = 4 * math.pi * g.area / g.length ** 2
    if circ < tol:
        return False
    if center is not None:
        return geom.centroid.distance(center) < 0.05
    return True


def gdacs_to_hazard(fc, crisis):
    """Split a GDACS FeatureCollection into hazard polygons + epicentre. Returns (gdf, epicentre, report)."""
    feats = fc.get("features", fc) if isinstance(fc, dict) else fc
    kept, dropped, epic = [], [], None
    for f in feats:
        p = f.get("properties") or {}
        cls = str(p.get("Class") or p.get("class") or "")
        geom = shape(f["geometry"]) if f.get("geometry") else None
        if geom is None:
            continue
        if cls == "Point_Centroid" or (geom.geom_type == "Point" and epic is None and crisis == "earthquake"):
            sev = p.get("severitydata") or {}
            epic = dict(lon=geom.x, lat=geom.y, magnitude=sev.get("severity"), text=sev.get("severitytext"),
                        date=(p.get("fromdate") or "")[:10], name=p.get("name"), alert=p.get("alertlevel"),
                        country=p.get("country"), iso3=p.get("iso3"), eventid=p.get("eventid"),
                        episodeid=p.get("episodeid"))
            dropped.append((cls or "point", "kept as epicentre" if crisis == "earthquake" else "dropped (point)"))
            continue
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            dropped.append((cls or geom.geom_type, "dropped (not a polygon)"))
            continue
        if cls == "Poly_Circle" or (p.get("polygonlabel") or "").lower().endswith("km"):
            dropped.append((cls or p.get("polygonlabel"), "dropped (distance circle)"))
            continue
        kept.append(dict(cls=cls, intensity=p.get("intensity"), label=p.get("polygonlabel"), geometry=geom))
    if not kept:
        raise ValueError("The GDACS event has no hazard polygons")
    gdf = gpd.GeoDataFrame(kept, crs=GEOGRAPHIC)
    if crisis == "earthquake":
        has_i = gdf["intensity"].notna()
        if not has_i.any():
            raise ValueError("No intensity polygons (Class Poly_SMPInt_*) in this GDACS event")
        circles = gdf[~has_i]
        center = shapely.Point(epic["lon"], epic["lat"]) if epic else None
        for _, r in circles.iterrows():
            dropped.append((r.cls or "polygon", "dropped (no intensity" + (", circle)" if _is_circle(r.geometry, center) else ")")))
        gdf = gdf[has_i].copy()
        hz = eq_bands(gdf, "intensity")
    else:
        hz = single_level(gdf, "Flooded area")
    report = pd.DataFrame(dropped, columns=["feature", "handling"]).value_counts().reset_index(name="count")
    return hz, epic, report


# ---------------------------------------------------------------- files
def list_layers(path):
    import pyogrio
    return [str(n) for n, _ in pyogrio.list_layers(str(path))]


def read_vector(path, layer=None):
    path = str(path)
    if path.lower().endswith(".zip") and not path.startswith("/vsizip/"):
        path = "/vsizip/" + path
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"{path} has no CRS. Assign one before using it.")
    return gdf.to_crs(GEOGRAPHIC)


def guess_intensity_field(gdf):
    for c in INTENSITY_FIELDS:
        if c in gdf.columns and pd.api.types.is_numeric_dtype(gdf[c]):
            return c
    nums = [c for c in gdf.columns if c != "geometry" and pd.api.types.is_numeric_dtype(gdf[c])]
    return nums[0] if nums else None


def load_hazard_file(path, crisis, layer=None, intensity_field=None):
    gdf = read_vector(path, layer)
    epic = None
    pts = gdf[gdf.geometry.geom_type.isin(["Point", "MultiPoint"])]
    if crisis == "earthquake" and len(pts):
        row = pts.iloc[0]
        p = row.geometry
        p = p.geoms[0] if p.geom_type == "MultiPoint" else p
        low = {c.lower(): c for c in pts.columns}

        def pick(*names):
            for n in names:
                if n in low and pd.notna(row[low[n]]) and str(row[low[n]]).strip():
                    return row[low[n]]
            return None
        mag = pick("magnitude", "mag", "severity")
        sev = pick("severitydata")                       # GDACS points saved to a file keep this as text/JSON
        if mag is None and sev is not None:
            try:
                mag = (json.loads(sev) if isinstance(sev, str) else sev).get("severity")
            except Exception:
                pass
        date = pick("fromdate", "date", "eventdate", "time", "origintime")
        epic = dict(lon=p.x, lat=p.y, magnitude=float(mag) if mag is not None else None,
                    date=str(date)[:10] if date is not None else "", name=pick("name", "eventname"))
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if gdf.empty:
        raise ValueError("No polygons in the hazard file")
    if crisis == "earthquake":
        field = intensity_field or guess_intensity_field(gdf)
        if not field:
            raise ValueError("Choose the field that holds the intensity")
        return eq_bands(gdf, field), epic
    return single_level(gdf, "Flooded area"), None


# ---------------------------------------------------------------- shaping
def _clean(geoms):
    g = shapely.make_valid(np.asarray(geoms))
    g = shapely.get_parts(shapely.get_parts(g))           # flatten collections
    g = [x for x in g if x.geom_type in ("Polygon", "MultiPolygon") and not x.is_empty]
    return shapely.union_all(g) if g else shapely.Polygon()


def single_level(gdf, label):
    geom = _clean(gdf.geometry.values)
    return gpd.GeoDataFrame({"hz_class": [1], "hz_label": [label]}, geometry=[geom], crs=GEOGRAPHIC)


def eq_bands(gdf, field):
    """Whole-MMI bands without overlaps: each place keeps its highest class."""
    v = pd.to_numeric(gdf[field], errors="coerce")
    gdf = gdf.assign(_c=np.floor(v + 1e-9).clip(upper=10)).dropna(subset=["_c"])
    rows, higher = [], shapely.Polygon()
    for c in sorted(gdf["_c"].unique(), reverse=True):
        band = _clean(gdf.loc[gdf["_c"] == c].geometry.values)
        if not higher.is_empty:
            band = band.difference(higher)
        higher = band if higher.is_empty else shapely.union_all([higher, band])
        if not band.is_empty:
            rows.append(dict(hz_class=int(c), hz_label=ROMAN.get(int(c), str(int(c))), geometry=band))
    return gpd.GeoDataFrame(rows, crs=GEOGRAPHIC).sort_values("hz_class").reset_index(drop=True)


def remove_permanent_water(hazard, raster_path, water_values=(1,), simplify_m=30):
    """Cut permanent water (raster cells equal to water_values) out of the hazard polygons.
    For JRC Global Surface Water 'seasonality' tiles use water_values=(12,)."""
    import rasterio
    from rasterio.features import shapes
    from rasterio.windows import from_bounds
    out = hazard.copy()
    with rasterio.open(raster_path) as src:
        hz = out.to_crs(src.crs)
        win = from_bounds(*hz.total_bounds, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=win)
        mask = np.isin(arr, list(water_values)).astype("uint8")
        if not mask.any():
            return out, 0.0
        tr = src.window_transform(win)
        polys = [shape(g) for g, v in shapes(mask, mask=mask.astype(bool), transform=tr) if v == 1]
        water = gpd.GeoSeries([shapely.union_all(polys)], crs=src.crs).to_crs(GEOGRAPHIC).iloc[0]
    before = out.to_crs(EQUAL_AREA).area.sum()
    out["geometry"] = out.geometry.difference(water)
    out = out[~out.geometry.is_empty]
    removed = (before - out.to_crs(EQUAL_AREA).area.sum()) / 1e6
    return out.reset_index(drop=True), removed


def hazard_summary(hz, crisis):
    a = hz.to_crs(EQUAL_AREA).area / 1e6
    df = pd.DataFrame({"class": hz["hz_label"], "area_km2": a.round(1)})
    if crisis == "earthquake":
        df.insert(0, "mmi", hz["hz_class"])
    return df
