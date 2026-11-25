"""Overlay admin units with the crisis polygons.

Every affected unit is cut into one sub-polygon per hazard class plus its unaffected remainder,
so RAPIDA returns both the exposed values and the unit totals in one run.
"""
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .config import GEOGRAPHIC, EQUAL_AREA

MIN_PART_KM2 = 0.0005      # slivers smaller than 500 m² are dropped


def _polygons_only(g):
    """Polygon parts of any geometry (drops slivers turned into lines/points by an overlay)."""
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    polys = [p for p in shapely.get_parts(g) if p.geom_type == "Polygon" and not p.is_empty]
    polys += [q for p in shapely.get_parts(g) if p.geom_type == "MultiPolygon" for q in p.geoms]
    if not polys:
        return None
    mp = polys[0] if len(polys) == 1 else shapely.multipolygons(polys)
    return mp if mp.is_valid else shapely.union_all(polys)


def units_hit(admin, hazard, crisis, threshold=None):
    """Admin units that intersect the hazard (earthquakes: classes >= threshold)."""
    hz = hazard if crisis != "earthquake" else hazard[hazard["hz_class"] >= threshold]
    if hz.empty:
        return admin.iloc[0:0]
    H = shapely.union_all(hz.geometry.values)
    shapely.prepare(H)
    return admin[shapely.intersects(admin.geometry.values, H)].copy()


def split_units(units, hazard, crisis, iso3, name_col, pcode_col, parent_col=None, threshold=None):
    units = units.to_crs(GEOGRAPHIC).reset_index(drop=True)
    pcode = units[pcode_col].astype(str) if pcode_col else pd.Series([f"U{i + 1:05d}" for i in range(len(units))])
    name = units[name_col].astype(str) if name_col else pcode
    parent = units[parent_col].astype(str) if parent_col and parent_col in units else pd.Series([""] * len(units))
    U = units.geometry.values
    parts = []

    def add(idx, geoms, cls, label, affected):
        for i in idx:
            g = geoms[i]
            if g is None or g.is_empty:
                continue
            if not (g.geom_type in ("Polygon", "MultiPolygon") and g.is_valid):
                g = _polygons_only(shapely.make_valid(g))
            if g is None or g.is_empty:
                continue
            parts.append(dict(unit_pcode=pcode[i], unit_name=name[i], parent_name=parent[i], hz_class=int(cls),
                              hz_label=label, affected=int(affected), geometry=g))

    if crisis == "admin":
        add(range(len(units)), U, 1, "Selected", True)
    else:
        # Spatial index over the pieces of each band: every unit is cut only by the pieces that touch it,
        # instead of by the whole (often million-vertex) hazard geometry.
        rem = np.array(U, dtype=object)
        for _, band in hazard.sort_values("hz_class").iterrows():
            pieces = np.array([g for g in shapely.get_parts(band.geometry) if not g.is_empty], dtype=object)
            if not len(pieces):
                continue
            tree = shapely.STRtree(pieces)
            ui, pi = tree.query(U, predicate="intersects")
            if not len(ui):
                continue
            inter = np.empty(len(U), dtype=object)
            for i in np.unique(ui):
                local = pieces[pi[ui == i]]
                # pieces of one merged band never overlap: a multipolygon is enough, no costly union
                local = local[0] if len(local) == 1 else shapely.multipolygons(local)
                if not local.is_valid:
                    local = shapely.union_all(pieces[pi[ui == i]])
                inter[i] = shapely.intersection(U[i], local)
                rem[i] = shapely.difference(rem[i], local)
            aff = True if crisis == "flood" else band.hz_class >= threshold
            add(np.unique(ui), inter, band.hz_class, band.hz_label, aff)
        add(range(len(units)), rem, 0, "Outside", False)

    gdf = gpd.GeoDataFrame(parts, crs=GEOGRAPHIC)
    gdf["area_km2"] = gdf.to_crs(EQUAL_AREA).area / 1e6
    gdf = gdf[gdf["area_km2"] >= MIN_PART_KM2].reset_index(drop=True)
    gdf.insert(0, "poly_id", np.arange(1, len(gdf) + 1, dtype="int64"))
    gdf.insert(1, "iso3", iso3.upper())
    gdf["part_key"] = gdf["unit_pcode"] + "|" + gdf["hz_class"].astype(str)
    return gdf


def checks(parts, units, pcode_col, iso3):
    """Table of validation checks; every 'ok' must be True before RAPIDA runs."""
    rows = []
    def add(name, ok, detail=""):
        rows.append(dict(check=name, ok=bool(ok), detail=detail))
    add("Sub-polygons created", len(parts) > 0, f"{len(parts)} parts")
    add("iso3 field present and valid", "iso3" in parts and parts["iso3"].notna().all()
        and parts["iso3"].str.fullmatch(r"[A-Z]{3}").all(), iso3.upper())
    add("poly_id unique", parts["poly_id"].is_unique, "")
    add("CRS set (EPSG:4326)", parts.crs is not None and parts.crs.to_epsg() == 4326, str(parts.crs))
    add("No empty geometries", (~parts.geometry.is_empty).all(), "")
    add("At least one affected part", (parts["affected"] == 1).any(),
        f"{int((parts['affected'] == 1).sum())} affected parts")
    add("One part per unit and class", parts["part_key"].is_unique, "")
    ua = units.to_crs(EQUAL_AREA).area / 1e6
    key = units[pcode_col].astype(str) if pcode_col else pd.Series([f"U{i + 1:05d}" for i in range(len(units))])
    unit_area = pd.Series(ua.values, index=key.values).groupby(level=0).sum()
    part_area = parts.groupby("unit_pcode")["area_km2"].sum()
    rel = (part_area.reindex(unit_area.index).fillna(0) - unit_area).abs() / unit_area.replace(0, np.nan)
    worst = float(rel.max()) if len(rel) else 0
    add("Area preserved (no gaps or overlaps)", worst < 0.005, f"largest difference {worst * 100:.2f}%")
    return pd.DataFrame(rows)


def signature(parts):
    """Short fingerprint of a split (pieces + areas). Changes when the hazard, the admin layer or the
    threshold changes the pieces, so every split gets its own RAPIDA project."""
    import hashlib
    key = parts[["part_key", "area_km2"]].assign(area_km2=parts["area_km2"].round(3)).sort_values("part_key")
    return hashlib.sha1(key.to_csv(index=False).encode()).hexdigest()[:8]


def to_rapida_input(parts, path):
    """Write the polygons RAPIDA will assess (one layer, simple field names)."""
    cols = ["poly_id", "part_key", "iso3", "unit_pcode", "unit_name", "parent_name", "hz_class", "hz_label",
            "affected", "area_km2", "geometry"]
    from .io_util import write_gpkg
    return write_gpkg([(parts[cols], "polygons")], path)
