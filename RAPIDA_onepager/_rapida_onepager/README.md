# RAPIDA one-pager – helper package

Code behind the marimo notebook `RAPIDA_onepager/rapida_onepager.py`. The folder name starts with `_` so it is a
helper module, not a notebook.

| Module | Role |
|---|---|
| `flow.py` | One function per notebook step; no UI code, so steps can also be run from a script |
| `hazard.py` | GDACS API and files → hazard polygons (earthquake bands grouped into whole MMI classes, epicentre kept, 100 km circle dropped) |
| `admin.py` | OCHA COD-AB from HDX, or a file / folder / File GDB |
| `split.py` | Admin units cut by the hazard; checks; RAPIDA input |
| `rapida_runner.py` | `rapida create` / `assess` in a child process; project status |
| `stats.py` | Merge `stats.*` layers on `part_key`; per-unit exposed / total / %; results GeoPackage |
| `maps.py` | Map JPG + locator PNG for the poster's map window |
| `poster.py` | Feed, validation, self-contained HTML, headless check, PDF/PNG |
| `i18n.py` | English / French / Spanish texts |
| `template/` | The one-pager page (HTML, CSS, JS, feed schema, UNDP logo) |
| `data/` | Natural Earth 1:50m countries (public domain, simplified to ~1 km, 1 MB) and country names in en/fr/es |

## Python packages the server needs

The notebook checks them when it opens and lists any that are missing. With pixi (conda-forge):

```
pixi add geopandas pyogrio pyproj shapely matplotlib pillow jsonschema requests pyarrow
pixi add gdal rasterio                                                  # gdal: needed by rapida; rasterio: optional
pixi add --pypi playwright "rapida @ git+https://github.com/UNDP-Data/rapida.git"
pixi run playwright install chromium                                    # headless check, PDF and PNG
```

RAPIDA is not on PyPI or conda-forge, so it is installed from GitHub. Without playwright/Chromium the HTML is
still produced, without the headless check, PDF and PNG.

## No RAPIDA sign-in needed

`rapida create` and `rapida assess` read public data (GeoHub, WorldPop), so no UNDP sign-in is needed. The notebook
runs `rapida init --no-input` by itself the first time, which writes `~/.rapida/config.json`. A sign-in
(`rapida auth`) is only needed for RAPIDA's upload / publish to UNDP Azure, which this notebook does not use.

## Running RAPIDA

`create` and `assess` run in a separate Python process (RAPIDA's `nest_asyncio` / `asyncio.run` would otherwise
nest in the kernel's event loop). Each split gets its own project, named `<run>_<fingerprint>`: changing the
threshold, the crisis polygons or the admin layer creates a new project; an unchanged split reuses its results.
Before merging, the project is checked against the current split, so a project made from another split is refused.

## Outputs

`<output folder>/<run>/`: `<run>_onepager.html|pdf|png`, `<run>_rapida_results.gpkg` (`crisis_polygons`,
`crisis_epicentre`, `split_polygons`, `admin_stats`, `summary`, `run_metadata`), optional `.gdb`, map and locator
images, `<run>_feed.json`, and `rapida_project/`. Step 9 offers each file, and a zip of all, as downloads.
