/* Render the envelope contract with Plotly. See agent.md, section 3. */
(function () {
  "use strict";

  const axisStyle = { gridcolor: "#2a313b", zerolinecolor: "#2a313b", color: "#93a0b0" };
  const layoutBase = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#e8ecf1", size: 12 },
    margin: { l: 56, r: 16, t: 8, b: 42 },
    legend: { orientation: "h", y: -0.25 },
    hovermode: "x unified",
  };
  const config = {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
  };

  /* Speed heatmap: green = slow, yellow = medium, red = fast. */
  const SPEED_STOPS = [
    [0.0, [0, 200, 83]],
    [0.5, [255, 214, 0]],
    [1.0, [255, 23, 68]],
  ];
  const SPEED_COLORSCALE = [
    [0, "rgb(0,200,83)"],
    [0.5, "rgb(255,214,0)"],
    [1, "rgb(255,23,68)"],
  ];

  let animation = null;

  function speedColor(value, vmin, vmax) {
    if (typeof value !== "number" || !isFinite(value)) return "rgb(120,127,138)";
    const span = vmax - vmin;
    const t = span > 0 ? Math.min(1, Math.max(0, (value - vmin) / span)) : 0.5;
    let lower = SPEED_STOPS[0];
    let upper = SPEED_STOPS[SPEED_STOPS.length - 1];
    for (let index = 1; index < SPEED_STOPS.length; index += 1) {
      if (t <= SPEED_STOPS[index][0]) {
        lower = SPEED_STOPS[index - 1];
        upper = SPEED_STOPS[index];
        break;
      }
    }
    const range = upper[0] - lower[0] || 1;
    const f = (t - lower[0]) / range;
    const rgb = lower[1].map((channel, index) =>
      Math.round(channel + (upper[1][index] - channel) * f)
    );
    return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
  }

  /* -------------------- track map play/pause animation ------------------ */

  function updatePlayButton() {
    const button = document.getElementById("trackmap-play");
    if (!button) return;
    button.textContent = animation && animation.playing ? "Pause" : "Play";
    button.disabled = !animation;
  }

  function stopTrackmapAnimation() {
    if (!animation) return;
    if (animation.raf) cancelAnimationFrame(animation.raf);
    animation = null;
    updatePlayButton();
  }

  function tick(timestamp) {
    if (!animation || !animation.playing) return;
    if (animation.start === null) animation.start = timestamp;
    const elapsed = animation.offset + (timestamp - animation.start) / 1000;
    const fraction = (elapsed % animation.duration) / animation.duration;
    const index = Math.min(
      animation.x.length - 1,
      Math.max(0, Math.floor(fraction * (animation.x.length - 1)))
    );
    if (index !== animation.index) {
      animation.index = index;
      Plotly.restyle(
        animation.div,
        { x: [[animation.x[index]]], y: [[animation.y[index]]] },
        [animation.traceIndex]
      );
    }
    animation.raf = requestAnimationFrame(tick);
  }

  function playTrackmap() {
    if (!animation) return;
    animation.playing = true;
    animation.start = null;
    animation.raf = requestAnimationFrame(tick);
    updatePlayButton();
  }

  function pauseTrackmap() {
    if (!animation) return;
    if (animation.start !== null) {
      animation.offset += (performance.now() - animation.start) / 1000;
    }
    animation.playing = false;
    animation.start = null;
    if (animation.raf) cancelAnimationFrame(animation.raf);
    animation.raf = null;
    updatePlayButton();
  }

  const playButton = document.getElementById("trackmap-play");
  if (playButton) {
    playButton.addEventListener("click", () => {
      if (!animation) return;
      if (animation.playing) pauseTrackmap();
      else playTrackmap();
    });
  }

  /* ------------------------------ renderers ----------------------------- */

  function xValues(env, series) {
    if (env.x && env.x.values) return env.x.values;
    return (series.values || []).map((_, index) => index);
  }

  function xTitle(env) {
    if (!env.x || !env.x.name) return "";
    const unit = env.x.unit ? ` (${env.x.unit})` : "";
    return `${env.x.name}${unit}`;
  }

  function yTitle(env) {
    const meta = env.meta || {};
    const name = meta.channel || meta.mode || "";
    const unit = meta.unit ? ` (${meta.unit})` : "";
    return `${name}${unit}`;
  }

  function lineTraces(env) {
    const unit = (env.meta || {}).unit;
    return (env.series || [])
      .filter((series) => Array.isArray(series.values))
      .map((series) => ({
        x: xValues(env, series),
        y: series.values,
        type: "scattergl",
        mode: "lines",
        name: series.label,
        connectgaps: false,
        line: {
          color: series.color || undefined,
          width: series.dash ? 1.5 : 2,
          dash: series.dash ? "dash" : "solid",
        },
        hovertemplate: unit ? `%{y:.2f} ${unit}<extra>%{fullData.name}</extra>` : undefined,
      }));
  }

  function renderTelemetry(div, env) {
    const layout = Object.assign({}, layoutBase, {
      xaxis: Object.assign({ title: xTitle(env) }, axisStyle),
      yaxis: Object.assign({ title: yTitle(env) }, axisStyle),
    });
    Plotly.react(div, lineTraces(env), layout, config);
  }

  function renderTrackmap(div, env) {
    stopTrackmapAnimation();
    const series = (env.series || [])[0] || {};
    const meta = env.meta || {};
    const x = series.x || [];
    const y = series.y || [];
    const values = Array.isArray(series.values) ? series.values : [];
    const finite = values.filter((value) => typeof value === "number" && isFinite(value));
    const vmin = typeof meta.vmin === "number" ? meta.vmin : finite.length ? Math.min(...finite) : 0;
    const vmax = typeof meta.vmax === "number" ? meta.vmax : finite.length ? Math.max(...finite) : 1;
    const heatColors = x.map((_, index) => speedColor(values[index], vmin, vmax));
    const unit = meta.unit ? ` (${meta.unit})` : "";
    const traces = [
      {
        /* Grey background: the full track, built from interpolated points. */
        x,
        y,
        type: "scatter",
        mode: "lines",
        line: { color: "#454d59", width: 12 },
        hoverinfo: "skip",
        showlegend: false,
      },
      {
        /* Speed heatmap: the track line is 2 px wider than the driver dot. */
        x,
        y,
        type: "scatter",
        mode: "lines",
        line: { color: heatColors, width: 8 },
        customdata: values,
        hovertemplate: `${meta.channel || "value"}: %{customdata}${unit}<extra></extra>`,
        showlegend: false,
      },
      {
        /* Invisible trace that carries the colorbar. */
        x: x.length ? [x[0]] : [],
        y: y.length ? [y[0]] : [],
        type: "scatter",
        mode: "markers",
        marker: {
          size: 0.5,
          color: [vmin, vmax],
          colorscale: SPEED_COLORSCALE,
          showscale: true,
          colorbar: {
            thickness: 10,
            len: 0.55,
            tickfont: { color: "#93a0b0" },
            title: { text: (meta.channel || "") + unit, font: { color: "#93a0b0" } },
          },
        },
        hoverinfo: "skip",
        showlegend: false,
      },
      {
        /* The driver dot. The play button moves it across the track. */
        x: x.length ? [x[0]] : [],
        y: y.length ? [y[0]] : [],
        type: "scatter",
        mode: "markers",
        marker: { size: 6, color: "#ffffff", line: { width: 2, color: "#101318" } },
        hoverinfo: "skip",
        showlegend: false,
      },
    ];
    const layout = Object.assign({}, layoutBase, {
      xaxis: Object.assign({ visible: false }, axisStyle),
      yaxis: Object.assign({ visible: false, scaleanchor: "x" }, axisStyle),
      margin: { l: 10, r: 10, t: 10, b: 10 },
      showlegend: false,
      hovermode: "closest",
    });
    Promise.resolve(Plotly.react(div, traces, layout, config)).then(() => {
      if (x.length > 1) {
        animation = {
          div,
          x,
          y,
          traceIndex: traces.length - 1,
          index: 0,
          duration:
            typeof meta.lap_time_s === "number" && meta.lap_time_s > 0 ? meta.lap_time_s : 90,
          playing: false,
          start: null,
          offset: 0,
          raf: null,
        };
      }
      updatePlayButton();
    });
  }

  function renderBarchart(div, env) {
    const series = (env.series || [])[0] || { values: [] };
    const meta = env.meta || {};
    const text = (meta.gap_s || []).map((gap) => (gap === 0 ? "fastest" : `+${gap}`));
    const layout = Object.assign({}, layoutBase, {
      xaxis: Object.assign({ title: xTitle(env) }, axisStyle),
      yaxis: Object.assign({ title: yTitle(env) }, axisStyle),
      hovermode: "closest",
    });
    Plotly.react(
      div,
      [
        {
          x: (env.x || {}).values || [],
          y: series.values,
          type: "bar",
          marker: { color: meta.colors || "#e10600" },
          text: text.length ? text : undefined,
          textposition: "outside",
          textfont: { color: "#93a0b0" },
        },
      ],
      layout,
      config
    );
  }

  function renderImage(div, env) {
    div.innerHTML = "";
    const image = document.createElement("img");
    image.src = `data:${env.mime || "image/png"};base64,${env.data_base64}`;
    image.alt = "analysis output";
    image.style.maxWidth = "100%";
    div.appendChild(image);
  }

  function renderEnvelope(div, env) {
    if (!env || typeof env !== "object") {
      div.innerHTML = "<p class='hint'>No data.</p>";
      return;
    }
    if (env.kind === "trackmap") return renderTrackmap(div, env);
    if (env.kind === "barchart") return renderBarchart(div, env);
    if (env.kind === "image") return renderImage(div, env);
    if (Array.isArray(env.series)) return renderTelemetry(div, env);
    div.innerHTML = "";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(env, null, 2);
    div.appendChild(pre);
  }

  window.TTCharts = { renderEnvelope, stopTrackmapAnimation };
})();
