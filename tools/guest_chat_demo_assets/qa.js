"use strict";

(() => {
  const feedback = document.getElementById("qa-feedback");
  const scenarioCode = document.getElementById("scenario-code");
  const createScenario = document.getElementById("create-scenario");
  const buttons = [...document.querySelectorAll("[data-role]")];
  createScenario.addEventListener("click", async () => {
    createScenario.disabled = true;
    feedback.textContent = "Creating a shared local example scenario…";
    try {
      const response = await fetch("/api/qa/scenario", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || typeof result.scenario_code !== "string") throw new Error();
      scenarioCode.value = result.scenario_code;
      scenarioCode.focus();
      scenarioCode.select();
      feedback.textContent = "Scenario created in local memory. Copy the code to the other private browser sessions.";
    } catch (_error) {
      feedback.textContent = "A local scenario could not be created. Refresh this QA page and try again.";
    } finally {
      createScenario.disabled = false;
    }
  });
  buttons.forEach((button) => button.addEventListener("click", async () => {
    if (buttons.some((item) => item.disabled)) return;
    buttons.forEach((item) => { item.disabled = true; });
    const code = scenarioCode.value.trim();
    if (!code) {
      feedback.textContent = "Create a local scenario or paste its code before opening a workspace.";
      buttons.forEach((item) => { item.disabled = false; });
      return;
    }
    feedback.textContent = "Opening a separate local example session…";
    try {
      const response = await fetch("/api/qa/select", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: button.dataset.role, scenario_code: code }),
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
