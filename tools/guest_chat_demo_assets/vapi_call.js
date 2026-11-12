"use strict";

// Vapi Web SDK adapter for the loopback-only guest QA application.
// The browser receives a Vapi public key only; no private Vapi credential is
// read or sent by this module. The call never submits a hotel action.
(() => {
  const MAX_SECONDS = 180;
  const SAFE_GUEST_PROMPT = [
    "You are Remi, a warm and concise Roomay guest conversation assistant.",
    "Follow the guest's current language: natural English for English and natural Nigerian Pidgin for Pidgin, and follow language switches.",
    "This is an internal local example session, not a real authenticated hotel account. You have no verified hotel records, availability, prices, bookings, or guest identity.",
    "A spoken room number, name, caller ID, or AI statement is never identity proof. Never infer a verified stay or disclose any guest or room information.",
    "Never claim a request was submitted, sent, saved, persisted, assigned, acknowledged, resolved, or that staff was contacted or a call was transferred. You have no hotel action tools that authorize such claims.",
    "If a guest wants hotel service, help them phrase the request and direct them to the My Stay text composer. The existing deterministic Roomay intake will ask for explicit confirmation; this call alone does not submit it.",
    "Do not invent availability, prices, policies, or amenities. For urgent danger, advise contacting local emergency services and the hotel's official Reception contact; do not claim to contact anyone.",
    "Do not ask for passwords, stay PINs, payment details, or sensitive personal information.",
  ].join(" ");

  function attach({ windowRef, documentRef, onTranscript, onState }) {
    const root = documentRef.getElementById("remi-call");
    const startButton = documentRef.getElementById("call-remi");
    const endButton = documentRef.getElementById("end-remi");
    const muteButton = documentRef.getElementById("mute-remi");
    const status = documentRef.getElementById("remi-call-status");
    const captions = documentRef.getElementById("remi-call-captions");
    const useTranscript = documentRef.getElementById("use-call-transcript");
    let client = null;
    let state = "unavailable";
    let active = false;
    let busy = false;
    let timer = null;
    let latestUserTranscript = "";
    let releasePending = false;
    let startAttempt = 0;

    const setState = (next, copy) => {
      state = next;
      if (root) root.dataset.state = next;
      if (status) status.textContent = copy;
      if (typeof onState === "function") onState(next);
      const connecting = next === "connecting";
      if (startButton) {
        startButton.disabled = connecting || active || busy || next === "unavailable";
        startButton.hidden = active;
        startButton.textContent = connecting ? "Connecting…" : "Call Remi";
      }
      if (endButton) endButton.hidden = !active && !connecting;
      if (muteButton) muteButton.hidden = !active;
    };

    async function post(path) {
      const response = await windowRef.fetch(path, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error("voice_request_failed");
        error.status = response.status;
        error.code = data.error;
        throw error;
      }
      return data;
    }

    function appendCaption(role, text) {
      if (!captions || !text) return;
      const line = documentRef.createElement("p");
      line.className = "call-caption";
      const label = documentRef.createElement("strong");
      label.textContent = role === "assistant" ? "Remi: " : "You: ";
      line.append(label, documentRef.createTextNode(text));
      captions.hidden = false;
      captions.append(line);
      while (captions.children.length > 8) captions.removeChild(captions.children[0]);
      captions.scrollTop = captions.scrollHeight;
    }

    function safeFailure(error) {
      const code = String(error?.type || error?.name || error?.code || error?.error || "").toLowerCase();
      if (/notallowed|permission|microphone|denied/.test(code)) {
        return "Microphone access was not granted. You can use typed chat or try the call again.";
      }
      if (error?.status === 401 || error?.status === 403) {
        return "The voice session could not be authorized. Use typed chat or contact Reception.";
      }
      if (/network|connection|timeout|websocket/.test(code)) {
        return "The voice connection was interrupted. Use typed chat or try again.";
      }
      return "The voice call could not start or continue. Use typed chat or try again.";
    }

    function releaseClaim() {
      if (releasePending) return;
      releasePending = true;
      post("/api/voice/release").catch(() => {}).finally(() => { releasePending = false; });
    }

    function finish(copy = "Call ended. You can continue in the request chat.") {
      startAttempt += 1;
      if (timer !== null) windowRef.clearTimeout(timer);
      timer = null;
      const wasConnecting = state === "connecting";
      active = false;
      busy = false;
      const current = client;
      client = null;
      if (current) Promise.resolve(current.stop()).catch(() => {});
      releaseClaim();
      setState("ended", wasConnecting ? "Voice setup stopped. No call is active." : copy);
    }

    function onMessage(message) {
      if (!message || typeof message !== "object") return;
      if (message.type === "assistant.speechStarted") {
        setState("speaking", "Remi is speaking. You can interrupt at any time.");
        return;
      }
      if (message.type === "speech-update") {
        const role = message.role || message.speaker;
        if (role === "assistant" && message.status === "started") {
          setState("speaking", "Remi is speaking. You can interrupt at any time.");
        } else if (role === "assistant" && message.status === "stopped") {
          setState("listening", "Listening. Speak whenever you’re ready.");
        }
        return;
      }
      if (message.type === "user-interrupted") {
        setState("listening", "Listening. Remi was interrupted and is ready to hear you.");
        return;
      }
      if (message.type !== "transcript" || typeof message.transcript !== "string") return;
      if (message.transcriptType && message.transcriptType !== "final") return;
      const transcript = message.transcript.trim().slice(0, 1000);
      if (!transcript) return;
      const role = message.role === "assistant" ? "assistant" : "user";
      appendCaption(role, transcript);
      if (role === "user") {
        latestUserTranscript = transcript;
        if (useTranscript) useTranscript.hidden = false;
      }
    }

    async function start() {
      if (busy || active) return;
      const attempt = ++startAttempt;
      const sdk = windowRef.RoomayVapiSDK;
      if (!sdk || typeof sdk.Vapi !== "function") {
        setState("unavailable", "Vapi voice support is not available in this local setup. Typed chat remains available.");
        return;
      }
      busy = true;
      setState("connecting", "Connecting to Remi. Your browser will ask for microphone access.");
      try {
        const config = await post("/api/voice/config");
        if (attempt !== startAttempt) return;
        if (!config.enabled || !config.publicKey || !config.assistantId
            || config.assistantLabel !== "Remi") throw new Error("voice_not_configured");
        await post("/api/voice/claim");
        if (attempt !== startAttempt) {
          releaseClaim();
          return;
        }
        const vapi = new sdk.Vapi(config.publicKey);
        client = vapi;
        vapi.on("call-start", () => {
          busy = false;
          active = true;
          setState("listening", "Connected to Remi. Listening. You can interrupt while Remi speaks.");
          const seconds = Math.min(Number(config.maxDurationSeconds) || MAX_SECONDS, MAX_SECONDS);
          timer = windowRef.setTimeout(() => finish("The 3-minute call limit was reached. The call has ended."), seconds * 1000);
        });
        vapi.on("call-end", () => finish());
        vapi.on("speech-start", () => {
          if (active) setState("listening", "Listening to you.");
        });
        vapi.on("speech-end", () => {
          if (active) setState("listening", "Thanks. Remi is preparing a reply.");
        });
        vapi.on("message", onMessage);
        vapi.on("call-start-failed", (event) => {
          busy = false;
          active = false;
          setState("error", safeFailure(event));
          releaseClaim();
        });
        vapi.on("error", (error) => {
          const message = safeFailure(error);
          if (active || busy) {
            if (active) finish(message);
            else {
              busy = false;
              setState("error", message);
              releaseClaim();
            }
          }
        });
        // Per-call controls are supported by Vapi's AssistantOverrides. Saved
        // assistant configuration remains unchanged. The local timer is a
        // second bound if the provider-side max duration is not honored.
        const overrides = {
          maxDurationSeconds: MAX_SECONDS,
          firstMessageInterruptionsEnabled: true,
          model: {
            provider: config.modelProvider,
            model: config.modelName,
            messages: [{ role: "system", content: SAFE_GUEST_PROMPT }],
          },
          clientMessages: ["transcript", "speech-update", "assistant.speechStarted", "user-interrupted"],
          artifactPlan: {
            recordingEnabled: false,
            loggingEnabled: false,
            transcriptPlan: { enabled: false },
            videoRecordingEnabled: false,
          },
        };
        const started = vapi.start(config.assistantId, overrides);
        if (started && typeof started.then === "function") await started;
      } catch (error) {
        if (attempt !== startAttempt) return;
        busy = false;
        active = false;
        if (timer !== null) windowRef.clearTimeout(timer);
        timer = null;
        client = null;
        releaseClaim();
        if (error?.code === "voice_demo_limit_reached") {
          setState("error", "This example session has reached its call limit. Continue with typed chat.");
        } else if (error?.code === "voice_call_already_active") {
          setState("error", "A voice call is already active for this session. Return to the active call or wait for its limit to expire.");
        } else if (error?.status === 404) {
          setState("unavailable", "Voice calls are not configured for this local session. Typed chat remains available.");
        } else {
          setState("error", safeFailure(error));
        }
      }
    }

    if (startButton) startButton.addEventListener("click", start);
    if (endButton) endButton.addEventListener("click", () => finish());
    if (muteButton) muteButton.addEventListener("click", () => {
      if (!client || !active || typeof client.setMuted !== "function") return;
      const muted = !client.isMuted();
      client.setMuted(muted);
      muteButton.textContent = muted ? "Unmute microphone" : "Mute microphone";
      muteButton.setAttribute("aria-pressed", muted ? "true" : "false");
      if (status) status.textContent = muted ? "Microphone muted. Remi cannot hear you." : "Microphone on. Listening.";
    });
    if (useTranscript) useTranscript.addEventListener("click", () => {
      if (!latestUserTranscript) return;
      if (typeof onTranscript === "function") onTranscript(latestUserTranscript);
      latestUserTranscript = "";
      useTranscript.hidden = true;
    });
    windowRef.addEventListener?.("pagehide", () => {
      if (client) {
        Promise.resolve(client.stop()).catch(() => {});
        releaseClaim();
      }
    });

    if (!windowRef.RoomayVapiSDK) {
      setState("unavailable", "Voice calls are unavailable in this local setup. Typed chat remains available.");
    } else {
      setState("ready", "Ready when you are. Call starts only after you press the button.");
    }
    return { start, finish, get state() { return state; } };
  }

  globalThis.RoomayVapiCall = Object.freeze({ attach });
})();
