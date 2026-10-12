/* List the built screens. */
(function () {
  "use strict";

  function escapeHTML(text) {
    const div = document.createElement("div");
    div.textContent = String(text || "");
    return div.innerHTML;
  }

  (async function () {
    const list = document.getElementById("screens-list");
    try {
      const response = await fetch("/builder/screens");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `request failed (${response.status})`);
      if (!data.screens.length) {
        list.innerHTML = "<p class='hint'>No screens yet. Use the builder box on the Analyze page.</p>";
        return;
      }
      list.innerHTML = "";
      for (const screen of data.screens) {
        const card = document.createElement("a");
        card.className = "screen-card";
        card.href = `/screens/${encodeURIComponent(screen.id)}`;
        card.innerHTML = `
          <h3>${escapeHTML(screen.title || screen.id)}</h3>
          <p>${escapeHTML(screen.instruction || "")}</p>
          <span class="hint">${escapeHTML(screen.created || "")}${screen.mock ? " · mock" : ""}</span>`;
        list.appendChild(card);
      }
    } catch (error) {
      list.innerHTML = `<p class='hint'>Cannot load the screens: ${escapeHTML(error.message)}</p>`;
    }
  })();
})();
