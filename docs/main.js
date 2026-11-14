const SCENARIOS = ["ssp126", "ssp245", "ssp585"];
const NAMES = { ssp126: "Low emissions", ssp245: "Middle", ssp585: "High emissions" };
const COLORS = { ssp126: "#2a9d8f", ssp245: "#e9a23b", ssp585: "#c0392b" };
const STEP = 5; // grid cell size in degrees

const state = { scenario: "ssp585", yearIdx: 0, selected: null, timer: null };

// Warming colour: blue below 0, white at 0, red above. Clamped at the ends.
const color = d3.scaleDiverging(t => d3.interpolateRdBu(1 - t)).domain([-4, 0, 12]).clamp(true);

Promise.all([d3.json("data/warming.json"), d3.json("data/land-110m.json")]).then(([data, world]) => {
  const nLon = data.lons.length;
  const cells = [];
  data.lats.forEach((lat, i) => data.lons.forEach((lon, j) => {
    cells.push({ idx: i * nLon + j, lat, lon, geometry: cellPolygon(lat, lon) });
  }));

  // Start on the cell containing San Diego and the last time step.
  state.selected = cells.find(c => Math.abs(c.lat - 32.7) <= STEP / 2 && Math.abs(c.lon + 117.2) <= STEP / 2) || cells[0];
  state.yearIdx = data.years.length - 1;

  const slider = d3.select("#year").attr("max", data.years.length - 1).property("value", state.yearIdx);

  // ---- map ----
  const W = 960, H = 470;
  const projection = d3.geoEqualEarth().fitExtent([[4, 4], [W - 4, H - 4]], { type: "Sphere" });
  const path = d3.geoPath(projection);
  const svg = d3.select("#map").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
  svg.append("path").attr("class", "sphere").attr("d", path({ type: "Sphere" }));

  const cellSel = svg.append("g").selectAll("path").data(cells).join("path")
    .attr("class", "cell")
    .attr("d", d => path(d.geometry))
    .on("mousemove", (event, d) => showTooltip(event, d))
    .on("mouseleave", () => d3.select("#tooltip").attr("hidden", true))
    .on("click", (event, d) => { state.selected = d; update(); });

  svg.append("path").attr("class", "land")
    .attr("d", path(topojson.feature(world, world.objects.land)));

  drawLegend();

  // ---- detail chart ----
  const cw = 960, ch = 260, m = { t: 14, r: 150, b: 28, l: 44 };
  const chart = d3.select("#chart").append("svg").attr("viewBox", `0 0 ${cw} ${ch}`);
  const x = d3.scaleLinear().domain([data.years[0], data.years.at(-1) + STEP]).range([m.l, cw - m.r]);
  const y = d3.scaleLinear().range([ch - m.b, m.t]);
  const xAxis = chart.append("g").attr("class", "axis").attr("transform", `translate(0,${ch - m.b})`);
  const yAxis = chart.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`);
  chart.append("text").attr("class", "chart-label").attr("x", m.l + 4).attr("y", m.t + 2)
    .attr("fill", "#6b6b70").text("°C warming since 1850–1900");
  const nowLine = chart.append("line").attr("class", "now-line");
  const lineGroup = chart.append("g");
  const line = d3.line().x((v, k) => x(data.years[k] + STEP / 2)).y(v => y(v));

  // ---- controls ----
  d3.selectAll(".scenarios button").on("click", function () {
    state.scenario = this.dataset.s;
    d3.selectAll(".scenarios button").classed("on", false);
    d3.select(this).classed("on", true);
    update();
  });
  slider.on("input", function () { state.yearIdx = +this.value; update(); });
  d3.select("#play").on("click", togglePlay);

  d3.select("#search").on("submit", async event => {
    event.preventDefault();
    const q = d3.select("#city").property("value").trim();
    if (!q) return;
    const status = d3.select("#search-status").text("Searching…");
    try {
      const result = await geocode(q.split(",")[0].trim());
      if (!result) { status.text(`No match for “${q}”.`); return; }
      const cell = findCell(result.latitude, result.longitude);
      if (!cell) { status.text("That location is outside the grid."); return; }
      state.selected = cell;
      update();
      status.text(`${result.name}${result.admin1 ? ", " + result.admin1 : ""}, ${result.country} → cell ${place(cell)}`);
    } catch (err) {
      status.text("Search failed. Check your connection and try again.");
    }
  });

  async function geocode(name) {
    const url = "https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&format=json&name="
      + encodeURIComponent(name);
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.status);
    const json = await res.json();
    return json.results?.[0] ?? null;
  }

  let typingTimer;
  d3.select("#city").on("input", function () {
    clearTimeout(typingTimer);
    const q = this.value.trim();
    if (q.length < 2) return;
    typingTimer = setTimeout(async () => {
      try {
        const results = await geocodeMany(q);
        d3.select("#city-options").selectAll("option")
          .data(results, d => d.id)
          .join("option")
          .attr("value", d => label(d));
      } catch (err) { /* ignore: autocomplete is optional */ }
    }, 250);
  });

  async function geocodeMany(name) {
    const url = "https://geocoding-api.open-meteo.com/v1/search?count=8&language=en&format=json&name="
      + encodeURIComponent(name);
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.status);
    const json = await res.json();
    return json.results ?? [];
  }

  function label(r) {
    return [r.name, r.admin1, r.country].filter(Boolean).join(", ");
  }

  function findCell(lat, lon) {
  const h = STEP / 2;
  lon = ((lon + 180) % 360 + 360) % 360 - 180;   // normalize to [-180, 180)
  return cells.find(c => lat >= c.lat - h && lat < c.lat + h && lon >= c.lon - h && lon < c.lon + h) || null;
}

  update();

  function update() {
    const grid = data.grid[state.scenario][state.yearIdx];
    const g = data.global[state.scenario][state.yearIdx];
    cellSel.attr("fill", d => color(grid[d.idx])).attr("stroke", d => color(grid[d.idx]))  // stroke hides seams
      .classed("selected", d => d === state.selected);
    cellSel.filter(d => d === state.selected).raise();
    slider.property("value", state.yearIdx);
    d3.select("#year-label").text(yearRange(state.yearIdx));
    d3.select("#global-readout").html(`Global average: <b>${fmt(g)}</b>`);
    updateChart();
  }

  function updateChart() {
    const c = state.selected;
    d3.select("#detail-title").text(`${place(c)}: warming under each scenario`);
    const series = SCENARIOS.map(s => ({ s, values: data.grid[s].map(row => row[c.idx]) }));
    const globalVals = data.global[state.scenario];
    const all = series.flatMap(d => d.values).concat(globalVals);
    y.domain([Math.min(-1, d3.min(all)), Math.max(2, d3.max(all))]).nice();
    xAxis.call(d3.axisBottom(x).tickFormat(d3.format("d")).ticks(10));
    yAxis.call(d3.axisLeft(y).ticks(6));

    const yr = data.years[state.yearIdx] + STEP / 2;
    nowLine.attr("x1", x(yr)).attr("x2", x(yr)).attr("y1", m.t).attr("y2", ch - m.b);

    const rows = series.map(d => ({ ...d, cls: "series", stroke: COLORS[d.s], label: NAMES[d.s],
      width: d.s === state.scenario ? 3 : 1.5 }))
      .concat([{ s: "global", values: globalVals, cls: "global", stroke: "#222",
        label: "Global average", width: 1.5 }]);
    lineGroup.selectAll("g.row").data(rows, d => d.s).join(enter => {
      const gr = enter.append("g").attr("class", "row");
      gr.append("path");
      gr.append("text").attr("class", "chart-label").attr("dx", 6).attr("dy", "0.32em");
      return gr;
    }).each(function (d) {
      const gr = d3.select(this);
      gr.select("path").attr("class", d.cls).attr("stroke", d.stroke).attr("stroke-width", d.width)
        .attr("d", line(d.values));
      gr.select("text").attr("x", x(data.years.at(-1) + STEP / 2)).attr("y", y(d.values.at(-1)))
        .attr("fill", d.stroke).text(d.label);
    });
    // Keep the end labels from overlapping.
    const labels = lineGroup.selectAll("text").nodes().sort((a, b) => +a.getAttribute("y") - +b.getAttribute("y"));
    for (let k = 1; k < labels.length; k++) {
      const prev = +labels[k - 1].getAttribute("y"), cur = +labels[k].getAttribute("y");
      if (cur - prev < 13) labels[k].setAttribute("y", prev + 13);
    }
  }

  function showTooltip(event, d) {
    const v = data.grid[state.scenario][state.yearIdx][d.idx];
    const g = data.global[state.scenario][state.yearIdx];
    const ratio = g > 0.3 ? `${(v / g).toFixed(1)}× the global average` : "global average still near 0";
    d3.select("#tooltip").attr("hidden", null)
      .style("left", `${event.clientX + 14}px`).style("top", `${event.clientY + 14}px`)
      .html(`<div class="dim">${place(d)} · ${yearRange(state.yearIdx)}</div>
             <div class="big">${fmt(v)}</div>
             <div>${ratio}</div>
             <div class="dim">${NAMES[state.scenario]}</div>`);
  }

  function togglePlay() {
    if (state.timer) { stop(); return; }
    if (state.yearIdx === data.years.length - 1) state.yearIdx = 0;
    d3.select("#play").text("❚❚").attr("aria-label", "Pause");
    state.timer = d3.interval(() => {
      if (state.yearIdx >= data.years.length - 1) { stop(); return; }
      state.yearIdx += 1;
      update();
    }, 350);
  }
  function stop() {
    state.timer.stop(); state.timer = null;
    d3.select("#play").text("▶").attr("aria-label", "Play");
  }

  function yearRange(i) { return `${data.years[i]}–${data.years[i] + STEP - 1}`; }
});

// A 5° cell as a GeoJSON polygon, edges densified so they follow the projection's curves.
// Ring order is clockwise (d3-geo's convention for "the small polygon, not the rest of the globe").
function cellPolygon(lat, lon) {
  const h = STEP / 2, x0 = lon - h, x1 = lon + h, y0 = lat - h, y1 = lat + h;
  const ring = [];
  for (let y = y0; y < y1; y += 1) ring.push([x0, y]);
  for (let x = x0; x < x1; x += 1) ring.push([x, y1]);
  for (let y = y1; y > y0; y -= 1) ring.push([x1, y]);
  for (let x = x1; x > x0; x -= 1) ring.push([x, y0]);
  ring.push([x0, y0]);
  return { type: "Polygon", coordinates: [ring] };
}

function fmt(v) { return `${v > 0 ? "+" : ""}${v.toFixed(1)} °C`; }

function place(d) {
  const la = `${Math.abs(d.lat).toFixed(1)}°${d.lat >= 0 ? "N" : "S"}`;
  const lo = `${Math.abs(d.lon).toFixed(1)}°${d.lon >= 0 ? "E" : "W"}`;
  return `${la}, ${lo}`;
}

function drawLegend() {
  const w = 380, h = 44, pad = 24;
  const svg = d3.select("#legend").append("svg").attr("width", w).attr("height", h);
  const defs = svg.append("defs").append("linearGradient").attr("id", "grad");
  const [lo, , hi] = color.domain();
  d3.range(0, 1.0001, 0.05).forEach(t => defs.append("stop")
    .attr("offset", `${t * 100}%`).attr("stop-color", color(lo + t * (hi - lo))));
  svg.append("rect").attr("x", pad).attr("y", 4).attr("width", w - 2 * pad).attr("height", 12)
    .attr("fill", "url(#grad)");
  const s = d3.scaleLinear().domain([lo, hi]).range([pad, w - pad]);
  svg.append("g").attr("class", "axis").attr("transform", "translate(0,16)")
    .call(d3.axisBottom(s).tickValues([-4, 0, 4, 8, 12]).tickFormat(v => v === hi ? `${v}+ °C` : `${v > 0 ? "+" : ""}${v}`))
    .call(g => g.select(".domain").remove());
}
