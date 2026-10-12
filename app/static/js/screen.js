/* Render one built screen from its spec. Panels use the envelope contract. */
(function () {
  "use strict";

  function escapeHTML(text) {
    const div = document.createElement("div");
    div.textContent = String(text || "");
    return div.innerHTML;
  }

  async function getJSON(url) {
    const response = await fetch(url);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `request failed (${response.status})`);
    return data;
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `request failed (${response.status})`);
    return data;
  }

  function builtinQuery(session, params) {
    return new URLSearchParams(Object.assign({}, session, params || {}));
  }

  async function panelEnvelope(panel) {
    const session = panel.session || {};
    const params = panel.params || {};
    if (panel.type === "registered") {
      return postJSON(`/server/api/registry/${encodeURIComponent(panel.fn)}/run`, {
        params,
        session,
      });
    }
    switch (panel.fn) {
      case "trackmap":
        return getJSON(`/server/api/analysis/trackmap?${builtinQuery(session, params)}`);
      case "telemetry":
        return getJSON(`/server/api/analysis/telemetry?${builtinQuery(session, params)}`);
      case "lap-times": {
        const query = new URLSearchParams({
          year: session.year,
          round: session.round,
          code: session.code,
        });
        if (params.drivers) query.set("drivers", params.drivers.join(","));
        return getJSON(`/server/api/analysis/lap-times?${query}`);
      }
      case "compare":
        return postJSON("/server/api/analysis/compare", Object.assign({ session }, params));
      default:
        throw new Error(`unknown panel function: ${panel.fn}`);
    }
  }

  (async function () {
    const screenId = window.SCREEN_ID;
    const title = document.getElementById("screen-title");
    const instruction = document.getElementById("screen-instruction");
    const container = document.getElementById("screen-panels");
    try {
      const data = await getJSON(`/builder/screens/${encodeURIComponent(screenId)}`);
      const spec = data.screen;
      title.textContent = spec.title || spec.id;
      document.title = `${spec.title || spec.id} — Telemetry Tracker`;
      instruction.textContent = spec.instruction || "";
      for (const panel of spec.panels || []) {
        const box = document.createElement("div");
        box.className = "panel chart-panel";
        const heading = document.createElement("h2");
        heading.textContent = panel.title || spec.title || "Analysis";
        const chart = document.createElement("div");
        chart.className = "chart chart-tall";
        chart.innerHTML = "<p class='hint'>Loading…</p>";
        box.appendChild(heading);
        box.appendChild(chart);
        container.appendChild(box);
        panelEnvelope(panel)
          .then((envelope) => TTCharts.renderEnvelope(chart, envelope))
          .catch((error) => {
            chart.innerHTML = `<p class='hint'>${escapeHTML(error.message)}</p>`;
          });
      }
    } catch (error) {
      title.textContent = "Screen not available";
      instruction.textContent = error.message;
    }
  })();
})();
