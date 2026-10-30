// Settings page: change the simple settings, and update the web interface when GitHub is ahead.
(function () {
  const FIELDS = ["DEVICE_NAME", "DEFAULT_VOLUME", "SOLOIST_UPDATE_AFTER_DAYS", "APT_UPGRADE_AFTER_DAYS"];
  const saveButton = document.getElementById("save");
  const saveStatus = document.getElementById("save-status");
  const codeStatus = document.getElementById("code-status");
  const commitList = document.getElementById("code-commits");
  const checkButton = document.getElementById("check");
  const updateButton = document.getElementById("update");
  let loaded = {};

  function showError(target, err) {
    target.textContent = err.message || String(err);
  }

  async function loadSettings() {
    const data = await api("/api/config");
    loaded = data.values;
    FIELDS.forEach(function (key) {
      const input = document.getElementById(key);
      if (input) input.value = loaded[key] || "";
      const hint = document.querySelector('[data-hint="' + key + '"]');
      if (hint && data.editable[key]) hint.textContent = data.editable[key];
    });
  }

  async function save() {
    const body = {};
    FIELDS.forEach(function (key) {
      const input = document.getElementById(key);
      if (input && input.value !== String(loaded[key] || "")) body[key] = input.value;
    });
    if (!Object.keys(body).length) {
      saveStatus.textContent = "Nothing changed.";
      return;
    }
    saveButton.disabled = true;
    try {
      const result = await api("/api/config", { body: body });
      if (result.restart && result.restart.length) {
        await api("/api/config/apply", { body: { services: result.restart } });
      }
      await loadSettings();
      saveStatus.textContent = "Saved.";
    } catch (err) {
      showError(saveStatus, err);
    } finally {
      saveButton.disabled = false;
    }
  }

  async function checkCode() {
    checkButton.disabled = true;
    updateButton.disabled = true;
    codeStatus.textContent = "Checking GitHub...";
    commitList.replaceChildren();
    try {
      const info = await api("/api/code/update");
      if (info.update_available) {
        codeStatus.textContent = "Update available on " + info.branch + ": " + info.current + " to " + info.latest + ".";
        info.commits.forEach(function (subject) {
          const item = document.createElement("li");
          item.textContent = subject;
          commitList.append(item);
        });
        updateButton.disabled = false;
      } else {
        codeStatus.textContent = "Up to date (" + info.branch + ", " + info.current + ").";
      }
    } catch (err) {
      showError(codeStatus, err);
    } finally {
      checkButton.disabled = false;
    }
  }

  async function updateCode() {
    if (!window.confirm("Update the web interface from GitHub now? The page reloads in a few seconds.")) return;
    updateButton.disabled = true;
    checkButton.disabled = true;
    codeStatus.textContent = "Updating...";
    try {
      await api("/api/code/update", { body: { confirm: true } });
      codeStatus.textContent = "Updated. Restarting the web service...";
      setTimeout(function () { window.location.reload(); }, 6000);
    } catch (err) {
      showError(codeStatus, err);
      checkButton.disabled = false;
    }
  }

  // ---- audio output and GPIO (the case and the fan) ----
  const sinkSelect = document.getElementById("sink");
  const saveAudioButton = document.getElementById("save-audio");
  const audioStatus = document.getElementById("audio-status");
  const caseSelect = document.getElementById("case");
  const nespiOnly = document.getElementById("nespi-only");
  const saveGpioButton = document.getElementById("save-gpio");
  const gpioStatus = document.getElementById("gpio-status");

  function pinValue(id) {
    const text = document.getElementById(id).value.trim();
    return text === "" ? null : Number(text);
  }
  function restartText(result) {
    return result.restarted && result.restarted.length ? "Applied: " + result.restarted.join(", ") + "." : "Saved.";
  }

  async function loadHardware() {
    const hw = await api("/api/hardware");
    sinkSelect.replaceChildren(...hw.audio.sinks.map(function (name) {
      const option = new Option(name, name);
      option.selected = name === hw.audio.selected;
      return option;
    }));
    if (!hw.audio.sinks.length) sinkSelect.append(new Option("No audio device found", ""));
    saveAudioButton.disabled = !hw.audio.sinks.length;

    caseSelect.value = hw.case;
    document.getElementById("poweroff").value = hw.poweroff;
    document.getElementById("power_pin").value = hw.pins.POWER_PIN;
    document.getElementById("reset_pin").value = hw.pins.RESET_PIN;
    document.getElementById("led_pin").value = hw.pins.LED_PIN;
    document.getElementById("power_enable_pin").textContent = hw.power_enable_pin;
    document.getElementById("fan_enabled").checked = hw.fan.enabled;
    document.getElementById("fan_pin").value = hw.fan.pin;
    document.getElementById("hat-note").textContent = hw.hat
      ? "The IQaudIO HAT uses GPIO " + hw.hat_pins.join(", ") + ", so those pins can't be used here."
      : "";
    nespiOnly.hidden = caseSelect.value !== "nespi";
  }

  async function saveAudio() {
    saveAudioButton.disabled = true;
    try {
      const result = await api("/api/hardware", { body: { sink: sinkSelect.value } });
      await loadHardware();
      audioStatus.textContent = restartText(result);
    } catch (err) {
      showError(audioStatus, err);
    } finally {
      saveAudioButton.disabled = false;
    }
  }

  async function saveGpio() {
    const body = {
      case: caseSelect.value,
      poweroff: document.getElementById("poweroff").value,
      fan_enabled: document.getElementById("fan_enabled").checked,
      fan_pin: pinValue("fan_pin"),
    };
    if (caseSelect.value === "nespi") {
      body.power_pin = pinValue("power_pin");
      body.reset_pin = pinValue("reset_pin");
      body.led_pin = pinValue("led_pin");
    }
    saveGpioButton.disabled = true;
    try {
      const result = await api("/api/hardware", { body: body });
      await loadHardware();
      gpioStatus.textContent = restartText(result);
    } catch (err) {
      showError(gpioStatus, err);
    } finally {
      saveGpioButton.disabled = false;
    }
  }

  caseSelect.addEventListener("change", function () { nespiOnly.hidden = caseSelect.value !== "nespi"; });
  saveAudioButton.addEventListener("click", function () { saveAudio(); });
  saveGpioButton.addEventListener("click", function () { saveGpio(); });
  loadHardware().catch(function (err) { showError(audioStatus, err); });

  saveButton.addEventListener("click", function () { save().catch(function (err) { showError(saveStatus, err); }); });
  checkButton.addEventListener("click", checkCode);
  updateButton.addEventListener("click", updateCode);

  loadSettings().catch(function (err) { showError(saveStatus, err); });
  checkCode();
})();
