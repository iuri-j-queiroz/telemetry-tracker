/* Live data flow: F1TV access, capture, and stop. See plan.md, section 10. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const server = (path) => `/server/api/${path}`;

  let pollTimer = null;
  let capturing = false;

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

  function open() {
    $("live-modal").classList.remove("hidden");
    refresh();
  }

  function close() {
    $("live-modal").classList.add("hidden");
    stopPoll();
  }

  function stopPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function schedulePoll(ms) {
    stopPoll();
    pollTimer = setTimeout(tick, ms);
  }

  function setButtons(visible) {
    for (const id of ["live-auth-start", "live-auth-link", "live-capture", "live-stop"]) {
      $(id).classList.toggle("hidden", !visible.includes(id));
    }
  }

  async function refresh() {
    const body = $("live-modal-body");
    try {
      const status = await fetchJSON(server("live/status"));
      render(status);
    } catch (error) {
      body.innerHTML = `<p class="err">${error.message}</p>`;
      setButtons(["live-close"]);
    }
  }

  function render(status) {
    const body = $("live-modal-body");
    const capture = status.capture || {};
    capturing = capture.state === "capturing";

    if (capturing) {
      body.innerHTML =
        "<p class='ok'>Capture in progress.</p>" +
        `<p class="hint">${capture.file || ""} · ${Math.round((capture.bytes || 0) / 1024)} KB</p>` +
        "<p class='hint'>Keep this page open. Press Stop when the session ends, or let the capture stop on its own after 5 quiet minutes.</p>";
      setButtons(["live-stop"]);
      schedulePoll(3000);
      return;
    }

    if (status.has_credentials) {
      const product = (status.credentials || {}).product;
      let text = `<p class="ok">F1TV access is ready${product ? ` (${product})` : ""}.</p>`;
      if (status.live_window) {
        text += `<p>Live now: ${status.live_window.name} · ${status.live_window.session}.</p>`;
      } else {
        text += "<p class='hint'>No session is in progress now. A capture still records if you start it.</p>";
      }
      if (capture.state === "done") {
        text += "<p class='ok'>The last capture is loaded. Open the session from the main screen.</p>";
      }
      if (capture.state === "error") {
        text += `<p class="err">The last capture failed: ${capture.error}</p>`;
      }
      body.innerHTML = text;
      setButtons(["live-capture"]);
      return;
    }

    body.innerHTML =
      "<p>Live timing needs F1TV access (F1TV Access, Pro, or Premium).</p>" +
      "<p class='hint'>Press Authenticate. Your browser opens the FastF1 login page. Log in with your F1TV account. The token stays on this machine.</p>";
    setButtons(["live-auth-start"]);
  }

  async function startAuth() {
    try {
      const info = await fetchJSON(server("live/auth/start"), { method: "POST" });
      showAuthWaiting(info);
      schedulePoll(2000);
    } catch (error) {
      $("live-modal-body").innerHTML = `<p class="err">${error.message}</p>`;
    }
  }

  function showAuthWaiting(info) {
    $("live-modal-body").innerHTML =
      "<p>Waiting for the F1TV login…</p>" +
      "<p class='hint'>Open the login page and finish the login in your browser.</p>";
    const link = $("live-auth-link");
    link.href = info.url || "#";
    setButtons(["live-auth-link"]);
    if (info.url) window.open(info.url, "_blank", "noopener");
  }

  async function startCapture() {
    const session = window.TTApp.state.session;
    if (!session) {
      $("live-modal-body").innerHTML =
        "<p class='err'>Select an event and a session on the main screen first.</p>";
      return;
    }
    try {
      const info = await fetchJSON(server("live/capture/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session }),
      });
      capturing = info.state === "capturing";
      window.TTApp.setStatus("Live capture started.", "busy");
      refresh();
    } catch (error) {
      $("live-modal-body").innerHTML = `<p class="err">${error.message}</p>`;
    }
  }

  async function stopCapture() {
    try {
      await fetchJSON(server("live/capture/stop"), { method: "POST" });
      schedulePoll(1500);
    } catch (error) {
      $("live-modal-body").innerHTML = `<p class="err">${error.message}</p>`;
    }
  }

  async function tick() {
    try {
      if (capturing) {
        const info = await fetchJSON(server("live/capture/state"));
        if (info.state === "capturing") {
          render({ capture: info, has_credentials: true });
          return;
        }
        capturing = false;
        if (info.state === "error") {
          window.TTApp.setStatus(`Live capture failed: ${info.error}`, "error");
        } else {
          window.TTApp.setStatus("Live capture complete. The session loads now.", "ok");
          if (window.TTApp.state.session) {
            window.TTApp.prepareSession(window.TTApp.state.session.code);
          }
        }
        await refresh();
        return;
      }
      const info = await fetchJSON(server("live/auth/state"));
      if (info.state === "waiting") {
        schedulePoll(2000);
        return;
      }
      if (info.state === "error") {
        $("live-modal-body").innerHTML = `<p class="err">Login failed: ${info.error}</p>`;
        setButtons(["live-auth-start"]);
        return;
      }
      await refresh();
    } catch (error) {
      stopPoll();
    }
  }

  $("live-auth-start").addEventListener("click", startAuth);
  $("live-capture").addEventListener("click", startCapture);
  $("live-stop").addEventListener("click", stopCapture);
  $("live-close").addEventListener("click", close);

  window.TTLive = { open, close };
})();
