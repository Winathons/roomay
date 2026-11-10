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
  let view = null;
  let busy = false;
  let voiceDraft = false;
  let voiceListening = false;
  let voice = null;

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

  function setBusy(value) {
    busy = value;
    if (voice) voice.setBusy(value);
    updateComposerControls();
    feedback.textContent = value ? "Roomay is checking the request with offline rules…" : "";
  }

  async function act(path, body) {
    if (busy) return;
    setBusy(true);
    try {
      render(await post(path, body));
      feedback.textContent = "";
      return true;
    } catch (error) {
      feedback.textContent = error.status === 401
        ? "This demo session expired. Reload the page to start a new synthetic session."
        : error.status === 409
          ? "That confirmation is out of date. Review the latest chat before confirming."
          : "The offline demo could not complete that step. Please try again with a short message.";
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

  async function start() {
    try {
      render(await post("/api/session", {}));
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
