/*
 * app.js - Fills in the dashboard page using the data in data.js.
 *
 * data.js is rebuilt by build_dashboard.py after every daily run, so this
 * file never needs to change when new picks come in.
 *
 * Everything that comes from the data is inserted with textContent (never
 * as raw HTML), so a strange headline can't break or hijack the page.
 */
(function () {
  "use strict";

  var DATA = window.DASHBOARD_DATA || { picks: [], days: [], stats: {} };
  var picks = DATA.picks || [];
  var days = DATA.days || [];
  var stats = DATA.stats || {};
  var SVG_NS = "http://www.w3.org/2000/svg";

  // ---------------------------------------------------------------------------
  // Small helpers
  // ---------------------------------------------------------------------------

  /* Creates an HTML element. Strings become text (never HTML). */
  function el(tag, attrs) {
    var node = document.createElement(tag);
    setAttrs(node, attrs);
    for (var i = 2; i < arguments.length; i++) append(node, arguments[i]);
    return node;
  }

  /* Creates an SVG element (used for the charts). */
  function svg(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    setAttrs(node, attrs);
    for (var i = 2; i < arguments.length; i++) append(node, arguments[i]);
    return node;
  }

  function setAttrs(node, attrs) {
    if (!attrs) return;
    Object.keys(attrs).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "text") node.textContent = value;
      else if (key === "class") node.setAttribute("class", value);
      else node.setAttribute(key, value);
    });
  }

  function append(parent, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(parent, c); }); return; }
    parent.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  // Dates are stored as "2026-09-22". Noon UTC avoids time-zone date shifts.
  function toDate(s) { return new Date(s + "T12:00:00Z"); }
  function fmtLongDate(s) {
    return toDate(s).toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
  }
  function fmtShortDate(s) {
    return toDate(s).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  }
  function fmtTableDate(s) {
    return toDate(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  }
  function fmtUpdated(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("en-US", {
      weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
      timeZone: "America/New_York"
    }) + " ET";
  }

  function fmtPrice(v) {
    if (v === null || v === undefined) return "—";
    return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  /* +1.23% / −0.45% (uses a real minus sign, like a newspaper would). */
  function fmtPct(v, digits) {
    if (v === null || v === undefined) return "—";
    var d = digits === undefined ? 2 : digits;
    var text = Math.abs(v).toFixed(d);
    // Decide the sign after rounding, so -0.02 shown as 0.0 gets no minus.
    var sign = Number(text) === 0 ? "" : v > 0 ? "+" : "−";
    return sign + text + "%";
  }
  function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  function resultOf(p) { return p.correct === true ? "right" : p.correct === false ? "wrong" : "open"; }
  var RESULT_LABEL = { right: "Right so far", wrong: "Wrong so far", open: "Too early to tell" };

  /* A colored dot plus words, so the result never relies on color alone. */
  function resultBadge(p) {
    var r = resultOf(p);
    var glyph = r === "right" ? el("span", { class: "glyph-good", "aria-hidden": "true", text: "● " })
      : r === "wrong" ? el("span", { class: "glyph-bad", "aria-hidden": "true", text: "● " })
      : el("span", { "aria-hidden": "true", text: "○ " });
    return el("span", { class: "result" }, glyph, RESULT_LABEL[r]);
  }

  function directionText(p) {
    return (p.direction === "bullish" ? "▲ " : "▼ ") + capitalize(p.direction);
  }

  function confidencePips(level) {
    var n = { low: 1, medium: 2, high: 3 }[level] || 0;
    var pips = el("span", { class: "pips", "aria-hidden": "true" });
    for (var i = 1; i <= 3; i++) pips.appendChild(el("i", { class: i <= n ? "on" : null }));
    return pips;
  }

  /*
   * Claude's "market mood" is one or two sentences. If it starts with a short
   * phrase before a colon or full stop, use that as the headline and the rest
   * as the deck (the smaller line under a newspaper headline).
   */
  function splitMood(mood) {
    if (!mood) return [null, null];
    var colon = mood.indexOf(":");
    if (colon > 10 && colon < 90) return [mood.slice(0, colon), capitalize(mood.slice(colon + 1).trim())];
    var stop = mood.search(/[.;]\s/);
    if (stop > 10 && stop < 110) return [mood.slice(0, stop), mood.slice(stop + 1).trim()];
    return [null, mood];
  }

  // ---------------------------------------------------------------------------
  // News links and photos
  // ---------------------------------------------------------------------------

  /* Only allow normal web addresses (never "javascript:" or similar). */
  function safeUrl(u) { return typeof u === "string" && /^https?:\/\//i.test(u) ? u : null; }

  /* A link that opens the original article in a new tab. */
  function articleLink(url, text, cls) {
    var href = safeUrl(url);
    if (!href) return el("span", { class: cls, text: text });
    return el("a", { href: href, target: "_blank", rel: "noopener noreferrer", class: cls, text: text });
  }

  /*
   * A news photo. Photos come straight from the news sites, so if one fails
   * to load it quietly removes itself instead of showing a broken image.
   */
  function photo(url, alt, cls, fallback) {
    var src = safeUrl(url);
    if (!src) return null;
    var img = el("img", { src: src, alt: alt || "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer", class: cls });
    img.addEventListener("error", function () {
      // Swap in a stand-in picture if one was given, otherwise just hide it.
      var stand_in = fallback ? fallback() : null;
      if (stand_in) img.replaceWith(stand_in); else img.remove();
    });
    return img;
  }

  /* "2026-09-22 11:00 UTC" -> "11:00 AM ET" */
  function fmtNewsTime(t) {
    var d = new Date(String(t || "").replace(" UTC", "Z").replace(" ", "T"));
    if (isNaN(d)) return t || "";
    return d.toLocaleString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET";
  }

  // ---------------------------------------------------------------------------
  // Tooltip (one shared box for all charts)
  // ---------------------------------------------------------------------------

  var tooltip = document.getElementById("tooltip");

  function showTooltip(event, lines) {
    clear(tooltip);
    lines.forEach(function (line) { tooltip.appendChild(el("div", { class: line[0], text: line[1] })); });
    var x, y;
    if (event.type === "focus") {
      var box = event.target.getBoundingClientRect();
      x = box.left + box.width / 2; y = box.top;
    } else { x = event.clientX; y = event.clientY; }
    tooltip.classList.add("show");
    var w = tooltip.offsetWidth, h = tooltip.offsetHeight;
    var left = Math.min(Math.max(8, x + 14), window.innerWidth - w - 8);
    var top = y - h - 12 < 8 ? y + 16 : y - h - 12;
    tooltip.style.left = left + "px";
    tooltip.style.top = top + "px";
  }
  function hideTooltip() { tooltip.classList.remove("show"); }

  function withTooltip(node, lines) {
    node.addEventListener("pointermove", function (e) { showTooltip(e, lines); });
    node.addEventListener("pointerleave", hideTooltip);
    node.addEventListener("focus", function (e) { showTooltip(e, lines); });
    node.addEventListener("blur", hideTooltip);
  }

  // ---------------------------------------------------------------------------
  // Chart helpers
  // ---------------------------------------------------------------------------

  /* Picks "nice" round tick values (like 0, 2, 4, 6) covering lo..hi. */
  function niceTicks(lo, hi, count) {
    var span = hi - lo || 1;
    var raw = span / Math.max(1, count);
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var step = [1, 2, 2.5, 5, 10].map(function (m) { return m * mag; })
      .find(function (s) { return s >= raw; }) || 10 * mag;
    var start = Math.floor(lo / step) * step, end = Math.ceil(hi / step) * step;
    var ticks = [];
    for (var v = start; v <= end + step / 2; v += step) ticks.push(Math.round(v * 1000) / 1000);
    return ticks;
  }

  /*
   * A bar with a 4px rounded end at the data value and a square end at the
   * zero line. Works for bars going either way (horizontal or vertical).
   */
  function barPath(horizontal, base, value, cross, thickness) {
    var len = Math.abs(value - base);
    var r = Math.min(4, len, thickness / 2);
    var dir = value >= base ? 1 : -1;
    var a = cross, b = cross + thickness;
    if (horizontal) {
      var end = value, cornerStart = end - dir * r;
      return "M" + base + "," + a + "H" + cornerStart +
        "A" + r + "," + r + " 0 0 " + (dir > 0 ? 1 : 0) + " " + end + "," + (a + r) +
        "V" + (b - r) +
        "A" + r + "," + r + " 0 0 " + (dir > 0 ? 1 : 0) + " " + cornerStart + "," + b +
        "H" + base + "Z";
    }
    // Vertical: SVG y grows downward, so "up" means a smaller y.
    var endY = value, cornerY = endY - dir * r;
    return "M" + a + "," + base + "V" + cornerY +
      "A" + r + "," + r + " 0 0 " + (dir < 0 ? 1 : 0) + " " + (a + r) + "," + endY +
      "H" + (b - r) +
      "A" + r + "," + r + " 0 0 " + (dir < 0 ? 1 : 0) + " " + b + "," + cornerY +
      "V" + base + "Z";
  }

  function colorFor(v) { return v > 0 ? "var(--good)" : v < 0 ? "var(--bad)" : "var(--muted)"; }

  /*
   * Stand-in picture for a story without a real news photo: the stock's last
   * ~3 months of prices, with a dot where the bot made its call.
   */
  function chartArt(p, large) {
    var full = (DATA.charts || {})[p.ticker];
    if (!full || full.length < 5) return null;
    var series = full.slice(-63);
    var w = large ? 300 : 100, h = large ? 200 : 100, pad = large ? 16 : 8;
    var values = series.map(function (d) { return d[1]; });
    if (p.price_at_pick) values.push(p.price_at_pick);
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    var x = function (i) { return pad + i * (w - 2 * pad) / (series.length - 1); };
    var y = function (v) { return pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad); };
    var line = series.map(function (d, i) { return (i ? "L" : "M") + x(i).toFixed(1) + "," + y(d[1]).toFixed(1); }).join("");
    var art = svg("svg", { class: "story-photo story-chart", viewBox: "0 0 " + w + " " + h, preserveAspectRatio: "none",
      role: "img", "aria-label": p.ticker + " price over the last 3 months" });
    art.appendChild(svg("rect", { width: w, height: h, fill: "var(--paper-2)" }));
    art.appendChild(svg("path", { d: line + "L" + x(series.length - 1) + "," + h + "L" + x(0) + "," + h + "Z", fill: "var(--ink)", opacity: 0.06 }));
    art.appendChild(svg("path", { d: line, fill: "none", stroke: "var(--ink)", "stroke-width": large ? 2 : 1.5,
      "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke" }));
    // Mark the day of the call (or the last point, if the pick is newer than the data).
    var idx = series.findIndex(function (d) { return d[0] >= p.date; });
    if (idx === -1) idx = series.length - 1;
    var r = resultOf(p);
    art.appendChild(svg("line", { x1: x(idx), x2: x(idx), y1: pad / 2, y2: h - pad / 2, stroke: "var(--muted)", "stroke-width": 1, "vector-effect": "non-scaling-stroke", opacity: 0.6 }));
    art.appendChild(svg("circle", { cx: x(idx), cy: y(p.price_at_pick || series[idx][1]), r: large ? 5 : 4,
      fill: r === "right" ? "var(--good)" : r === "wrong" ? "var(--bad)" : "var(--ink)", stroke: "var(--paper-2)", "stroke-width": 2 }));
    return art;
  }

  /* Small price line for a story: grey line, colored end dot. */
  function sparkline(p) {
    var w = 100, h = 28, pad = 4;
    var pts = (p.history || []).filter(function (d) { return d[1] !== null; });
    var values = pts.map(function (d) { return d[1]; });
    if (p.price_at_pick) values.push(p.price_at_pick);
    if (!values.length) return null;
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    var y = function (v) { return pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad); };
    var x = function (i) { return pts.length < 2 ? w - pad : pad + i * (w - 2 * pad) / (pts.length - 1); };
    var chart = svg("svg", { width: w, height: h, viewBox: "0 0 " + w + " " + h, "aria-hidden": "true" });
    if (p.price_at_pick) {
      chart.appendChild(svg("line", { x1: 0, x2: w, y1: y(p.price_at_pick), y2: y(p.price_at_pick), stroke: "var(--hair)", "stroke-width": 1 }));
    }
    if (pts.length > 1) {
      var d = pts.map(function (pt, i) { return (i ? "L" : "M") + x(i).toFixed(1) + "," + y(pt[1]).toFixed(1); }).join("");
      chart.appendChild(svg("path", { d: d, fill: "none", stroke: "var(--spark)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }
    var last = pts.length ? pts[pts.length - 1][1] : p.price_at_pick;
    chart.appendChild(svg("circle", {
      cx: x(Math.max(0, pts.length - 1)), cy: y(last), r: 4,
      fill: colorFor(p.directional_return_pct || 0), stroke: "var(--paper)", "stroke-width": 2
    }));
    return chart;
  }

  // ---------------------------------------------------------------------------
  // Masthead
  // ---------------------------------------------------------------------------

  var latestDate = (days[0] && days[0].date) || (picks[0] && picks[0].date) || null;

  function renderMasthead() {
    document.getElementById("today-date").textContent = latestDate ? fmtLongDate(latestDate) : "Awaiting the first edition";
    document.getElementById("volume").textContent = "Vol. I · No. " + (stats.days_tracked || 0);
    var updated = fmtUpdated(DATA.generated_at);
    document.getElementById("edition").textContent = updated ? "Weekday Edition · Updated " + updated : "Weekday Edition";
    document.getElementById("prices-asof").textContent = updated ? "Prices as of the latest close · Updated " + updated : "";
    document.getElementById("footer-meta").textContent =
      "News from Finnhub · Analysis by Claude · Prices from Yahoo Finance · " + (updated ? "Updated " + updated : "");
  }

  // ---------------------------------------------------------------------------
  // Front page: the lead story (today's picks)
  // ---------------------------------------------------------------------------

  function renderLead() {
    var lead = document.getElementById("lead");
    clear(lead);
    if (!latestDate) {
      append(lead, [
        el("p", { class: "kicker", text: "Markets" }),
        el("h2", { class: "headline", text: "The first edition is on its way" }),
        el("p", { class: "deck", text: "Once the bot's first weekday run finishes, today's stock ideas and the scorecard will appear here." })
      ]);
      return;
    }
    var today = days[0] || {};
    var todays = picks.filter(function (p) { return p.date === latestDate; });
    var parts = splitMood(today.market_mood);
    var bulls = todays.filter(function (p) { return p.direction === "bullish"; }).length;
    var headline = parts[0] || (todays.length + " ideas from the morning's news");

    var byline = el("p", { class: "byline" },
      "By ", el("strong", { text: "The Morning Brief" }), " · Analysis by Claude · ",
      todays.length + " ideas (" + bulls + " bullish, " + (todays.length - bulls) + " bearish)",
      today.headlines && today.headlines.length ? " from " + today.headlines.length + " headlines" : "");

    var stories = el("div", { class: "stories" });
    todays.forEach(function (p, i) {
      // The first story runs full width; the rest sit in two columns.
      var cls = i === 0 ? "first" : (i % 2 ? "col-l" : "col-r");
      stories.appendChild(storyFor(p, cls));
    });

    append(lead, [
      el("p", { class: "kicker", text: "Markets · " + fmtLongDate(latestDate) }),
      el("h2", { class: "headline", text: headline }),
      parts[1] ? el("p", { class: "deck", text: parts[1] }) : null,
      byline,
      el("p", { class: "today-score" },
        stats.judged
          ? "Scorecard: " + Math.round(stats.hit_rate) + "% of calls right so far (" + stats.correct + " of " + stats.judged + "). "
          : "Scorecard: results start after the next market close. ",
        el("a", { href: "#results", text: "See results →" })),
      stories
    ]);
  }

  function storyFor(p, cls) {
    var move = p.return_pct === null || p.return_pct === undefined ? "Too early to tell" : fmtPct(p.return_pct) + " since pick";
    var title = el("h3", null, el("span", { class: "ticker", text: p.ticker }), p.company || "");
    // One quiet line: "▲ Bullish · ●●○ Medium · ● Right so far".
    // The result only appears once there is one.
    var sep = function () { return el("span", { class: "sep", "aria-hidden": "true", text: "·" }); };
    var tags = el("div", { class: "tags" },
      el("span", { class: "tag", text: directionText(p) }),
      p.confidence ? [sep(), el("span", { class: "tag", title: capitalize(p.confidence) + " confidence" },
        confidencePips(p.confidence), capitalize(p.confidence),
        el("span", { class: "visually-hidden", text: " confidence" }))] : null,
      resultOf(p) !== "open" ? [sep(), el("span", { class: "tag" }, resultBadge(p))] : null);
    var price = el("div", { class: "story-price" },
      el("div", { class: "now", text: fmtPrice(p.price_now || p.price_at_pick) }),
      el("div", { class: "move", text: move }),
      sparkline(p),
      chartLink(p.ticker, "Chart →", "chart-link"));
    var a = p.article;
    // The picture for a story: the news photo if there's a real one,
    // otherwise a small 3-month price chart of the stock.
    var story;
    var makeChart = function () {
      var c = chartArt(p, cls === "first");
      if (c) story.classList.add("has-chart-art"); else story.classList.remove("has-photo");
      return c;
    };
    var art = a && safeUrl(a.image) ? photo(a.image, a.headline, "story-photo", makeChart) : chartArt(p, cls === "first");
    story = el("article", { class: "story " + cls + (art ? " has-photo" : "") + (art && art.tagName === "svg" ? " has-chart-art" : "") },
      art,
      el("div", { class: "story-top" }, el("div", null, title, tags), price),
      el("p", { class: "reason", text: p.reason }),
      a && safeUrl(a.url) ? el("p", { class: "read-more" },
        el("span", { class: "src", text: a.source }), " · ",
        articleLink(a.url, "Read the article ↗", null)) : null);
    return story;
  }

  // ---------------------------------------------------------------------------
  // Scorecard (right-hand column)
  // ---------------------------------------------------------------------------

  function renderScorecard() {
    var rail = document.getElementById("scorecard");
    clear(rail);
    var judged = stats.judged || 0;
    var hero = stats.hit_rate === null || stats.hit_rate === undefined ? "—" : Math.round(stats.hit_rate) + "%";
    var heroNote = judged
      ? stats.correct + " of " + judged + " calls are working, measured from the price when each was picked."
      : "Calls are scored against later prices, so the newest ideas start at zero. The first results arrive after the next market close.";

    // Before any call has a result, only show numbers that already mean something.
    var best = stats.best, worst = stats.worst;
    var tiles = judged
      ? el("div", { class: "tiles" },
          tile("Ideas published", String(stats.total_picks || 0), (stats.days_tracked || 0) + (stats.days_tracked === 1 ? " trading day" : " trading days")),
          tile("Average move for the call", fmtPct(stats.avg_directional_return), "Above zero means calls are working"),
          tile("Best call", best.ticker + " " + fmtPct(best.directional_return_pct, 1), capitalize(best.direction) + " · " + fmtShortDate(best.date)),
          tile("Worst call", worst.ticker + " " + fmtPct(worst.directional_return_pct, 1), capitalize(worst.direction) + " · " + fmtShortDate(worst.date)))
      : el("div", { class: "tiles" },
          tile("Ideas published", String(stats.total_picks || 0), "Waiting for results"),
          tile("Days tracked", String(stats.days_tracked || 0), "Scores start after the next close"));

    // Three columns: the headline number, the tiles, and the breakdowns.
    append(rail, [
      el("div", { class: "sc-col" },
        el("p", { class: "hero-label", text: "Calls right so far" }),
        el("div", { class: "hero-figure" + (judged ? "" : " pending"), text: judged ? hero : "Pending" }),
        el("p", { class: "hero-note", text: heroNote })),
      el("div", { class: "sc-col" }, tiles),
      judged ? el("div", { class: "sc-col" },
        breakdown("By call", stats.by_direction || []),
        breakdown("By confidence", stats.by_confidence || []),
        el("p", { class: "legend-note" },
          el("span", { class: "key" }, el("i", { style: "background:var(--good)" }), "Right so far"),
          el("span", { class: "key" }, el("i", { style: "background:var(--bad)" }), "Wrong so far"),
          el("br"),
          "A bullish call is right so far if the stock is up since the pick; a bearish call if it's down.")) : null
    ]);
  }

  function tile(label, value, sub) {
    return el("div", { class: "tile" },
      el("div", { class: "label", text: label }),
      el("div", { class: "value", text: value }),
      el("div", { class: "sub", text: sub }));
  }

  /* Rows of "hit rate" meters, e.g. bullish vs bearish calls. */
  function breakdown(title, groups) {
    var rows = groups.filter(function (g) { return g.count > 0; });
    if (!rows.length) return null;
    return el("div", { class: "breakdown" },
      el("h3", { text: title }),
      rows.map(function (g) {
        var has = g.hit_rate !== null && g.hit_rate !== undefined;
        var meter = el("div", { class: "meter" + (has ? "" : " empty"), role: "img",
          "aria-label": capitalize(g.label) + ": " + (has ? g.hit_rate + "% right so far" : "no results yet") });
        if (has) meter.appendChild(el("span", { style: "width:" + Math.max(0, Math.min(100, g.hit_rate)) + "%" }));
        return el("div", { class: "meter-row" },
          el("span", { class: "name", text: g.label }),
          meter,
          el("span", { class: "val" }, has ? Math.round(g.hit_rate) + "% right" : "—",
            el("small", { text: g.count + (g.count === 1 ? " pick" : " picks") })));
      }));
  }

  // ---------------------------------------------------------------------------
  // Charts
  // ---------------------------------------------------------------------------

  function emptyChart(title, text) {
    return el("div", { class: "empty-chart" }, el("strong", { text: title }), text);
  }

  /* Horizontal bars: each call's move since the pick, in the call's direction. */
  function renderCallsChart() {
    var fig = document.getElementById("calls-figure");
    clear(fig);
    append(fig, [
      el("h3", { text: "How each call is doing" }),
      el("p", { class: "chart-sub", text: "Move since the pick, counted in the direction of the call. Bars to the right of the line are working; bars to the left are not." })
    ]);

    var rows = picks.filter(function (p) { return p.directional_return_pct !== null && p.directional_return_pct !== undefined; })
      .slice(0, 40)
      .sort(function (a, b) { return b.directional_return_pct - a.directional_return_pct; });
    var anyMove = rows.some(function (p) { return Math.abs(p.directional_return_pct) >= 0.005; });
    if (!anyMove) {
      fig.appendChild(emptyChart("Scores arrive after the next close",
        "Every call so far was made at the latest price, so each one sits at 0%. Tomorrow's run adds the first real moves, and this chart fills in."));
      return;
    }

    var box = el("div", { class: "chart" });
    fig.appendChild(box);
    var W = Math.max(300, fig.clientWidth - (parseFloat(getComputedStyle(fig).paddingLeft) || 0) - (parseFloat(getComputedStyle(fig).paddingRight) || 0));
    var labelW = 96, sidePad = 50, rowH = 26, barH = 12, top = 6, bottom = 26;
    var values = rows.map(function (p) { return p.directional_return_pct; });
    var ticks = niceTicks(Math.min(0, Math.min.apply(null, values)), Math.max(0, Math.max.apply(null, values)), W < 520 ? 4 : 6);
    var lo = ticks[0], hi = ticks[ticks.length - 1];
    var plotL = labelW + sidePad, plotR = W - sidePad;
    var x = function (v) { return plotL + (v - lo) / (hi - lo) * (plotR - plotL); };
    var H = top + rows.length * rowH + bottom;

    var chart = svg("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img",
      "aria-label": "Bar chart of " + rows.length + " calls by move since the pick. The same numbers are in The Record tab." });

    ticks.forEach(function (t) {
      chart.appendChild(svg("line", { class: t === 0 ? "baseline" : "grid", x1: x(t), x2: x(t), y1: top, y2: H - bottom }));
      chart.appendChild(svg("text", { class: "axis-text", x: x(t), y: H - 8, "text-anchor": "middle", text: fmtPct(t, t % 1 ? 1 : 0) }));
    });

    var list = svg("g", { role: "list" });
    rows.forEach(function (p, i) {
      var v = p.directional_return_pct, y = top + i * rowH;
      var row = svg("g", { class: "row", tabindex: 0, role: "listitem",
        "aria-label": p.ticker + ", " + p.direction + " call from " + fmtShortDate(p.date) + ": " + fmtPct(v) + ", " + RESULT_LABEL[resultOf(p)] });
      row.appendChild(svg("rect", { class: "hit", x: 0, y: y, width: W, height: rowH }));
      row.appendChild(svg("text", { x: labelW, y: y + rowH / 2 + 4, "text-anchor": "end", "font-size": 11 },
        svg("tspan", { "font-weight": 700, fill: "var(--ink)", text: p.ticker }),
        svg("tspan", { fill: "var(--muted)", "font-size": 11, dx: 6, text: fmtShortDate(p.date) })));
      if (Math.abs(v) >= 0.005) {
        row.appendChild(svg("path", { class: "bar", d: barPath(true, x(0), x(v), y + (rowH - barH) / 2, barH), fill: colorFor(v) }));
      }
      var labelX = v >= 0 ? x(v) + 6 : x(v) - 6;
      row.appendChild(svg("text", { x: labelX, y: y + rowH / 2 + 4, "text-anchor": v >= 0 ? "start" : "end", "font-size": 11, fill: "var(--ink-2)", class: "tab", text: fmtPct(v, 1) }));
      withTooltip(row, [
        ["tt-value", fmtPct(v) + " for the call"],
        ["tt-title", p.ticker + (p.company ? " · " + p.company : "")],
        ["tt-line", capitalize(p.direction) + " call · " + fmtTableDate(p.date)],
        ["tt-line", fmtPrice(p.price_at_pick) + " → " + fmtPrice(p.price_now)],
        ["tt-line", RESULT_LABEL[resultOf(p)]]
      ]);
      list.appendChild(row);
    });
    chart.appendChild(list);
    box.appendChild(chart);
    append(fig, el("figcaption", { text: rows.length < picks.length ? "Showing the " + rows.length + " most recent calls. Every call is in The Record tab." : "Every value is also in The Record tab." }));
  }

  /* Vertical bars: the average result of each day's calls. */
  function renderDaysChart() {
    var fig = document.getElementById("days-figure");
    clear(fig);
    append(fig, [
      el("h3", { text: "Day by day" }),
      el("p", { class: "chart-sub", text: "The average move of each day's calls, in the direction of the call." })
    ]);
    var byDay = (stats.by_day || []).filter(function (d) { return d.avg_directional_return !== null; }).slice(-30);
    var anyMove = byDay.some(function (d) { return Math.abs(d.avg_directional_return) >= 0.005; });
    if (byDay.length < 2 || !anyMove) {
      fig.appendChild(emptyChart(byDay.length < 2 ? "One day in the books" : "Scores arrive after the next close",
        "This chart compares days, so it fills in once there are at least two days of scored calls."));
      return;
    }

    var latest = byDay[byDay.length - 1];
    fig.querySelector(".chart-sub").textContent += " Latest day (" + fmtShortDate(latest.date) + "): " +
      fmtPct(latest.avg_directional_return) + ".";
    var box = el("div", { class: "chart" });
    fig.appendChild(box);
    var W = Math.max(280, fig.clientWidth - (parseFloat(getComputedStyle(fig).paddingLeft) || 0) - (parseFloat(getComputedStyle(fig).paddingRight) || 0));
    var H = 240, left = 44, right = 8, top = 18, bottom = 28;
    var values = byDay.map(function (d) { return d.avg_directional_return; });
    var ticks = niceTicks(Math.min(0, Math.min.apply(null, values)), Math.max(0, Math.max.apply(null, values)), 4);
    var lo = ticks[0], hi = ticks[ticks.length - 1];
    var y = function (v) { return top + (1 - (v - lo) / (hi - lo)) * (H - top - bottom); };
    var slot = (W - left - right) / byDay.length;
    var colW = Math.min(24, Math.max(4, slot - 2));  // thin bars with at least a 2px gap
    var labelEvery = Math.ceil(byDay.length / Math.max(1, Math.floor((W - left) / 56)));

    var chart = svg("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img",
      "aria-label": "Column chart of the average move of each day's calls. The same numbers are in the table below the chart." });
    ticks.forEach(function (t) {
      chart.appendChild(svg("line", { class: t === 0 ? "baseline" : "grid", x1: left, x2: W - right, y1: y(t), y2: y(t) }));
      chart.appendChild(svg("text", { class: "axis-text", x: left - 8, y: y(t) + 4, "text-anchor": "end", text: fmtPct(t, t % 1 ? 1 : 0) }));
    });
    byDay.forEach(function (d, i) {
      var v = d.avg_directional_return, cx = left + i * slot + slot / 2;
      var col = svg("g", { class: "col", tabindex: 0,
        "aria-label": fmtShortDate(d.date) + ": " + fmtPct(v) + " average, " + d.count + " calls" });
      col.appendChild(svg("rect", { class: "hit", x: cx - slot / 2, y: top, width: slot, height: H - top - bottom }));
      if (Math.abs(v) >= 0.005) col.appendChild(svg("path", { class: "bar", d: barPath(false, y(0), y(v), cx - colW / 2, colW), fill: colorFor(v) }));
      if (i % labelEvery === 0 || i === byDay.length - 1) {
        col.appendChild(svg("text", { class: "axis-text", x: cx, y: H - 8, "text-anchor": "middle", text: fmtShortDate(d.date) }));
      }
      withTooltip(col, [
        ["tt-value", fmtPct(v) + " average"],
        ["tt-title", fmtLongDate(d.date)],
        ["tt-line", d.count + (d.count === 1 ? " call" : " calls") + (d.hit_rate !== null ? " · " + Math.round(d.hit_rate) + "% right so far" : "")]
      ]);
      chart.appendChild(col);
    });
    box.appendChild(chart);

    // The same numbers as a table, so nothing depends on hovering.
    var table = el("table", null,
      el("thead", null, el("tr", null, el("th", { text: "Day" }), el("th", { class: "r", text: "Calls" }), el("th", { class: "r", text: "Average" }), el("th", { class: "r", text: "Right" }))),
      el("tbody", null, byDay.slice().reverse().map(function (d) {
        return el("tr", null,
          el("td", { text: fmtTableDate(d.date) }),
          el("td", { class: "r tab", text: String(d.count) }),
          el("td", { class: "r tab", text: fmtPct(d.avg_directional_return) }),
          el("td", { class: "r tab", text: d.hit_rate === null ? "—" : Math.round(d.hit_rate) + "%" }));
      })));
    fig.appendChild(el("details", null, el("summary", { text: "Show as a table" }), el("div", { class: "table-wrap" }, table)));
  }

  // ---------------------------------------------------------------------------
  // Stock charts: a big chart for one stock, plus a card for every stock
  // ---------------------------------------------------------------------------

  var charts = DATA.charts || {};
  var RANGES = [["1M", 31], ["3M", 92], ["6M", 183], ["All", 0]];
  var RANGE_WORDS = { "1M": "the past month", "3M": "the past 3 months", "6M": "the past 6 months", "All": "the full period" };
  var stockState = { ticker: null, range: "3M" };

  var watchlist = DATA.watchlist || [];

  /*
   * Every stock the page can chart: the bot's picks (newest first), then the
   * "market watch" list. Each gets a name and a short note about what's going on.
   */
  function stockList() {
    var list = [], seen = {};
    picks.forEach(function (p) {
      if (!charts[p.ticker] || seen[p.ticker]) return;
      seen[p.ticker] = true;
      list.push({ ticker: p.ticker, name: p.company || "", kind: "pick", pick: p, note: p.reason });
    });
    watchlist.forEach(function (w) {
      if (!charts[w.ticker]) return;
      if (seen[w.ticker]) {  // also a pick: keep the pick, remember the watch note
        var item = list.find(function (i) { return i.ticker === w.ticker; });
        item.watchNote = w.note;
        return;
      }
      seen[w.ticker] = true;
      list.push({ ticker: w.ticker, name: w.name, kind: "watch", note: w.note });
    });
    return list;
  }

  function companyOf(ticker) {
    var item = stockList().find(function (i) { return i.ticker === ticker; });
    return item ? item.name : "";
  }

  function toMs(s) { return toDate(s).getTime(); }

  /* Jump to a stock's chart (used by the "Chart →" links). */
  function openStockChart(ticker) {
    if (charts[ticker]) openStockModal(ticker);
  }

  function chartLink(ticker, text, cls) {
    if (!charts[ticker]) return null;
    var a = el("a", { href: "#stock-charts", class: cls, text: text });
    a.addEventListener("click", function (e) { e.preventDefault(); openStockChart(ticker); });
    return a;
  }

  /* The slice of a stock's price history for the chosen time range. */
  function seriesFor(ticker) {
    var full = charts[ticker];
    var days = RANGES.find(function (r) { return r[0] === stockState.range; })[1];
    var cutoff = days ? toMs(full[full.length - 1][0]) - days * 86400000 : -Infinity;
    var series = full.filter(function (d) { return toMs(d[0]) >= cutoff; });
    return series.length < 2 ? full.slice(-2) : series;
  }

  /* Blue when the stock is up over the range, red when it's down. */
  function trendColor(change) { return change >= 0 ? "var(--good)" : "var(--bad)"; }

  /* "▲ +4.20%" in a colored pill (the arrow and sign carry it, not just color). */
  function changePill(change) {
    return el("span", { class: "chg-pill " + (change >= 0 ? "up" : "down") },
      el("span", { class: "arrow", "aria-hidden": "true", text: change >= 0 ? "▲ " : "▼ " }), fmtPct(change));
  }

  function kindTag(item) {
    if (item.kind === "pick") {
      return el("span", { class: "kind-tag pick" }, "Bot pick · " + directionText(item.pick));
    }
    return el("span", { class: "kind-tag watch", text: "Market watch" });
  }

  var stocksShowAll = false;  // "Show more" pressed?
  var MAIN_FUNDS = ["SPY", "QQQ", "DIA"];

  /*
   * The order cards appear in: today's picks first, then the big market funds,
   * then everything else (older picks and the rest of the market-watch list,
   * biggest movers first).
   */
  function stockOrder(all) {
    var latest = picks.length ? picks[0].date : null;
    var rank = function (i) {
      if (i.kind === "pick" && i.pick.date === latest) return 0;
      if (MAIN_FUNDS.indexOf(i.ticker) !== -1) return 1;
      return 2;
    };
    var move = function (i) {
      var sr = seriesFor(i.ticker);
      return Math.abs((sr[sr.length - 1][1] - sr[0][1]) / sr[0][1]);
    };
    return all.map(function (i, n) { return [i, n]; }).sort(function (a, b) {
      var ra = rank(a[0]), rb = rank(b[0]);
      if (ra !== rb) return ra - rb;
      if (ra === 2) return move(b[0]) - move(a[0]);
      if (ra === 1) return MAIN_FUNDS.indexOf(a[0].ticker) - MAIN_FUNDS.indexOf(b[0].ticker);
      return a[1] - b[1];
    }).map(function (x) { return x[0]; });
  }

  function renderStockSection() {
    var area = document.getElementById("stock-area");
    clear(area);
    var all = stockList();
    if (!all.length) {
      area.appendChild(emptyChart("Charts appear with the first run", "Once the bot has run, price charts for its picks and the market-watch list show up here."));
      return;
    }
    var ordered = stockOrder(all);
    // First view: today's picks plus the big market funds (at least 4 cards).
    var latest = picks.length ? picks[0].date : null;
    var mainCount = all.filter(function (i) {
      return (i.kind === "pick" && i.pick.date === latest) || MAIN_FUNDS.indexOf(i.ticker) !== -1;
    }).length;
    var STOCKS_FIRST = Math.max(4, mainCount);

    // Time range for every card.
    var ranges = el("div", { class: "range-picker", role: "group", "aria-label": "Time range" });
    RANGES.forEach(function (r) {
      var b = el("button", { type: "button", class: "pill", "aria-pressed": String(r[0] === stockState.range), text: r[0] });
      b.addEventListener("click", function () { stockState.range = r[0]; renderStockSection(); });
      ranges.appendChild(b);
    });
    area.appendChild(el("div", { class: "stock-controls" },
      el("p", { class: "stock-hint", text: "Today's picks and the big market funds first. Click a card for the full chart and story." }),
      ranges));

    var grid = el("div", { class: "stock-grid" });
    var visible = stocksShowAll ? ordered : ordered.slice(0, STOCKS_FIRST);
    visible.forEach(function (i) { grid.appendChild(stockCard(i)); });
    area.appendChild(grid);

    if (ordered.length > STOCKS_FIRST) {
      var more = el("button", { type: "button", class: "more",
        text: stocksShowAll ? "Show fewer" : "Show " + (ordered.length - STOCKS_FIRST) + " more stocks" });
      more.addEventListener("click", function () { stocksShowAll = !stocksShowAll; renderStockSection(); });
      area.appendChild(more);
    }
    area.appendChild(el("p", { class: "stock-foot" },
      el("span", null,
        el("span", { class: "key" }, el("i", { style: "background:var(--good)" }), "Up over the period"),
        el("span", { class: "key" }, el("i", { style: "background:var(--bad)" }), "Down over the period")),
      el("span", { text: "Prices from Yahoo Finance · Notes by Claude from the morning's news" })));
  }

  /* One card: name, price, colored mini chart, and a short note. */
  function stockCard(item) {
    var series = seriesFor(item.ticker);
    var first = series[0][1], last = series[series.length - 1][1];
    var change = (last - first) / first * 100;
    var w = 300, h = 70, pad = 4;
    var vals = series.map(function (d) { return d[1]; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    var x = function (i) { return i * w / (series.length - 1); };
    var y = function (v) { return pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad); };
    var line = series.map(function (d, i) { return (i ? "L" : "M") + x(i).toFixed(1) + "," + y(d[1]).toFixed(1); }).join("");
    var mini = svg("svg", { class: "card-chart", viewBox: "0 0 " + w + " " + h, preserveAspectRatio: "none", "aria-hidden": "true" });
    mini.appendChild(svg("path", { d: line + "L" + w + "," + h + "L0," + h + "Z", fill: trendColor(change), opacity: 0.12 }));
    mini.appendChild(svg("path", { d: line, fill: "none", stroke: trendColor(change), "stroke-width": 2, "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round" }));

    var note = item.note || (item.kind === "watch" ? "Notes arrive with the next morning run." : "");
    var card = el("button", { type: "button", class: "stock-card", "aria-haspopup": "dialog",
      "aria-label": item.ticker + ", " + item.name + ", " + fmtPrice(last) + ", " + fmtPct(change) + " over " + RANGE_WORDS[stockState.range] + ". Open the full chart." },
      el("div", { class: "card-top" },
        el("div", null, el("span", { class: "card-ticker", text: item.ticker }), el("span", { class: "card-name", text: item.name })),
        el("div", { class: "card-price" }, el("div", { class: "now", text: fmtPrice(last) }), changePill(change))),
      mini,
      kindTag(item),
      note ? el("p", { class: "card-note" + (item.note ? "" : " muted"), text: note }) : null);
    card.addEventListener("click", function () { openStockModal(item.ticker); });
    return card;
  }

  // ---------------------------------------------------------------------------
  // Stock popup: the full chart plus everything we know about the stock
  // ---------------------------------------------------------------------------

  var modal = document.getElementById("stock-modal");
  var modalTicker = null;

  function openStockModal(ticker) {
    modalTicker = ticker;
    // The tooltip has to live inside the popup to show on top of it.
    modal.querySelector(".modal-inner").appendChild(tooltip);
    if (!modal.open) modal.showModal();
    renderStockModal();
    modal.querySelector(".modal-close").focus();
  }

  function closeStockModal() {
    hideTooltip();
    document.body.appendChild(tooltip);
    modalTicker = null;
    if (modal.open) modal.close();
  }

  /* Percent change over the last `days` calendar days (null if not enough data). */
  function changeOver(full, days) {
    var lastMs = toMs(full[full.length - 1][0]);
    var start = null;
    for (var i = full.length - 1; i >= 0; i--) {
      if (toMs(full[i][0]) <= lastMs - days * 86400000) { start = full[i]; break; }
    }
    if (!start) return null;
    return (full[full.length - 1][1] - start[1]) / start[1] * 100;
  }

  /* Today's headlines that mention this stock (tagged by Claude, or by name). */
  function headlinesAbout(item) {
    var day = days.find(function (d) { return d.headlines && d.headlines.length; });
    if (!day) return [];
    var word = (item.name || "").split(/[\s(,]/)[0];
    var tickerRe = new RegExp("\\b" + item.ticker.replace(/[^A-Z]/g, "") + "\\b");
    return day.headlines.filter(function (h) {
      return (h.tickers || []).indexOf(item.ticker) !== -1 || tickerRe.test(h.headline) ||
        (word.length > 3 && h.headline.indexOf(word) !== -1);
    }).slice(0, 5);
  }

  function statTile(label, value, extra) {
    return el("div", { class: "m-stat" }, el("div", { class: "m-label", text: label }),
      el("div", { class: "m-value" }, value), extra ? el("div", { class: "m-sub", text: extra }) : null);
  }

  function renderStockModal() {
    var body = document.getElementById("modal-body");
    clear(body);
    var item = stockList().find(function (i) { return i.ticker === modalTicker; });
    if (!item) { closeStockModal(); return; }
    var full = charts[item.ticker];
    var last = full[full.length - 1][1];

    // Range buttons for the popup chart.
    var ranges = el("div", { class: "range-picker", role: "group", "aria-label": "Time range" });
    RANGES.forEach(function (r) {
      var b = el("button", { type: "button", class: "pill", "aria-pressed": String(r[0] === stockState.range), text: r[0] });
      b.addEventListener("click", function () { stockState.range = r[0]; renderStockModal(); renderStockSection(); });
      ranges.appendChild(b);
    });
    body.appendChild(el("div", { class: "modal-top" }, el("span", { class: "m-kicker", text: "Stock chart" }), ranges));

    // The full interactive chart (same one as before, now in the popup).
    var chartBox = el("div", { class: "modal-chart" });
    body.appendChild(chartBox);
    drawBigChart(chartBox, item);

    // Key numbers.
    var vals = full.map(function (d) { return d[1]; });
    var pctOrDash = function (v) { return v === null ? "—" : changePill(v); };
    var dayChange = full.length > 1 ? (last - full[full.length - 2][1]) / full[full.length - 2][1] * 100 : null;
    body.appendChild(el("div", { class: "m-stats" },
      statTile("Latest close", fmtPrice(last), fmtShortDate(full[full.length - 1][0])),
      statTile("Last day", pctOrDash(dayChange)),
      statTile("1 month", pctOrDash(changeOver(full, 30))),
      statTile("3 months", pctOrDash(changeOver(full, 91))),
      statTile("6 months", pctOrDash(changeOver(full, 182))),
      statTile("6-month range", fmtPrice(Math.min.apply(null, vals)) + " – " + fmtPrice(Math.max.apply(null, vals)))));

    // The bot's call (for picks), with its news story.
    if (item.kind === "pick") {
      var p = item.pick, a = p.article;
      var sec = el("section", { class: "m-section" },
        el("h4", { text: "The bot's call" }),
        el("div", { class: "m-call" },
          el("span", { class: "kind-tag pick", text: directionText(p) }),
          p.confidence ? el("span", { class: "m-conf" }, confidencePips(p.confidence), capitalize(p.confidence) + " confidence") : null,
          el("span", { class: "m-conf", text: "Picked " + fmtLongDate(p.date) + (p.price_at_pick ? " at " + fmtPrice(p.price_at_pick) : "") }),
          resultBadge(p),
          p.return_pct !== null && p.return_pct !== undefined ? el("span", { class: "m-conf" }, "Since the pick: ", changePill(p.return_pct)) : null),
        el("p", { class: "m-reason", text: p.reason }));
      if (a && safeUrl(a.url)) {
        sec.appendChild(el("a", { class: "m-article", href: a.url, target: "_blank", rel: "noopener noreferrer" },
          photo(a.image, a.headline, "m-article-photo"),
          el("span", { class: "m-article-text" },
            el("span", { class: "m-article-src", text: a.source + " · Read the article ↗" }),
            el("span", { class: "m-article-hl", text: a.headline }))));
      }
      body.appendChild(sec);
    }

    // Claude's note (market watch).
    var note = item.kind === "watch" ? item.note : item.watchNote;
    var w = watchlist.find(function (x) { return x.ticker === item.ticker; });
    if (w) {
      body.appendChild(el("section", { class: "m-section" },
        el("h4", { text: "What's going on" + (w.note_date ? " · " + fmtShortDate(w.note_date) : "") }),
        el("p", { class: "m-reason", text: note || "Claude's notes on the market-watch stocks arrive with the next morning run." })));
    }

    // Headlines that mention it.
    var related = headlinesAbout(item);
    if (related.length) {
      body.appendChild(el("section", { class: "m-section" },
        el("h4", { text: "In today's news" }),
        el("ul", { class: "m-news" }, related.map(function (h) {
          return el("li", null, articleLink(h.url, h.headline, null), el("small", { text: h.source + " · " + fmtNewsTime(h.time) }));
        }))));
    }
    body.appendChild(el("p", { class: "m-disclaimer", text: "Ideas for research only, not financial advice." }));
  }

  modal.querySelector(".modal-close").addEventListener("click", closeStockModal);
  modal.addEventListener("close", function () { if (modalTicker) closeStockModal(); });  // Esc key
  modal.addEventListener("click", function (e) { if (e.target === modal) closeStockModal(); });  // click outside

  /* The large interactive chart (hover or arrow keys to read each day). */
  function drawBigChart(area, item) {
    var t = item.ticker;
    var series = seriesFor(t);
    var first = series[0][1], last = series[series.length - 1][1];
    var change = (last - first) / first * 100;
    var color = trendColor(change);

    area.appendChild(el("div", { class: "stock-head" },
      el("div", null,
        el("h3", null, el("span", { class: "ticker", text: t }), item.name),
        kindTag(item)),
      el("div", { class: "stock-price" },
        el("div", { class: "now", text: fmtPrice(last) }),
        el("div", { class: "chg" }, changePill(change), " over " + RANGE_WORDS[stockState.range]))));

    // The bot's calls on this stock that fall inside the range.
    var calls = picks.filter(function (p) { return p.ticker === t && toMs(p.date) >= toMs(series[0][0]); });

    // --- Geometry.
    // Measure the space inside the box (its width minus its padding).
    var cs = getComputedStyle(area);
    var W = Math.max(280, area.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0));
    var narrow = W < 560;
    var H = narrow ? 230 : 300, left = 6, right = 56, top = 14, bottom = 26;
    var xs = series.map(function (d) { return toMs(d[0]); });
    var values = series.map(function (d) { return d[1]; }).concat(calls.map(function (p) { return p.price_at_pick; }).filter(Boolean));
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    var pad = (hi - lo) * 0.08 || hi * 0.02 || 1;
    var ticks = niceTicks(lo - pad, hi + pad, narrow ? 4 : 5);
    var yLo = ticks[0], yHi = ticks[ticks.length - 1];
    var x = function (ms) { return left + (ms - xs[0]) / (xs[xs.length - 1] - xs[0] || 1) * (W - left - right); };
    var y = function (v) { return top + (1 - (v - yLo) / (yHi - yLo)) * (H - top - bottom); };

    var plot = svg("svg", { class: "stock-plot", viewBox: "0 0 " + W + " " + H, width: W, height: H, tabindex: 0, role: "img",
      "aria-label": t + " closing price, " + fmtShortDate(series[0][0]) + " to " + fmtShortDate(series[series.length - 1][0]) +
        ": from " + fmtPrice(first) + " to " + fmtPrice(last) + ". Use the left and right arrow keys to read each day." });

    // Gridlines + price labels on the right.
    ticks.forEach(function (v) {
      plot.appendChild(svg("line", { class: "grid", x1: left, x2: W - right, y1: y(v), y2: y(v), stroke: "var(--hair)", "stroke-width": 1 }));
      plot.appendChild(svg("text", { x: W - right + 8, y: y(v) + 4, text: fmtPrice(v).replace(/\.00$/, "") }));
    });
    // Date labels along the bottom (about one per 90px).
    var labelCount = Math.max(2, Math.floor((W - left - right) / 90));
    for (var i = 0; i < labelCount; i++) {
      var idx = Math.round(i * (series.length - 1) / (labelCount - 1));
      var anchor = i === 0 ? "start" : i === labelCount - 1 ? "end" : "middle";
      plot.appendChild(svg("text", { x: x(xs[idx]), y: H - 8, "text-anchor": anchor, text: fmtShortDate(series[idx][0]) }));
    }

    // Price line in the trend color, with a light wash of the same color underneath.
    var line = series.map(function (d, i) { return (i ? "L" : "M") + x(xs[i]).toFixed(1) + "," + y(d[1]).toFixed(1); }).join("");
    var areaPath = line + "L" + x(xs[xs.length - 1]).toFixed(1) + "," + (H - bottom) + "L" + x(xs[0]).toFixed(1) + "," + (H - bottom) + "Z";
    plot.appendChild(svg("path", { d: areaPath, fill: color, opacity: 0.1 }));
    plot.appendChild(svg("path", { d: line, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));

    // A dot for each of the bot's calls, at the price when it was picked.
    calls.forEach(function (p) {
      if (!p.price_at_pick) return;
      var cx = x(Math.max(xs[0], Math.min(xs[xs.length - 1], toMs(p.date)))), cy = y(p.price_at_pick);
      var r = resultOf(p);
      plot.appendChild(svg("circle", { cx: cx, cy: cy, r: 5, "stroke-width": 2, stroke: r === "open" ? "var(--ink)" : "var(--paper)",
        fill: r === "right" ? "var(--good)" : r === "wrong" ? "var(--bad)" : "var(--paper)" }));
      plot.appendChild(svg("text", { x: cx, y: p.direction === "bullish" ? cy - 11 : cy + 19, "text-anchor": "middle", fill: "var(--ink-2)", "font-size": 10,
        "aria-hidden": "true", text: p.direction === "bullish" ? "▲" : "▼" }));
    });

    // Crosshair: a thin line and a dot that follow the pointer (or arrow keys).
    var cross = svg("line", { y1: top, y2: H - bottom, stroke: "var(--muted)", "stroke-width": 1, visibility: "hidden" });
    var dot = svg("circle", { r: 4, fill: color, stroke: "var(--paper)", "stroke-width": 2, visibility: "hidden" });
    plot.appendChild(cross);
    plot.appendChild(dot);
    var active = series.length - 1;

    function showAt(i, event) {
      active = Math.max(0, Math.min(series.length - 1, i));
      var d = series[active], px = x(xs[active]), py = y(d[1]);
      cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.setAttribute("visibility", "visible");
      var lines = [["tt-value", fmtPrice(d[1])], ["tt-title", fmtLongDate(d[0])]];
      var since = (d[1] - first) / first * 100;
      lines.push(["tt-line", fmtPct(since) + " since " + fmtShortDate(series[0][0])]);
      calls.filter(function (p) { return p.date === d[0]; }).forEach(function (p) {
        lines.push(["tt-line", capitalize(p.direction) + " call · " + RESULT_LABEL[resultOf(p)]]);
      });
      if (event.type === "keydown") {
        var box = plot.getBoundingClientRect(), scale = box.width / W;
        showTooltip({ type: "pointer", clientX: box.left + px * scale, clientY: box.top + py * scale }, lines);
      } else showTooltip(event, lines);
    }
    function nearestIndex(clientX) {
      var box = plot.getBoundingClientRect();
      var ms = xs[0] + ((clientX - box.left) * (W / box.width) - left) / (W - left - right) * (xs[xs.length - 1] - xs[0]);
      var best = 0;
      for (var k = 1; k < xs.length; k++) if (Math.abs(xs[k] - ms) < Math.abs(xs[best] - ms)) best = k;
      return best;
    }
    function hide() { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); hideTooltip(); }
    plot.addEventListener("pointermove", function (e) { showAt(nearestIndex(e.clientX), e); });
    plot.addEventListener("pointerleave", hide);
    plot.addEventListener("blur", hide);
    plot.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        showAt(active + (e.key === "ArrowRight" ? 1 : -1), e);
      }
    });
    area.appendChild(plot);

    // In the popup, the story and context are shown in their own sections below.
    if (area.classList.contains("modal-chart")) {
      if (calls.length) area.appendChild(el("p", { class: "stock-foot" },
        el("span", null,
          el("span", { class: "key" }, el("i", { style: "background:var(--good)" }), "Call right so far"),
          el("span", { class: "key" }, el("i", { style: "background:var(--bad)" }), "Call wrong so far"),
          el("span", { class: "key" }, el("i", { style: "border:2px solid var(--ink);width:6px;height:6px" }), "Too early to tell"),
          "▲ bullish · ▼ bearish")));
      var tbl = el("table", null,
        el("thead", null, el("tr", null, el("th", { text: "Date" }), el("th", { class: "r", text: "Close" }))),
        el("tbody", null, series.slice().reverse().map(function (d) {
          return el("tr", null, el("td", { class: "tab", text: fmtTableDate(d[0]) }), el("td", { class: "r tab", text: fmtPrice(d[1]) }));
        })));
      area.appendChild(el("details", null, el("summary", { text: "Show prices as a table" }),
        el("div", { class: "table-wrap", style: "max-height:260px;overflow-y:auto" }, tbl)));
      return;
    }

    // What's going on: the pick's reason (with its article) or the market-watch note.
    var story = el("div", { class: "stock-story" });
    if (item.kind === "pick") {
      var a = item.pick.article;
      story.appendChild(el("p", { class: "story-label", text: "Why the bot picked it · " + fmtLongDate(item.pick.date) }));
      story.appendChild(el("p", { text: item.pick.reason }));
      if (item.watchNote) story.appendChild(el("p", { class: "muted-note", text: "Market watch: " + item.watchNote }));
      if (a && safeUrl(a.url)) story.appendChild(el("p", { class: "read-more" },
        el("span", { class: "src", text: a.source }), " · ", articleLink(a.url, "Read the article ↗", null)));
    } else {
      var w = watchlist.find(function (x) { return x.ticker === t; }) || {};
      story.appendChild(el("p", { class: "story-label", text: "What's going on" + (w.note_date ? " · " + fmtLongDate(w.note_date) : "") }));
      story.appendChild(el("p", { text: item.note || "Claude's notes on the market-watch stocks arrive with the next morning run." }));
    }
    if (calls.length) story.appendChild(el("p", { class: "stock-foot" },
      el("span", { class: "key" }, el("i", { style: "background:var(--good)" }), "Call right so far"),
      el("span", { class: "key" }, el("i", { style: "background:var(--bad)" }), "Call wrong so far"),
      el("span", { class: "key" }, el("i", { style: "border:2px solid var(--ink);width:6px;height:6px" }), "Too early to tell"),
      "▲ bullish · ▼ bearish"));
    area.appendChild(story);

    var table = el("table", null,
      el("thead", null, el("tr", null, el("th", { text: "Date" }), el("th", { class: "r", text: "Close" }))),
      el("tbody", null, series.slice().reverse().map(function (d) {
        return el("tr", null, el("td", { class: "tab", text: fmtTableDate(d[0]) }), el("td", { class: "r tab", text: fmtPrice(d[1]) }));
      })));
    area.appendChild(el("details", null, el("summary", { text: "Show prices as a table" }),
      el("div", { class: "table-wrap", style: "max-height:320px;overflow-y:auto" }, table)));
  }

  // ---------------------------------------------------------------------------
  // The Record (searchable, sortable table)
  // ---------------------------------------------------------------------------

  var sortState = { key: "date", dir: "desc" };
  var PAGE = 20, recordLimit = PAGE;  // rows shown before "Show more"
  var ORDER = {
    confidence: { high: 3, medium: 2, low: 1 },
    correct: function (p) { return p.correct === true ? 2 : p.correct === null || p.correct === undefined ? 1 : 0; }
  };

  function sortValue(p, key) {
    if (key === "confidence") return ORDER.confidence[p.confidence] || 0;
    if (key === "correct") return ORDER.correct(p);
    return p[key];
  }

  function renderRecord() {
    var q = document.getElementById("q").value.trim().toLowerCase();
    var dir = document.getElementById("f-dir").value;
    var res = document.getElementById("f-res").value;
    var day = document.getElementById("f-date").value;

    var rows = picks.filter(function (p) {
      if (dir && p.direction !== dir) return false;
      if (res && resultOf(p) !== res) return false;
      if (day && p.date !== day) return false;
      if (q) {
        var hay = [p.ticker, p.company, p.reason].join(" ").toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });

    // Sort a copy; the original order breaks ties, so a day's picks stay in Claude's order.
    var indexed = rows.map(function (p, i) { return [p, i]; });
    indexed.sort(function (a, b) {
      var va = sortValue(a[0], sortState.key), vb = sortValue(b[0], sortState.key);
      var aMissing = va === null || va === undefined, bMissing = vb === null || vb === undefined;
      if (aMissing !== bMissing) return aMissing ? 1 : -1;  // blanks always last
      if (va < vb) return sortState.dir === "asc" ? -1 : 1;
      if (va > vb) return sortState.dir === "asc" ? 1 : -1;
      return a[1] - b[1];
    });

    var tbody = document.querySelector("#record-table tbody");
    clear(tbody);
    indexed.slice(0, recordLimit).forEach(function (pair) {
      var p = pair[0];
      tbody.appendChild(el("tr", null,
        el("td", { class: "tab", text: fmtTableDate(p.date) }),
        el("td", null, chartLink(p.ticker, p.ticker, "t-link") || el("span", { class: "t", text: p.ticker }),
          p.company ? el("span", { class: "co", text: p.company }) : null),
        el("td", { class: "tab", text: directionText(p) }),
        el("td", null, p.confidence ? [confidencePips(p.confidence), capitalize(p.confidence)] : "—"),
        el("td", { class: "r tab", text: fmtPrice(p.price_at_pick) }),
        el("td", { class: "r tab", text: fmtPrice(p.price_now) }),
        el("td", { class: "r tab", text: fmtPct(p.directional_return_pct) }),
        el("td", null, resultBadge(p)),
        el("td", { class: "why", text: p.reason })));
    });
    if (!indexed.length) {
      tbody.appendChild(el("tr", null, el("td", { colspan: 9, text: picks.length ? "No picks match these filters." : "No picks yet." })));
    }
    var shown = Math.min(indexed.length, recordLimit);
    document.getElementById("count").textContent = "Showing " + shown + " of " + indexed.length +
      (indexed.length === 1 ? " pick" : " picks") + (indexed.length < picks.length ? " (filtered from " + picks.length + ")" : "");
    var more = document.getElementById("record-more");
    more.hidden = indexed.length <= recordLimit;
    more.textContent = "Show " + Math.min(PAGE, indexed.length - shown) + " more picks";

    document.querySelectorAll("#record-table th[data-key]").forEach(function (th) {
      if (th.getAttribute("data-key") === sortState.key) th.setAttribute("aria-sort", sortState.dir === "asc" ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
  }

  function setupRecord() {
    var dateSelect = document.getElementById("f-date");
    days.forEach(function (d) { dateSelect.appendChild(el("option", { value: d.date, text: fmtTableDate(d.date) })); });
    ["q", "f-dir", "f-res", "f-date"].forEach(function (id) {
      document.getElementById(id).addEventListener("input", function () { recordLimit = PAGE; renderRecord(); });
    });
    document.getElementById("record-more").addEventListener("click", function () {
      recordLimit += PAGE;
      renderRecord();
    });
    document.querySelectorAll("#record-table th[data-key] button").forEach(function (button) {
      button.addEventListener("click", function () {
        var key = button.parentNode.getAttribute("data-key");
        if (sortState.key === key) sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
        else sortState = { key: key, dir: key === "ticker" || key === "direction" ? "asc" : "desc" };
        renderRecord();
      });
    });
    renderRecord();
  }

  // ---------------------------------------------------------------------------
  // News tab: the latest day's headlines as photo cards
  // ---------------------------------------------------------------------------

  var newsLimit = 24, newsOnlyPicks = false;

  function renderNews() {
    var grid = document.getElementById("news-grid");
    var more = document.getElementById("news-more");
    var note = document.getElementById("news-note");
    clear(grid);
    var day = days.find(function (d) { return d.headlines && d.headlines.length; });
    if (!day) {
      note.textContent = "";
      more.hidden = true;
      grid.appendChild(emptyChart("Headlines arrive with the next morning run",
        "Each weekday the bot saves the stories it read, with photos and links to the full articles. They'll show up here."));
      return;
    }
    // Stories behind the day's picks come first, then the rest in their original order.
    var all = day.headlines.slice().sort(function (a, b) { return (b.tickers.length > 0) - (a.tickers.length > 0); });
    var list = newsOnlyPicks ? all.filter(function (h) { return h.tickers.length; }) : all;
    note.textContent = fmtLongDate(day.date) + " · " + day.headlines.length + " stories · " +
      all.filter(function (h) { return h.tickers.length; }).length + " led to picks";

    list.slice(0, newsLimit).forEach(function (h) {
      var dirOf = function (t) {
        var p = picks.find(function (q) { return q.date === day.date && q.ticker === t; });
        return p && p.direction === "bearish" ? "▼ " : "▲ ";
      };
      grid.appendChild(el("article", { class: "news-card" + (h.tickers.length ? " led" : "") },
        photo(h.image, h.headline, "news-photo"),
        el("p", { class: "news-meta", text: h.source + " · " + fmtNewsTime(h.time) }),
        el("h3", null, articleLink(h.url, h.headline, null)),
        h.summary ? el("p", { class: "news-summary", text: h.summary }) : null,
        h.tickers.length ? el("div", { class: "chips" },
          el("span", { class: "led-label", text: "Led to" }),
          h.tickers.map(function (t) {
            return chartLink(t, dirOf(t) + t, "chip chip-link") || el("span", { class: "chip", text: dirOf(t) + t });
          })) : null));
    });
    more.hidden = list.length <= newsLimit;
  }

  // ---------------------------------------------------------------------------
  // Archive (one card per day)
  // ---------------------------------------------------------------------------

  var archiveLimit = 6;  // days shown before "Show older days"

  function renderArchive() {
    var list = document.getElementById("archive-list");
    var more = document.getElementById("archive-more");
    clear(list);
    more.hidden = days.length <= archiveLimit;
    if (!days.length) {
      list.appendChild(el("p", { text: "Past editions will be collected here." }));
      return;
    }
    days.slice(0, archiveLimit).forEach(function (d) {
      var parts = splitMood(d.market_mood);
      var dayPicks = picks.filter(function (p) { return p.date === d.date; });
      var chips = el("div", { class: "chips" }, dayPicks.map(function (p) {
        var r = resultOf(p);
        return el("span", { class: "chip", title: capitalize(p.direction) + " · " + RESULT_LABEL[r] },
          el("span", { class: r === "right" ? "glyph-good" : r === "wrong" ? "glyph-bad" : null, "aria-hidden": "true", text: r === "open" ? "○" : "●" }),
          (p.direction === "bullish" ? "▲ " : "▼ ") + p.ticker,
          el("span", { class: "visually-hidden", text: ", " + p.direction + ", " + RESULT_LABEL[r] }));
      }));
      var headlines = d.headlines || [];
      var reading = headlines.length
        ? el("details", null,
            el("summary", { text: "Headlines the bot read (" + headlines.length + ")" }),
            el("ul", null, headlines.map(function (h) {
              return el("li", null, articleLink(h.url, h.headline, "hl"), el("small", { text: h.source + " · " + fmtNewsTime(h.time) }));
            })))
        : el("p", { class: "hero-note", text: "Headlines weren't saved for this day." });
      list.appendChild(el("article", { class: "day" },
        el("time", { datetime: d.date, text: fmtLongDate(d.date) }),
        el("h3", { text: parts[0] || (dayPicks.length + " ideas from the news") }),
        parts[1] ? el("p", { text: parts[1] }) : null,
        chips,
        reading));
    });
  }

  // ---------------------------------------------------------------------------
  // Light / dark toggle (remembered in this browser only)
  // ---------------------------------------------------------------------------

  function setupTheme() {
    var root = document.documentElement;
    var button = document.getElementById("theme-toggle");
    var saved = null;
    try { saved = localStorage.getItem("theme"); } catch (e) { /* storage blocked: fine */ }
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);

    function isDark() {
      var t = root.getAttribute("data-theme");
      if (t) return t === "dark";
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    function label() { button.textContent = isDark() ? "Light mode" : "Dark mode"; }
    button.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
      label();
    });
    label();
  }

  // ---------------------------------------------------------------------------
  // Start
  // ---------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // Tabs: the menu links change the address (#today, #results, ...) and only
  // the matching section is shown. The back button and bookmarks work too.
  // ---------------------------------------------------------------------------

  var TABS = ["today", "news", "stock-charts", "results", "record", "archive", "about"];
  var OLD_LINKS = { scorecard: "results", charts: "results" };  // addresses used before tabs existed
  var currentTab = null;

  function tabFromHash() {
    var id = location.hash.replace("#", "");
    id = OLD_LINKS[id] || id;
    return TABS.indexOf(id) === -1 ? "today" : id;
  }

  function showTab() {
    var id = tabFromHash();
    var changed = id !== currentTab;
    currentTab = id;
    TABS.forEach(function (t) { document.getElementById(t).hidden = t !== id; });
    document.querySelectorAll(".sections a[data-tab]").forEach(function (a) {
      if (a.getAttribute("data-tab") === id) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    if (modalTicker) closeStockModal();
    hideTooltip();
    // Charts measure their width, so they're drawn once their tab is visible.
    renderVisibleCharts();
    if (changed) window.scrollTo(0, 0);
  }

  function renderVisibleCharts() {
    if (modalTicker) renderStockModal();
    if (currentTab === "stock-charts") renderStockSection();
    if (currentTab === "results") { renderCallsChart(); renderDaysChart(); }
  }

  setupTheme();
  renderMasthead();
  renderLead();
  renderScorecard();
  setupRecord();
  renderArchive();
  renderNews();
  document.getElementById("news-more").addEventListener("click", function () { newsLimit += 24; renderNews(); });
  document.getElementById("news-only").addEventListener("change", function (e) {
    newsOnlyPicks = e.target.checked;
    newsLimit = 24;
    renderNews();
  });
  window.addEventListener("hashchange", showTab);
  showTab();
  // Opening a bookmarked tab (e.g. .../#results) makes the browser jump to that
  // section; start at the top instead so the title and menu stay in view.
  // (app.js may load after the page has finished loading, so check both.)
  if (document.readyState === "complete") window.scrollTo(0, 0);
  else window.addEventListener("load", function () { window.scrollTo(0, 0); });
  document.getElementById("archive-more").addEventListener("click", function () {
    archiveLimit += 6;
    renderArchive();
  });

  // Redraw the charts when the window width changes (e.g. phone rotation).
  var lastWidth = window.innerWidth, timer = null;
  window.addEventListener("resize", function () {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(timer);
    timer = setTimeout(renderVisibleCharts, 150);
  });
})();
