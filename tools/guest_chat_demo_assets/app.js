"use strict";

(() => {
  const log = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("guest-message");
  const sendButton = document.getElementById("send-button");
  const voiceButton = document.getElementById("voice-button");
  const voiceStatus = document.getElementById("voice-status");
  const confirmation = document.getElementById("confirmation");
  const feedback = document.getElementById("feedback");
  const journeyFeedback = document.getElementById("journey-feedback") || { textContent: "" };
  const panels = {
    guest: document.getElementById("guest-panel"),
    reception: document.getElementById("reception-panel"),
    housekeeping: document.getElementById("housekeeping-panel"),
  };
  const roleTabs = [...document.querySelectorAll("[data-role]")];
  let view = null;
  let busy = false;
  let voiceDraft = false;
  let voiceListening = false;
  let voice = null;
  let activeRole = "guest";

  function announce(message) {
    feedback.textContent = activeRole === "guest" ? message : "";
    journeyFeedback.textContent = activeRole === "guest" ? "" : message;
  }

  function updateComposerControls() {
    sendButton.disabled = busy || voiceListening;
    input.disabled = busy || voiceListening;
    sendButton.querySelector("span").textContent = busy
      ? "One moment"
      : voiceDraft ? "Send reviewed transcript" : "Send";
    sendButton.setAttribute("aria-label", busy ? "Sending message"
      : voiceDraft ? "Send reviewed transcript" : "Send message");
  }

  if (globalThis.RoomayVoiceIntake && voiceButton && voiceStatus) {
    voice = globalThis.RoomayVoiceIntake.attachVoiceIntake({
      windowRef: globalThis,
      button: voiceButton,
      input,
      status: voiceStatus,
      onDraft(value) {
        voiceDraft = value;
        updateComposerControls();
      },
      onListening(value) {
        voiceListening = value;
        updateComposerControls();
      },
    });
  } else if (voiceButton && voiceStatus) {
    voiceButton.disabled = true;
    voiceStatus.textContent = "Voice input is unavailable. Type your message instead.";
  }

  async function post(path, body = {}) {
    const response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || "demo_temporarily_unavailable");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function makeMessage(message) {
    const row = document.createElement("div");
    row.className = `message-row ${message.role === "guest" ? "guest" : "assistant"}`;
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = message.role === "guest" ? "G" : "R";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = message.text;
    row.append(avatar, bubble);
    return row;
  }

  function renderReview(pending) {
    confirmation.replaceChildren();
    if (!pending) return;
    const card = document.createElement("section");
    card.className = "review-card";
    card.setAttribute("aria-label", "Review request before preparation");
    const label = document.createElement("p");
    label.className = "review-label";
    label.textContent = "REVIEW BEFORE PREPARING";
    const description = document.createElement("p");
    description.className = "review-description";
    description.textContent = pending.summary.description;
    const tags = document.createElement("div");
    tags.className = "review-tags";
    for (const value of [pending.summary.category, pending.summary.department]) {
      const tag = document.createElement("span");
      tag.className = "review-tag";
      tag.textContent = value;
      tags.append(tag);
    }
    const actions = document.createElement("div");
    actions.className = "review-actions";
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "confirm-button";
    confirm.textContent = "Confirm and prepare";
    confirm.addEventListener("click", () => act("/api/confirm", { revision: pending.revision }));
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "cancel-button";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => act("/api/cancel", { revision: pending.revision }));
    actions.append(confirm, cancel);
    card.append(label, description, tags, actions);
    confirmation.append(card);
  }

  function render(next) {
    view = next;
    log.replaceChildren(...next.messages.map(makeMessage));
    renderReview(next.pending);
    log.scrollTop = log.scrollHeight;
    updateComposerControls();
  }

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function requestCard(item, controls = [], audit = "") {
    const card = node("article", "request-card");
    const header = node("div", "request-card-header");
    const status = node("span", "status-pill status-" + String(item.status || "received"),
      String(item.status || "received").replaceAll("_", " ").toUpperCase());
    header.append(node("strong", "", item.description || "Guest request"), status);
    const meta = [item.category, item.department, item.room ? "Room " + item.room : "",
      item.guest || "", item.urgency ? item.urgency + " priority" : ""].filter(Boolean).join(" · ");
    card.append(header, node("p", "request-meta", meta));
    if (audit) card.append(node("p", "audit-note", audit));
    if (controls.length) {
      const actions = node("div", "request-actions");
      controls.forEach(([action, label]) => {
        const button = node("button", "action-button", label);
        button.type = "button";
        button.addEventListener("click", () => act("/api/staff-action", { action }));
        actions.append(button);
      });
      card.append(actions);
    }
    return card;
  }

  function renderJourney(next) {
    // Keep the existing isolated voice-controller harness contract usable; its
    // mocked responses are guest-chat views, while the real server returns the
    // full multi-role journey envelope.
    if (!next || !next.chat) {
      render(next);
      return;
    }
    activeRole = next.role;
    journeyFeedback.textContent = "";
    render(next.chat);
    Object.entries(panels).forEach(([role, panel]) => { panel.hidden = next.role !== role; });
    roleTabs.forEach((tab) => tab.setAttribute("aria-pressed", String(tab.dataset.role === next.role)));

    document.getElementById("guest-stay-title").textContent = `${next.guest.name} · Room ${next.guest.room}`;
    document.getElementById("guest-stay-meta").textContent =
      `Stay ${next.guest.stay_status.replaceAll("_", " ")} · reservation ${next.guest.reservation_status} · scheduled departure ${next.guest.departure}`;
    const guestStatuses = document.getElementById("guest-request-status");
    guestStatuses.replaceChildren();
    if (!next.guest.requests.length) {
      guestStatuses.append(node("p", "empty-state", "Your synthetic stay has no requests yet."));
    } else next.guest.requests.forEach((item) => guestStatuses.append(requestCard(item)));

    const metrics = document.getElementById("reception-metrics");
    metrics.replaceChildren();
    [["In house", next.reception.metrics.in_house], ["Arrivals", next.reception.metrics.arrivals],
      ["Departures", next.reception.metrics.departures], ["Open requests", next.reception.metrics.open_requests]]
      .forEach(([label, value]) => {
        const card = node("div", "metric-card");
        card.append(node("span", "metric-value", String(value)), node("span", "metric-label", label));
        metrics.append(card);
      });
    const room = next.reception.room;
    const stayDetails = document.getElementById("active-stay-details");
    stayDetails.replaceChildren(
      node("p", "", `${room.guest} · ${room.room_type}`),
      node("p", "stay-meta", `Reservation ${room.reservation_status} · stay ${room.stay_status} · housekeeping ${room.housekeeping} · maintenance ${room.maintenance.toLowerCase()}`),
    );
    const board = document.getElementById("room-board");
    board.replaceChildren();
    next.reception.rooms.forEach((item) => {
      const card = node("div", "room-chip" + (item.number === "205" ? " room-active" : ""));
      card.append(node("strong", "", item.number), node("span", "", item.occupancy),
        node("small", "", `${item.room_type} · ${item.housekeeping} · ${item.maintenance.toLowerCase()}`));
      board.append(card);
    });
    const receptionRequests = document.getElementById("reception-requests");
    receptionRequests.replaceChildren();
    if (!next.reception.requests.length) receptionRequests.append(node("p", "empty-state", "No synthetic requests yet."));
    next.reception.requests.forEach((item) => receptionRequests.append(requestCard(
      item, [], `Synthetic status v${item.demo_version} · ${item.demo_history.join(" → ")} · local process memory only; not a Workpeg audit`)));
    const assign = document.getElementById("assign-housekeeping");
    assign.disabled = !next.reception.requests.length || next.reception.requests.at(-1).status !== "received";
    assign.textContent = assign.disabled && next.reception.requests.length
      ? "Housekeeping assignment recorded" : "Assign to Housekeeping";

    const inbox = document.getElementById("housekeeping-requests");
    inbox.replaceChildren();
    const items = next.housekeeping.requests;
    document.getElementById("housekeeping-empty").hidden = items.length > 0;
    items.forEach((item) => {
      let controls = [];
      if (item.status === "assigned") controls = [["acknowledge", "Acknowledge request"]];
      else if (item.status === "acknowledged") controls = [["start", "Start work"]];
      else if (item.status === "in_progress") controls = [["resolve", "Resolve request"]];
      inbox.append(requestCard(item, controls));
    });
  }

  function setBusy(value) {
    busy = value;
    if (voice) voice.setBusy(value);
    updateComposerControls();
    announce(value ? "Roomay is checking the request with offline rules…" : "");
  }

  async function act(path, body) {
    if (busy) return;
    setBusy(true);
    try {
      renderJourney(await post(path, body));
      feedback.textContent = "";
      journeyFeedback.textContent = "";
      return true;
    } catch (error) {
      const message = error.status === 401
        ? "This demo session expired. Reload the page to start a new synthetic session."
        : error.status === 403
          ? "That action is unavailable in this synthetic role. Switch to the appropriate demo view."
          : error.status === 409 && (path === "/api/confirm" || path === "/api/cancel")
            ? "That confirmation is out of date. Review the latest chat before confirming."
            : error.status === 409
              ? "This request is no longer in a state that allows that action. Review its current status."
              : "The offline demo could not complete that step. Please try again or reload the page.";
      announce(message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    if (voiceListening) {
      feedback.textContent = "Stop voice input and review the transcript before sending.";
      return;
    }
    if (text.length > 1000) {
      feedback.textContent = "Please edit the message to 1,000 characters or fewer before sending.";
      input.focus();
      return;
    }
    const sent = await act("/api/message", { text });
    if (sent) {
      input.value = "";
      if (voice) voice.clearDraft();
      input.focus();
    }
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  document.querySelectorAll("[data-example]").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.example;
      input.focus();
    });
  });

  roleTabs.forEach((button) => button.addEventListener("click", () => {
    if (!busy) act("/api/role", { role: button.dataset.role });
  }));
  const assignHousekeeping = document.getElementById("assign-housekeeping");
  if (assignHousekeeping) assignHousekeeping.addEventListener("click", () => {
    if (!busy) act("/api/assign", {});
  });

  async function start() {
    try {
      renderJourney(await post("/api/session", {}));
      input.focus();
    } catch (_error) {
      log.replaceChildren();
      const message = document.createElement("p");
      message.className = "loading-state";
      message.textContent = "Could not start the local demo. Check that it is running on this computer and reload.";
      log.append(message);
      form.hidden = true;
    }
  }

  start();
})();
