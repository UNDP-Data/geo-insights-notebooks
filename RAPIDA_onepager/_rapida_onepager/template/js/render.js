/* RAPIDA one-pager – renders a validated data feed into the poster.
   Public API:  Rapida.render(data)  ->  { errors: [...] }
   Feed source: ?feed=<url to JSON>, otherwise the inline <script id="rapida-data">. */
(function () {
  "use strict";
  var S = window.RapidaSchema, SVGNS = "http://www.w3.org/2000/svg";
  var THEMES = ["approved", "clean"];
  var $ = function (sel) { return document.querySelector(sel); };

  // Number formats follow the feed language (lang: en | fr | es): 9,053 / 9 053 / 9.053
  var LOCALES = { en: "en-US", fr: "fr-FR", es: "es-ES" };
  var nf0, nf1, nfc;
  function makeFormat(locale, opts) {
    try { return new Intl.NumberFormat(locale, Object.assign({ useGrouping: "always" }, opts)); }
    catch (e) { return new Intl.NumberFormat(locale, opts); }        // older browsers: no "always"
  }
  function setLocale(lang) {
    var loc = LOCALES[lang] || "en-US";
    nf0 = makeFormat(loc, { maximumFractionDigits: 0 });
    nf1 = makeFormat(loc, { maximumFractionDigits: 1 });
    nfc = makeFormat(loc, { notation: "compact", maximumFractionDigits: 1 });
  }
  setLocale("en");
  function num(v) { return v == null ? null : (Math.abs(v) < 10 && v % 1 ? nf1 : nf0).format(v); }
  function compact(v) { return v == null ? null : Math.abs(v) < 1000 ? nf0.format(v) : nfc.format(v); }
  // Hard stop so an over-limit field can never break the layout; validation reports it.
  function clip(text, path) {
    var max = S.LIMITS[path.replace(/\[\d+\]/g, "[]")], chars = Array.from(String(text == null ? "" : text));
    return max && chars.length > max ? chars.slice(0, max - 1).join("") + "…" : chars.join("");
  }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  function svgEl(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    return n;
  }
  function icon(name) {
    var s = svgEl("svg", { "aria-hidden": "true" }), u = svgEl("use", { href: "#ic-" + name });
    s.appendChild(u); return s;
  }
  function setText(sel, text, path) { var n = $(sel); if (n) n.textContent = clip(text, path); }

  /* ---- Map: always an inline <svg> with an explicit viewBox and preserveAspectRatio ---- */
  // Only plain drawing elements and attributes survive. No style, script, links,
  // animation or HTML; references may point only inside the map itself.
  var SVG_TAGS = ["svg", "g", "path", "polygon", "polyline", "line", "rect", "circle", "ellipse",
    "text", "tspan", "defs", "clipPath", "mask", "linearGradient", "radialGradient", "stop",
    "pattern", "symbol", "use", "title", "desc"];
  var SVG_ATTRS = /^(id|class|d|points|x|y|x1|y1|x2|y2|cx|cy|r|rx|ry|width|height|viewBox|preserveAspectRatio|transform|fill|fill-opacity|fill-rule|stroke|stroke-width|stroke-opacity|stroke-linecap|stroke-linejoin|stroke-dasharray|opacity|clip-path|clip-rule|mask|offset|stop-color|stop-opacity|gradientUnits|gradientTransform|patternUnits|patternTransform|font-size|font-family|font-weight|text-anchor|dominant-baseline|letter-spacing|href|xlink:href)$/;

  function safeInlineSvg(markup) {
    var doc = new DOMParser().parseFromString(markup, "image/svg+xml"), root = doc.documentElement;
    if (!root || root.namespaceURI !== SVGNS || root.localName !== "svg" || doc.querySelector("parsererror")) return null;
    (function clean(n) {
      Array.from(n.children).forEach(function (c) {
        if (c.namespaceURI !== SVGNS || SVG_TAGS.indexOf(c.localName) < 0) c.remove(); else clean(c);
      });
      Array.from(n.attributes).forEach(function (a) {
        var keep = /href$/.test(a.name) ? /^#[\w-]+$/.test(a.value)               // internal refs only
                 : SVG_ATTRS.test(a.name) && !/url\(\s*['"]?(?!#)/i.test(a.value);  // no external url()
        if (!keep) n.removeAttribute(a.name);
      });
    })(root);
    // Prefix ids so the map's ids cannot clash with the page's own (#ic-people, …).
    root.querySelectorAll("[id]").forEach(function (n) { n.id = "m-" + n.id; });
    root.querySelectorAll("*").forEach(function (n) {
      Array.from(n.attributes).forEach(function (a) {
        if (/href$/.test(a.name)) a.value = "#m-" + a.value.slice(1);
        else if (/url\(#/.test(a.value)) a.value = a.value.replace(/url\(#/g, "url(#m-");
      });
    });
    return document.importNode(root, true);
  }
  function buildMap(m) {
    var svg, vb = m.viewBox;
    if (m.svg) {
      svg = safeInlineSvg(m.svg);
      if (!svg) return null;
      if (!vb && svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width)
        vb = [svg.viewBox.baseVal.x, svg.viewBox.baseVal.y, svg.viewBox.baseVal.width, svg.viewBox.baseVal.height];
      svg.removeAttribute("width"); svg.removeAttribute("height");
    } else {
      svg = svgEl("svg");
      svg.appendChild(svgEl("image", { href: m.src, x: 0, y: 0, width: m.width, height: m.height, preserveAspectRatio: "none" }));
    }
    if (!vb) return null;
    var par = m.preserveAspectRatio || "xMidYMid slice";
    svg.setAttribute("viewBox", vb.join(" "));
    svg.setAttribute("preserveAspectRatio", par);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", clip(m.alt, "map.alt"));

    // poster units per map unit, following the same rule the browser applies
    // the map window size belongs to the theme, so read it from the stylesheet
    $(".poster").classList.toggle("map-framed", m.frame !== "bleed");
    var cs = getComputedStyle($(".poster")), boxW = parseFloat(cs.getPropertyValue("--map-w")) || 974, boxH = parseFloat(cs.getPropertyValue("--map-h")) || 728;
    var sx = boxW / vb[2], sy = boxH / vb[3];
    var scale = par === "none" ? sx : /slice/.test(par) ? Math.max(sx, sy) : Math.min(sx, sy);

    (m.labels || []).forEach(function (l, i) {
      var country = l.level === "country";
      var t = svgEl("text", {
        x: l.x, y: l.y, "text-anchor": "middle", "dominant-baseline": "middle",
        "font-size": (country ? 46 : 18) / scale, "font-weight": country ? 800 : 700,
        "letter-spacing": (country ? 8 : 4) / scale, fill: country ? "#cecece" : "#a9bdc9",
        "font-family": getComputedStyle(document.documentElement).getPropertyValue("--font")
      });
      t.textContent = clip(l.text, "map.labels[" + i + "].text");
      svg.appendChild(t);
    });
    return { svg: svg, scale: scale };
  }
  function buildScale(box, unitsPerKm, scale) {
    box.textContent = "";
    if (!unitsPerKm) { box.hidden = true; return; }
    box.hidden = false;
    var nice = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000], MAXW = 140;
    function pick(perUnit) { var best = nice[0]; nice.forEach(function (n) { if (n * perUnit <= MAXW) best = n; }); return best; }
    var perKm = unitsPerKm * scale, km = pick(perKm), mi = pick(perKm * 1.609344);
    [[mi, "mi", mi * perKm * 1.609344], [km, "km", km * perKm]].forEach(function (r) {
      var d = el("div"), bar = el("b");
      d.appendChild(document.createTextNode(nf0.format(r[0]) + " " + r[1]));
      bar.style.width = "calc(var(--u) * " + r[2].toFixed(1) + ")";
      d.appendChild(bar); box.appendChild(d);
    });
  }

  function render(data) {
    var errors = S.validate(data), d = data || {};
    var theme = new URLSearchParams(location.search).get("theme") || d.theme;   // the URL wins over the feed
    document.documentElement.setAttribute("data-theme", THEMES.indexOf(theme) < 0 ? "approved" : theme);
    var lang = ["en", "fr", "es"].indexOf(d.lang) < 0 ? "en" : d.lang;
    setLocale(lang);
    document.documentElement.setAttribute("lang", lang);
    var L = Object.assign({ methodology: "Methodology", more_info: "For More Information", email: "E-mail:",
      website: "Website:", no_data: "No data", date: "Date" }, d.labels || {});
    var meta = d.meta || {}, kf = d.key_figure || {}, m = d.map || {}, hd = d.headings || {},
        vul = d.vulnerable || {}, grp = d.population_groups || {}, c = d.contact || {};

    setText(".hd-org", meta.org_line, "meta.org_line");
    setText(".hd-title", meta.title, "meta.title");
    setText(".hd-loc", meta.location, "meta.location");
    setText(".hd-date", meta.date_line, "meta.date_line");
    $(".hd-date").setAttribute("data-label", L.date);
    setText(".ft-meth-h", L.methodology, "labels.methodology");
    setText(".ft-more", L.more_info, "labels.more_info");
    setText(".ft-email-l", L.email, "labels.email");
    setText(".ft-web-l", L.website, "labels.website");
    document.title = [meta.title, meta.location].filter(Boolean).join(" – ") || "RAPIDA one-pager";

    setText(".kf-h", hd.key_figures || "Key figures", "headings.key_figures");
    setText(".km-h", hd.key_messages || "Key messages", "headings.key_messages");
    setText(".kf-lab", kf.label, "key_figure.label");
    var people = num(kf.value) || "—";
    $(".kf-num").textContent = people;
    $(".kf-num").classList.toggle("long", people.length > 7);
    setText(".kf-note", kf.note, "key_figure.note");

    var km = $(".km"); km.textContent = "";
    (d.key_messages || []).slice(0, 3).forEach(function (msg, i) {
      var li = el("li");
      li.appendChild(icon(["flood", "alert", "analysis"].indexOf(msg.icon) < 0 ? "alert" : msg.icon));
      li.appendChild(el("p", { "data-fit": "key_messages[" + i + "].text" }, clip(msg.text, "key_messages[" + i + "].text")));
      km.appendChild(li);
    });

    var art = $(".map-art"), built = (m.src || m.svg) ? buildMap(m) : null;
    art.textContent = "";
    if (built) art.appendChild(built.svg);
    else if (!errors.some(function (e) { return e.path.indexOf("map") === 0; })) errors.push({ path: "map", message: "Map could not be drawn" });
    setText(".map-chip", m.title_chip, "map.title_chip");
    buildScale($(".map-scale"), built && m.units_per_km, built ? built.scale : 1);
    var lg = $(".map-legend"); lg.textContent = "";
    // Intensity ramp (earthquakes): a row of class swatches with their labels underneath.
    var ramp = m.legend_ramp;
    if (ramp && Array.isArray(ramp.items) && ramp.items.length) {
      var rli = el("li", { class: "ramp" }), row = el("span", { class: "ramp-row" });
      rli.appendChild(el("span", { class: "ramp-title" }, clip(ramp.title || "", "map.legend_ramp.title")));
      ramp.items.slice(0, 9).forEach(function (it, i) {
        var cell = el("span", { class: "ramp-cell" }), sw = el("i");
        if (/^#[0-9a-fA-F]{6}$/.test(it.color)) sw.style.background = it.color;
        cell.appendChild(sw); cell.appendChild(el("span", null, clip(it.label, "map.legend_ramp.items[" + i + "].label")));
        row.appendChild(cell);
      });
      rli.appendChild(row); lg.appendChild(rli);
    }
    (m.legend || []).slice(0, 3).forEach(function (it, i) {
      var li = el("li"), shape = ["dot", "square", "outline", "star", "line"].indexOf(it.shape) < 0 ? "dot" : it.shape;
      var dot = el("i", { class: shape });
      if (/^#[0-9a-fA-F]{6}$/.test(it.color)) { dot.style.background = it.color; dot.style.borderColor = it.color; }
      li.appendChild(dot); li.appendChild(document.createTextNode(clip(it.label, "map.legend[" + i + "].label")));
      lg.appendChild(li);
    });
    var mapBox = $(".map"), pos = ["tl", "tr", "bl", "br"].indexOf(m.inset_position) < 0 ? "br" : m.inset_position;
    ["tl", "tr", "bl", "br"].forEach(function (p) { mapBox.classList.toggle("pos-" + p, p === pos); });
    mapBox.classList.toggle("inset-landscape", m.inset_shape === "landscape");
    $(".poster").classList.toggle("map-framed", m.frame !== "bleed");
    var inset = $(".map-inset"), loc = m.locator || {};
    inset.hidden = !loc.src; inset.textContent = "";
    if (loc.src) inset.appendChild(el("img", { src: loc.src, alt: clip(loc.alt || "", "map.locator.alt") }));

    // Indicator band: up to six slots filled in feed order; unused slots stay empty.
    var dl = $(".ind"); dl.textContent = "";
    var inds = (Array.isArray(d.indicators) ? d.indicators : []).slice(0, 6).map(function (it, i) { return [it, i]; });
    if (!d.indicators_show_empty) inds = inds.filter(function (p) { return p[0] && p[0].value != null; });
    dl.setAttribute("data-count", String(inds.length));
    inds.forEach(function (p) {
      var it = p[0], i = p[1];
      var wrap = el("div"), dd = el("dd", { "data-fit": "indicators[" + i + "].value" });
      var unit = clip(it.unit || "", "indicators[" + i + "].unit"), text = num(it.value);
      // Long figures switch to compact form (12.4M) so they always fit their slot.
      if (text != null && (it.format === "compact" || text.length + unit.length > 12)) text = compact(it.value);
      wrap.appendChild(el("dt", { "data-fit": "indicators[" + i + "].label" }, clip(it.label, "indicators[" + i + "].label")));
      if (text == null) dd.appendChild(el("span", { class: "na", title: L.no_data, "data-label": L.no_data }, "—"));
      else {
        if (unit && it.unit_position === "before") dd.appendChild(document.createTextNode(unit + " "));
        dd.appendChild(el("b", null, text));
        if (unit && it.unit_position !== "before") dd.appendChild(document.createTextNode(" " + unit));
      }
      wrap.appendChild(dd); dl.appendChild(wrap);
    });
    setText(".narr", d.narrative, "narrative");

    var hasVul = d.vulnerable && d.vulnerable.pct != null;
    $(".poster").classList.toggle("no-vul", !hasVul);
    setText(".vul h3", vul.title, "vulnerable.title");
    $(".vul-pct").textContent = vul.pct == null ? "—" : num(Math.min(100, Math.max(0, vul.pct)));
    if (vul.pct != null) $(".vul-pct").appendChild(el("sup", null, "%"));
    setText(".vul-cap", vul.caption, "vulnerable.caption");

    setText(".grp h3", grp.title, "population_groups.title");
    var bars = $(".bars"), items = (grp.items || []).slice(0, 4); bars.textContent = "";
    items.forEach(function (it, i) {
      var row = el("div"), track = el("div", { class: "track" }), bar = el("div", { class: "bar" });
      var pct = Math.min(100, Math.max(0, +it.pct || 0));
      bar.style.width = (pct * 0.92).toFixed(2) + "%";   // scaled to 100%; 8% of the track is kept for the value
      row.appendChild(el("span", null, clip(it.label, "population_groups.items[" + i + "].label")));
      track.appendChild(bar); track.appendChild(el("em", null, num(pct)));
      row.appendChild(track); bars.appendChild(row);
    });
    setText(".grp-note", grp.note, "population_groups.note");

    setText(".disc p", d.disclaimer, "disclaimer");
    setText(".ft-meth span", d.methodology, "methodology");
    var mail = $(".ft-mail"), web = $(".ft-web");
    mail.textContent = clip(c.email, "contact.email");
    mail.setAttribute("href", /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c.email || "") ? "mailto:" + c.email : "#");
    web.textContent = clip(c.website_label, "contact.website_label");
    web.setAttribute("href", /^https:\/\//.test(c.website_url || "") ? c.website_url : "#");

    // Shown at once; the status stays "pending" until fonts and feed images have
    // loaded and the overflow check has run.
    report(errors);
    var images = [[".map-art image", "map.src"], [".map-inset img", "map.locator.src"]].map(function (s) {
      var n = $(s[0]);
      return n ? loaded(n).then(function (ok) { return ok ? null : { path: s[1], message: "Image could not be loaded" }; }) : null;
    });
    Promise.all([document.fonts ? document.fonts.ready : null].concat(images)).then(function (r) {
      // No requestAnimationFrame: it never fires in a hidden tab. Reading scroll sizes forces layout anyway.
      report(errors.concat(r.slice(1).filter(Boolean), findOverflow()), true);
    });
    return { errors: errors };
  }
  function loaded(n) {
    return new Promise(function (ok) {
      if (n.complete) return ok(n.naturalWidth > 0);   // <img> already settled; SVG <image> has no .complete
      n.addEventListener("load", function () { ok(true); }, { once: true });
      n.addEventListener("error", function () { ok(false); }, { once: true });
    });
  }

  // Safety net behind the character limits: flags any text box whose content is cut off.
  function findOverflow() {
    var out = [];
    document.querySelectorAll(".poster [data-fit]").forEach(function (n) {
      if (n.clientWidth <= 2) return;                 // visually hidden in this theme
      // single-line boxes can only overflow sideways; tall glyphs there are not a real overflow
      var oneLine = getComputedStyle(n).whiteSpace === "nowrap";
      if ((!oneLine && n.scrollHeight > n.clientHeight + 1) || n.scrollWidth > n.clientWidth + 1)
        out.push({ path: n.getAttribute("data-fit"), message: "Text does not fit its box and is cut off" });
    });
    return out;
  }
  function report(errors, final) {
    var box = $(".report"), list = box.querySelector("ul");
    document.documentElement.setAttribute("data-rapida-status", !final ? "pending" : errors.length ? "invalid" : "ok");
    box.hidden = !errors.length; list.textContent = "";
    errors.forEach(function (e) {
      var li = el("li"); li.appendChild(el("code", null, e.path || "feed"));
      li.appendChild(document.createTextNode(" " + e.message)); list.appendChild(li);
      if (window.console) console.warn("[RAPIDA] " + e.path + ": " + e.message);
    });
  }

  // Feeds are accepted only from the page's own site plus the origins listed in
  // <meta name="rapida-feed-origins">, so nobody can put their own figures under UNDP branding.
  var originsMeta = document.querySelector('meta[name="rapida-feed-origins"]');
  var FEED_ORIGINS = [location.origin].concat((originsMeta ? originsMeta.content : "").split(/\s+/).filter(Boolean));

  function start() {
    var url = new URLSearchParams(location.search).get("feed");
    if (!url) return render(JSON.parse($("#rapida-data").textContent));
    var abs = null;
    try { abs = new URL(url, location.href); } catch (e) {}
    if (!abs || FEED_ORIGINS.indexOf(abs.origin) < 0)
      return report([{ path: "feed", message: "Feed address is not on the approved list" }], true);
    fetch(abs.href, { headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(render)
      .catch(function (e) { report([{ path: "feed", message: "Could not load " + abs.href + " (" + e.message + ")" }], true); });
  }

  window.Rapida = { render: render, findOverflow: findOverflow };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
