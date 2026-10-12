/* Main screen logic: events, sessions, drivers, timeline, compare, builder. */
(function () {
  "use strict";

  const state = {
    events: [],
    event: null,
    sessions: [],
    session: null,
    drivers: [],
    primary: null,
    laps: {},
    fastest: {},
    currentLap: {},
  };

  const $ = (id) => document.getElementById(id);
  const server = (path) => `/server/api/${path}`;

  /* ------------------------------- Tabs -------------------------------- */

  function showTab(name) {
    for (const button of document.querySelectorAll(".tab-button")) {
      button.classList.toggle("active", button.dataset.tab === name);
    }
    for (const page of document.querySelectorAll(".tab-page")) {
      page.classList.toggle("active", page.id === `tab-${name}`);
    }
  }

  for (const button of document.querySelectorAll(".tab-button")) {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  }

  function setStatus(text, kind) {
    const banner = $("status-banner");
    banner.textContent = text || "";
    banner.className = `status-banner ${kind || ""}`;
    if (!text) banner.classList.add("hidden");
  }

  async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error(`bad response (${response.status})`);
    }
    if (!response.ok) throw new Error(data.error || `request failed (${response.status})`);
    return data;
  }

  function eventLabel(event) {
    return `${event.year} · R${event.round} · ${event.name}`;
  }

  /* ------------------------------- Events ------------------------------ */

  async function init() {
    try {
      const data = await fetchJSON(server("events?years=2"));
      state.events = data.events;
      const list = $("event-list");
      list.innerHTML = "";
      for (const event of state.events) {
        const option = document.createElement("option");
        option.value = eventLabel(event);
        list.appendChild(option);
      }
      const latest = state.events.find((event) => event.completed) || state.events[0];
      if (latest) {
        $("event-input").value = eventLabel(latest);
        await selectEvent(latest);
      }
    } catch (error) {
      setStatus(`Cannot reach the data server. Start all services with ./run.sh (${error.message})`, "error");
    }
  }

  $("event-input").addEventListener("change", () => {
    const event = state.events.find((item) => eventLabel(item) === $("event-input").value);
    if (event) selectEvent(event);
  });

  async function selectEvent(event) {
    state.event = event;
    try {
      const data = await fetchJSON(server(`events/${event.year}/${event.round}/sessions`));
      state.sessions = data.sessions;
      const select = $("session-select");
      select.innerHTML = "";
      for (const item of state.sessions) {
        const option = document.createElement("option");
        option.value = item.code;
        option.textContent = item.completed ? item.name : `${item.name} (not started)`;
        option.disabled = !item.completed;
        select.appendChild(option);
      }
      select.disabled = false;
      const latest = [...state.sessions].reverse().find((item) => item.completed);
      if (latest) {
        select.value = latest.code;
        prepareSession(latest.code);
      } else {
        setStatus("No completed session for this event.", "error");
      }
    } catch (error) {
      setStatus(`Cannot load sessions: ${error.message}`, "error");
    }
  }

  $("session-select").addEventListener("change", () => prepareSession($("session-select").value));

  /* ------------------------------ Session ------------------------------ */

  function resetSessionView() {
    state.drivers = [];
    state.primary = null;
    state.laps = {};
    state.fastest = {};
    state.currentLap = {};
    TTCharts.stopTrackmapAnimation();
    const playButton = $("trackmap-play");
    if (playButton) playButton.disabled = true;
    showTab("trackmap");
    $("drivers").innerHTML = "<p class='hint'>Loading session…</p>";
    $("timeline").innerHTML = "<p class='hint'>Loading session…</p>";
    $("trackmap").innerHTML = "<p class='hint'>Loading session…</p>";
    $("minitelemetry").innerHTML = "<p class='hint'>Loading session…</p>";
    $("results").innerHTML = "<p class='hint'>Loading session…</p>";
    $("compare-button").disabled = true;
  }

  async function prepareSession(code) {
    state.session = { year: state.event.year, round: state.event.round, code };
    resetSessionView();
    setStatus(`Loading ${state.event.name} · ${code}. First load can take minutes…`, "busy");
    try {
      await fetchJSON(server(`session/${state.session.year}/${state.session.round}/${code}/prepare`), {
        method: "POST",
      });
      pollSession();
    } catch (error) {
      setStatus(`Cannot start the session load: ${error.message}`, "error");
    }
  }

  async function pollSession() {
    const { year, round, code } = state.session;
    try {
      const status = await fetchJSON(server(`session/${year}/${round}/${code}/status`));
      if (status.state === "ready") {
        setStatus(`Session ready: ${state.event.name} · ${code}`, "ok");
        await onSessionReady();
        return;
      }
      if (status.state === "error") {
        setStatus(`Session load failed: ${status.error || "unknown error"}`, "error");
        return;
      }
    } catch (error) {
      setStatus(`Cannot read the session state: ${error.message}`, "error");
      return;
    }
    setTimeout(pollSession, 2000);
  }

  async function onSessionReady() {
    const data = await fetchJSON(server(sessionPath("drivers")));
    state.drivers = data.drivers;
    renderDrivers("");
    fillDriverSelects();
    if (state.drivers.length) {
      await setPrimary(state.drivers[0].code);
      drawTrackmap(null);
    }
  }

  function sessionPath(tail) {
    const { year, round, code } = state.session;
    return `session/${year}/${round}/${code}/${tail}`;
  }

  /* ------------------------------ Drivers ------------------------------ */

  function renderDrivers(filter) {
    const container = $("drivers");
    container.innerHTML = "";
    const needle = (filter || "").toLowerCase();
    const visible = state.drivers.filter(
      (driver) =>
        !needle ||
        driver.code.toLowerCase().includes(needle) ||
        driver.name.toLowerCase().includes(needle) ||
        driver.team.toLowerCase().includes(needle)
    );
    if (!visible.length) {
      container.innerHTML = "<p class='hint'>No driver found.</p>";
      return;
    }
    for (const driver of visible) {
      const row = document.createElement("div");
      row.className = "driver" + (driver.code === state.primary ? " active" : "");
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = driver.color || "#888";
      const code = document.createElement("span");
      code.className = "code";
      code.textContent = driver.code;
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = driver.name;
      row.appendChild(dot);
      row.appendChild(code);
      row.appendChild(name);
      row.addEventListener("click", () => setPrimary(driver.code));
      container.appendChild(row);
    }
  }

  $("driver-search").addEventListener("input", () => renderDrivers($("driver-search").value));

  async function setPrimary(code) {
    state.primary = code;
    renderDrivers($("driver-search").value);
    await ensureLaps(code);
    const fastest = state.fastest[code] || null;
    state.currentLap[code] = fastest;
    drawTimeline();
    drawTrackmap(code);
    drawMiniTelemetry(code, state.currentLap[code]);
    fillCompareDefaults();
  }

  async function ensureLaps(code) {
    if (state.laps[code]) return;
    const data = await fetchJSON(server(`${sessionPath("laps")}?driver=${encodeURIComponent(code)}`));
    state.laps[code] = data.laps;
    state.fastest[code] = data.fastest;
  }

  function fillDriverSelects() {
    for (const id of ["driver-a", "driver-b"]) {
      const select = $(id);
      select.innerHTML = "";
      for (const driver of state.drivers) {
        const option = document.createElement("option");
        option.value = driver.code;
        option.textContent = `${driver.code} — ${driver.name}`;
        select.appendChild(option);
      }
    }
    $("driver-a").addEventListener("change", () => fillLapSelect("lap-a", $("driver-a").value));
    $("driver-b").addEventListener("change", () => fillLapSelect("lap-b", $("driver-b").value));
  }

  async function fillLapSelect(id, driver) {
    await ensureLaps(driver);
    const select = $(id);
    select.innerHTML = "";
    for (const lap of state.laps[driver] || []) {
      const option = document.createElement("option");
      option.value = lap.number;
      option.textContent = `L${lap.number}`;
      select.appendChild(option);
    }
    select.value = state.fastest[driver] ?? "";
  }

  function fillCompareDefaults() {
    const codes = state.drivers.map((driver) => driver.code);
    if (codes.length >= 2) {
      if (!$("driver-a").value) $("driver-a").value = codes[0];
      if (!$("driver-b").value) $("driver-b").value = codes[1];
    }
    fillLapSelect("lap-a", $("driver-a").value);
    fillLapSelect("lap-b", $("driver-b").value);
    $("compare-button").disabled = false;
  }

  /* ------------------------------ Charts ------------------------------- */

  async function drawTrackmap(driver) {
    const query = new URLSearchParams({
      year: state.session.year,
      round: state.session.round,
      code: state.session.code,
    });
    if (driver) query.set("driver", driver);
    try {
      const env = await fetchJSON(server(`analysis/trackmap?${query}`));
      const meta = env.meta || {};
      $("trackmap-title").textContent = `Track map — ${meta.driver || ""} L${meta.lap || ""} (fastest lap)`;
      TTCharts.renderEnvelope($("trackmap"), env);
    } catch (error) {
      $("trackmap").innerHTML = `<p class='hint'>${error.message}</p>`;
    }
  }

  async function drawMiniTelemetry(driver, lap) {
    if (!driver) return;
    const query = new URLSearchParams({
      year: state.session.year,
      round: state.session.round,
      code: state.session.code,
      driver,
      channel: "Speed",
      axis: "distance",
    });
    if (lap) query.set("lap", lap);
    try {
      const env = await fetchJSON(server(`analysis/telemetry?${query}`));
      $("mini-title").textContent = `Telemetry — ${driver} L${lap || ""} · Speed`;
      TTCharts.renderEnvelope($("minitelemetry"), env);
    } catch (error) {
      $("minitelemetry").innerHTML = `<p class='hint'>${error.message}</p>`;
    }
  }

  function drawTimeline() {
    const code = state.primary;
    if (!code) return;
    $("timeline-title").textContent = `Timeline — ${code}`;
    TTTimeline.drawTimeline(
      $("timeline"),
      state.laps[code] || [],
      state.currentLap[code],
      state.fastest[code],
      (lapNumber) => {
        state.currentLap[code] = lapNumber;
        drawTimeline();
        drawMiniTelemetry(code, lapNumber);
      }
    );
  }

  /* ------------------------------ Compare ------------------------------ */

  $("compare-button").addEventListener("click", runCompare);

  async function runCompare() {
    const refs = [
      { driver: $("driver-a").value, lap: Number($("lap-a").value) },
      { driver: $("driver-b").value, lap: Number($("lap-b").value) },
    ];
    const channel = $("channel").value;
    const normalize = $("normalize").value;
    setStatus(`Comparing ${refs[0].driver} L${refs[0].lap} against ${refs[1].driver} L${refs[1].lap}…`, "busy");
    try {
      const env = await fetchJSON(server("analysis/compare"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: state.session, refs, channel, normalize, delta: true }),
      });
      setStatus("", "");
      showTab("comparison");
      const container = $("results");
      container.innerHTML = "";
      const mainBox = document.createElement("div");
      mainBox.className = "chart chart-tall";
      container.appendChild(mainBox);
      const deltaSeries = (env.series || []).find((series) => series.dash);
      const mainEnv = Object.assign({}, env, {
        series: (env.series || []).filter((series) => !series.dash),
      });
      TTCharts.renderEnvelope(mainBox, mainEnv);
      if (deltaSeries) {
        const deltaBox = document.createElement("div");
        deltaBox.className = "chart";
        container.appendChild(deltaBox);
        TTCharts.renderEnvelope(deltaBox, {
          kind: "telemetry",
          x: env.x,
          series: [deltaSeries],
          meta: { channel: "Delta", unit: env.meta.unit },
        });
      }
    } catch (error) {
      setStatus(`Compare failed: ${error.message}`, "error");
    }
  }

  /* ------------------------------- Live -------------------------------- */

  $("live-button").addEventListener("click", () => {
    if (window.TTLive) window.TTLive.open();
  });

  /* ------------------------------ Builder ------------------------------ */

  $("builder-button").addEventListener("click", async () => {
    const instruction = $("builder-input").value.trim();
    if (!instruction) return;
    const log = $("builder-log");
    log.innerHTML = "";
    appendBuilderMessage(`Request: ${instruction}`, "");
    if (!state.session) {
      appendBuilderMessage("Select an event and a session first.", "error");
      return;
    }
    $("builder-button").disabled = true;
    appendBuilderMessage("Building… The builder writes the code, registers it, and tests it.", "");
    try {
      const result = await fetchJSON("/builder/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction,
          context: {
            event: state.event,
            session: state.session,
            session_name: $("session-select").selectedOptions[0]?.textContent || "",
          },
        }),
      });
      if (result.status === "built") {
        appendBuilderMessageLink(result.message || "Screen built.", result.screen_id);
      } else if (result.status === "refused") {
        appendBuilderMessage(`Refused: ${result.message}`, "refused");
      } else {
        appendBuilderMessage(`Error: ${result.message}`, "error");
      }
    } catch (error) {
      appendBuilderMessage(`Builder unavailable: ${error.message}`, "error");
    } finally {
      $("builder-button").disabled = false;
    }
  });

  function appendBuilderMessage(text, kind) {
    const message = document.createElement("div");
    message.className = `builder-message ${kind || ""}`;
    message.textContent = text;
    $("builder-log").appendChild(message);
  }

  function appendBuilderMessageLink(text, screenId) {
    const message = document.createElement("div");
    message.className = "builder-message ok";
    message.textContent = text;
    if (screenId) {
      const link = document.createElement("a");
      link.href = `/screens/${screenId}`;
      link.textContent = " Open the screen";
      message.appendChild(link);
    }
    $("builder-log").appendChild(message);
  }

  window.TTApp = { state, prepareSession, setStatus };

  init();
})();
