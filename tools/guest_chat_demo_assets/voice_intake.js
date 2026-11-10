"use strict";

// Optional browser speech input for the loopback-only WOR-57 demo.
// Refuse cloud recognition: only use SpeechRecognition with processLocally=true.
(() => {
  const MAX_TRANSCRIPT_CHARS = 1000;

  function attachVoiceIntake({ windowRef, button, input, status, onDraft, onListening }) {
    const Recognition = windowRef.SpeechRecognition || windowRef.webkitSpeechRecognition;
    let recognition = null;
    let listening = false;
    let transcript = "";
    let baseText = "";
    let lastError = "";
    let voiceDraft = false;
    let available = false;
    let busy = false;

    const updateButton = () => { button.disabled = busy || !available; };

    const setStatus = (message) => { status.textContent = message; };
    const setListening = (value) => {
      listening = value;
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
      setStatus("Voice input is not supported in this browser. Type your message instead.");
      return { supported: false, get listening() { return listening; }, get voiceDraft() { return voiceDraft; }, clearDraft: () => setDraft(false), setBusy: () => {} };
    }

    try {
      recognition = new Recognition();
    } catch (_error) {
      button.disabled = true;
      setStatus("Voice input is unavailable here. Type your message instead.");
      return { supported: false, get listening() { return listening; }, get voiceDraft() { return voiceDraft; }, clearDraft: () => setDraft(false), setBusy: () => {} };
    }

    // An older/vendor implementation without this property may use a remote
    // service. Do not fall back to cloud speech recognition.
    if (!("processLocally" in recognition)
        || typeof recognition.start !== "function"
        || typeof recognition.stop !== "function") {
      button.disabled = true;
      setStatus("Private on-device voice input is not supported in this browser. Type your message instead.");
      return { supported: false, get listening() { return listening; }, get voiceDraft() { return voiceDraft; }, clearDraft: () => setDraft(false), setBusy: () => {} };
    }

    recognition.lang = "en-NG";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.processLocally = true;
    available = true;
    updateButton();
    setStatus("On-device voice is ready if this browser has the en-NG language pack. Press Start voice input to grant microphone access.");

    recognition.onstart = () => {
      transcript = "";
      lastError = "";
      setDraft(false);
      setListening(true);
      setStatus("Listening on this device. Speak, then stop or wait for recognition to finish.");
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
        "service-not-allowed": "Private on-device recognition is unavailable. No cloud speech service was used; type your message instead.",
        "language-not-supported": "This browser does not have an en-NG on-device language pack. Roomay did not download one; type your message instead.",
        "audio-capture": "The microphone is unavailable. Check the device or type your message instead.",
        "no-speech": "No speech was recognized. Try again or type your message instead.",
        "network": "On-device recognition was interrupted. Type your message instead.",
        "aborted": "Voice input was interrupted. Review any transcript or type your message instead.",
      };
      lastError = messages[code] || "Voice input could not continue. Review any transcript or type your message instead.";
      if (code === "language-not-supported" || code === "service-not-allowed") {
        available = false;
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
        setDraft(false);
        setStatus("No clear speech was recognized. Type your message instead.");
      } else {
        setDraft(false);
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
      // Preserve typed text; a prior voice-only draft is replaced by a fresh
      // attempt, while ordinary typed content is retained before the transcript.
      baseText = voiceDraft ? "" : input.value.trim();
      try {
        recognition.start();
      } catch (_error) {
        stopWithFallback("Could not start on-device voice input. Check microphone access or type your message instead.");
      }
    });

    return {
      supported: true,
      get listening() { return listening; },
      get voiceDraft() { return voiceDraft; },
      clearDraft() {
        transcript = "";
        setDraft(false);
      },
      setBusy(value) {
        busy = value === true;
        updateButton();
      },
    };
  }

  globalThis.RoomayVoiceIntake = { attachVoiceIntake };
})();
