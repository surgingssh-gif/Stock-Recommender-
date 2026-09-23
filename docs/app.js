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
    var move = p.return_pct === null || p.return_pct === undefined ? "No price yet" : fmtPct(p.return_pct) + " since pick";
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
    return el("article", { class: "story " + cls },
      el("div", { class: "story-top" }, el("div", null, title, tags), price),
      el("p", { class: "reason", text: p.reason }));
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
  // Stock charts (one big price chart, pick a stock and a time range)
  // ---------------------------------------------------------------------------

  var charts = DATA.charts || {};
  var RANGES = [["1M", 31], ["3M", 92], ["6M", 183], ["All", 0]];
  var RANGE_WORDS = { "1M": "the past month", "3M": "the past 3 months", "6M": "the past 6 months", "All": "the full period" };
  var stockState = { ticker: null, range: "3M" };

  /* Tickers in a helpful order: today's picks first, then by most recent pick. */
  function chartTickers() {
    var order = [];
    picks.forEach(function (p) { if (charts[p.ticker] && order.indexOf(p.ticker) === -1) order.push(p.ticker); });
    return order;
  }

  function companyOf(ticker) {
    var p = picks.find(function (q) { return q.ticker === ticker && q.company; });
    return p ? p.company : "";
  }

  function toMs(s) { return toDate(s).getTime(); }

  /* Jump to a stock's chart (used by the "Chart →" links). */
  function openStockChart(ticker) {
    if (!charts[ticker]) return;
    stockState.ticker = ticker;
    if (location.hash === "#stock-charts") renderStockSection();
    else location.hash = "stock-charts";  // switches tabs (see showTab below)
  }

  function chartLink(ticker, text, cls) {
    if (!charts[ticker]) return null;
    var a = el("a", { href: "#stock-charts", class: cls, text: text });
    a.addEventListener("click", function (e) { e.preventDefault(); openStockChart(ticker); });
    return a;
  }

  function renderStockSection() {
    var area = document.getElementById("stock-area");
    clear(area);
    var tickers = chartTickers();
    if (!tickers.length) {
      area.appendChild(emptyChart("Charts appear with the first picks", "Once the bot has made some calls, their price charts show up here."));
      return;
    }
    if (tickers.indexOf(stockState.ticker) === -1) stockState.ticker = tickers[0];

    // --- Controls: stock buttons (first 8) + a menu for the rest, and ranges.
    var picker = el("div", { class: "ticker-picker", role: "group", "aria-label": "Choose a stock" });
    tickers.slice(0, 8).forEach(function (t) {
      var b = el("button", { type: "button", class: "pill", "aria-pressed": String(t === stockState.ticker), text: t });
      b.addEventListener("click", function () { stockState.ticker = t; renderStockSection(); });
      picker.appendChild(b);
    });
    if (tickers.length > 8) {
      var more = el("select", { "aria-label": "More stocks" }, el("option", { value: "", text: "More…" }),
        tickers.slice(8).map(function (t) { return el("option", { value: t, text: t, selected: t === stockState.ticker ? "selected" : null }); }));
      more.addEventListener("change", function () { if (more.value) { stockState.ticker = more.value; renderStockSection(); } });
      picker.appendChild(more);
    }
    var ranges = el("div", { class: "range-picker", role: "group", "aria-label": "Time range" });
    RANGES.forEach(function (r) {
      var b = el("button", { type: "button", class: "pill", "aria-pressed": String(r[0] === stockState.range), text: r[0] });
      b.addEventListener("click", function () { stockState.range = r[0]; renderStockSection(); });
      ranges.appendChild(b);
    });
    area.appendChild(el("div", { class: "stock-controls" }, picker, ranges));

    // --- The data for this stock and range.
    var t = stockState.ticker;
    var full = charts[t];
    var days = RANGES.find(function (r) { return r[0] === stockState.range; })[1];
    var cutoff = days ? toMs(full[full.length - 1][0]) - days * 86400000 : -Infinity;
    var series = full.filter(function (d) { return toMs(d[0]) >= cutoff; });
    if (series.length < 2) series = full.slice(-2);
    var first = series[0][1], last = series[series.length - 1][1];
    var change = (last - first) / first * 100;

    area.appendChild(el("div", { class: "stock-head" },
      el("h3", null, el("span", { class: "ticker", text: t }), companyOf(t)),
      el("div", { class: "stock-price" },
        el("div", { class: "now", text: fmtPrice(last) }),
        el("div", { class: "chg", text: fmtPct(change) + " over " + RANGE_WORDS[stockState.range] }))));

    // The bot's calls on this stock that fall inside the range.
    var calls = picks.filter(function (p) { return p.ticker === t && toMs(p.date) >= toMs(series[0][0]); });

    // --- Geometry.
    var W = Math.max(300, area.clientWidth);
    var narrow = W < 560;
    var H = narrow ? 230 : 320, left = 6, right = 56, top = 14, bottom = 26;
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

    // Price line with a light wash underneath.
    var line = series.map(function (d, i) { return (i ? "L" : "M") + x(xs[i]).toFixed(1) + "," + y(d[1]).toFixed(1); }).join("");
    var areaPath = line + "L" + x(xs[xs.length - 1]).toFixed(1) + "," + (H - bottom) + "L" + x(xs[0]).toFixed(1) + "," + (H - bottom) + "Z";
    plot.appendChild(svg("path", { d: areaPath, fill: "var(--ink)", opacity: 0.05 }));
    plot.appendChild(svg("path", { d: line, fill: "none", stroke: "var(--ink)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));

    // A dot for each call, placed at the price when it was picked.
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
    var dot = svg("circle", { r: 4, fill: "var(--ink)", stroke: "var(--paper)", "stroke-width": 2, visibility: "hidden" });
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

    // Key for the dots, plus the same prices as a table.
    var foot = el("div", { class: "stock-foot" },
      calls.length ? el("span", null,
        el("span", { class: "key" }, el("i", { style: "background:var(--good)" }), "Call right so far"),
        el("span", { class: "key" }, el("i", { style: "background:var(--bad)" }), "Call wrong so far"),
        el("span", { class: "key" }, el("i", { style: "border:2px solid var(--ink);width:6px;height:6px" }), "Too early to tell"),
        "▲ bullish · ▼ bearish") : el("span", { text: "No calls on this stock in this time range." }),
      el("span", { text: "Prices from Yahoo Finance" }));
    area.appendChild(foot);

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
              return el("li", null, h.headline, el("small", { text: h.source + " · " + h.time }));
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

  var TABS = ["today", "stock-charts", "results", "record", "archive", "about"];
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
    hideTooltip();
    // Charts measure their width, so they're drawn once their tab is visible.
    renderVisibleCharts();
    if (changed) window.scrollTo(0, 0);
  }

  function renderVisibleCharts() {
    if (currentTab === "stock-charts") renderStockSection();
    if (currentTab === "results") { renderCallsChart(); renderDaysChart(); }
  }

  setupTheme();
  renderMasthead();
  renderLead();
  renderScorecard();
  setupRecord();
  renderArchive();
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
