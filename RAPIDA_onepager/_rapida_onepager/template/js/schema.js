/* RAPIDA one-pager – feed contract and validation.
   Single source of truth for field types and character limits.
   Works in the browser (window.RapidaSchema) and in Node (require). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RapidaSchema = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // t: s=string, n=number, b=boolean, a=array, o=object. max = character limit (strings),
  // items = max array length. "[]" in a path means "every item of the array".
  var RULES = [
    { p: "theme", t: "s", oneOf: ["approved", "clean"] },
    { p: "lang", t: "s", oneOf: ["en", "fr", "es"] },
    { p: "indicators_show_empty", t: "b" },

    // Fixed page texts, translated by the app
    { p: "labels.methodology", t: "s", max: 20 },
    { p: "labels.more_info", t: "s", max: 30 },
    { p: "labels.email", t: "s", max: 12 },
    { p: "labels.website", t: "s", max: 12 },
    { p: "labels.no_data", t: "s", max: 14 },
    { p: "labels.date", t: "s", max: 10 },

    { p: "meta.org_line", t: "s", req: 1, max: 64 },
    { p: "meta.title", t: "s", req: 1, max: 34 },
    { p: "meta.location", t: "s", req: 1, max: 42 },
    { p: "meta.date_line", t: "s", req: 1, max: 48 },

    { p: "headings.key_figures", t: "s", max: 18 },
    { p: "headings.key_messages", t: "s", max: 18 },

    { p: "key_figure.label", t: "s", req: 1, max: 18 },
    { p: "key_figure.value", t: "n", req: 1, min: 0, maxv: 999999999 },
    { p: "key_figure.note", t: "s", max: 62 },

    { p: "key_messages", t: "a", req: 1, minItems: 1, items: 3 },
    { p: "key_messages[].icon", t: "s", req: 1, oneOf: ["flood", "alert", "analysis"] },
    { p: "key_messages[].text", t: "s", req: 1, max: 165 },

    { p: "map.src", t: "s", max: 2048 },
    { p: "map.svg", t: "s" },
    { p: "map.width", t: "n", min: 1 },
    { p: "map.height", t: "n", min: 1 },
    { p: "map.viewBox", t: "a", minItems: 4, items: 4 },
    { p: "map.preserveAspectRatio", t: "s", req: 1, pattern: /^(none|x(Min|Mid|Max)Y(Min|Mid|Max)( (meet|slice))?)$/ },
    { p: "map.alt", t: "s", req: 1, max: 140 },
    { p: "map.title_chip", t: "s", req: 1, max: 30 },
    { p: "map.units_per_km", t: "n", min: 0 },
    { p: "map.legend", t: "a", items: 3 },
    { p: "map.legend[].label", t: "s", req: 1, max: 20 },
    { p: "map.legend[].color", t: "s", req: 1, pattern: /^#[0-9a-fA-F]{6}$/ },
    { p: "map.legend[].shape", t: "s", oneOf: ["dot", "square", "outline", "star", "line"] },
    { p: "map.legend_ramp.title", t: "s", max: 24 },
    { p: "map.legend_ramp.items", t: "a", items: 9 },
    { p: "map.legend_ramp.items[].label", t: "s", req: 1, max: 5 },
    { p: "map.legend_ramp.items[].color", t: "s", req: 1, pattern: /^#[0-9a-fA-F]{6}$/ },
    { p: "map.inset_position", t: "s", oneOf: ["tl", "tr", "bl", "br"] },
    { p: "map.inset_shape", t: "s", oneOf: ["portrait", "landscape"] },
    { p: "map.frame", t: "s", oneOf: ["framed", "bleed"] },
    { p: "map.labels", t: "a", items: 8 },
    { p: "map.labels[].text", t: "s", req: 1, max: 24 },
    { p: "map.labels[].x", t: "n", req: 1 },
    { p: "map.labels[].y", t: "n", req: 1 },
    { p: "map.labels[].level", t: "s", oneOf: ["country", "place"] },
    { p: "map.locator.src", t: "s", max: 2048 },
    { p: "map.locator.alt", t: "s", max: 140 },

    // One to six indicators, shown in feed order. A null value renders as "—".
    { p: "indicators", t: "a", req: 1, minItems: 1, items: 6 },
    { p: "indicators[].label", t: "s", req: 1, max: 28 },
    { p: "indicators[].value", t: "n", nullable: 1, min: 0, maxv: 999e12 },
    { p: "indicators[].unit", t: "s", max: 5 },
    { p: "indicators[].unit_position", t: "s", oneOf: ["before", "after"] },
    { p: "indicators[].format", t: "s", oneOf: ["number", "compact"] },

    { p: "narrative", t: "s", req: 1, max: 470 },

    // Optional card: leave "vulnerable" out (or pct null) and the card is hidden.
    { p: "vulnerable.title", t: "s", max: 40 },
    { p: "vulnerable.pct", t: "n", nullable: 1, min: 0, maxv: 100 },
    { p: "vulnerable.caption", t: "s", max: 75 },

    { p: "population_groups.title", t: "s", req: 1, max: 44 },
    { p: "population_groups.items", t: "a", req: 1, minItems: 1, items: 4 },
    { p: "population_groups.items[].label", t: "s", req: 1, max: 10 },
    { p: "population_groups.items[].pct", t: "n", req: 1, min: 0, maxv: 100 },
    { p: "population_groups.note", t: "s", max: 100 },

    { p: "disclaimer", t: "s", max: 210 },
    { p: "methodology", t: "s", max: 760 },

    { p: "contact.email", t: "s", req: 1, max: 40, pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/ },
    { p: "contact.website_label", t: "s", req: 1, max: 24 },
    { p: "contact.website_url", t: "s", req: 1, max: 2048, pattern: /^https:\/\// }
  ];

  var LIMITS = {};
  RULES.forEach(function (r) { if (r.max) LIMITS[r.p] = r.max; });

  // Unicode-aware length, so "é" counts as one character.
  function len(s) { return Array.from(String(s)).length; }

  // Expand "a.b[].c" into every concrete [path, value] pair in the data.
  function resolve(data, path) {
    var out = [["", data]];
    path.split(".").forEach(function (seg) {
      var each = seg.slice(-2) === "[]", key = each ? seg.slice(0, -2) : seg, next = [];
      out.forEach(function (pv) {
        var v = pv[1] == null ? undefined : pv[1][key], p = pv[0] ? pv[0] + "." + key : key;
        if (each) { if (Array.isArray(v)) v.forEach(function (it, i) { next.push([p + "[" + i + "]", it]); }); }
        else next.push([p, v]);
      });
      out = next;
    });
    return out;
  }

  function validate(data) {
    var errors = [];
    function err(path, msg) { errors.push({ path: path, message: msg }); }
    if (!data || typeof data !== "object") return [{ path: "", message: "Feed is not a JSON object" }];

    RULES.forEach(function (r) {
      resolve(data, r.p).forEach(function (pv) {
        var path = pv[0], v = pv[1];
        if (v === undefined || v === null || v === "") {
          if (v === null && r.nullable) return;
          if (r.req) err(path, "Required field is missing");
          return;
        }
        if (r.t === "s") {
          if (typeof v !== "string") return err(path, "Must be text");
          if (r.max && len(v) > r.max) err(path, "Too long: " + len(v) + " characters, limit is " + r.max);
          if (r.oneOf && r.oneOf.indexOf(v) < 0) err(path, "Must be one of: " + r.oneOf.join(", "));
          if (r.pattern && !r.pattern.test(v)) err(path, "Wrong format");
        } else if (r.t === "n") {
          if (typeof v !== "number" || !isFinite(v)) return err(path, "Must be a number");
          if (r.min != null && v < r.min) err(path, "Must be at least " + r.min);
          if (r.maxv != null && v > r.maxv) err(path, "Must be at most " + r.maxv);
        } else if (r.t === "b") {
          if (typeof v !== "boolean") err(path, "Must be true or false");
        } else if (r.t === "a") {
          if (!Array.isArray(v)) return err(path, "Must be a list");
          if (r.minItems && v.length < r.minItems) err(path, "Needs at least " + r.minItems + " item(s)");
          if (r.items && v.length > r.items) err(path, "Too many items: " + v.length + ", limit is " + r.items);
        }
      });
    });

    var vu = data.vulnerable;
    if (vu && vu.pct != null && !vu.title) err("vulnerable.title", "Required when vulnerable.pct is given");

    // Map rules that span several fields.
    var m = data.map || {};
    if (!m.src && !m.svg) err("map", "Provide either map.src (image URL) or map.svg (inline SVG markup)");
    if (m.src && !m.svg) {
      if (!Array.isArray(m.viewBox)) err("map.viewBox", "Required when map.src is used");
      if (!m.width || !m.height) err("map.width", "map.width and map.height (image pixel size) are required when map.src is used");
    }
    if (Array.isArray(m.viewBox) && (m.viewBox.some(function (n) { return typeof n !== "number" || !isFinite(n); }) || m.viewBox[2] <= 0 || m.viewBox[3] <= 0))
      err("map.viewBox", "Must be four numbers [x, y, width, height] with positive width and height");
    if (m.svg && !Array.isArray(m.viewBox) && !/<svg[^>]*\sviewBox\s*=/i.test(m.svg))
      err("map.svg", "Inline SVG has no viewBox; add one or supply map.viewBox");

    return errors;
  }

  return { RULES: RULES, LIMITS: LIMITS, validate: validate, length: len };
});
