"use strict";

(() => {
  const feedback = document.getElementById("qa-feedback");
  const buttons = [...document.querySelectorAll("[data-role]")];
  buttons.forEach((button) => button.addEventListener("click", async () => {
    if (buttons.some((item) => item.disabled)) return;
    buttons.forEach((item) => { item.disabled = true; });
    feedback.textContent = "Opening the selected example workspace…";
    try {
      const response = await fetch("/api/qa/select", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: button.dataset.role }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || typeof result.path !== "string") throw new Error();
      location.assign(result.path);
    } catch (_error) {
      feedback.textContent = "The workspace could not be opened. Refresh this local QA page and try again.";
      buttons.forEach((item) => { item.disabled = false; });
    }
  }));
})();
