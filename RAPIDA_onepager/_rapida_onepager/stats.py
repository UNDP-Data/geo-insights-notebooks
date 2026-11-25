"""Merge RAPIDA output, compute exposed / total / % per admin unit, write the final GeoPackage."""
import datetime as dt
import json
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import GEOGRAPHIC


def _find_col(cols, var, year=None):
    if year and f"{var}_{year}" in cols:
        return f"{var}_{year}"
    if var in cols:
        return var
    pat = re.compile(rf"^{re.escape(var)}_(\d{{4}})$")
    hits = sorted([c for c in cols if pat.match(c)], reverse=True)
    return hits[0] if hits else None


class ProjectMismatch(ValueError):
    pass


def check_project(gpkg, parts, tol=0.005):
    """Does this RAPIDA project hold exactly the pieces of the current split? -> (ok, key, message).
    Every current piece must be in the project's polygons with the same area (±0.5 %)."""
    import pyogrio
    pol = pyogrio.read_dataframe(str(gpkg), layer="polygons", read_geometry=False)
    key = "part_key" if "part_key" in pol.columns else "poly_id"
    if "area_km2" not in pol.columns or key not in pol.columns:
        return False, key, "the project's polygons were not made by this app (no part_key / area_km2)"
    ref = pol.groupby(key)["area_km2"].sum()
    cur = parts.groupby(key)["area_km2"].sum()
    missing = cur.index.difference(ref.index)
    common = cur.index.intersection(ref.index)
    rel = ((cur[common] - ref[common]).abs() / cur[common].where(cur[common] > 0)).fillna(0)
    changed = rel[rel > tol]
    if len(missing) or len(changed):
        what = []
        if len(missing):
            what.append(f"{len(missing)} of {len(cur)} pieces are not in the project")
        if len(changed):
            what.append(f"{len(changed)} pieces have a different shape")
        return False, key, ("the RAPIDA project was made from a different split (" + "; ".join(what) +
                            "). The threshold, the crisis polygons or the admin layer changed since it was created.")
    return True, key, f"project matches the current split ({len(cur)} pieces, merged on {key})"


def merge_stats(gpkg, parts, selected, year=None):
    """parts: split polygons (with poly_id). selected: catalog rows (variable, component, kind, unit).
    Returns (parts_with_stats, found{var: (layer, column)}, missing[var])."""
    import pyogrio
    layers = [str(n) for n, _ in pyogrio.list_layers(str(gpkg))]
    ok, key, msg = check_project(gpkg, parts)
    if not ok:
        raise ProjectMismatch(msg)
    out = parts.copy()
    found, missing = {}, []
    by_comp = selected.groupby("component")["variable"].apply(list).to_dict()
    for comp, vars_ in by_comp.items():
        layer = f"stats.{comp}"
        if layer not in layers:
            missing += vars_
            continue
        df = pyogrio.read_dataframe(str(gpkg), layer=layer, read_geometry=False)
        if key not in df.columns:
            raise KeyError(f"{layer} has no {key} column – was the project created from the app's polygons?")
        take = {}
        for v in vars_:
            c = _find_col(df.columns, v, year)
            if c is None:
                missing.append(v)
                continue
            take[c] = v
            found[v] = (layer, c)
        if not take:
            continue
        sub = df[[key] + list(take)].rename(columns=take)
        if sub[key].duplicated().any():
            raise ProjectMismatch(f"{layer} has several rows per {key}; cannot merge safely")
        out = out.drop(columns=[v for v in take.values() if v in out.columns]).merge(sub, on=key, how="left")
    # unit conversions for the poster / GPKG
    for v in selected["variable"]:
        if v in out.columns and v.endswith("_length"):
            out[v] = pd.to_numeric(out[v], errors="coerce") / 1000.0   # m -> km
    return gpd.GeoDataFrame(out, geometry="geometry", crs=parts.crs), found, missing


def _wmean(x, w):
    x, w = pd.to_numeric(x, errors="coerce"), pd.to_numeric(w, errors="coerce")
    m = x.notna() & w.notna() & (w > 0)
    return float(np.average(x[m], weights=w[m])) if m.any() else np.nan


def admin_stats(parts, units, meta, crisis, threshold, pcode_col, name_col, parent_col=None):
    """One row per affected admin unit (full boundary) with total / exposed / % per selected stat."""
    rows = []
    vars_ = [v for v in meta["variable"] if v in parts.columns]
    kinds = dict(zip(meta["variable"], meta["kind"]))
    classes = sorted(c for c in parts["hz_class"].unique() if crisis == "earthquake" and c >= (threshold or 0))
    for pc, g in parts.groupby("unit_pcode"):
        aff = g[g["affected"] == 1]
        r = dict(unit_pcode=pc, unit_name=g["unit_name"].iloc[0], parent_name=g["parent_name"].iloc[0],
                 area_km2_total=g["area_km2"].sum(), area_km2_exp=aff["area_km2"].sum())
        r["area_exp_pct"] = 100 * r["area_km2_exp"] / r["area_km2_total"] if r["area_km2_total"] else np.nan
        if crisis == "earthquake":
            r["max_mmi"] = int(g["hz_class"].max())
            for c in classes:
                r[f"area_km2_mmi{c}"] = g.loc[g["hz_class"] == c, "area_km2"].sum()
        for v in vars_:
            k = kinds[v]
            if k == "count":
                tot, exp = pd.to_numeric(g[v], errors="coerce").sum(), pd.to_numeric(aff[v], errors="coerce").sum()
                r[f"{v}_all"], r[f"{v}_exp"] = tot, exp
                r[f"{v}_exp_pct"] = 100 * exp / tot if tot else np.nan
                for c in classes:
                    r[f"{v}_mmi{c}"] = pd.to_numeric(g.loc[g["hz_class"] == c, v], errors="coerce").sum()
            elif k in ("min", "max"):
                f = np.nanmin if k == "min" else np.nanmax
                r[f"{v}_all"] = f(pd.to_numeric(g[v], errors="coerce")) if g[v].notna().any() else np.nan
                r[f"{v}_exp"] = f(pd.to_numeric(aff[v], errors="coerce")) if aff[v].notna().any() else np.nan
            else:
                r[f"{v}_all"], r[f"{v}_exp"] = _wmean(g[v], g["area_km2"]), _wmean(aff[v], aff["area_km2"])
        rows.append(r)
    df = pd.DataFrame(rows)
    df = df[df["area_km2_exp"] > 0]
    key = units[pcode_col].astype(str) if pcode_col else pd.Series([f"U{i + 1:05d}" for i in range(len(units))])
    geo = gpd.GeoDataFrame({"unit_pcode": key.values}, geometry=units.geometry.values, crs=units.crs)
    geo = geo.dissolve("unit_pcode").reset_index()
    out = geo.merge(df, on="unit_pcode", how="inner")
    out.insert(1, "iso3", parts["iso3"].iloc[0])
    return gpd.GeoDataFrame(out, geometry="geometry", crs=GEOGRAPHIC)


def summary(parts, meta, crisis, threshold):
    """Overall totals that feed the poster: exposed, total in affected units, %."""
    aff = parts[parts["affected"] == 1]
    rows = [dict(key="area_km2", label="Affected area", unit="km²", exposed=aff["area_km2"].sum(),
                 total=parts["area_km2"].sum(), source="rapida")]
    for _, m in meta.iterrows():
        v = m["variable"]
        if v not in parts.columns:
            continue
        if m["kind"] == "count":
            rows.append(dict(key=v, label=m["title"], unit=m["unit"], exposed=pd.to_numeric(aff[v], errors="coerce").sum(),
                             total=pd.to_numeric(parts[v], errors="coerce").sum(), source="rapida"))
        else:
            rows.append(dict(key=v, label=m["title"], unit=m["unit"], exposed=_wmean(aff[v], aff["area_km2"]),
                             total=_wmean(parts[v], parts["area_km2"]), source="rapida"))
    if crisis == "earthquake":
        for c in sorted(parts["hz_class"].unique()):
            if c >= threshold:
                p = parts[parts["hz_class"] == c]
                rows.append(dict(key=f"area_km2_mmi{c}", label=f"Area MMI {c}", unit="km²", exposed=p["area_km2"].sum(),
                                 total=np.nan, source="rapida"))
                for _, m in meta[meta["kind"] == "count"].iterrows():
                    if m["variable"] in p.columns:
                        rows.append(dict(key=f"{m['variable']}_mmi{c}", label=f"{m['title']} MMI {c}", unit=m["unit"],
                                         exposed=pd.to_numeric(p[m["variable"]], errors="coerce").sum(), total=np.nan,
                                         source="rapida"))
    df = pd.DataFrame(rows)
    df["pct"] = np.where(df["total"] > 0, 100 * df["exposed"] / df["total"], np.nan)
    return df


def write_output(path, crisis_polys, epicentre, parts, adm, summ, metadata, also_gdb=False):
    """Final GeoPackage: crisis_polygons, crisis_epicentre, split_polygons, admin_stats, summary, run_metadata.
    Built on local disk and copied into place (see io_util). Returns the list of files written."""
    from .io_util import write_gpkg, gpkg_to_gdb
    layers = [(crisis_polys, "crisis_polygons")]
    if epicentre:
        layers.append((gpd.GeoDataFrame([{k: v for k, v in epicentre.items() if k not in ("lon", "lat")}],
                                        geometry=gpd.points_from_xy([epicentre["lon"]], [epicentre["lat"]]),
                                        crs=GEOGRAPHIC), "crisis_epicentre"))
    layers += [(parts.drop(columns=["part_key"], errors="ignore"), "split_polygons"), (adm, "admin_stats"),
               (pd.DataFrame(summ), "summary"),
               (pd.DataFrame([dict(key=k, value=v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str))
                              for k, v in metadata.items()]), "run_metadata")]
    written = write_gpkg(layers, path)
    out = [written]
    if also_gdb:
        try:
            out.append(gpkg_to_gdb(written, Path(written).with_suffix(".gdb")))
        except Exception as e:
            print(f"⚠ File GDB not written ({e}). GDAL 3.6+ is needed for the OpenFileGDB writer.")
    return out


def run_metadata(state):
    return dict(created=dt.datetime.now().isoformat(timespec="seconds"), **state)
