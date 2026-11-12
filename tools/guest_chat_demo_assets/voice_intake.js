"use strict";

// Optional browser speech input for the loopback-only WOR-57 example journey.
// Prefer on-device dictation. Remote browser recognition requires a separate,
// unchecked consent control and is never selected automatically.
(() => {
  const MAX_TRANSCRIPT_CHARS = 1000;

  function attachVoiceIntake({ windowRef, button, cancelButton, input, status, remoteConsent, onDraft, onListening }) {
    const Recognition = windowRef.SpeechRecognition || windowRef.webkitSpeechRecognition;
    let recognition = null;
    let listening = false;
    let transcript = "";
    let baseText = "";
    let baseWasVoiceDraft = false;
    let lastError = "";
    let voiceDraft = false;
    let available = false;
    let localAvailable = false;
    let remoteAvailable = false;
    let busy = false;
    let remoteCheck = 0;
    let remoteChecking = false;
    // Track the selected processing mode explicitly. Older implementations
    // may omit processLocally even when an opted-in browser service is used.
    let selectedMode = null;

    const remoteApproved = () => Boolean(remoteConsent && remoteConsent.checked);
    const updateButton = () => {
      available = localAvailable || (remoteApproved() && remoteAvailable);
      button.disabled = busy || remoteChecking || !(localAvailable || (remoteApproved() && remoteAvailable));
      if (cancelButton) cancelButton.disabled = busy || listening;
    };
    const controller = (supported, ready = Promise.resolve()) => ({
      get supported() { return supported && available; },
      get listening() { return listening; },
      get voiceDraft() { return voiceDraft; },
      ready,
      clearDraft() {
        transcript = "";
        baseText = "";
        baseWasVoiceDraft = false;
        setDraft(false);
      },
      discardDraft() {
        if (busy || listening) return;
        transcript = "";
        lastError = "";
        input.value = baseText;
        setDraft(baseWasVoiceDraft);
        setStatus(baseText
          ? "Voice text discarded. Your earlier message text has been restored."
          : "Voice text discarded. Type a message or start voice input again.");
      },
      setBusy(value) {
        busy = value === true;
        if (remoteConsent) remoteConsent.disabled = busy || listening;
        updateButton();
      },
    });

    const setStatus = (message) => { status.textContent = message; };
    const setListening = (value) => {
      listening = value;
      if (cancelButton) cancelButton.disabled = value || busy;
      if (remoteConsent) remoteConsent.disabled = value || busy;
      button.setAttribute("aria-pressed", value ? "true" : "false");
      button.textContent = value ? "Stop listening" : "Start voice input";
      if (typeof onListening === "function") onListening(value);
    };
    const setDraft = (value) => {
      voiceDraft = value;
      if (typeof onDraft === "function") onDraft(value);
    };
    const stopWithFallback = (message, disable = false) => {
      setListening(false);
      setStatus(message);
      if (disable) button.disabled = true;
    };

    if (!Recognition) {
      button.disabled = true;
      if (remoteConsent) remoteConsent.disabled = true;
      setStatus("Voice input is not supported in this browser. Type your message instead.");
      return controller(false);
    }

    try {
      recognition = new Recognition();
    } catch (_error) {
      button.disabled = true;
      if (remoteConsent) remoteConsent.disabled = true;
      setStatus("Voice input is unavailable here. Type your message instead.");
      return controller(false);
    }

    if (typeof recognition.start !== "function"
        || typeof recognition.stop !== "function") {
      button.disabled = true;
      if (remoteConsent) remoteConsent.disabled = true;
      setStatus("Voice input is unavailable in this browser. Type your message instead.");
      return controller(false);
    }

    recognition.lang = "en-NG";
    recognition.continuous = false;
    recognition.interimResults = true;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    setStatus("Checking for an installed on-device en-NG dictation pack…");

    const canCheckAvailability = typeof Recognition.available === "function";
    const canUseLocal = "processLocally" in recognition && canCheckAvailability;
    if (canUseLocal) recognition.processLocally = true;
    if (remoteConsent) remoteConsent.disabled = true;
    const messagesForLocal = {
      downloadable: "The on-device en-NG language pack is not installed. Roomay will not download it.",
      downloading: "The on-device en-NG language pack is still downloading. Roomay did not start the download.",
      unavailable: "On-device en-NG dictation is unavailable in this browser.",
      unknown: "On-device en-NG availability could not be verified.",
    };

    async function checkAvailability(processLocally) {
      if (!canCheckAvailability) return processLocally ? "unavailable" : "available";
      try {
        return await Recognition.available({
          langs: ["en-NG"], processLocally, quality: "dictation",
        });
      } catch (_error) {
        return "error";
      }
    }

    const ready = (async () => {
      if (canUseLocal) {
        const result = await checkAvailability(true);
        if (result === "available") {
          localAvailable = true;
          available = true;
          setStatus("On-device en-NG dictation is available. Press Use voice to allow microphone access.");
        } else {
          const reason = result === "error" ? messagesForLocal.unknown : (messagesForLocal[result] || messagesForLocal.unknown);
          setStatus(`${reason} Typed input is always available. You may opt in to your browser’s speech service below.`);
        }
      } else {
        setStatus("On-device dictation cannot be verified in this browser. Typed input works; you may opt in to your browser’s speech service below.");
      }
      button.setAttribute("aria-busy", "false");
      if (remoteConsent) remoteConsent.disabled = false;
      updateButton();
      if (remoteConsent && remoteConsent.checked) await setRemoteConsent(true);
    })();

    async function setRemoteConsent(approved) {
      if (approved && listening) {
        setStatus("Stop the current recording before changing speech processing mode.");
        return;
      }
      const checkId = ++remoteCheck;
      remoteAvailable = false;
      remoteChecking = approved;
      updateButton();
      if (!approved) {
        remoteChecking = false;
        updateButton();
        if (localAvailable) setStatus("On-device en-NG dictation is available. Browser speech service remains off.");
        else setStatus("Browser speech service is off. Type your message instead.");
        return;
      }
      if (canCheckAvailability) {
        const result = await checkAvailability(false);
        if (checkId !== remoteCheck || !remoteApproved()) return;
        remoteChecking = false;
        if (result !== "available") {
          setStatus("The browser speech service is unavailable for en-NG. No audio was sent; type your message instead.");
          updateButton();
          return;
        }
      }
      if (checkId !== remoteCheck || !remoteApproved()) return;
      remoteChecking = false;
      remoteAvailable = true;
      updateButton();
      setStatus("Browser speech service enabled by your choice. Your browser may send audio to its provider; provider privacy terms apply.");
    }

    if (remoteConsent) {
      remoteConsent.disabled = true;
      remoteConsent.addEventListener("change", () => { setRemoteConsent(remoteConsent.checked); });
    }

    recognition.onstart = () => {
      transcript = "";
      lastError = "";
      setDraft(baseWasVoiceDraft);
      setListening(true);
      const modeCopy = selectedMode === "browser-managed"
        ? "Listening with your browser’s speech service. Audio may be sent to its provider."
        : selectedMode === "on-device"
          ? "Listening on this device."
          : "Listening mode could not be verified. Stop and type your message instead.";
      setStatus(baseText
        ? `${modeCopy} Existing text is being kept; new recognized words will be appended.`
        : `${modeCopy} Speak, then stop or wait for recognition to finish.`);
    };

    recognition.onresult = (event) => {
      let finalText = "";
      let interimText = "";
      const results = event.results || recognition.results || [];
      for (let i = 0; i < results.length; i += 1) {
        const result = results[i];
        const alternative = result && result[0];
        if (!alternative || typeof alternative.transcript !== "string") continue;
        if (result.isFinal) finalText += alternative.transcript;
        else interimText += alternative.transcript;
      }
      transcript = (finalText + interimText).trim();
      if (transcript) {
        input.value = [baseText, transcript].filter(Boolean).join(" ");
        setDraft(true);
        if (input.value.length > MAX_TRANSCRIPT_CHARS) {
          setStatus("Transcript is longer than 1,000 characters. Edit it before sending.");
        } else {
          setStatus("Transcript ready to review. Edit it if needed, then choose Send reviewed transcript.");
        }
      }
    };

    recognition.onerror = (event) => {
      const code = event && typeof event.error === "string" ? event.error : "";
      const messages = {
        "not-allowed": "Microphone permission was denied. Type your message instead or change the browser permission.",
        "service-not-allowed": "Speech recognition is not allowed by this browser. Type your message instead.",
        "language-not-supported": selectedMode === "browser-managed"
          ? "This browser speech service cannot recognize en-NG. Type your message instead."
          : "This browser does not have an en-NG on-device language pack. Roomay did not download one; type your message instead.",
        "audio-capture": "The microphone is unavailable. Check the device or type your message instead.",
        "no-speech": "No speech was recognized. Try again or type your message instead.",
        "network": "Speech recognition was interrupted. Review any transcript or type your message instead.",
        "aborted": "Voice input was interrupted. Review any transcript or type your message instead.",
      };
      lastError = messages[code] || "Voice input could not continue. Review any transcript or type your message instead.";
      if (code === "language-not-supported" || code === "service-not-allowed") {
        if (selectedMode === "browser-managed") remoteAvailable = false;
        else localAvailable = false;
        available = localAvailable || (remoteApproved() && remoteAvailable);
        updateButton();
      }
      setListening(false);
      setStatus(lastError);
    };

    recognition.onend = () => {
      setListening(false);
      const recognized = transcript.trim();
      const value = [baseText, recognized].filter(Boolean).join(" ");
      if (recognized) {
        input.value = value;
        setDraft(true);
        if (lastError) {
          setStatus("Voice input stopped early. Review or edit the partial transcript before sending.");
        } else if (value.length > MAX_TRANSCRIPT_CHARS) {
          setStatus("Transcript is longer than 1,000 characters. Edit it before sending.");
        } else {
          setStatus("Transcript ready to review. Edit it if needed, then choose Send reviewed transcript.");
        }
        input.focus();
      } else if (!lastError) {
        setDraft(baseWasVoiceDraft);
        setStatus("No clear speech was recognized. Type your message instead.");
      } else {
        setDraft(baseWasVoiceDraft);
      }
    };

    button.addEventListener("click", () => {
      if (button.disabled) return;
      if (listening) {
        setStatus("Stopping voice input and keeping any words recognized so far for review…");
        try {
          recognition.stop();
        } catch (_error) {
          stopWithFallback("Voice input stopped. Review any transcript or type your message instead.");
        }
        return;
      }
      // start() is called synchronously from this direct user click so that
      // microphone permission is never requested on page load or navigation.
      transcript = "";
      lastError = "";
      // Every existing draft is preserved. New recognition is appended so a
      // second recording cannot silently replace guest edits.
      baseText = input.value.trim();
      baseWasVoiceDraft = voiceDraft;
      // Prefer verified local en-NG even when remote-service consent is on.
      // Browser-managed recognition is only a fallback when local is absent.
      const mode = localAvailable
        ? "on-device"
        : (remoteApproved() && remoteAvailable ? "browser-managed" : null);
      if (!mode) {
        setStatus("Voice input is unavailable with your current settings. Type your message instead.");
        updateButton();
        return;
      }
      selectedMode = mode;
      try {
        if ("processLocally" in recognition) recognition.processLocally = mode === "on-device";
        if (mode === "browser-managed") {
          setStatus("Listening with your browser’s speech service. Audio may be sent to its provider; you can stop at any time.");
        } else {
          setStatus("Starting verified on-device en-NG recognition…");
        }
        recognition.start();
      } catch (_error) {
        stopWithFallback("Could not start voice input. Check microphone access or type your message instead.");
      }
    });

    return controller(true, ready);
  }

  globalThis.RoomayVoiceIntake = { attachVoiceIntake };
})();
