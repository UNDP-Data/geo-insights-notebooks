"""Administrative boundaries: OCHA COD-AB from the HDX API, or an uploaded SHP/GPKG/GDB."""
import re
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .config import GEOGRAPHIC, WORLD_COUNTRIES, COUNTRY_NAMES

HDX_API = "https://data.humdata.org/api/3/action"
VECTOR_EXT = (".shp", ".gpkg", ".geojson", ".json", ".gdb", ".fgb")


# ---------------------------------------------------------------- HDX
def hdx_resources(iso3):
    """Resources of the HDX dataset cod-ab-<iso3>: [{name, format, url, size}] (vector formats first)."""
    import requests
    r = requests.get(f"{HDX_API}/package_show", params={"id": f"cod-ab-{iso3.lower()}"}, timeout=60)
    if r.status_code == 404:
        raise ValueError(f"HDX has no dataset 'cod-ab-{iso3.lower()}'")
    r.raise_for_status()
    res = r.json()["result"]["resources"]
    out = []
    for x in res:
        name, fmt, url = x.get("name", ""), (x.get("format") or "").upper(), x.get("url") or x.get("download_url")
        low = (name + " " + fmt).lower()
        vector = any(k in low for k in ("shp", "shapefile", "gpkg", "geopackage", "geojson", "gdb", "geodatabase"))
        if url and vector and "emf" not in low and "kmz" not in low:
            out.append(dict(name=name, format=fmt, url=url, size=x.get("size")))
    rank = lambda d: (0 if "gpkg" in (d["name"] + d["format"]).lower() else 1 if "gdb" in d["name"].lower() else 2)
    return sorted(out, key=rank)


def download(url, dest_dir):
    import requests
    dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    name = url.split("?")[0].rstrip("/").split("/")[-1] or "admin_download"
    path = dest_dir / name
    if not path.exists():
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    if zipfile.is_zipfile(path):
        out = dest_dir / path.stem
        if not out.exists():
            with zipfile.ZipFile(path) as z:
                z.extractall(out)
        return out
    return path


def find_vector_layers(path):
    """All (dataset, layer) pairs in a file or folder (shapefiles, GPKG, GeoJSON, File GDB)."""
    import pyogrio
    path = Path(path)
    cands = [path] if path.suffix.lower() in VECTOR_EXT else []
    if path.is_dir() and path.suffix.lower() != ".gdb":
        cands = sorted([p for p in path.rglob("*") if p.suffix.lower() in VECTOR_EXT
                        and not any(q.suffix.lower() == ".gdb" for q in p.parents)])
    out = []
    for c in cands:
        try:
            for name, gtype in pyogrio.list_layers(str(c)):
                if gtype is None or "polygon" in str(gtype).lower():
                    out.append((str(c), str(name)))
        except Exception:
            continue
    return out


def guess_layer(layers, level):
    pat = re.compile(rf"(adm(in)?_?{level}(?!\d))|(admbnda_adm{level})", re.I)
    for ds, ly in layers:
        if pat.search(ly) or pat.search(Path(ds).name):
            return ds, ly
    return layers[0] if layers else None


def read_admin(dataset, layer=None):
    gdf = gpd.read_file(dataset, layer=layer) if layer else gpd.read_file(dataset)
    if gdf.crs is None:
        raise ValueError("The admin layer has no CRS")
    gdf = gdf.to_crs(GEOGRAPHIC)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf.reset_index(drop=True)


def guess_columns(gdf, level, lang="en"):
    """(name_col, pcode_col, parent_name_col) for an admin level, OCHA COD naming first."""
    cols = list(gdf.columns)
    low = {c.lower(): c for c in cols}

    def first(cands):
        for c in cands:
            if c.lower() in low:
                return low[c.lower()]
        return None
    lang_order = {"en": ["en", "pt", "fr", "es"], "fr": ["fr", "en", "pt", "es"], "es": ["es", "en", "pt", "fr"]}[lang]
    def name_for(lv):
        return first([f"adm{lv}_{l}" for l in lang_order] + [f"adm{lv}_name", f"admin{lv}name", f"adm{lv}name",
                     f"name_{lv}", f"adm{lv}_name1", f"adm{lv}_ref"])
    name = name_for(level) or first(["name", "shapeName", "NAME"])
    pcode = first([f"adm{level}_pcode", f"admin{level}pcode", f"adm{level}_code", f"adm{level}pcode",
                   f"gid_{level}", "shapeID", "pcode"])
    parent = name_for(level - 1) if level > 1 else None
    return name, pcode, parent


def add_unit_key(gdf, pcode_col=None):
    """Stable key per admin unit: the pcode (made unique) or U00001, U00002, ... in file order."""
    gdf = gdf.copy()
    if pcode_col and pcode_col in gdf:
        k = gdf[pcode_col].astype(str).str.strip()
        dup = k.duplicated(keep=False)
        if dup.any():
            k[dup] = k[dup] + "_" + gdf[dup].groupby(k[dup]).cumcount().add(1).astype(str)
    else:
        k = pd.Series([f"U{i + 1:05d}" for i in range(len(gdf))], index=gdf.index)
    gdf["unit_key"] = k.values
    return gdf


def country_names(iso3):
    """{'en','fr','es'} names from the bundled table (fallback: the ISO3 code)."""
    import json
    try:
        names = json.loads(COUNTRY_NAMES.read_text(encoding="utf-8"))
        if iso3.upper() in names:
            return names[iso3.upper()]
    except Exception:
        pass
    return {"en": iso3, "fr": iso3, "es": iso3}


def world_countries():
    return gpd.read_parquet(WORLD_COUNTRIES)
