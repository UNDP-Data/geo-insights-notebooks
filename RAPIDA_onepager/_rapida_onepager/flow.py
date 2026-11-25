"""Step logic of the RAPIDA one-pager, independent of the user interface.

The marimo notebook (../rapida_onepager.py) calls one function per step and shows what comes back. Every
function takes plain values and returns plain values or dicts, so the steps can also be run from a script.
"""
import datetime as dt
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import admin as A, hazard as H, i18n, maps as M, poster as P, rapida_runner as R, split as S, stats as ST
from .config import COLORS, LIMITS, MMI_COLORS, ROMAN, layout_for

LEVEL_NAMES = {   # defaults the user edits: (singular, plural, gender for fr/es)
    1: {"en": ("Province", "Provinces", "m"), "fr": ("province", "provinces", "f"), "es": ("provincia", "provincias", "f")},
    2: {"en": ("District", "Districts", "m"), "fr": ("district", "districts", "m"), "es": ("distrito", "distritos", "m")},
    3: {"en": ("Area", "Areas", "m"), "fr": ("zone", "zones", "f"), "es": ("zona", "zonas", "f")},
    4: {"en": ("Area", "Areas", "m"), "fr": ("zone", "zones", "f"), "es": ("zona", "zonas", "f")},
}


def L(path):
    return LIMITS.get(path)


def png(fig, dpi=110):
    import matplotlib.pyplot as plt
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return b.getvalue()


# ============================================================= 1 setup
def default_out_root():
    return str(Path.home() / "rapida_onepager_runs")


def validate_setup(v):
    """Cheap checks for the setup form. Returns an error string or None."""
    iso = (v.get("iso3") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", iso):
        return "ISO3 must be three letters, e.g. MOZ"
    run = (v.get("run_name") or "").strip()
    if run and not re.fullmatch(r"[A-Za-z0-9_\-]+", run):
        return "Run name: letters, digits, _ and - only"
    return None


def make_config(v):
    """Setup form values -> (cfg, errors). Creates the output and working folders."""
    err = validate_setup(v)
    if err:
        return None, [err]
    iso = v["iso3"].strip().upper()
    run = (v.get("run_name") or "").strip() or f"{iso}_{v['crisis']}_{dt.date.today():%Y%m%d}"
    cfg = dict(crisis=v["crisis"], lang=v["lang"], theme=v["theme"], iso3=iso, run_name=run,
               rapida_in_temp=bool(v.get("rapida_in_temp", True)), copyback=v.get("copyback", "gpkg"))
    try:
        cfg["out_dir"] = Path(v.get("out_root") or default_out_root()).expanduser().resolve() / run
        cfg["out_dir"].mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return None, [f"Cannot create the output folder: {e}"]
    try:
        root = Path(v.get("work_root") or tempfile.gettempdir()).expanduser().resolve()
        cfg["work_dir"] = root / "rapida_onepager" / run
        (cfg["work_dir"] / "uploads").mkdir(parents=True, exist_ok=True)
        probe = cfg["work_dir"] / ".write_test"
        probe.write_text("ok")
        probe.unlink()
    except Exception as e:
        return None, [f"Cannot write to the fast temp folder: {e}"]
    tempfile.tempdir = str(root)                      # every temporary GeoPackage is built here too
    cfg["country_names"] = A.country_names(iso)
    return cfg, []


def save_upload(file_value, folder):
    """Save a marimo file-upload value (list of objects with .name/.contents) -> path or None."""
    if not file_value:
        return None
    f = file_value[0]
    p = Path(folder) / Path(f.name).name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(f.contents)
    return p


# ============================================================= 2 admin
def hdx_cached(url, dest_dir):
    """Path of an HDX file already downloaded (and unzipped) by admin.download, or None."""
    name = url.split("?")[0].rstrip("/").split("/")[-1] or "admin_download"
    p = Path(dest_dir) / name
    if p.with_suffix("").is_dir() and p.suffix.lower() == ".zip":
        return p.with_suffix("")
    return p if p.exists() and p.suffix.lower() != ".zip" else None


def layer_fields(dataset, layer):
    import pyogrio
    try:
        return list(pyogrio.read_info(str(dataset), layer=layer)["fields"])
    except Exception:
        return []


def guess_fields(fields, level, lang):
    name, pcode, parent = A.guess_columns(pd.DataFrame(columns=fields), level, lang)
    return name, pcode, parent if parent in fields else None


def level_names(level, lang):
    sing, plur, gender = LEVEL_NAMES.get(level, LEVEL_NAMES[3])[lang]
    return dict(singular=sing, plural=plur, gender=gender)


def load_admin(dataset, layer, level, name_col, pcode_col, parent_col, names, country, source):
    """-> (adm_info, errors)."""
    e = []
    if not name_col:
        e.append("Choose the field that holds the unit names")
    if not (names.get("plural") or "").strip():
        e.append("Give the plural name of the admin level")
    if not (country or "").strip():
        e.append("Give the country name")
    if e:
        return None, e
    try:
        adm = A.add_unit_key(A.read_admin(dataset, layer), pcode_col)
    except Exception as ex:
        return None, [f"Could not read the layer: {ex}"]
    if adm.empty:
        return None, ["The admin layer has no polygons"]
    info = dict(adm=adm, level=level, cols=dict(name=name_col, pcode="unit_key", parent=parent_col),
                names={k: v.strip() if isinstance(v, str) else v for k, v in names.items()},
                country=country.strip(), source=source)
    return info, []


def preview_admin(adm, level):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.set_axis_off()
    adm.plot(ax=ax, color="#eef0f2", edgecolor="#8a96a3", linewidth=0.3)
    ax.set_title(f"{len(adm)} units at admin level {level}", fontsize=10)
    return png(fig)


def unit_options(adm_info):
    """{label: unit_key} for picking units (admin-list crisis)."""
    adm, c = adm_info["adm"], adm_info["cols"]
    lab = adm[c["name"]].astype(str)
    if c["parent"]:
        lab = lab + " (" + adm[c["parent"]].astype(str) + ")"
    lab = lab.where(~lab.duplicated(keep=False), lab + " · " + adm["unit_key"].astype(str))
    return dict(sorted(zip(lab, adm["unit_key"])))


# ============================================================= 3 hazard
def load_hazard(cfg, adm_info, source=None, gdacs_ref="", path=None, layer=None, field=None, label="",
                water=None, water_values="1", threshold=None, unit_keys=(), echo=print):
    """-> (hz_info, errors). hz_info: hazard, epicentre, report, source, gdacs_url, threshold, units."""
    crisis, adm = cfg["crisis"], adm_info["adm"]
    epic = report = url = None
    try:
        if crisis == "admin":
            if not unit_keys:
                return None, ["Select at least one admin unit"]
            sel = adm[adm["unit_key"].isin(list(unit_keys))]
            hz = sel[["geometry"]].assign(hz_class=1, hz_label="Selected").reset_index(drop=True)
            src = "administrative units selected by the analyst"
        elif source == "gdacs":
            et, ev, ep = H.parse_gdacs_ref(gdacs_ref)
            want = {"earthquake": "EQ", "flood": "FL"}[crisis]
            if et != want:
                return None, [f"This GDACS event is {et}; the crisis type needs {want}"]
            echo(f"GDACS: downloading {et} {ev} {ep or ''} …")
            fc, url = H.fetch_gdacs(et, ev, ep)
            hz, epic, report = H.gdacs_to_hazard(fc, crisis)
            src = label.strip() or f"GDACS event {et} {ev}"
        else:
            if not path:
                return None, ["Upload the crisis polygons or give their path on the server"]
            if not layer:
                polys = [n for n in H.list_layers(path)]
                layer = polys[0] if polys else None
            hz, epic = H.load_hazard_file(path, crisis, layer or None, field or None)
            src = label.strip() or Path(str(path)).name
        if crisis == "flood" and water:
            vals = tuple(int(v) for v in re.split(r"[,\s]+", str(water_values).strip()) if v)
            hz, removed = H.remove_permanent_water(hz, water, vals)
            echo(f"Permanent water removed: {removed:,.1f} km²")
    except Exception as ex:
        return None, [f"{type(ex).__name__}: {ex}"]
    if hz.empty or hz.geometry.is_empty.all():
        return None, ["The crisis polygons are empty"]
    thr = threshold if crisis == "earthquake" else None
    if crisis == "earthquake" and not (hz["hz_class"] >= thr).any():
        return None, [f"No intensity band reaches MMI {ROMAN[thr]}; lower the threshold"]
    units = adm[adm["unit_key"].isin(list(unit_keys))] if crisis == "admin" else S.units_hit(adm, hz, crisis, thr)
    if units.empty:
        return None, ["The crisis polygons do not intersect any admin unit of this country"]
    return dict(hazard=hz, epicentre=epic, report=report, source=src, gdacs_url=url, threshold=thr,
                units=units), []


def preview_hazard(adm, hz, crisis, epic=None):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_axis_off()
    adm.plot(ax=ax, color="#f0f0f1", edgecolor="#c8c8cc", linewidth=0.3)
    if crisis == "earthquake":
        hz.plot(ax=ax, color=[MMI_COLORS.get(int(c), "#a32c18") for c in hz["hz_class"]], alpha=0.8)
        if epic:
            ax.scatter([epic["lon"]], [epic["lat"]], marker="*", s=220, color="k")
    else:
        hz.plot(ax=ax, color=COLORS["flood"] if crisis == "flood" else COLORS["selected_fill"],
                edgecolor=COLORS["affected"] if crisis == "admin" else "none")
    x0, y0, x1, y1 = hz.total_bounds
    pad = max(x1 - x0, y1 - y0) * 0.3
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    return png(fig)


# ============================================================= 4 split
def do_split(cfg, adm_info, hz_info):
    """-> dict(parts, checks, ok, sig, rapida_input)."""
    c = adm_info["cols"]
    parts = S.split_units(hz_info["units"], hz_info["hazard"], cfg["crisis"], cfg["iso3"], c["name"], "unit_key",
                          c["parent"], hz_info["threshold"])
    checks = S.checks(parts, hz_info["units"], "unit_key", cfg["iso3"])
    out = dict(parts=parts, checks=checks, ok=bool(checks.ok.all()), sig=S.signature(parts), rapida_input=None)
    if out["ok"]:
        out["rapida_input"] = S.to_rapida_input(parts, cfg["work_dir"] / f"rapida_input_{out['sig']}.gpkg")
    return out


def preview_split(parts, crisis):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_axis_off()
    parts[parts.affected == 0].plot(ax=ax, color="#e9ebee", edgecolor="#9aa0a6", linewidth=0.2)
    aff = parts[parts.affected == 1]
    if crisis == "earthquake":
        aff.plot(ax=ax, color=[MMI_COLORS.get(int(k), "#a32c18") for k in aff.hz_class], edgecolor="#555",
                 linewidth=0.2)
    else:
        aff.plot(ax=ax, color=COLORS["flood"] if crisis == "flood" else COLORS["selected_fill"],
                 edgecolor="#555", linewidth=0.2)
    return png(fig)


# ============================================================= 5 RAPIDA
def last_selection(folder):
    try:
        return json.loads((Path(folder) / ".last_stats.json").read_text())
    except Exception:
        return {}


def save_selection(folder, sel):
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / ".last_stats.json").write_text(json.dumps(sel))
    except Exception:
        pass


def default_project(cfg, split_info):
    base = cfg["work_dir"] if cfg["rapida_in_temp"] else cfg["out_dir"]
    return Path(base) / f"{cfg['run_name']}_{split_info['sig']}"


def project_report(path, parts, selection):
    """Status of a RAPIDA project (folder or .gpkg) for the current split.
    -> dict(rows=[(text, ok)], ready, gpkg, errors)."""
    path = Path(path)
    rows, errors, gpkg = [], [], None
    if path.suffix.lower() == ".gpkg":
        if path.exists():
            gpkg = path
        rows.append(("GeoPackage found", gpkg is not None))
    else:
        st = R.project_state(path)
        rows += [("project folder", st["folder"]), ("rapida.json (project created)", st["config"]),
                 ("results GeoPackage", st["gpkg"] is not None)]
        if st["folder"] and not st["config"]:
            rows.append(("folder exists without rapida.json – an earlier attempt did not finish; "
                         "'Create project' moves it aside and starts again", False))
        gpkg = st["gpkg"] if st["config"] else None
    if gpkg is None:
        errors.append(f"No RAPIDA results at {path} yet – press 'Create project & run assessment'.")
        return dict(rows=rows, ready=False, gpkg=None, errors=errors)
    layers = R.stats_layers(gpkg)
    rows.append((f"stats layers: {', '.join(l[6:] for l in layers) or 'none yet'}", bool(layers)))
    ok, _, msg = ST.check_project(gpkg, parts)
    rows.append((msg, ok))
    if not ok:
        errors.append(msg + " Use a project made for this split (the default project name already is).")
    miss = [c for c in selection if f"stats.{c}" not in layers]
    if miss:
        errors.append(f"No results yet for: {', '.join(miss)} – run the assessment.")
    if not selection:
        errors.append("Choose at least one statistic.")
    return dict(rows=rows, ready=not errors, gpkg=gpkg, errors=errors)


def run_rapida(project, rapida_input, selection, year, force=False, echo=print):
    """Create the project if needed, then assess. -> (ok, message)."""
    project = Path(project)
    try:
        if project.suffix.lower() == ".gpkg":
            return False, "An existing GeoPackage cannot be assessed again; point to its project folder."
        if not R.is_project(project):
            echo(f"Creating RAPIDA project {project} …")
            R.create_project(project.name, project.parent, rapida_input)
        R.assess(project, selection, year, force)
        return True, "Assessment finished."
    except Exception as ex:
        return False, f"{type(ex).__name__}: {ex}"


def selected_catalog(catalog, selection):
    pairs = {(c, v) for c, vs in selection.items() for v in vs}
    return catalog[[(c, v) in pairs for c, v in zip(catalog.component, catalog.variable)]].reset_index(drop=True)


# ============================================================= 6 stats
def compute_stats(cfg, adm_info, hz_info, split_info, gpkg, selected, year):
    """-> dict(ps, adm_stats, summary, missing)."""
    c = adm_info["cols"]
    ps, _, missing = ST.merge_stats(gpkg, split_info["parts"], selected, year)
    adm_stats = ST.admin_stats(ps, hz_info["units"], selected, cfg["crisis"], hz_info["threshold"], "unit_key",
                               c["name"], c["parent"])
    summary = ST.summary(ps, selected, cfg["crisis"], hz_info["threshold"])
    return dict(ps=ps, adm_stats=adm_stats, summary=summary, missing=missing,
                components=sorted(selected["component"].unique()))


def metadata(cfg, adm_info, hz_info, gpkg, selected, year):
    return dict(crisis=cfg["crisis"], lang=cfg["lang"], iso3=cfg["iso3"], admin_level=adm_info["level"],
                admin_source=adm_info["source"], hazard_source=hz_info["source"], gdacs_url=hz_info["gdacs_url"],
                threshold_mmi=hz_info["threshold"], epicentre=hz_info["epicentre"],
                stats_selected=selected[["component", "variable", "kind"]].to_dict("records"),
                rapida_project=str(gpkg), year=year,
                units=dict(length="km (converted from RAPIDA metres)", area="km² (EPSG:6933)"))


def write_results(cfg, hz_info, st, meta, also_gdb=False, gpkg=None, summary=None, echo=print):
    """Write the results GeoPackage (and copy the RAPIDA project back). -> list of files."""
    files = ST.write_output(cfg["out_dir"] / f"{cfg['run_name']}_rapida_results.gpkg", hz_info["hazard"],
                            hz_info["epicentre"], st["ps"], st["adm_stats"],
                            st["summary"] if summary is None else summary, meta, also_gdb=also_gdb)
    if gpkg is not None:
        proj = Path(str(gpkg)).parent.parent if Path(str(gpkg)).parent.name == "data" else None
        if proj and R.is_project(proj) and cfg["copyback"] != "none" and not str(proj).startswith(str(cfg["out_dir"])):
            files.append(R.copy_back(proj, cfg["out_dir"] / "rapida_project", cfg["copyback"]))
    return files


def summary_table(summary):
    t = summary.copy()
    for c in ("exposed", "total"):
        t[c] = t[c].map(lambda v: f"{v:,.1f}" if pd.notna(v) else "")
    t["pct"] = t["pct"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "")
    return t[["key", "label", "unit", "exposed", "total", "pct"]]


# ============================================================= 7 maps
def default_chip(cfg, adm_info):
    nm = adm_info["names"]
    return i18n.phrase("chip_admin" if cfg["crisis"] == "admin" else "chip", cfg["lang"], nm["plural"], nm["gender"])


def draw_maps(cfg, adm_info, hz_info, st, frame="framed", min_shown=4, corner="auto", region_labels=True,
              country_label=""):
    nm = adm_info["names"]
    return M.make_maps(cfg["out_dir"], cfg["run_name"], cfg["crisis"], adm_info["adm"], adm_info["adm"]["unit_key"],
                       st["ps"], hz_info["hazard"], hz_info["epicentre"], cfg["lang"], nm["plural"], nm["gender"],
                       country_label.strip(), threshold=hz_info["threshold"], inset_position=corner,
                       region_labels=region_labels, layout=layout_for(cfg["theme"], frame)["name"],
                       min_shown=min_shown)


def legend_problems(mapinfo):
    lim = L("map.legend[].label")
    return [f"Legend label '{it['label']}' is longer than {lim} characters – shorten the admin-level plural (step 2)"
            for it in mapinfo["legend"] if len(it["label"]) > lim]


def map_preview(cfg, mapinfo, chip, content=None):
    """(png path, exact): the map area as on the poster (headless page) or an approximate composite."""
    out = cfg["work_dir"] / f"{cfg['run_name']}_map_preview.png"
    if content:
        try:
            feed, imgs = P.build_feed(content, mapinfo)
            html_path = cfg["work_dir"] / "map_preview.html"
            html_path.write_text(P.assemble_html(feed, imgs), encoding="utf-8")
            if P.render_element(html_path, ".map", out):
                return out, True
        except Exception:
            pass
    return M.composite_preview(mapinfo, chip, out), False


# ============================================================= 8 content
def value(summary, key):
    s = summary.set_index("key")
    return float(s.loc[key, "exposed"]) if key in s.index and pd.notna(s.loc[key, "exposed"]) else None


def nice(v):
    if v is None:
        return None
    return round(v) if abs(v) >= 10 else round(v, 1)


def headline_options(selected, ps):
    return {f"{r.title} [{r.variable}]": r.variable for r in selected.itertuples()
            if r.kind == "count" and r.variable in ps.columns}


def indicator_options(selected, summary):
    opts = {"— (leave out)": None, "Affected area (km²)": "area_km2"}
    for r in selected.itertuples():
        if r.variable in summary["key"].values:
            tag = "exposed" if r.kind == "count" else "mean in affected area"
            opts[f"{r.title} [{r.variable}] – {tag}"] = r.variable
    opts["Economic damage (manual input)"] = "manual:econ"
    opts["Forecasted IDPs (manual input)"] = "manual:idps"
    return opts


DEFAULT_INDICATORS = ["area_km2", "nbuildings", "roads_length", "elegrid_length", "manual:econ", "manual:idps"]


def indicator_defaults(key, cfg, threshold, selected):
    """Label / unit / unit-before / compact suggested for an indicator source."""
    lg = cfg["lang"]
    ind = i18n.t(lg, "ind")
    thr = i18n.roman(threshold) if threshold else ""
    if key == "area_km2":
        lab = ind[{"flood": "area_flood", "earthquake": "area_eq", "admin": "area_admin"}[cfg["crisis"]]]
        return dict(label=lab.format(thr=thr), unit="km²", before=False, compact=False)
    if key == "manual:econ":
        return dict(label=ind["econ"], unit="USD", before=True, compact=True)
    if key == "manual:idps":
        return dict(label=ind["idps"], unit="", before=False, compact=False)
    if not key:
        return dict(label="", unit="", before=False, compact=False)
    row = selected.set_index("variable").loc[key]
    unit = row["unit"] if row["unit"] in ("km", "km²", "USD", "m²") else ""
    return dict(label=ind.get(key, row["title"])[:L("indicators[].label")], unit=unit, before=unit == "USD",
                compact=False)


def bar_pct(summary, head_key, key):
    head, v = value(summary, head_key), value(summary, key)
    return 100 * v / head if (v is not None and head) else None


def bar_options(selected, ps):
    return {"—": None, **headline_options(selected, ps)}


def mmi_bar_items(ps, threshold, head_key):
    classes = [c for c in sorted(ps["hz_class"].unique()) if c >= threshold][-4:]
    return [(i18n.roman(c), f"{head_key}_mmi{c}") for c in classes]


def draft_texts(cfg, adm_info, hz_info, st, head_key, bar_mode):
    """Suggested poster texts, all within their limits."""
    lg, crisis = cfg["lang"], cfg["crisis"]
    thr = i18n.roman(hz_info["threshold"]) if hz_info["threshold"] else None
    nm, country, ps, summ = adm_info["names"], adm_info["country"], st["ps"], st["summary"]
    aff = ps[ps.affected == 1]
    col = "parent_name" if aff["parent_name"].astype(str).str.len().gt(0).any() else "unit_name"
    regs = list(aff.groupby(col)["area_km2"].sum().sort_values(ascending=False).index)
    loc = f"{i18n.join_list(regs[:3], lg)}, {country}" if regs else country
    if len(loc) > L("meta.location"):
        loc = f"{i18n.join_list(regs[:2], lg)}, {country}"
    if len(loc) > L("meta.location"):
        loc = country
    epic = hz_info["epicentre"] or {}
    date = epic.get("date") or dt.date.today().isoformat()
    fmt = lambda k: i18n.fmt_int(value(summ, k), lg) if value(summ, k) is not None else None
    Sd = dict(pop=fmt(head_key), bld=fmt("nbuildings"), roads=fmt("roads_length"), elec=fmt("elegrid_length"),
              regions=i18n.join_list(regs[:3], lg), mag=epic.get("magnitude"), thr=thr,
              date=i18n.long_date(date, lg), n_units=aff["unit_pcode"].nunique(), plural=nm["plural"].lower())
    kms = i18n.draft_key_messages(lg, crisis, Sd) + [("alert", "")] * 3
    if bar_mode == "mmi":
        comp = [(i18n.t(lg, "groups")[v], bar_pct(summ, head_key, v))
                for v in ("child_total", "elderly_total", "female_total")
                if v in ps.columns and bar_pct(summ, head_key, v) is not None]
        grp_title = i18n.t(lg, "grp_title_eq")
        grp_note = i18n.composition_line(lg, comp) if comp else i18n.t(lg, "grp_note_eq")
    else:
        grp_title, grp_note = i18n.t(lg, "grp_title"), i18n.t(lg, "grp_note")
    plural = nm["plural"].lower()
    return dict(
        org_line="UNDP | RAPIDA | CB Assessments and Digital Solutions Team",
        title=i18n.t(lg, "title", crisis), location=loc,
        date_line=(i18n.t(lg, "event_date") if cfg["theme"] == "approved" else "") + i18n.long_date(date, lg),
        kf_h=i18n.t(lg, "headings")["key_figures"], km_h=i18n.t(lg, "headings")["key_messages"],
        kf_label=i18n.t(lg, "kf_label"), kf_note=i18n.t(lg, "kf_note", crisis).format(thr=thr or ""),
        km=[dict(icon=i, text=t) for i, t in kms[:3]],
        narrative=i18n.draft_narrative(lg, crisis, Sd),
        grp_title=grp_title, grp_note=grp_note,
        vul_title=i18n.t(lg, "vul_title"), vul_caption=i18n.t(lg, "vul_caption"),
        chip=default_chip(cfg, adm_info),
        map_alt={"en": f"Map of the affected {plural} in {country}", "fr": f"Carte des {plural} touchés, {country}",
                 "es": f"Mapa de {plural} afectados, {country}"}[lg][:L("map.alt")],
        loc_alt={"en": f"Locator map of {country}", "fr": f"Carte de situation, {country}",
                 "es": f"Mapa de ubicación, {country}"}[lg],
        disclaimer=i18n.t(lg, "disclaimer"),
        methodology=i18n.draft_methodology(lg, crisis, hz_info["source"], adm_info["source"],
                                           st.get("components") or ["population"], thr),
        email="assessments@undp.org", web_label="RAPIDA", web_url="https://www.undp.org/crisis/rapida")


def parse_number(text):
    t = str(text or "").strip().replace(" ", "").replace(" ", "").replace(",", "")
    if not t:
        return None, None
    try:
        return float(t), None
    except ValueError:
        return None, f"'{text}' is not a number"


def collect_content(cfg, st, head_key, slots, bar_mode, bars, mmi_items, texts, show_empty):
    """Assemble the poster content. slots: [{src, label, unit, before, compact, manual}],
    bars: [{src, label}], texts: dict like draft_texts. -> (content, errors)."""
    summ, e = st["summary"], []
    inds = []
    for i, sl in enumerate(slots):
        key = sl.get("src")
        if not key:
            continue
        if key.startswith("manual:"):
            v, err = parse_number(sl.get("manual"))
            if err:
                e.append(f"Indicator {i + 1}: {err}")
        else:
            v = nice(value(summ, key))
        it = dict(label=(sl.get("label") or "").strip(), value=v, source=key)
        if not it["label"]:
            e.append(f"Indicator {i + 1}: the label is empty")
        if (sl.get("unit") or "").strip():
            it["unit"] = sl["unit"].strip()
            it["unit_position"] = "before" if sl.get("before") else "after"
        if sl.get("compact"):
            it["format"] = "compact"
        inds.append(it)
    if bar_mode == "mmi":
        items = [dict(label=lab, pct=round(bar_pct(summ, head_key, k) or 0)) for lab, k in mmi_items]
    else:
        items = [dict(label=(b.get("label") or "").strip(), pct=round(bar_pct(summ, head_key, b["src"]) or 0))
                 for b in bars if b.get("src")]
    vul = None
    vp = str(texts.get("vul_pct") or "").strip().replace("%", "").replace(",", ".")
    if vp:
        try:
            pct = float(vp)
            if not 0 <= pct <= 100:
                e.append("Poverty %: must be between 0 and 100")
            vul = dict(title=texts.get("vul_title", "").strip(), pct=pct, caption=texts.get("vul_caption", "").strip())
            if not vul["title"]:
                e.append("Poverty card: a title is needed when a % is given")
        except ValueError:
            e.append(f"Poverty %: '{texts.get('vul_pct')}' is not a number")
    g = lambda k: (texts.get(k) or "").strip()
    c = dict(lang=cfg["lang"], theme=cfg["theme"], labels=i18n.t(cfg["lang"], "labels"), show_empty=bool(show_empty),
             org_line=g("org_line"), title=g("title"), location=g("location"), date_line=g("date_line"),
             headings=dict(key_figures=g("kf_h"), key_messages=g("km_h")),
             kf_label=g("kf_label"), kf_value=round(value(summ, head_key) or 0), kf_note=g("kf_note"),
             key_messages=[(k.get("icon", "alert"), (k.get("text") or "").strip()) for k in texts.get("km", [])],
             chip=g("chip"), map_alt=g("map_alt"), locator_alt=g("loc_alt"),
             indicators=[{k: v for k, v in it.items() if k != "source"} for it in inds], narrative=g("narrative"),
             vulnerable=vul, groups=dict(title=g("grp_title"), items=items, note=g("grp_note")),
             disclaimer=g("disclaimer"), methodology=g("methodology"), email=g("email"),
             website_label=g("web_label"), website_url=g("web_url"))
    # limits and required fields (the same limits the page enforces)
    checks = [("Organisation line", c["org_line"], "meta.org_line", True), ("Title", c["title"], "meta.title", True),
              ("Location", c["location"], "meta.location", True), ("Date line", c["date_line"], "meta.date_line", True),
              ("Heading: key figures", c["headings"]["key_figures"], "headings.key_figures", False),
              ("Heading: key messages", c["headings"]["key_messages"], "headings.key_messages", False),
              ("Headline label", c["kf_label"], "key_figure.label", True),
              ("Headline note", c["kf_note"], "key_figure.note", False),
              ("Narrative", c["narrative"], "narrative", True), ("Map title", c["chip"], "map.title_chip", True),
              ("Map description", c["map_alt"], "map.alt", True),
              ("Locator description", c["locator_alt"], "map.locator.alt", False),
              ("Bars title", c["groups"]["title"], "population_groups.title", True),
              ("Bars note", c["groups"]["note"], "population_groups.note", False),
              ("Disclaimer", c["disclaimer"], "disclaimer", False), ("Methodology", c["methodology"], "methodology", False),
              ("E-mail", c["email"], "contact.email", True), ("Website label", c["website_label"], "contact.website_label", True),
              ("Website URL", c["website_url"], "contact.website_url", True)]
    checks += [(f"Key message {i + 1}", t, "key_messages[].text", False) for i, (_, t) in enumerate(c["key_messages"])]
    checks += [(f"Indicator {i + 1} label", it["label"], "indicators[].label", False) for i, it in enumerate(inds)]
    checks += [(f"Indicator {i + 1} unit", it.get("unit", ""), "indicators[].unit", False) for i, it in enumerate(inds)]
    checks += [(f"Bar {i + 1} label", it["label"], "population_groups.items[].label", True)
               for i, it in enumerate(items)]
    if vul:
        checks += [("Poverty title", vul["title"], "vulnerable.title", False),
                   ("Poverty caption", vul["caption"], "vulnerable.caption", False)]
    for name, text, path, req in checks:
        if req and not text:
            e.append(f"{name}: required")
        lim = L(path)
        if lim and len(text) > lim:
            e.append(f"{name}: {len(text)} characters, the limit is {lim}")
    if c["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", c["email"]):
        e.append("E-mail: wrong format")
    if c["website_url"] and not c["website_url"].startswith("https://"):
        e.append("Website URL must start with https://")
    c["key_messages"] = [(i, t) for i, t in c["key_messages"] if t]
    if not c["key_messages"]:
        e.append("Write at least one key message")
    if not any(it["value"] is not None for it in inds) and not c["show_empty"]:
        e.append("No indicator has a value")
    if not items:
        e.append("Choose at least one bar")
    c["_manual"] = [dict(key=it["source"].split(":")[1], label=it["label"], unit=it.get("unit", ""),
                         exposed=it["value"], total=np.nan, pct=np.nan, source="manual")
                    for it in inds if it["source"].startswith("manual:") and it["value"] is not None]
    if vul:
        c["_manual"].append(dict(key="poverty_pct", label=vul["title"], unit="%", exposed=vul["pct"], total=np.nan,
                                 pct=np.nan, source="manual"))
    return c, e


# ============================================================= 9 generate
def generate(cfg, hz_info, st, meta, content, mapinfo, also_gdb=False, pdf=True, png_=True):
    """Build, validate and render the poster; rewrite the GeoPackage with the manual values tagged 'manual'.
    -> dict(ok, status, errors, files{label: path})."""
    manual = content.get("_manual") or []
    feed, images = P.build_feed({k: v for k, v in content.items() if not k.startswith("_")}, mapinfo)
    errs = P.validate(feed)
    if errs:
        return dict(ok=False, status="invalid", errors=errs, files={})
    out, run = cfg["out_dir"], cfg["run_name"]
    html_path = out / f"{run}_onepager.html"
    html_path.write_text(P.assemble_html(feed, images), encoding="utf-8")
    feed_path = out / f"{run}_feed.json"
    feed_path.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    summ = pd.concat([st["summary"], pd.DataFrame(manual)], ignore_index=True) if manual else st["summary"]
    written = ST.write_output(out / f"{run}_rapida_results.gpkg", hz_info["hazard"], hz_info["epicentre"], st["ps"],
                              st["adm_stats"], summ, dict(meta, poster_html=str(html_path), feed=feed),
                              also_gdb=also_gdb)
    files = {"One-pager (HTML)": html_path, "Results (GeoPackage)": Path(written[0]),
             "Map (JPG)": Path(mapinfo["map_path"]), "Locator (PNG)": Path(mapinfo["locator_path"]),
             "Feed (JSON)": feed_path}
    files.update({"Results (File GDB)": Path(f) for f in written[1:] if str(f).endswith(".gdb")})
    res = P.render_check(html_path, pdf=pdf, png=png_)
    if res is None:
        return dict(ok=True, status=None, files=files,
                    errors=["Playwright/Chromium is not installed here: the poster was built but not checked "
                            "headless, and no PDF/PNG was made."])
    if res.get("status") != "ok":
        return dict(ok=False, status=res.get("status"), errors=res.get("errors") or ["render failed"], files=files)
    for label, suf in (("One-pager (PDF)", ".pdf"), ("One-pager (PNG)", ".png")):
        if html_path.with_suffix(suf).exists():
            files[label] = html_path.with_suffix(suf)
    return dict(ok=True, status="ok", errors=[], files=files)


def zip_outputs(files, run_name):
    """All output files (folders such as .gdb included) in one zip, as bytes."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files.values():
            p = Path(p)
            if p.is_dir():
                for q in p.rglob("*"):
                    if q.is_file():
                        z.write(q, f"{run_name}/{p.name}/{q.relative_to(p)}")
            elif p.exists():
                z.write(p, f"{run_name}/{p.name}")
    return b.getvalue()
