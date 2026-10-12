/* Draw the lap timeline at the bottom of the main screen. */
(function () {
  "use strict";

  const COMPOUND_COLORS = {
    SOFT: "#e10600",
    MEDIUM: "#f2c200",
    HARD: "#c8c8c8",
    INTERMEDIATE: "#2ecc71",
    WET: "#3498db",
    UNKNOWN: "#4a5361",
  };

  function formatTime(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    const minutes = Math.floor(seconds / 60);
    const rest = (seconds % 60).toFixed(3).padStart(6, "0");
    return `${minutes}:${rest}`;
  }

  function drawTimeline(container, laps, currentLap, fastestLap, onSelect) {
    container.innerHTML = "";
    if (!laps || !laps.length) {
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = "No laps for this driver.";
      container.appendChild(hint);
      return;
    }
    const strip = document.createElement("div");
    strip.className = "timeline-strip";
    for (const lap of laps) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "lap-chip";
      if (lap.number === currentLap) chip.classList.add("active");
      if (lap.number === fastestLap) chip.classList.add("fastest");
      chip.style.borderColor = COMPOUND_COLORS[lap.compound] || COMPOUND_COLORS.UNKNOWN;
      const number = document.createElement("span");
      number.className = "lap-number";
      number.textContent = `L${lap.number}`;
      const time = document.createElement("span");
      time.className = "lap-time";
      time.textContent = formatTime(lap.time_s);
      chip.appendChild(number);
      chip.appendChild(time);
      chip.addEventListener("click", () => onSelect(lap.number));
      strip.appendChild(chip);
    }
    container.appendChild(strip);
  }

  window.TTTimeline = { drawTimeline, formatTime };
})();
