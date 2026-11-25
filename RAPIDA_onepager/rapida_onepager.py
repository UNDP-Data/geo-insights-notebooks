"""Build a RAPIDA exposure one-pager (HTML, PDF, PNG) and a results GeoPackage from a crisis footprint
(flood extent, earthquake shakemap or a list of admin units) and administrative boundaries."""

import marimo

__generated_with = "0.26.0"
app = marimo.App(width="medium", app_title="RAPIDA one-pager")


@app.cell(hide_code=True)
def _():
    import sys
    import tempfile
    from pathlib import Path

    import marimo as mo

    _here = Path(str(mo.notebook_dir() or Path.cwd()))
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))

    from _rapida_onepager import admin as A
    from _rapida_onepager import auth, flow, i18n
    from _rapida_onepager import rapida_runner as R
    from _rapida_onepager.config import CRISIS_TYPES, LANGS, ROMAN, THEMES

    def problems(errs, title="Please fix:"):
        return mo.callout(mo.md(f"**{title}**\n\n" + "\n".join(f"- {e}" for e in errs)), kind="danger")

    def waiting(text):
        return mo.callout(mo.md(text), kind="neutral")

    def card(text, kind="success"):
        return mo.callout(mo.md(text), kind=kind)
    return (
        A,
        CRISIS_TYPES,
        LANGS,
        Path,
        R,
        ROMAN,
        THEMES,
        auth,
        card,
        flow,
        i18n,
        mo,
        problems,
        tempfile,
        waiting,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # RAPIDA one-pager

    Turns a crisis footprint into a one-page exposure overview in **English, French or Spanish**, with UNDP
    [RAPIDA](https://github.com/UNDP-Data/rapida) computing who and what is exposed.

    | Step | What happens |
    |:---|:---|
    | 1 · Setup | Crisis type (flood, earthquake or a list of admin units), language, layout, country |
    | 2 · Boundaries | OCHA COD-AB from HDX, or your own file; what the admin level is called |
    | 3 · Crisis polygons | GDACS event or your own file (flood extent, shakemap); earthquakes: affected from which intensity |
    | 4 · Split | Admin units cut by the hazard, with checks |
    | 5 · RAPIDA | Sign in (only when needed), choose the statistics, run the assessment |
    | 6 · Statistics | Exposed, total and % per admin unit; results GeoPackage |
    | 7 · Map | Map and locator as they will appear on the poster |
    | 8 · Content | Figures, texts and manual values (economic damage, IDPs, poverty), with character limits |
    | 9 · One-pager | Built, checked headless, ready to download |

    Each step opens when the one before it is complete. Changing an earlier step updates everything after it.
    """)
    return


@app.cell(hide_code=True)
def _(CRISIS_TYPES, LANGS, THEMES, flow, mo, tempfile):
    _e = dict(
        crisis=mo.ui.radio(options={v: k for k, v in CRISIS_TYPES.items()}, value=CRISIS_TYPES["flood"]),
        lang=mo.ui.radio(options={v: k for k, v in LANGS.items()}, value=LANGS["en"], inline=True),
        theme=mo.ui.dropdown(options={v: k for k, v in THEMES.items()}, value=THEMES["approved"]),
        iso3=mo.ui.text(placeholder="e.g. MOZ", max_length=3),
        run_name=mo.ui.text(placeholder="automatic: ISO3_crisis_date", full_width=True),
        out_root=mo.ui.text(value=flow.default_out_root(), full_width=True),
        work_root=mo.ui.text(value=tempfile.gettempdir(), full_width=True),
        rapida_in_temp=mo.ui.checkbox(value=True, label="Create the RAPIDA project in the fast temp folder"),
        copyback=mo.ui.dropdown(
            options={"rapida.json + results GeoPackage": "gpkg", "the whole RAPIDA project (can be large)": "all",
                     "nothing (keep the project only in temp)": "none"},
            value="rapida.json + results GeoPackage"),
    )
    setup_form = mo.md(r"""
    ## 1 · Crisis, language and output

    **Type of crisis**
    {crisis}

    **Poster language** {lang}  **Layout** {theme}

    **Country (ISO3 code)** {iso3}

    **Run name** {run_name}

    **Output folder on the server** – every result can also be downloaded at the end
    {out_root}

    **Fast temp folder** – downloads, the RAPIDA project and GeoPackages are built here first
    {work_root}

    {rapida_in_temp} · copy back to the output folder: {copyback}
    """).batch(**_e).form(submit_button_label="Validate & continue", validate=flow.validate_setup, bordered=True)
    setup_form
    return (setup_form,)


@app.cell(hide_code=True)
def _(card, flow, mo, problems, setup_form, waiting):
    mo.stop(setup_form.value is None, waiting("Fill in step 1 and press **Validate & continue**."))
    cfg, _errs = flow.make_config(setup_form.value)
    mo.stop(bool(_errs), problems(_errs))
    card(f"Run **{cfg['run_name']}** · results go to `{cfg['out_dir']}` · working folder `{cfg['work_dir']}`")
    return (cfg,)


@app.cell(hide_code=True)
def _(cfg, mo):
    adm_src = mo.ui.dictionary({
        "source": mo.ui.radio(options={"OCHA COD-AB from HDX": "hdx", "Upload a file": "upload",
                                       "File on the server": "server"},
                              value="OCHA COD-AB from HDX", inline=True),
        "level": mo.ui.dropdown(options={"1": 1, "2": 2, "3": 3, "4": 4}, value="2", label="Admin level"),
    })
    mo.vstack([mo.md(f"## 2 · Administrative boundaries · {cfg['country_names'][cfg['lang']]}"),
               adm_src["source"], adm_src["level"]])
    return (adm_src,)


@app.cell(hide_code=True)
def _(A, adm_src, cfg, mo):
    _src = adm_src.value["source"]
    _items, _note = {}, ""
    if _src == "hdx":
        try:
            with mo.status.spinner(title=f"Listing HDX boundaries cod-ab-{cfg['iso3'].lower()} …"):
                _res = A.hdx_resources(cfg["iso3"])
            _opts = {f"{r['name']}  [{r['format']}]": r["url"] for r in _res}
            if _opts:
                _items["resource"] = mo.ui.dropdown(options=_opts, value=next(iter(_opts)), label="HDX file",
                                                    full_width=True)
            else:
                _note = "HDX lists no vector boundaries for this country – upload a file instead."
        except Exception as _ex:
            _note = f"HDX could not be reached ({_ex}) – upload a file or give a path on the server."
    elif _src == "upload":
        _items["file"] = mo.ui.file(filetypes=[".zip", ".gpkg", ".geojson", ".json", ".fgb"],
                                    max_size=500 * 1024 * 1024, label="Shapefile as .zip, GeoPackage, GeoJSON")
    else:
        _items["path"] = mo.ui.text(placeholder="/path/to/admin.gpkg, a folder, a .zip or a .gdb", full_width=True)
    adm_input = mo.ui.dictionary(_items)
    mo.vstack([adm_input[k] for k in _items] + ([mo.callout(mo.md(_note), kind="warn")] if _note else []))
    return (adm_input,)


@app.cell(hide_code=True)
def _(mo):
    hdx_btn = mo.ui.run_button(label="Download from HDX")
    return (hdx_btn,)


@app.cell(hide_code=True)
def _(A, Path, adm_input, adm_src, card, cfg, flow, hdx_btn, mo, waiting):
    _src, _v = adm_src.value["source"], adm_input.value
    adm_dataset, adm_source_label = None, None
    if _src == "hdx" and _v.get("resource"):
        _dest = cfg["work_dir"] / "admin_download"
        adm_dataset = flow.hdx_cached(_v["resource"], _dest)
        if adm_dataset is None and hdx_btn.value:
            with mo.status.spinner(title="Downloading boundaries from HDX …"):
                adm_dataset = A.download(_v["resource"], _dest)
        adm_source_label = f"OCHA COD-AB (HDX, {Path(_v['resource'].split('?')[0]).name})"
        mo.stop(adm_dataset is None, mo.hstack([hdx_btn, waiting("Press **Download from HDX**.")], justify="start"))
    elif _src == "upload":
        adm_dataset = flow.save_upload(_v.get("file"), cfg["work_dir"] / "uploads")
        adm_source_label = adm_dataset.name if adm_dataset else None
    elif _src == "server" and (_v.get("path") or "").strip():
        adm_dataset = Path(_v["path"].strip()).expanduser()
        mo.stop(not adm_dataset.exists(), card(f"`{adm_dataset}` does not exist on the server.", "danger"))
        adm_source_label = adm_dataset.name
    mo.stop(adm_dataset is None, waiting("Choose the boundaries file."))
    card(f"Boundaries: `{Path(adm_dataset).name}`")
    return adm_dataset, adm_source_label


@app.cell(hide_code=True)
def _(A, Path, adm_dataset, adm_src, mo, problems):
    _layers = A.find_vector_layers(adm_dataset)
    mo.stop(not _layers, problems([f"No polygon layers found in {Path(adm_dataset).name}"]))
    _opts = {f"{Path(ds).name} › {ly}": (ds, ly) for ds, ly in _layers}
    _guess = A.guess_layer(_layers, adm_src.value["level"])
    adm_layer = mo.ui.dropdown(options=_opts, value=next(k for k, v in _opts.items() if v == _guess),
                               label="Layer", full_width=True)
    adm_layer
    return (adm_layer,)


@app.cell(hide_code=True)
def _(adm_layer, adm_src, cfg, flow, mo):
    _ds, _ly = adm_layer.value
    _level = adm_src.value["level"]
    _fields = flow.layer_fields(_ds, _ly)
    _name, _pcode, _parent = flow.guess_fields(_fields, _level, cfg["lang"])
    _opts = {"—": None, **{f: f for f in _fields}}
    _nm = flow.level_names(_level, cfg["lang"])
    _lang = cfg["lang"]
    _e = dict(
        name=mo.ui.dropdown(options=_opts, value=_name if _name in _fields else "—"),
        pcode=mo.ui.dropdown(options=_opts, value=_pcode if _pcode in _fields else "—"),
        parent=mo.ui.dropdown(options=_opts, value=_parent if _parent in _fields else "—"),
        singular=mo.ui.text(value=_nm["singular"]),
        plural=mo.ui.text(value=_nm["plural"]),
        gender=mo.ui.dropdown(options={"masculine": "m", "feminine": "f"},
                              value="feminine" if _nm["gender"] == "f" else "masculine"),
        country=mo.ui.text(value=cfg["country_names"][_lang], max_length=40),
    )
    adm_form = mo.md(f"""
    **Fields** · names {{name}} · pcodes {{pcode}} · names one level up (for labels) {{parent}}

    **What this level is called** ({_lang}) · singular {{singular}} · plural {{plural}}
    {"· gender {gender}" if _lang != "en" else ""}

    Used in the map title and legend, e.g. *Map of affected districts*.

    **Country name on the poster** {{country}}
    """).batch(**(_e if _lang != "en" else {k: v for k, v in _e.items() if k != "gender"})).form(
        submit_button_label="Load boundaries", bordered=True)
    adm_form
    return (adm_form,)


@app.cell(hide_code=True)
def _(
    adm_dataset,
    adm_form,
    adm_layer,
    adm_source_label,
    adm_src,
    card,
    flow,
    mo,
    problems,
    waiting,
):
    mo.stop(adm_form.value is None, waiting("Check the fields and press **Load boundaries**."))
    _v = adm_form.value
    _ds, _ly = adm_layer.value
    with mo.status.spinner(title="Reading boundaries …"):
        adm_info, _errs = flow.load_admin(
            _ds, _ly, adm_src.value["level"], _v["name"], _v["pcode"], _v["parent"],
            dict(singular=_v["singular"], plural=_v["plural"], gender=_v.get("gender", "m")), _v["country"],
            adm_source_label or str(adm_dataset))
    mo.stop(bool(_errs), problems(_errs))
    _cols = [c for c in (_v["name"], _v["pcode"], _v["parent"]) if c]
    mo.vstack([card(f"{len(adm_info['adm'])} units loaded"),
               mo.hstack([mo.image(flow.preview_admin(adm_info["adm"], adm_info["level"]), width=380),
                          mo.ui.table(adm_info["adm"][_cols].head(50), selection=None, page_size=8)],
                         widths=[1, 1.4])])
    return (adm_info,)


@app.cell(hide_code=True)
def _(ROMAN, adm_info, cfg, flow, mo):
    _crisis = cfg["crisis"]
    if _crisis == "admin":
        _e = dict(units=mo.ui.multiselect(options=flow.unit_options(adm_info), full_width=True))
        _tpl = r"""
    ## 3 · Affected admin units
    Pick the affected units (type to search):
    {units}
    """
    else:
        _e = dict(
            source=mo.ui.radio(options={"GDACS event": "gdacs", "Upload a file": "upload", "File on the server": "server"},
                               value="GDACS event", inline=True),
            gdacs=mo.ui.text(placeholder="GDACS link, or  EQ 1570339 1738684", full_width=True),
            file=mo.ui.file(filetypes=[".zip", ".gpkg", ".geojson", ".json", ".fgb"], max_size=500 * 1024 * 1024,
                            label="Polygons as .zip, GeoPackage or GeoJSON"),
            path=mo.ui.text(placeholder="/path/on/the/server/footprint.gpkg", full_width=True),
            layer=mo.ui.text(placeholder="empty: the first layer"),
            field=mo.ui.text(placeholder="empty: found automatically"),
            label=mo.ui.text(placeholder="e.g. UNOSAT, Sentinel-1, 29 Dec–18 Jan", full_width=True),
        )
        if _crisis == "earthquake":
            _e["thr"] = mo.ui.dropdown(options={f"MMI {ROMAN[c]}": c for c in range(4, 10)}, value="MMI VI")
        else:
            _e["water"] = mo.ui.text(placeholder="optional raster, e.g. a JRC Global Surface Water mosaic (.tif)",
                                     full_width=True)
            _e["water_values"] = mo.ui.text(value="1")
        _extra = (r"""
    **Affected from** {thr} – units reaching this intensity or more count as affected; bands from MMI IV
    are drawn on the map.""" if _crisis == "earthquake" else r"""
    **Permanent water to remove** {water}
    water value(s) {water_values} – JRC *seasonality* tiles: 12; a 0/1 permanent-water mosaic: 1.""")
        _tpl = r"""
    ## 3 · Crisis polygons
    {source}

    **GDACS** {gdacs}
    Only the hazard polygons are kept. Earthquakes: the intensity bands and the epicentre (star); the 100 km circle
    is dropped. The earthquake bands are grouped into whole MMI classes (6.5 counts as VI).

    **Upload** {file}  **or a path on the server** {path}

    Layer {layer} · intensity field (shakemaps) {field}

    **Source, as it should read in the methodology** {label}
    """ + _extra
    hz_form = mo.md(_tpl).batch(**_e).form(submit_button_label="Load crisis polygons", bordered=True)
    hz_form
    return (hz_form,)


@app.cell(hide_code=True)
def _(adm_info, card, cfg, flow, hz_form, mo, problems, waiting):
    mo.stop(hz_form.value is None, waiting("Fill in step 3 and press **Load crisis polygons**."))
    _v = hz_form.value
    _path = None
    if cfg["crisis"] != "admin":
        if _v["source"] == "upload":
            _path = flow.save_upload(_v["file"], cfg["work_dir"] / "uploads")
        elif _v["source"] == "server":
            _path = _v["path"].strip() or None
    with mo.status.spinner(title="Loading crisis polygons …"):
        hz_info, _errs = flow.load_hazard(
            cfg, adm_info, source=_v.get("source"), gdacs_ref=_v.get("gdacs", ""), path=_path,
            layer=(_v.get("layer") or "").strip() or None, field=(_v.get("field") or "").strip() or None,
            label=_v.get("label", ""), water=(_v.get("water") or "").strip() or None,
            water_values=_v.get("water_values", "1"), threshold=_v.get("thr"), unit_keys=_v.get("units", ()))
    mo.stop(bool(_errs), problems(_errs))
    _epic = hz_info["epicentre"]
    _rows = [card(f"{len(hz_info['units'])} admin units intersect the crisis polygons · source: {hz_info['source']}")]
    if _epic:
        _rows.append(mo.md(f"Epicentre {_epic['lat']:.3f}, {_epic['lon']:.3f} · magnitude {_epic.get('magnitude')} · "
                           f"{_epic.get('date', '')}"))
    _right = []
    if cfg["crisis"] != "admin":
        _right.append(mo.ui.table(flow.H.hazard_summary(hz_info["hazard"], cfg["crisis"]), selection=None))
    if hz_info["report"] is not None:
        _right += [mo.md("**GDACS features**"), mo.ui.table(hz_info["report"], selection=None)]
    _rows.append(mo.hstack([mo.image(flow.preview_hazard(adm_info["adm"], hz_info["hazard"], cfg["crisis"], _epic),
                                     width=420), mo.vstack(_right)], widths=[1.2, 1]))
    mo.vstack(_rows)
    return (hz_info,)


@app.cell(hide_code=True)
def _(adm_info, card, cfg, flow, hz_info, mo, problems):
    with mo.status.spinner(title="Splitting admin units by the hazard …"):
        split_info = flow.do_split(cfg, adm_info, hz_info)
    _c = split_info["checks"]
    _tbl = mo.md("\n".join(["| | Check | Detail |", "|---|---|---|"] +
                           [f"| {'✅' if r.ok else '❌'} | {r.check} | {r.detail} |" for r in _c.itertuples()]))
    _parts = split_info["parts"]
    _n_aff = _parts.loc[_parts.affected == 1, "unit_pcode"].nunique()
    _out = mo.vstack([
        mo.md("## 4 · Split admin units\nEach affected unit is cut into one part per hazard class plus its "
              "unaffected remainder. RAPIDA runs on these parts, so the totals per unit (for the ratios) come from "
              "the same run."),
        mo.hstack([_tbl, mo.image(flow.preview_split(_parts, cfg["crisis"]), width=360)], widths=[1.3, 1]),
        card(f"{len(hz_info['units'])} units hit · {_n_aff} affected · {len(_parts)} parts · split fingerprint "
             f"`{split_info['sig']}`") if split_info["ok"] else problems(
            [f"{r.check} ({r.detail})" for r in _c[~_c.ok].itertuples()]),
    ])
    mo.stop(not split_info["ok"], _out)
    _out
    return (split_info,)


@app.cell(hide_code=True)
def _(mo):
    get_auth_n, set_auth_n = mo.state(0)
    return get_auth_n, set_auth_n


@app.cell(hide_code=True)
def _(auth, get_auth_n, mo, split_info):
    get_auth_n()
    _ = split_info
    with mo.status.spinner(title="Checking the RAPIDA sign-in …"):
        _ok, _text = auth.describe(auth.token_status())
    mo.vstack([
        mo.md("## 5 · RAPIDA"),
        mo.callout(mo.md(_text + ("" if _ok else
                                  " Sign in below; the sign-in is kept and renewed automatically afterwards.")),
                   kind="success" if _ok else "warn"),
    ])
    return


@app.cell(hide_code=True)
def _(mo, split_info):
    _ = split_info                      # shown once step 4 is done
    signin_form = mo.md(r"""
    **Sign in to RAPIDA** (only when the line above asks for it)

    UNDP e-mail {email}  password {password}

    The password goes only to RAPIDA's own sign-in, in a separate process; it is not stored. After you press
    *Sign in*, a number appears here: approve it in Microsoft Authenticator.
    The sign-in is saved for the account running this server, so everyone using this server shares it.
    """).batch(email=mo.ui.text(placeholder="name@undp.org", kind="email"),
               password=mo.ui.text(kind="password")).form(submit_button_label="Sign in", clear_on_submit=True)
    signin_form
    return (signin_form,)


@app.cell(hide_code=True)
def _(auth, mo, set_auth_n, signin_form):
    mo.stop(signin_form.value is None)
    _v = signin_form.value
    mo.stop(not (_v["email"] and _v["password"]), mo.callout("Give e-mail and password.", kind="warn"))

    def _mfa(n):
        mo.output.replace(mo.callout(mo.md(f"### Approve **{n}** in Microsoft Authenticator\nWaiting for approval …"),
                                     kind="info"))

    mo.output.replace(mo.callout("Signing in …", kind="neutral"))
    _ok, _msg = auth.sign_in(_v["email"], _v["password"], echo=print, on_mfa=_mfa)
    set_auth_n(lambda n: n + 1)
    mo.output.replace(mo.callout(_msg, kind="success" if _ok else "danger"))
    return


@app.cell(hide_code=True)
def _(R, split_info):
    _ = split_info
    rapida_catalog, catalog_live = R.catalog()
    return catalog_live, rapida_catalog


@app.cell(hide_code=True)
def _(catalog_live, cfg, flow, mo, rapida_catalog):
    _last = flow.last_selection(cfg["out_dir"].parent)
    _pick = {}
    for _comp, _g in rapida_catalog.groupby("component"):
        _opts = {f"{r.variable} – {r.title} ({r.operator or 'ratio'})": r.variable for r in _g.itertuples()}
        _val = [k for k, v in _opts.items() if v in _last.get(_comp, [])]
        _pick[_comp] = mo.ui.multiselect(options=_opts, value=_val, label=_comp, full_width=True)
    stat_pick = mo.ui.dictionary(_pick)
    mo.vstack([
        mo.md("**Statistics to compute** – nothing is pre-selected except your last choice. Count statistics "
              "(sum/count) get exposed, total and % per admin unit; mean-type statistics get the affected-area mean "
              "next to the whole-unit mean." +
              ("" if catalog_live else " *(RAPIDA's own list could not be read; showing the built-in list.)*")),
        *[stat_pick[k] for k in _pick],
    ])
    return (stat_pick,)


@app.cell(hide_code=True)
def _(mo, split_info):
    import datetime as _dt
    _ = split_info
    _y = _dt.date.today().year
    rapida_opts = mo.ui.dictionary({
        "mode": mo.ui.radio(options={"New project for this split (recommended)": "new",
                                     "Existing project or results GeoPackage": "existing"},
                            value="New project for this split (recommended)"),
        "existing": mo.ui.text(placeholder="/path/to/project  or  /path/to/project/data/project.gpkg",
                               full_width=True),
        "year": mo.ui.dropdown(options={str(y): y for y in range(_y + 1, _y - 10, -1)}, value=str(_y),
                               label="Data year"),
        "force": mo.ui.checkbox(label="Force recompute (-f)"),
        "isolated": mo.ui.checkbox(value=True, label="Run RAPIDA in a separate process (recommended)"),
    })
    mo.vstack([mo.md("**RAPIDA project**"), rapida_opts["mode"], rapida_opts["existing"],
               mo.hstack([rapida_opts["year"], rapida_opts["force"], rapida_opts["isolated"]], justify="start",
                         wrap=True)])
    return (rapida_opts,)


@app.cell(hide_code=True)
def _(mo, split_info):
    _ = split_info
    rapida_btn = mo.ui.run_button(label="Create project & run assessment", kind="warn")
    rapida_btn
    return (rapida_btn,)


@app.cell(hide_code=True)
def _(Path, R, cfg, flow, mo, rapida_btn, rapida_opts, split_info, stat_pick):
    _o = rapida_opts.value
    R.ISOLATED = bool(_o["isolated"])
    selection = {c: v for c, v in stat_pick.value.items() if v}
    if _o["mode"] == "existing" and (_o["existing"] or "").strip():
        rapida_project = Path(_o["existing"].strip()).expanduser()
    else:
        rapida_project = flow.default_project(cfg, split_info)
    _run_msg = None
    if rapida_btn.value:
        mo.stop(not selection, mo.callout("Choose at least one statistic first.", kind="warn"))
        flow.save_selection(cfg["out_dir"].parent, selection)
        with mo.status.spinner(title="RAPIDA is running – progress is shown below …"):
            _ok, _run_msg = flow.run_rapida(rapida_project, split_info["rapida_input"], selection, _o["year"],
                                            _o["force"], echo=print)
        _run_msg = mo.callout(_run_msg, kind="success" if _ok else "danger")
    rapida_report = flow.project_report(rapida_project, split_info["parts"], selection)
    _rows = "\n".join(f"- {'✅' if ok else '▫️'} {t}" for t, ok in rapida_report["rows"])
    mo.vstack(([_run_msg] if _run_msg else []) +
              [mo.md(f"**Project** `{rapida_project}`\n\n{_rows}")])
    return rapida_project, rapida_report, selection


@app.cell(hide_code=True)
def _(card, flow, mo, problems, rapida_catalog, rapida_opts, rapida_report, selection):
    mo.stop(not rapida_report["ready"], problems(rapida_report["errors"], "RAPIDA results not ready:"))
    rapida_info = dict(gpkg=rapida_report["gpkg"], year=int(rapida_opts.value["year"]),
                       selected=flow.selected_catalog(rapida_catalog, selection))
    mo.stop(not (rapida_info["selected"]["kind"] == "count").any(),
            problems(["Select at least one count statistic (e.g. population total) for the headline figure"]))
    card(f"RAPIDA results ready · `{rapida_info['gpkg'].name}`")
    return (rapida_info,)


@app.cell(hide_code=True)
def _(mo, rapida_info):
    _ = rapida_info
    want_gdb = mo.ui.checkbox(label="Also write an Esri File Geodatabase (.gdb)")
    mo.vstack([mo.md("## 6 · Statistics and results GeoPackage"), want_gdb])
    return (want_gdb,)


@app.cell(hide_code=True)
def _(
    adm_info,
    card,
    cfg,
    flow,
    hz_info,
    mo,
    problems,
    rapida_info,
    split_info,
    want_gdb,
):
    with mo.status.spinner(title="Merging RAPIDA results and computing statistics …"):
        try:
            st = flow.compute_stats(cfg, adm_info, hz_info, split_info, rapida_info["gpkg"], rapida_info["selected"],
                                    rapida_info["year"])
        except Exception as _ex:
            mo.stop(True, problems([f"{type(_ex).__name__}: {_ex}"]))
        meta = flow.metadata(cfg, adm_info, hz_info, rapida_info["gpkg"], rapida_info["selected"],
                             rapida_info["year"])
        _files = flow.write_results(cfg, hz_info, st, meta, also_gdb=want_gdb.value, gpkg=rapida_info["gpkg"])
    _warn = [mo.callout(mo.md("Not found in the RAPIDA output: " + ", ".join(st["missing"])), kind="warn")] \
        if st["missing"] else []
    mo.vstack(_warn + [
        mo.md("**Overall** – exposed, total in the affected units, % exposed"),
        mo.ui.table(flow.summary_table(st["summary"]), selection=None, page_size=12),
        mo.md(f"**Per admin unit** ({len(st['adm_stats'])} affected units)"),
        mo.ui.table(st["adm_stats"].drop(columns="geometry"), selection=None, page_size=8),
        card("Written: " + ", ".join(f"`{getattr(f, 'name', f)}`" for f in _files)),
    ])
    return meta, st


@app.cell(hide_code=True)
def _(adm_info, cfg, mo):
    _e = {
        "corner": mo.ui.dropdown(options={"Automatic (emptiest corner)": "auto", "Top left": "tl", "Top right": "tr",
                                          "Bottom left": "bl", "Bottom right": "br"},
                                 value="Automatic (emptiest corner)", label="Locator"),
        "region_labels": mo.ui.checkbox(value=True, label="Label affected regions (one level up)"),
        "country_label": mo.ui.text(value=adm_info["country"], placeholder="empty: no country label",
                                    label="Country label"),
    }
    if cfg["theme"] == "approved":
        _e["frame"] = mo.ui.dropdown(options={"Inside the page margins": "framed",
                                              "To the right page edge (original design)": "bleed"},
                                     value="Inside the page margins", label="Map window")
    if cfg["crisis"] == "earthquake":
        _e["min_shown"] = mo.ui.dropdown(options={"≤III (all bands)": 3, "IV": 4, "V": 5}, value="IV",
                                         label="Draw intensity from")
    map_opts = mo.ui.dictionary(_e)
    mo.vstack([mo.md("## 7 · Map and locator"), mo.hstack([map_opts[k] for k in _e], wrap=True, justify="start")])
    return (map_opts,)


@app.cell(hide_code=True)
def _(adm_info, cfg, flow, hz_info, map_opts, mo, problems, st):
    _o = map_opts.value
    with mo.status.spinner(title="Drawing the map and the locator …"):
        mapinfo = flow.draw_maps(cfg, adm_info, hz_info, st, frame=_o.get("frame", "framed"),
                                 min_shown=_o.get("min_shown", 4), corner=_o["corner"],
                                 region_labels=_o["region_labels"],
                                 country_label=_o["country_label"] or "")
        _prev, _ = flow.map_preview(cfg, mapinfo, flow.default_chip(cfg, adm_info))
    _bad = flow.legend_problems(mapinfo)
    mo.vstack(([problems(_bad)] if _bad else []) + [
        mo.md(f"Locator in the **{mapinfo['inset_position']}** corner · labels: "
              f"{', '.join(l['text'] for l in mapinfo['labels']) or 'none'}"),
        mo.image(_prev, width=760),
        mo.accordion({"The two image files (the page draws title, labels, legend, scale bar and locator box on top)":
                      mo.hstack([mo.image(mapinfo["map_path"], width=460),
                                 mo.image(mapinfo["locator_path"], width=140)], justify="start")}),
    ])
    return (mapinfo,)


@app.cell(hide_code=True)
def _(cfg, flow, mo, rapida_info, st):
    _sel = rapida_info["selected"]
    _heads = flow.headline_options(_sel, st["ps"])
    _hv = next((k for k, v in _heads.items() if v == "total"), next(iter(_heads)))
    _ind = flow.indicator_options(_sel, st["summary"])
    _rev = {v: k for k, v in _ind.items()}
    _slots = [mo.ui.dropdown(options=_ind, value=_rev.get(d, "— (leave out)")) for d in flow.DEFAULT_INDICATORS]
    _bars = flow.bar_options(_sel, st["ps"])
    _brev = {v: k for k, v in _bars.items()}
    _avail = [v for v in ("child_total", "elderly_total", "female_total") if v in st["ps"].columns]
    _modes = {"Composition of exposed people": "comp"}
    if cfg["crisis"] == "earthquake":
        _modes["Exposed people by intensity"] = "mmi"
    content_choice = mo.ui.dictionary({
        "head": mo.ui.dropdown(options=_heads, value=_hv, label="Headline figure"),
        "slots": mo.ui.array(_slots, label="Indicators (up to 6; empty ones are left out and the band re-flows)"),
        "show_empty": mo.ui.checkbox(label="Show indicators without a value as 'No data' instead"),
        "bar_mode": mo.ui.radio(options=_modes, value=list(_modes)[-1], label="Bar chart"),
        "bars": mo.ui.array([mo.ui.dropdown(options=_bars, value=_brev.get(_avail[i]) if i < len(_avail) else "—")
                             for i in range(4)], label="Bars (composition mode)"),
    })
    mo.vstack([
        mo.md("## 8 · Poster content"), content_choice["head"],
        mo.md("**Indicators** – up to six; empty ones are left out and the band re-flows. Economic damage and "
              "forecasted IDPs are manual values, typed below."),
        mo.hstack([content_choice["slots"][i] for i in range(6)], wrap=True, justify="start"),
        content_choice["show_empty"], content_choice["bar_mode"],
        mo.md("**Bars** (composition mode)"),
        mo.hstack([content_choice["bars"][i] for i in range(4)], wrap=True, justify="start"),
    ])
    return (content_choice,)


@app.cell(hide_code=True)
def _(adm_info, cfg, content_choice, flow, hz_info, mo, rapida_info, st):
    _c = content_choice.value
    _d = flow.draft_texts(cfg, adm_info, hz_info, st, _c["head"], _c["bar_mode"])

    def _t(key, path, label, area=False, rows=3):
        lim = flow.L(path)
        lab = f"{label} · max {lim}" if lim else label
        if area:
            return mo.ui.text_area(value=_d[key], max_length=lim, rows=rows, label=lab, full_width=True)
        return mo.ui.text(value=_d[key], max_length=lim, label=lab, full_width=True)

    _texts = {
        "org_line": _t("org_line", "meta.org_line", "Organisation line"),
        "title": _t("title", "meta.title", "Title"),
        "location": _t("location", "meta.location", "Location"),
        "date_line": _t("date_line", "meta.date_line", "Date line"),
        "kf_h": _t("kf_h", "headings.key_figures", "Heading: key figures"),
        "km_h": _t("km_h", "headings.key_messages", "Heading: key messages"),
        "kf_label": _t("kf_label", "key_figure.label", "Headline label"),
        "kf_note": _t("kf_note", "key_figure.note", "Headline note"),
        "narrative": _t("narrative", "narrative", "Narrative", area=True, rows=5),
        "grp_title": _t("grp_title", "population_groups.title", "Bars title"),
        "grp_note": _t("grp_note", "population_groups.note", "Bars note"),
        "vul_pct": mo.ui.text(value="", placeholder="empty: the card is hidden",
                              label="Population in multidimensional poverty, % (manual input)"),
        "vul_title": _t("vul_title", "vulnerable.title", "Poverty card title"),
        "vul_caption": _t("vul_caption", "vulnerable.caption", "Poverty card caption"),
        "chip": _t("chip", "map.title_chip", "Map title"),
        "map_alt": _t("map_alt", "map.alt", "Map description (accessibility)"),
        "loc_alt": _t("loc_alt", "map.locator.alt", "Locator description"),
        "disclaimer": _t("disclaimer", "disclaimer", "Disclaimer", area=True),
        "methodology": _t("methodology", "methodology", "Methodology", area=True, rows=6),
        "email": _t("email", "contact.email", "E-mail"),
        "web_label": _t("web_label", "contact.website_label", "Website label"),
        "web_url": _t("web_url", "contact.website_url", "Website URL"),
    }
    _km = mo.ui.array([mo.ui.dictionary({
        "icon": mo.ui.dropdown(options=["flood", "alert", "analysis"], value=k["icon"]),
        "text": mo.ui.text_area(value=k["text"], max_length=flow.L("key_messages[].text"), rows=3,
                                label=f"Key message {i + 1} · max {flow.L('key_messages[].text')}", full_width=True),
    }) for i, k in enumerate(_d["km"])])
    _slots = []
    for _i, _src in enumerate(_c["slots"]):
        _df = flow.indicator_defaults(_src, cfg, hz_info["threshold"], rapida_info["selected"])
        _v = flow.nice(flow.value(st["summary"], _src)) if _src and not _src.startswith("manual:") else None
        _slots.append(mo.ui.dictionary({
            "label": mo.ui.text(value=_df["label"], max_length=flow.L("indicators[].label"),
                                label=f"{_i + 1} · label" + (f" ({_v:,})" if _v is not None else "")),
            "unit": mo.ui.text(value=_df["unit"], max_length=flow.L("indicators[].unit"), label="unit"),
            "before": mo.ui.checkbox(value=_df["before"], label="unit before"),
            "compact": mo.ui.checkbox(value=_df["compact"], label="short (1.2M)"),
            "manual": mo.ui.text(value="", placeholder="value" if (_src or "").startswith("manual:") else "—",
                                 label="manual value"),
        }))
    _bars = mo.ui.array([mo.ui.text(value=i18n_label, max_length=flow.L("population_groups.items[].label"),
                                    label=f"Bar {i + 1} label")
                         for i, i18n_label in enumerate(
            [flow.i18n.t(cfg["lang"], "groups").get(b, b or "")[:10] for b in _c["bars"]])])
    content_text = mo.ui.dictionary({"t": mo.ui.dictionary(_texts), "km": _km, "slots": mo.ui.array(_slots),
                                     "bars": _bars})
    _T = content_text["t"]
    _ind_rows = [mo.hstack([s["label"], s["unit"], s["before"], s["compact"], s["manual"]], justify="start", wrap=True)
                 for s, src in ((content_text["slots"][i], src) for i, src in enumerate(_c["slots"])) if src]
    mo.accordion({
        "Header and key figure": mo.vstack([_T[k] for k in ("org_line", "title", "location", "date_line", "kf_h",
                                                           "kf_label", "kf_note")]),
        "Key messages and narrative": mo.vstack([_T["km_h"]] + [mo.hstack([k["icon"], k["text"]], widths=[0.2, 1])
                                                               for k in (content_text["km"][i] for i in range(3))]
                                               + [_T["narrative"]]),
        "Indicators (economic damage and IDPs are manual values)": mo.vstack(_ind_rows or [mo.md("No indicator chosen.")]),
        "Bars and poverty card": mo.vstack([_T["grp_title"], _T["grp_note"]] +
                                           ([content_text["bars"][i] for i, src in enumerate(_c["bars"]) if src]
                                            if _c["bar_mode"] == "comp" else []) +
                                           [_T["vul_pct"], _T["vul_title"], _T["vul_caption"]]),
        "Map texts and footer": mo.vstack([_T[k] for k in ("chip", "map_alt", "loc_alt", "disclaimer", "methodology",
                                                           "email", "web_label", "web_url")]),
    }, multiple=True)
    return (content_text,)


@app.cell(hide_code=True)
def _(card, cfg, content_choice, content_text, flow, hz_info, mo, problems, st):
    _c, _v = content_choice.value, content_text.value
    _slots = [dict(src=src, **vals) for src, vals in zip(_c["slots"], _v["slots"])]
    _bars = [dict(src=src, label=lab) for src, lab in zip(_c["bars"], _v["bars"])]
    _mmi = flow.mmi_bar_items(st["ps"], hz_info["threshold"], _c["head"]) if _c["bar_mode"] == "mmi" else []
    content, content_errors = flow.collect_content(cfg, st, _c["head"], _slots, _c["bar_mode"], _bars, _mmi,
                                                   dict(_v["t"], km=_v["km"]), _c["show_empty"])
    problems(content_errors) if content_errors else card("Content complete – all texts within their limits.")
    return content, content_errors


@app.cell(hide_code=True)
def _(content, mo):
    _ = content
    gen_opts = mo.ui.dictionary({"pdf": mo.ui.checkbox(value=True, label="PDF (A4)"),
                                 "png": mo.ui.checkbox(value=True, label="PNG")})
    mo.vstack([mo.md("## 9 · One-pager"), mo.hstack([gen_opts["pdf"], gen_opts["png"]], justify="start")])
    return (gen_opts,)


@app.cell(hide_code=True)
def _(content, mo):
    _ = content
    gen_btn = mo.ui.run_button(label="Build the one-pager", kind="success")
    gen_btn
    return (gen_btn,)


@app.cell(hide_code=True)
def _(
    cfg,
    content,
    content_errors,
    flow,
    gen_btn,
    gen_opts,
    hz_info,
    mapinfo,
    meta,
    mo,
    problems,
    st,
    waiting,
    want_gdb,
):
    mo.stop(bool(content_errors), problems(["Fix the content in step 8 first."]))
    mo.stop(not gen_btn.value, waiting("Press **Build the one-pager**. It is rendered headless and only accepted "
                                       "when the page reports nothing cut off and the data valid."))
    with mo.status.spinner(title="Building and checking the one-pager …"):
        result = flow.generate(cfg, hz_info, st, meta, content, mapinfo, also_gdb=want_gdb.value,
                               pdf=gen_opts.value["pdf"], png_=gen_opts.value["png"])
    _files = result["files"]
    _dl = [mo.download(data=p.read_bytes(), filename=p.name, label=lab)
           for lab, p in _files.items() if p.is_file()]
    if _files:
        _dl.insert(0, mo.download(data=flow.zip_outputs(_files, cfg["run_name"]), filename=f"{cfg['run_name']}.zip",
                                  label="Everything (.zip)"))
    _png = _files.get("One-pager (PNG)")
    _head = (mo.callout(mo.md("**The one-pager passed the check.** Download it below."), kind="success")
             if result["status"] == "ok" else
             mo.callout(mo.md("\n".join(f"- {e}" for e in result["errors"])),
                        kind="warn" if result["ok"] else "danger"))
    _html = _files.get("One-pager (HTML)")
    mo.vstack([_head, mo.hstack(_dl, wrap=True, justify="start")] +
              ([mo.image(_png, width=640)] if _png else []) +
              ([mo.accordion({"Open the HTML page here": mo.iframe(_html.read_text(encoding="utf-8"), height="900px")})]
               if _html else []) +
              [mo.md(f"Also saved on the server in `{cfg['out_dir']}`.")])
    return (result,)


if __name__ == "__main__":
    app.run()
