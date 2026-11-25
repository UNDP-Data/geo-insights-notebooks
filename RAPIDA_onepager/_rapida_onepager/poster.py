"""Build the feed, check it, assemble one self-contained HTML file, render it headless (PDF/PNG)."""
import base64
import html
import json
import mimetypes
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from .config import TEMPLATE_DIR, SCHEMA_PATH, LIMITS


def build_feed(c, mapinfo):
    """c: content dict collected by the app (see ui.PosterStep)."""
    feed = {
        "lang": c["lang"], "theme": c["theme"], "labels": c["labels"],
        "indicators_show_empty": bool(c.get("show_empty")),
        "meta": dict(org_line=c["org_line"], title=c["title"], location=c["location"], date_line=c["date_line"]),
        "headings": c["headings"],
        "key_figure": dict(label=c["kf_label"], value=c["kf_value"], note=c.get("kf_note") or ""),
        "key_messages": [dict(icon=i, text=t) for i, t in c["key_messages"] if t.strip()],
        "map": dict(src=mapinfo["map_path"].name, width=mapinfo["width"], height=mapinfo["height"],
                    viewBox=mapinfo["viewBox"], preserveAspectRatio="xMidYMid slice", alt=c["map_alt"],
                    title_chip=c["chip"], legend=mapinfo["legend"], labels=mapinfo["labels"],
                    inset_position=mapinfo["inset_position"], inset_shape=mapinfo.get("inset_shape", "portrait"), frame="bleed" if mapinfo.get("layout") == "approved_bleed" else "framed",
                    locator=dict(src=mapinfo["locator_path"].name, alt=c["locator_alt"])),
        "indicators": c["indicators"],
        "narrative": c["narrative"],
        "population_groups": c["groups"],
        "disclaimer": c["disclaimer"], "methodology": c["methodology"],
        "contact": dict(email=c["email"], website_label=c["website_label"], website_url=c["website_url"]),
    }
    if mapinfo.get("units_per_km"):
        feed["map"]["units_per_km"] = mapinfo["units_per_km"]
    if mapinfo.get("legend_ramp"):
        feed["map"]["legend_ramp"] = mapinfo["legend_ramp"]
    if c.get("vulnerable") and c["vulnerable"].get("pct") is not None:
        feed["vulnerable"] = c["vulnerable"]
    images = {mapinfo["map_path"].name: mapinfo["map_path"], mapinfo["locator_path"].name: mapinfo["locator_path"]}
    return feed, images


def validate(feed):
    """JSON-Schema errors + character limits (the same limits the page enforces)."""
    json.dumps(feed, allow_nan=False)
    errs = []
    try:
        from jsonschema import Draft202012Validator
        v = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        errs = [f"{'.'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in v.iter_errors(feed)]
    except ImportError:
        errs.append("jsonschema not installed – schema check skipped (pip install jsonschema)")
    return errs


def over_limit(path, text):
    lim = LIMITS.get(re.sub(r"\[\d+\]", "[]", path))
    return (lim is not None and len(text or "") > lim), lim


# ---- self-contained HTML ----
ASSET_SHIM = r"""
(function () {
  var a = document.getElementById("rapida-assets"), f = document.getElementById("rapida-data");
  if (!a || !f) return;
  var assets = JSON.parse(a.textContent), feed = JSON.parse(f.textContent), urls = {};
  function url(src) {
    if (!src || !assets[src]) return src;
    if (!urls[src]) {
      var m = assets[src].match(/^data:([^;]+);base64,(.*)$/), bin = atob(m[2]), buf = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      urls[src] = URL.createObjectURL(new Blob([buf], { type: m[1] }));
    }
    return urls[src];
  }
  if (feed.map) { feed.map.src = url(feed.map.src); if (feed.map.locator) feed.map.locator.src = url(feed.map.locator.src); }
  f.textContent = JSON.stringify(feed);
})();
"""


def _data_uri(p):
    mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(Path(p).read_bytes()).decode()


def _safe(t):
    return t.replace("</", "<\\/")


def _json(o):
    return json.dumps(o, ensure_ascii=False, allow_nan=False, indent=1).replace("<", "\\u003c")


def assemble_html(feed, images, logo=None):
    page = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
    page = re.sub(r'<link rel="stylesheet" href="(css/[^"]+\.css)">',
                  lambda m: f"<style>/* {m.group(1)} */\n{_safe((TEMPLATE_DIR / m.group(1)).read_text(encoding='utf-8'))}\n</style>", page)
    for js in ("schema.js", "render.js"):
        tag = f'<script src="js/{js}"></script>'
        body = _safe((TEMPLATE_DIR / "js" / js).read_text(encoding="utf-8"))
        extra = f"<script>/* asset shim */{ASSET_SHIM}</script>\n" if js == "render.js" else ""
        assert tag in page, f"{tag} missing in index.html"
        page = page.replace(tag, f"{extra}<script>/* {js} */\n{body}\n</script>")
    logo = Path(logo) if logo else TEMPLATE_DIR / "assets" / "undp-logo-white.png"
    page = re.sub(r'(<img class="hd-logo" src=")[^"]*(")', lambda m: m.group(1) + _data_uri(logo) + m.group(2), page)
    block = re.compile(r'(<script type="application/json" id="rapida-data">)(.*?)(</script>)', re.S)
    assets = {n: _data_uri(p) for n, p in images.items()}
    page = block.sub(lambda m: m.group(1) + "\n" + _json(feed) + "\n" + m.group(3) +
                     '\n<script type="application/json" id="rapida-assets">' + _json(assets) + "</script>", page, count=1)
    page = page.replace('<html lang="en"', f'<html lang="{feed.get("lang", "en")}"')
    title = " – ".join(x for x in [feed["meta"].get("title"), feed["meta"].get("location")] if x)
    return page.replace("<title>RAPIDA one-pager</title>", f"<title>{html.escape(title)}</title>")


# ---- headless render (separate process: Playwright's sync API cannot run inside Jupyter's event loop) ----
_RENDER = textwrap.dedent(r"""
    import json, sys
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    src, pdf, png = sys.argv[1], sys.argv[2] == "1", sys.argv[3] == "1"
    p = Path(src).resolve()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1200, "height": 1700}, device_scale_factor=2)
        page.goto(p.as_uri())
        page.wait_for_function("document.documentElement.dataset.rapidaStatus !== 'pending'", timeout=60000)
        status = page.evaluate("document.documentElement.dataset.rapidaStatus")
        errs = page.eval_on_selector_all(".report li", "els => els.map(e => e.textContent)")
        if png:
            page.locator(".poster").screenshot(path=str(p.with_suffix(".png")))
        if pdf:
            page.emulate_media(media="print")
            page.pdf(path=str(p.with_suffix(".pdf")), prefer_css_page_size=True, print_background=True)
        b.close()
    print(json.dumps({"status": status, "errors": errs}))
""")


def render_check(html_path, pdf=True, png=True, timeout=180):
    """-> {'status': 'ok'|'invalid', 'errors': [...]} or None when Playwright/Chromium is missing."""
    try:
        r = subprocess.run([sys.executable, "-c", _RENDER, str(html_path), "1" if pdf else "0", "1" if png else "0"],
                           capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return {"status": None, "errors": [str(e)]}
    if r.returncode != 0:
        if "No module named 'playwright'" in r.stderr or "Executable doesn't exist" in r.stderr:
            return None
        return {"status": None, "errors": [r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "render failed"]}
    return json.loads(r.stdout.strip().splitlines()[-1])


_ELEMENT = textwrap.dedent(r"""
    import sys
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    src, sel, out = sys.argv[1], sys.argv[2], sys.argv[3]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1200, "height": 1700}, device_scale_factor=1.5)
        page.goto(Path(src).resolve().as_uri())
        page.wait_for_function("document.documentElement.dataset.rapidaStatus !== 'pending'", timeout=60000)
        page.locator(sel).screenshot(path=out)
        b.close()
    print("ok")
""")


def render_element(html_path, selector, out_png, timeout=120):
    """Screenshot one element of the page (e.g. '.map'). True when done, False without Playwright/Chromium."""
    try:
        r = subprocess.run([sys.executable, "-c", _ELEMENT, str(html_path), selector, str(out_png)],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0 and Path(out_png).exists()
    except Exception:
        return False
