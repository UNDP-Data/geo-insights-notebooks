"""Main map (JPG) and locator (PNG).

The page draws the title chip, legend, scale bar and locator box on top of the map, so the image
contains only geography. Rules agreed for the layout:
  * extent = affected units (earthquake: + bands from MMI IV) + 12 % padding, at least 100 km wide,
    in the 4:3 shape of the map window;
  * the locator goes in the emptiest corner (hazard/affected area counts fully, land partly, sea not);
    legend and scale bar run along the bottom on the same side;
  * region labels and the country name are placed only where they do not collide with overlays.
"""
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pyproj
import shapely
from shapely.geometry import box

from . import i18n
from .admin import world_countries
from .config import (COLORS, MMI_COLORS, MMI_EDGE, MMI_ALPHA, MMI_MIN_SHOWN, MAP_DPI, MAP_PAD,
                     MAP_MIN_WIDTH_KM, LEGEND_H, GEOGRAPHIC, LAYOUTS)

CORNERS = ["br", "bl", "tr", "tl"]


def _fit(bounds, min_w, lay):
    x0, y0, x1, y1 = bounds
    w, h = x1 - x0, y1 - y0
    pad = MAP_PAD * max(w, h, 1)
    w, h = max(w + 2 * pad, min_w), h + 2 * pad
    asp = lay["w"] / lay["h"]
    w, h = max(w, h * asp), max(h, w / asp)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def _zoom(ext, f):
    x0, y0, x1, y1 = ext
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * f, (y1 - y0) * f
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def overlay_boxes(ext, pos, shape, lay):
    """(inset, legend strip, chip strip, hidden strip) as projected rectangles, mirroring the page CSS."""
    X0, Y0, X1, Y1 = ext
    W, H = X1 - X0, Y1 - Y0
    u = W / lay["w"]                                     # projected metres per poster unit
    top, right = pos.startswith("t"), pos.endswith("r")
    iw, ih = (lay["pw"], lay["ph"]) if shape == "portrait" else (lay["lw"], lay["lh"])
    t = (lay["top_t"] if right else lay["top_t_left"]) if top else (lay["top_b"] if shape == "portrait" else lay["ltop_b"])
    side = lay["side"] + (lay["hidden_left"] * lay["w"] if not right else 0)
    ix0 = X1 - (side + iw) * u if right else X0 + side * u
    inset = box(ix0, Y1 - (t + ih) * u, ix0 + iw * u, Y1 - t * u)
    hid = lay["hidden_left"] * W
    lx0, lx1 = (X0 + 0.38 * W, X1) if right else (X0 + hid, X0 + hid + 0.62 * W)
    legend = box(lx0, Y0, lx1, Y0 + LEGEND_H * H)
    chip = (box(X0 + 0.22 * W, Y1 - 40 * u, X0 + 0.78 * W, Y1) if lay["chip"] == "center"
            else box(X0, Y1 - 64 * u, X0 + 0.45 * W, Y1))
    hidden = box(X0, Y0, X0 + hid, Y1) if hid else None
    return inset, legend, chip, hidden


def choose_corner(ext, busy, land, neighbours, shape, lay):
    scores = {}
    for pos in CORNERS:
        inset, legend, _, _ = overlay_boxes(ext, pos, shape, lay)
        zone = shapely.union_all([inset, legend])
        a = zone.area
        s = zone.intersection(busy).area / a if busy is not None else 0
        s += 0.3 * zone.intersection(land).area / a if land is not None else 0
        s += 0.1 * zone.intersection(neighbours).area / a if neighbours is not None else 0
        scores[pos] = round(s, 4)
    best = min(scores, key=scores.get)
    return best, scores


def to_px(x, y, ext, lay):
    X0, Y0, X1, Y1 = ext
    return round((x - X0) / (X1 - X0) * lay["px_w"], 1), round((Y1 - y) / (Y1 - Y0) * lay["px_h"], 1)


def label_size(text, ext, lay, country):
    """Width/height in projected units of a label as the page draws it (render.js: 46/18 units, spacing 8/4)."""
    X0, _, X1, _ = ext
    u = (X1 - X0) / lay["w"]
    fs, sp = (46, 8) if country else (18, 4)
    return len(text) * (0.72 * fs + sp) * u * 1.08, fs * 1.6 * u


def fit_label(text, region, ext, lay, country=False, need=0.7, target=None):
    """A point where the label box fits inside `region`, nearest `target` (default: the view centre)."""
    if region is None or region.is_empty:
        return None
    X0, Y0, X1, Y1 = ext
    w, h = label_size(text, ext, lay, country)
    minx, miny, maxx, maxy = region.bounds
    if maxx - minx < w or maxy - miny < h:
        return None
    best, cx0, cy0 = None, (X0 + X1) / 2, (Y0 + Y1) / 2
    if target is not None:
        cx0, cy0 = target.x, target.y
    for cx in np.linspace(minx + w / 2, maxx - w / 2, 28):
        for cy in np.linspace(miny + h / 2, maxy - h / 2, 28):
            b = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if region.contains(box(cx - w / 4, cy - h / 4, cx + w / 4, cy + h / 4)) and \
                    b.intersection(region).area / b.area >= need:
                d = ((cx - cx0) / (X1 - X0)) ** 2 + ((cy - cy0) / (Y1 - Y0)) ** 2
                if best is None or d < best[0]:
                    best = (d, cx, cy)
    return None if best is None else shapely.Point(best[1], best[2])


def _valid(g):
    """Repair invalid shapes (a projection can make otherwise valid shapes invalid)."""
    bad = ~g.is_valid
    if bad.any():
        g = g.copy()
        g.loc[bad, "geometry"] = shapely.make_valid(g.loc[bad, "geometry"].values)
        g = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"]) & ~g.geometry.is_empty]
    return g


def _neighbours(iso3, ext, crs, zoom=4):
    """Countries other than iso3 within a wide lon/lat box around the map extent, projected to crs."""
    try:
        to_geo = pyproj.Transformer.from_crs(crs, GEOGRAPHIC, always_xy=True)
        lon0, lat0, lon1, lat1 = to_geo.transform_bounds(*_zoom(ext, zoom), densify_pts=21)
        if lon0 > lon1:                       # box crosses the antimeridian: keep it simple, skip neighbours
            return None
        lat0, lat1 = max(lat0, -85), min(lat1, 85)
        w = world_countries()
        w = w[w["iso3"] != iso3]
        w = w[w.intersects(box(lon0, lat0, lon1, lat1))]
        if w.empty:                           # an island: no neighbours, but the sea is still drawn
            return w.to_crs(crs)
        w = w.clip(box(lon0, lat0, lon1, lat1))
        return _valid(w.to_crs(crs))
    except Exception as e:
        print(f"ℹ neighbouring countries not drawn ({type(e).__name__}: {e})")
        return None


def _union_in(g, bounds):
    if g is None or g.empty:
        return None
    try:
        sub = g[g.intersects(box(*bounds))]
        return shapely.union_all(shapely.make_valid(sub.geometry.values)).intersection(box(*bounds)) if len(sub) else None
    except Exception:
        return None


def make_maps(out_dir, name, crisis, admin_all, units_key, parts, hazard, epicentre, lang, plural, gender,
              country_label, threshold=None, inset_position="auto", region_labels=True, max_labels=5,
              layout="approved_framed", min_shown=MMI_MIN_SHOWN):
    """admin_all: every unit of the country; units_key: Series of unit pcodes aligned with admin_all."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    lay = LAYOUTS[layout] if isinstance(layout, str) else layout
    PX_W, PX_H = lay["px_w"], lay["px_h"]
    aff_keys = set(parts.loc[parts["affected"] == 1, "unit_pcode"])
    adm = admin_all.assign(_key=units_key.astype(str).values)
    aff_units = adm[adm["_key"].isin(aff_keys)]
    crs = pyproj.CRS(aff_units.estimate_utm_crs())
    P = lambda g: None if g is None or len(g) == 0 else _valid(g.to_crs(crs))
    adm_p, aff_p = P(adm), P(aff_units)
    hz_show = None
    if crisis == "earthquake":
        hz_show = P(hazard[hazard["hz_class"] >= min_shown])
    elif crisis == "flood":
        hz_show = P(hazard)
    iso3 = parts["iso3"].iloc[0]

    # ---- extent and corner ----
    if crisis == "earthquake" and hz_show is not None and len(hz_show):
        b = np.r_[np.minimum(aff_p.total_bounds[:2], hz_show.total_bounds[:2]),
                  np.maximum(aff_p.total_bounds[2:], hz_show.total_bounds[2:])]
    else:
        b = aff_p.total_bounds
    ext = _fit(b, MAP_MIN_WIDTH_KM * 1000, lay)
    if lay["hidden_left"]:                       # widen to the left: the hidden strip shows no data
        x0, y0, x1, y1 = ext
        ext = (x0 - (x1 - x0) * lay["hidden_left"], y0, x1, y1)
        ext = _fit(ext, 0, lay)
    country = shapely.union_all(adm_p.geometry.values)
    busy = shapely.union_all([aff_p.union_all()] + ([] if hz_show is None or crisis == "flood"
                                                      else [hz_show[hz_show["hz_class"] >= threshold].union_all()]))
    # Neighbouring countries: cut to a wide box around the map in lon/lat FIRST, then project. Projecting the
    # whole world into a local UTM zone breaks far-away shapes (TopologyException).
    neighbours = _neighbours(iso3, ext, crs)
    cb = shapely.bounds(country)
    inset_shape = "landscape" if (cb[2] - cb[0]) > 1.15 * (cb[3] - cb[1]) else "portrait"   # wide country
    nb_union = _union_in(neighbours, _zoom(ext, 2))
    if inset_position in CORNERS:
        pos, scores = inset_position, {}
    else:
        for _ in range(4):
            pos, scores = choose_corner(ext, busy, country, nb_union, inset_shape, lay)
            if scores[pos] <= 0.12:
                break
            ext = _zoom(ext, 1.15)
            nb_union = _union_in(neighbours, _zoom(ext, 2))
    X0, Y0, X1, Y1 = ext
    view = box(*ext)
    clipv = lambda g: None if g is None else g[g.intersects(view.buffer((X1 - X0) * 0.05))]

    # ---- main map ----
    fig = plt.figure(figsize=(PX_W / MAP_DPI, PX_H / MAP_DPI), dpi=MAP_DPI,
                     facecolor=COLORS["sea"] if neighbours is not None else "#ffffff")
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1)
    if neighbours is not None:
        nb = clipv(neighbours)
        if len(nb):
            nb.plot(ax=ax, color=COLORS["neighbour"], edgecolor=COLORS["country_edge"], linewidth=0.8)
    adm_v = clipv(adm_p)
    adm_v.plot(ax=ax, color=COLORS["land"], edgecolor=COLORS["land_edge"], linewidth=0.35)
    gpd.GeoSeries([country], crs=crs).boundary.plot(ax=ax, color=COLORS["country_edge"], linewidth=1.4)
    if crisis == "flood":
        aff_p.plot(ax=ax, color=COLORS["affected_fill"], edgecolor="none")
        hz_v = clipv(hz_show)
        if len(hz_v):
            hz_v.plot(ax=ax, color=COLORS["flood"], edgecolor=COLORS["flood"], linewidth=0.4)
    elif crisis == "earthquake":
        hz_v = clipv(hz_show)
        for _, r in hz_v.sort_values("hz_class").iterrows():
            c = int(r.hz_class)
            gpd.GeoSeries([r.geometry], crs=crs).plot(ax=ax, color=MMI_COLORS.get(c, "#a32c18"), alpha=MMI_ALPHA,
                                                      edgecolor=MMI_EDGE.get(c, "#a32c18"), linewidth=0.6)
        adm_v.boundary.plot(ax=ax, color="#9aa0a6", linewidth=0.3)
    else:
        aff_p.plot(ax=ax, color=COLORS["selected_fill"], edgecolor="none")
    aff_p.boundary.plot(ax=ax, color=COLORS["affected"], linewidth=1.5)
    if crisis == "earthquake" and epicentre:
        e = gpd.GeoSeries([shapely.Point(epicentre["lon"], epicentre["lat"])], crs=GEOGRAPHIC).to_crs(crs).iloc[0]
        ax.scatter([e.x], [e.y], marker="*", s=420, color=COLORS["epicentre"], edgecolor="white", linewidth=1.2, zorder=10)
    map_path = out_dir / f"{name}_map.jpg"
    fig.savefig(map_path, dpi=MAP_DPI, facecolor=fig.get_facecolor(), pil_kwargs={"quality": 92})
    plt.close(fig)

    # ---- labels (drawn by the page) ----
    inset, legend, chip, hidden = overlay_boxes(ext, pos, inset_shape, lay)
    blocked = [inset.buffer((X1 - X0) * 0.01), legend, chip] + ([hidden] if hidden is not None else [])
    safe = view.buffer(-(X1 - X0) * 0.02).difference(shapely.union_all(blocked))
    labels, taken = [], []

    def label_box(pt, text, country):
        w, h = label_size(text, ext, lay, country)
        return box(pt.x - w / 2, pt.y - h / 2, pt.x + w / 2, pt.y + h / 2)

    def free_of_taken(g):
        return g.difference(shapely.union_all(taken)) if taken else g

    if country_label:
        text = country_label.upper()[:24]
        free = country.intersection(safe).difference(busy.buffer((X1 - X0) * 0.02))
        pt = fit_label(text, free, ext, lay, country=True)
        if pt is not None:
            taken.append(label_box(pt, text, True))
            x, y = to_px(pt.x, pt.y, ext, lay)
            labels.append({"text": text, "x": x, "y": y, "level": "country"})
    if region_labels:
        col = "parent_name" if parts["parent_name"].astype(str).str.len().gt(0).any() else "unit_name"
        areas = parts[parts["affected"] == 1].groupby(col)["area_km2"].sum().sort_values(ascending=False)
        for reg in areas.index[:max_labels]:
            text = str(reg).upper()[:24]
            keys = parts.loc[(parts[col] == reg) & (parts["affected"] == 1), "unit_pcode"].unique()
            whole = shapely.union_all(adm_p[adm_p["_key"].isin(keys)].geometry.values)
            g = free_of_taken(whole.intersection(safe))
            if g.is_empty:
                continue
            pt = fit_label(text, g, ext, lay, need=0.5, target=whole.representative_point())
            if pt is None:
                pt = g.representative_point()
                if taken and label_box(pt, text, False).intersects(shapely.union_all(taken)):
                    continue
            taken.append(label_box(pt, text, False))
            x, y = to_px(pt.x, pt.y, ext, lay)
            labels.append({"text": text, "x": x, "y": y, "level": "place"})

    # ---- locator ----
    cb = shapely.bounds(country)
    h_in = 5.0
    w_in = h_in * (cb[2] - cb[0]) / (cb[3] - cb[1])
    fig = plt.figure(figsize=(w_in, h_in), dpi=140)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    gpd.GeoSeries([country], crs=crs).plot(ax=ax, color=COLORS["locator_land"], edgecolor=COLORS["locator_edge"], linewidth=1.2)
    gpd.GeoSeries([aff_p.union_all()], crs=crs).plot(ax=ax, color=COLORS["locator_fill"], edgecolor=COLORS["locator_fill"], linewidth=0.6)
    ax.set_xlim(cb[0], cb[2]); ax.set_ylim(cb[1], cb[3]); ax.set_aspect("equal")
    loc_path = out_dir / f"{name}_locator.png"
    fig.savefig(loc_path, transparent=True, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)

    # ---- legend for the page ----
    if crisis == "flood":
        legend_items = [dict(label=i18n.phrase("affected", lang, plural, gender), color=COLORS["affected"], shape="outline"),
                        dict(label=i18n.t(lang, "legend_flood"), color=COLORS["flood"], shape="square")]
        ramp = None
    elif crisis == "earthquake":
        legend_items = [dict(label=i18n.phrase("affected", lang, plural, gender), color=COLORS["affected"], shape="outline")]
        if epicentre:
            legend_items.append(dict(label=i18n.t(lang, "epicentre"), color=COLORS["epicentre"], shape="star"))
        shown = sorted({min(max(int(c), 3), 10) for c in hazard["hz_class"].unique() if c >= min_shown})
        ramp = dict(title=i18n.t(lang, "ramp_title"),
                    items=[dict(label="≤III" if c == 3 else i18n.roman(c), color=MMI_COLORS.get(c, "#a32c18"))
                           for c in shown][:9])
    else:
        legend_items = [dict(label=i18n.phrase("selected", lang, plural, gender), color=COLORS["affected"], shape="outline")]
        ramp = None
    in_m = (crs.axis_info[0].unit_name or "").startswith("met")
    return dict(map_path=map_path, locator_path=loc_path, width=PX_W, height=PX_H, viewBox=[0, 0, PX_W, PX_H],
                layout=lay["name"],
                labels=labels[:8], inset_position=pos, inset_shape=inset_shape, corner_scores=scores, crs=crs.to_string(),
                units_per_km=round(PX_W / ((X1 - X0) / 1000), 4) if in_m else None,
                legend=legend_items, legend_ramp=ramp)


def composite_preview(mapinfo, chip_text, out_png):
    """Approximate map-window preview without a browser: map + title chip + place labels + locator box."""
    from PIL import Image, ImageDraw, ImageFont
    lay = LAYOUTS[mapinfo.get("layout", "approved_framed")]
    k = lay["px_w"] / lay["w"]                        # pixels per poster unit
    im = Image.open(mapinfo["map_path"]).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")

    def font(size):
        for f in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Arial.ttf"):
            try:
                return ImageFont.truetype(f, int(size))
            except Exception:
                continue
        return ImageFont.load_default()

    for lb in mapinfo["labels"]:
        big = lb.get("level") == "country"
        f = font((46 if big else 18) * k)
        text = " ".join(lb["text"]) if big else lb["text"]
        w = d.textlength(text, font=f)
        d.text((lb["x"] - w / 2, lb["y"] - f.size / 2), text, font=f,
               fill=(150, 160, 170, 150) if big else (120, 130, 140, 230))
    if chip_text:
        f = font(21 * k)
        w = d.textlength(chip_text, font=f)
        x0 = lay["px_w"] / 2 - w / 2 - 12 * k if lay["chip"] == "center" else 20 * k
        d.rounded_rectangle([x0, 0 if lay["chip"] == "center" else 20 * k, x0 + w + 24 * k,
                             (32 if lay["chip"] == "center" else 52) * k], 8 * k, fill="white")
        d.text((x0 + 12 * k, (4 if lay["chip"] == "center" else 24) * k), chip_text, font=f, fill="#2a4661")
    shape, pos = mapinfo.get("inset_shape", "portrait"), mapinfo["inset_position"]
    iw, ih = (lay["pw"], lay["ph"]) if shape == "portrait" else (lay["lw"], lay["lh"])
    right = pos.endswith("r")
    top = (lay["top_t"] if right else lay["top_t_left"]) if pos.startswith("t") else (
        lay["top_b"] if shape == "portrait" else lay["ltop_b"])
    side = lay["side"] + (0 if right else lay["hidden_left"] * lay["w"])
    x0 = (lay["w"] - side - iw) if right else side
    box_ = [x0 * k, top * k, (x0 + iw) * k, (top + ih) * k]
    d.rectangle(box_, fill="white", outline="#849eae", width=max(2, int(1.6 * k)))
    loc = Image.open(mapinfo["locator_path"]).convert("RGBA")
    pad = 10 * k
    bw, bh = box_[2] - box_[0] - 2 * pad, box_[3] - box_[1] - 2 * pad
    r = min(bw / loc.width, bh / loc.height)
    loc = loc.resize((max(1, int(loc.width * r)), max(1, int(loc.height * r))))
    im.paste(loc, (int(box_[0] + pad + (bw - loc.width) / 2), int(box_[1] + pad + (bh - loc.height) / 2)), loc)
    im.save(out_png)
    return out_png
