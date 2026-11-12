"use strict";

(() => {
  const workspace = document.body?.dataset?.workspace || "guest";
  const feedback = document.getElementById("feedback") || document.getElementById("workspace-feedback");
  const log = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("guest-message");
  const sendButton = document.getElementById("send-button");
  const voiceButton = document.getElementById("voice-button");
  const voiceCancelButton = document.getElementById("voice-cancel");
  const voiceStatus = document.getElementById("voice-status");
  const voiceRemoteConsent = document.getElementById("voice-remote-consent");
  const confirmation = document.getElementById("confirmation");
  let busy = false;
  let voiceDraft = false;
  let voiceListening = false;
  let voice = null;
  let vapiCallBusy = false;
  let vapiCall = null;

  async function post(path, body = {}) {
    const response = await fetch(path, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || "unavailable");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }

  function setFeedback(message) {
    if (feedback) feedback.textContent = message;
  }

  function statusLabel(value) {
    return String(value || "received").replaceAll("_", " ");
  }

  function safeStatusClass(value) {
    return String(value || "received").toLowerCase().replace(/[^a-z0-9_-]/g, "");
  }

  function formatDate(value) {
    if (!value) return "—";
    const parsed = new Date(`${value}T12:00:00`);
    return Number.isNaN(parsed.valueOf())
      ? String(value)
      : new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(parsed);
  }

  function makeMessage(message) {
    const row = node("div", `message-row ${message.role === "guest" ? "guest" : "assistant"}`);
    const avatar = node("span", "message-avatar", message.role === "guest" ? "G" : "R");
    avatar.setAttribute("aria-hidden", "true");
    row.append(avatar, node("div", "bubble", message.text));
    return row;
  }

  function renderConfirmation(chat) {
    if (!confirmation) return;
    confirmation.replaceChildren();
    const pending = chat.pending;
    if (!pending) return;
    const card = node("section", "review-card");
    card.setAttribute("aria-label", "Review your request before confirming");
    card.append(node("p", "review-label", "REVIEW YOUR REQUEST"));
    card.append(node("p", "review-description", pending.summary.description));
    const tags = node("div", "review-tags");
    [pending.summary.category, pending.summary.department].forEach((value) => tags.append(node("span", "review-tag", value)));
    card.append(tags);
    const actions = node("div", "review-actions");
    const confirm = node("button", "confirm-button", "Confirm request");
    confirm.type = "button";
    confirm.addEventListener("click", () => act("/api/confirm", { revision: pending.revision }));
    const cancel = node("button", "cancel-button", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => act("/api/cancel", { revision: pending.revision }));
    actions.append(confirm, cancel);
    card.append(actions);
    confirmation.append(card);
  }

  function renderChat(chat) {
    if (!log || !chat || !Array.isArray(chat.messages)) return;
    log.replaceChildren(...chat.messages.map(makeMessage));
    log.scrollTop = log.scrollHeight;
    renderConfirmation(chat);
    updateComposerControls();
  }

  function requestCard(item, { staff = false, action = null } = {}) {
    const card = node("article", "request-card");
    const header = node("div", "request-card-header");
    header.append(node("strong", "request-description", item.description || "Service request"));
    header.append(node("span", `status-pill status-${safeStatusClass(item.status)}`, statusLabel(item.status)));
    const detail = [item.category, item.department && item.department.replaceAll("_", " "),
      item.room ? `Room ${item.room}` : "", item.guest || "", item.urgency ? `${item.urgency} priority` : ""]
      .filter(Boolean).join(" · ");
    card.append(header, node("p", "request-meta", detail));
    if (Array.isArray(item.history) && item.history.length) {
      card.append(node("p", "activity-history", `Activity: ${item.history.map(statusLabel).join(" → ")}`));
    }
    if (staff && item.example_note) card.append(node("p", "example-note", item.example_note));
    if (action && item.request_id) {
      const actions = node("div", "request-actions");
      const button = node("button", "action-button", action.label);
      button.type = "button";
      button.addEventListener("click", () => act(action.path, {
        ...(action.action ? { action: action.action } : {}), request_id: item.request_id,
      }));
      actions.append(button);
      card.append(actions);
    }
    return card;
  }

  function renderGuest(data) {
    const guest = data.guest;
    document.getElementById("guest-name").textContent = guest.name;
    document.getElementById("guest-room").textContent = guest.room;
    document.getElementById("guest-room-type").textContent = guest.room_type;
    document.getElementById("guest-check-in").textContent = formatDate(guest.check_in);
    document.getElementById("guest-check-out").textContent = formatDate(guest.check_out);
    document.getElementById("guest-stay-status").textContent = statusLabel(guest.stay_status);
    document.getElementById("guest-reservation-status").textContent = statusLabel(guest.reservation_status);
    const contact = document.getElementById("reception-contact");
    if (contact) contact.textContent = data.reception_contact?.message || "Use the Reception contact details provided by your hotel.";
    const requests = document.getElementById("guest-requests");
    requests.replaceChildren();
    if (!data.requests.length) requests.append(node("p", "empty-state", "You have no service requests yet."));
    else data.requests.forEach((item) => requests.append(requestCard(item)));
    renderChat(data.chat);
  }

  const metricLabels = [
    ["in_house", "Guests in house", "Physically checked-in stays"],
    ["arrivals", "Arrivals today", "Reservations scheduled today"],
    ["departures", "Departures today", "Active stays due to check out"],
    ["ready_for_check_in", "Rooms ready", "Eligible for today’s arrivals"],
    ["needs_cleaning", "Need cleaning", "Housekeeping status is not ready"],
    ["maintenance_blocked_rooms", "Maintenance blocks", "Rooms under an active block"],
    ["overdue_active_stays", "Overdue stays", "Still physically in house"],
    ["open_requests", "Open requests", "Unresolved service requests"],
  ];

  function itemLine(item, detail) {
    const row = node("article", "simple-list-item");
    row.append(node("strong", "", item.guest || `Room ${item.room || "—"}`));
    row.append(node("span", "", detail));
    return row;
  }

  function renderReception(data) {
    document.getElementById("reception-property").textContent = data.property_name;
    document.getElementById("operational-date").textContent = formatDate(data.date);
    const metrics = document.getElementById("reception-metrics");
    metrics.replaceChildren();
    metricLabels.forEach(([key, label, helper]) => {
      const card = node("article", "metric-card");
      card.append(node("span", "metric-value", data.metrics[key] ?? 0), node("span", "metric-label", label), node("span", "metric-helper", helper));
      metrics.append(card);
    });
    document.getElementById("room-count").textContent = `${data.rooms.length} rooms`;
    const board = document.getElementById("room-board");
    board.replaceChildren();
    data.rooms.forEach((room) => {
      const card = node("article", `room-card ${room.occupancy === "In house" ? "room-occupied" : ""}`);
      card.append(node("div", "room-card-top", `Room ${room.number}`), node("strong", "room-type", room.room_type));
      card.append(node("span", `room-status status-${safeStatusClass(room.occupancy)}`, room.occupancy));
      card.append(node("span", "room-detail", `Housekeeping · ${room.housekeeping}`));
      card.append(node("span", `room-detail ${room.maintenance === "Blocked" ? "tone-warning" : ""}`, `Maintenance · ${room.maintenance}`));
      board.append(card);
    });
    const arrivals = document.getElementById("arrival-list");
    const departures = document.getElementById("departure-list");
    const inHouse = document.getElementById("in-house-list");
    [arrivals, departures, inHouse].forEach((element) => element.replaceChildren());
    if (!data.arrivals.length) arrivals.append(node("p", "empty-state", "No arrivals scheduled today."));
    else data.arrivals.forEach((item) => arrivals.append(itemLine(item, `Room ${item.room} · arrival ${formatDate(item.arrival)}`)));
    const departureItems = [...data.departures, ...data.overdue_departures.map((item) => ({ ...item, departure_status: "Overdue" }))];
    if (!departureItems.length) departures.append(node("p", "empty-state", "No departures scheduled today."));
    else departureItems.forEach((item) => departures.append(itemLine(item, `Room ${item.room} · ${item.departure_status || "Due today"}`)));
    if (!data.in_house.length) inHouse.append(node("p", "empty-state", "No checked-in stays."));
    else data.in_house.forEach((item) => inHouse.append(itemLine(item, `Room ${item.room} · departure ${formatDate(item.departure)} · ${item.departure_status}`)));

    const requests = document.getElementById("reception-requests");
    requests.replaceChildren();
    if (!data.requests.length) requests.append(node("p", "empty-state", "No service requests yet."));
    data.requests.forEach((item) => {
      const assign = item.department === "housekeeping" && item.status === "received"
        ? { path: "/api/assign", label: "Assign to Housekeeping" } : null;
      const card = requestCard({ ...item, example_note: "Status activity is held for this example session." }, { staff: true, action: assign });
      requests.append(card);
    });
  }

  function renderHousekeeping(data) {
    document.getElementById("housekeeping-property").textContent = data.property_name;
    document.getElementById("queue-count").textContent = `${data.requests.length} assigned`;
    const queue = document.getElementById("housekeeping-requests");
    const empty = document.getElementById("housekeeping-empty");
    queue.replaceChildren();
    empty.hidden = data.requests.length > 0;
    data.requests.forEach((item) => {
      let action = null;
      if (item.status === "assigned") action = { path: "/api/staff-action", action: "acknowledge", label: "Acknowledge" };
      else if (item.status === "acknowledged") action = { path: "/api/staff-action", action: "start", label: "Start work" };
      else if (item.status === "in_progress") action = { path: "/api/staff-action", action: "resolve", label: "Mark complete" };
      const card = requestCard({ ...item, department: "Housekeeping", example_note: "Updates apply to this example session only." }, { staff: true, action });
      card.classList.add("housekeeping-task");
      queue.append(card);
    });
  }

  function render(data) {
    if (data && !data.workspace && Array.isArray(data.messages)) {
      // Compatibility for the isolated WOR-19 compiled voice harness.
      return renderChat(data);
    }
    if (!data || data.workspace !== workspace) throw new Error("workspace_mismatch");
    setFeedback("");
    if (workspace === "guest") renderGuest(data);
    else if (workspace === "reception") renderReception(data);
    else if (workspace === "housekeeping") renderHousekeeping(data);
  }

  function updateComposerControls() {
    if (!sendButton || !input) return;
    sendButton.disabled = busy || voiceListening;
    input.disabled = busy || voiceListening;
    sendButton.querySelector("span").textContent = busy ? "One moment" : voiceDraft ? "Send reviewed transcript" : "Send request";
    sendButton.setAttribute("aria-label", busy ? "Sending request" : voiceDraft ? "Send reviewed transcript" : "Send request");
    if (voiceButton && voice) voice.setBusy(vapiCallBusy);
    const callButton = document.getElementById("call-remi");
    if (callButton && !callButton.hidden && !vapiCallBusy) callButton.disabled = busy || voiceListening;
  }

  if (workspace === "guest" && globalThis.RoomayVoiceIntake && voiceButton && voiceStatus) {
    voice = globalThis.RoomayVoiceIntake.attachVoiceIntake({
      windowRef: globalThis, button: voiceButton, cancelButton: voiceCancelButton, input, status: voiceStatus,
      remoteConsent: voiceRemoteConsent,
      consentDialog: document.getElementById("voice-remote-dialog"),
      consentAllow: document.getElementById("voice-remote-allow"),
      consentCancel: document.getElementById("voice-remote-cancel"),
      onDraft(value) { voiceDraft = value; if (voiceCancelButton) voiceCancelButton.hidden = !value; updateComposerControls(); },
      onListening(value) { voiceListening = value; updateComposerControls(); },
    });
  } else if (workspace === "guest" && voiceButton && voiceStatus) {
    voiceButton.disabled = true;
    if (voiceCancelButton) voiceCancelButton.disabled = true;
    voiceStatus.textContent = "Voice input is unavailable. Type your request instead.";
  }

  if (workspace === "guest" && globalThis.RoomayVapiCall) {
    vapiCall = globalThis.RoomayVapiCall.attach({
      windowRef: globalThis, documentRef: document,
      onState(next) {
        vapiCallBusy = ["connecting", "listening", "speaking", "muted"].includes(next);
        const orb = document.getElementById("remi-orb");
        if (orb) orb.state = globalThis.RoomayVapiCall.orbStateForCallState(next);
        updateComposerControls();
      },
      onTranscript(text) {
        if (typeof text !== "string" || !text.trim()) return;
        input.value = text.trim().slice(0, 1000);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        setFeedback("Transcript added to the editable request field. Review it, then send to Roomay’s validated intake. No request has been submitted yet.");
        // Do not move keyboard focus behind the open modal; the guest can
        // close/end the call before editing the imported transcript.
        if (document.getElementById("remi-call-overlay")?.hidden) input.focus();
      },
    });
  }

  if (voiceCancelButton && input) {
    voiceCancelButton.addEventListener("click", () => {
      if (busy || voiceListening || !voice) return;
      voice.discardDraft();
      input.focus();
    });
  }

  async function act(path, body) {
    if (busy) return false;
    busy = true;
    updateComposerControls();
    setFeedback("Updating request status…");
    try {
      render(await post(path, body));
      if (workspace !== "guest") setFeedback("Status updated for this example session.");
      return true;
    } catch (error) {
      const message = error.status === 401 ? "Your session has expired. Reload this page to begin again."
        : error.status === 403 ? "This workspace is not available for the current session."
          : error.status === 409 ? "The request changed state. Review the latest status before continuing."
            : "We couldn’t update this request. Please try again.";
      setFeedback(message);
      return false;
    } finally {
      busy = false;
      updateComposerControls();
    }
  }

  if (form && input) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text || busy) return;
      if (voiceListening) { setFeedback("Stop voice input and review the transcript before sending."); return; }
      if (text.length > 1000) { setFeedback("Please keep your request to 1,000 characters or fewer."); input.focus(); return; }
      if (await act("/api/message", { text })) {
        input.value = "";
        if (voice) voice.clearDraft();
        input.focus();
      }
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
    });
  }

  async function start() {
    try {
      render(await post("/api/session", {}));
      if (workspace === "guest" && input) input.focus();
    } catch (error) {
      setFeedback(error.status === 401 ? "Your session has expired. Open the local workspace again."
        : error.status === 403 ? "This workspace is not available for the current session."
          : "We couldn’t load this workspace. Please refresh to try again.");
      if (log) log.replaceChildren(node("p", "empty-panel", "Your stay details are unavailable right now."));
      if (form) form.hidden = true;
    }
  }

  start();
})();
