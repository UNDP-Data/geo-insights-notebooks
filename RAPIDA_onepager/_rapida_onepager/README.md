# RAPIDA one-pager – helper package

Code behind the marimo notebook `crisis_response/rapida_onepager.py`. The folder name starts with `_` so it is a
helper module, not a notebook.

| Module | Role |
|---|---|
| `flow.py` | One function per notebook step; no UI code, so steps can also be run from a script |
| `hazard.py` | GDACS API and files → hazard polygons (earthquake bands grouped into whole MMI classes, epicentre kept, 100 km circle dropped) |
| `admin.py` | OCHA COD-AB from HDX, or a file / folder / File GDB |
| `split.py` | Admin units cut by the hazard; checks; RAPIDA input |
| `auth.py` | RAPIDA sign-in without a terminal (see below) |
| `rapida_runner.py` | `rapida create` / `assess` in a child process; project status |
| `stats.py` | Merge `stats.*` layers on `part_key`; per-unit exposed / total / %; results GeoPackage |
| `maps.py` | Map JPG + locator PNG for the poster's map window |
| `poster.py` | Feed, validation, self-contained HTML, headless check, PDF/PNG |
| `i18n.py` | English / French / Spanish texts |
| `template/` | The one-pager page (HTML, CSS, JS, feed schema, UNDP logo) |
| `data/` | Natural Earth 1:50m countries (public domain, simplified to ~1 km, 1 MB) and country names in en/fr/es |

## Python packages the server needs

marimo, pandas, numpy, pyarrow, shapely ≥ 2, geopandas, pyogrio, pyproj, matplotlib, pillow, requests,
jsonschema, and **rapida** (which brings its own playwright for the sign-in).
Optional: rasterio (permanent-water removal for floods); Chromium for playwright (`playwright install chromium`)
for the headless poster check, PDF and PNG – without it the HTML is still produced.

## RAPIDA sign-in on a server

RAPIDA stores an encrypted token in `~/.rapida` of the OS account running the server and renews it on its own.
When there is none, step 5 shows a sign-in form: e-mail and password are passed only to RAPIDA's own login, in a
child process (through the `RAPIDA_USER` / `RAPIDA_PASSWORD` variables RAPIDA reads), and the Microsoft
Authenticator number is shown in the page. Because the token belongs to the server account, **everyone using the
same server shares one RAPIDA sign-in**.

## Running RAPIDA

`create` and `assess` run in a separate Python process (RAPIDA's `nest_asyncio` / `asyncio.run` would otherwise
nest in the kernel's event loop). Each split gets its own project, named `<run>_<fingerprint>`: changing the
threshold, the crisis polygons or the admin layer creates a new project; an unchanged split reuses its results.
Before merging, the project is checked against the current split, so a project made from another split is refused.

## Outputs

`<output folder>/<run>/`: `<run>_onepager.html|pdf|png`, `<run>_rapida_results.gpkg` (`crisis_polygons`,
`crisis_epicentre`, `split_polygons`, `admin_stats`, `summary`, `run_metadata`), optional `.gdb`, map and locator
images, `<run>_feed.json`, and `rapida_project/`. Step 9 offers each file, and a zip of all, as downloads.
