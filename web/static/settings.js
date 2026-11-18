// Settings page: General (Spotify, radio, device name, key, volume, colour), GPIO and Updates.
(function () {
  const $ = function (id) { return document.getElementById(id); };
  let loaded = {};          // settings as saved on the device
  let configLoaded = false; // true once the saved settings have arrived
  let hardware = null;      // GPIO settings as saved on the device

  function showError(target, err) { target.textContent = err.message || String(err); }

  // ---- LED toggle buttons ----
  function isOn(button) { return button.getAttribute("aria-pressed") === "true"; }
  function setOn(button, on) {
    button.setAttribute("aria-pressed", String(on));
    button.querySelector(".state").textContent = on ? "On" : "Off";
  }
  // a source that is not installed never shows its fields (see data-installed in settings.html)
  function showSpotifyFields() {
    const on = isOn($("toggle-spotify"));
    const installed = !(window.features && window.features.installed && window.features.installed.spotify === false);
    $("spotify-fields").hidden = !on || !installed;
    document.querySelectorAll('[data-feature="spotify"]').forEach(function (el) { el.hidden = !on; });
  }

  // ---- AirPlay: whether the receiver runs ----
  async function refreshAirplayStatus() {
    if (!configLoaded) return;  // the saved settings are not known yet: show nothing rather than "change not saved"
    const el = $("airplay-status");
    if (isOn($("toggle-airplay")) !== (loaded.AIRPLAY_ENABLED === "yes")) {
      el.textContent = "change not saved";
      el.className = "status warn";
      return;
    }
    if (!isOn($("toggle-airplay"))) { el.textContent = "off"; el.className = "status off"; return; }
    try {
      await api("/api/airplay");
      el.textContent = "enabled: turn it on or off on Home"; el.className = "status ok";
    } catch (err) { el.textContent = "unknown"; el.className = "status off"; }
  }

  // ---- Spotify: online status and the API key (set in a popup) ----
  function setKeyState(set) {
    const el = $("key-state");
    el.textContent = set ? "saved" : "not set";
    el.className = "status " + (set ? "ok" : "bad");
  }
  // The status shows the saved state. While the switch differs from it, the change is not saved yet.
  async function refreshSpotifyStatus() {
    if (!configLoaded) return;  // the saved settings are not known yet: show nothing rather than "change not saved"
    const el = $("spotify-status");
    if (isOn($("toggle-spotify")) !== (loaded.SPOTIFY_ENABLED !== "no")) {
      el.textContent = "change not saved";
      el.className = "status warn";
      return;
    }
    if (!isOn($("toggle-spotify"))) {
      el.textContent = "off";
      el.className = "status off";
      return;
    }
    try {
      const status = await api("/api/status");
      const sp = status.soloist.api;
      if (sp.reachable && sp.logged_in) { el.textContent = "online"; el.className = "status ok"; }
      else if (sp.reachable) { el.textContent = "not logged in"; el.className = "status warn"; }
      else { el.textContent = "offline"; el.className = "status bad"; }
    } catch (err) {
      el.textContent = "unknown";
      el.className = "status off";
    }
  }

  // ---- accent colour swatches: the page colour changes after Save general ----
  function chosenAccent() {
    const pressed = document.querySelector("#accent-swatches [aria-pressed='true']");
    return pressed ? pressed.dataset.name : "blue";
  }
  function selectAccent(name) {
    document.querySelectorAll("#accent-swatches [data-name]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.name === name));
    });
    const pressed = document.querySelector("#accent-swatches [aria-pressed='true']");
    if (pressed) $("accent-name").textContent = pressed.dataset.name.charAt(0).toUpperCase() + pressed.dataset.name.slice(1);
  }
  function applyAccent() {
    const pressed = document.querySelector("#accent-swatches [aria-pressed='true']");
    if (!pressed) return;
    document.documentElement.style.setProperty("--accent-light", pressed.dataset.light);
    document.documentElement.style.setProperty("--accent-dark", pressed.dataset.dark);
  }

  // ---- loading ----
  async function loadConfig() {
    const data = await api("/api/config");
    loaded = data.values;
    $("DEVICE_NAME").value = loaded.DEVICE_NAME || "";
    $("DEFAULT_VOLUME").value = loaded.DEFAULT_VOLUME || "";
    $("SOLOIST_UPDATE_AFTER_DAYS").value = loaded.SOLOIST_UPDATE_AFTER_DAYS || "";
    $("APT_UPGRADE_AFTER_DAYS").value = loaded.APT_UPGRADE_AFTER_DAYS || "";
    setOn($("toggle-spotify"), loaded.SPOTIFY_ENABLED !== "no");
    setOn($("toggle-radio"), loaded.RADIO_ENABLED !== "no");
    setOn($("toggle-airplay"), loaded.AIRPLAY_ENABLED === "yes");
    setKeyState(data.api_key_set);
    selectAccent(loaded.ACCENT_COLOR || "blue");
    showSpotifyFields();
    document.querySelectorAll("[data-hint]").forEach(function (hint) {
      const key = hint.getAttribute("data-hint");
      if (data.editable[key]) hint.textContent = data.editable[key];
    });
    // only now do the switches show the saved state, so the status can be compared with it
    configLoaded = true;
    refreshSpotifyStatus();
    refreshAirplayStatus();
  }

  async function loadHardware() {
    hardware = await api("/api/hardware");
    $("case").value = hardware.case;
    $("power_pin").value = hardware.pins.POWER_PIN;
    $("reset_pin").value = hardware.pins.RESET_PIN;
    $("led_pin").value = hardware.pins.LED_PIN;
    $("power_enable_pin").textContent = hardware.power_enable_pin;
    setOn($("fan_enabled"), hardware.fan.enabled);
    $("fan_pin").value = hardware.fan.pin;
    $("hat-note").textContent = hardware.hat
      ? "The IQaudIO HAT uses GPIO " + hardware.hat_pins.join(", ") + ", so those pins can't be used here."
      : "";
    showGpioFields();
  }
  function showGpioFields() {
    $("nespi-only").hidden = $("case").value !== "nespi";
    $("fan-pin-field").hidden = !isOn($("fan_enabled"));
  }

  // ---- saving ----
  function pinValue(id) {
    const text = $(id).value.trim();
    return text === "" ? null : Number(text);
  }

  async function saveGeneral() {
    const status = $("general-status");
    const body = {};
    const spotifyOn = isOn($("toggle-spotify"));
    const radioOn = isOn($("toggle-radio"));
    if (spotifyOn !== (loaded.SPOTIFY_ENABLED !== "no")) body.SPOTIFY_ENABLED = spotifyOn ? "yes" : "no";
    if (radioOn !== (loaded.RADIO_ENABLED !== "no")) body.RADIO_ENABLED = radioOn ? "yes" : "no";
    const airplayOn = isOn($("toggle-airplay"));
    if (airplayOn !== (loaded.AIRPLAY_ENABLED === "yes")) body.AIRPLAY_ENABLED = airplayOn ? "yes" : "no";
    if (spotifyOn && $("DEVICE_NAME").value !== (loaded.DEVICE_NAME || "")) body.DEVICE_NAME = $("DEVICE_NAME").value;
    if ($("DEFAULT_VOLUME").value !== String(loaded.DEFAULT_VOLUME || "")) body.DEFAULT_VOLUME = $("DEFAULT_VOLUME").value;
    if (chosenAccent() !== (loaded.ACCENT_COLOR || "blue")) body.ACCENT_COLOR = chosenAccent();
    if (!Object.keys(body).length) {
      status.textContent = "Nothing changed.";
      return;
    }
    $("save-general").disabled = true;
    try {
      const result = await api("/api/config", { body: body });
      applyAccent();
      await loadConfig();
      status.textContent = "Saved" + (result.applied && result.applied.length ? ": " + result.applied.join(", ") : "") + ".";
    } catch (err) {
      showError(status, err);
    } finally {
      $("save-general").disabled = false;
    }
  }

  async function saveGpio() {
    const status = $("gpio-status");
    const body = {
      case: $("case").value,
      fan_enabled: isOn($("fan_enabled")),
      fan_pin: pinValue("fan_pin"),
    };
    if ($("case").value === "nespi") {
      body.power_pin = pinValue("power_pin");
      body.reset_pin = pinValue("reset_pin");
      body.led_pin = pinValue("led_pin");
    }
    $("save-gpio").disabled = true;
    try {
      const result = await api("/api/hardware", { body: body });
      await loadHardware();
      status.textContent = result.restarted && result.restarted.length
        ? "Saved. Applied: " + result.restarted.join(", ") + "."
        : "Saved.";
    } catch (err) {
      showError(status, err);
    } finally {
      $("save-gpio").disabled = false;
    }
  }

  async function saveUpdates() {
    const status = $("updates-status");
    const body = {};
    ["SOLOIST_UPDATE_AFTER_DAYS", "APT_UPGRADE_AFTER_DAYS"].forEach(function (key) {
      if ($(key).value !== String(loaded[key] || "")) body[key] = $(key).value;
    });
    if (!Object.keys(body).length) {
      status.textContent = "Nothing changed.";
      return;
    }
    $("save-updates").disabled = true;
    try {
      await api("/api/config", { body: body });
      await loadConfig();
      status.textContent = "Saved.";
    } catch (err) {
      showError(status, err);
    } finally {
      $("save-updates").disabled = false;
    }
  }

  // ---- Code from GitHub ----
  async function checkCode() {
    const status = $("code-status");
    const list = $("code-commits");
    $("check").disabled = true;
    $("update").disabled = true;
    status.textContent = "Checking GitHub...";
    list.replaceChildren();
    try {
      const info = await api("/api/code/update");
      if (info.update_available) {
        status.textContent = "Update available on " + info.branch + ": " + info.current + " to " + info.latest + ".";
        info.commits.forEach(function (subject) {
          const item = document.createElement("li");
          item.textContent = subject;
          list.append(item);
        });
        $("update").disabled = false;
      } else {
        status.textContent = "Up to date (" + info.branch + ", " + info.current + ").";
      }
    } catch (err) {
      showError(status, err);
    } finally {
      $("check").disabled = false;
    }
  }

  async function updateCode() {
    if (!window.confirm("Update the web interface from GitHub now? The page reloads in a few seconds.")) return;
    $("update").disabled = true;
    $("check").disabled = true;
    $("code-status").textContent = "Updating...";
    try {
      await api("/api/code/update", { body: { confirm: true } });
      $("code-status").textContent = "Updated. Restarting the web service...";
      setTimeout(function () { window.location.reload(); }, 6000);
    } catch (err) {
      showError($("code-status"), err);
      $("check").disabled = false;
    }
  }

  // ---- wiring ----
  $("toggle-spotify").addEventListener("click", function () {
    setOn($("toggle-spotify"), !isOn($("toggle-spotify")));
    showSpotifyFields();
    refreshSpotifyStatus();
  });
  $("open-key").addEventListener("click", function () {
    $("key-input").value = "";
    $("key-error").textContent = "";
    $("key-dialog").showModal();
    $("key-input").focus();
  });
  $("key-cancel").addEventListener("click", function () { $("key-dialog").close(); });
  $("key-form").addEventListener("submit", function (e) {
    e.preventDefault();
    const value = $("key-input").value.trim();
    api("/api/config", { body: { SOLOIST_API_KEY: value } }).then(function () {
      $("key-dialog").close();
      $("general-status").textContent = "API key saved.";
      return loadConfig();
    }).then(refreshSpotifyStatus).catch(function (err) { showError($("key-error"), err); });
  });
  $("toggle-radio").addEventListener("click", function () { setOn($("toggle-radio"), !isOn($("toggle-radio"))); });
  $("toggle-airplay").addEventListener("click", function () { setOn($("toggle-airplay"), !isOn($("toggle-airplay"))); refreshAirplayStatus(); });
  $("fan_enabled").addEventListener("click", function () { setOn($("fan_enabled"), !isOn($("fan_enabled"))); showGpioFields(); });
  $("case").addEventListener("change", showGpioFields);
  document.querySelectorAll("#accent-swatches [data-name]").forEach(function (b) {
    b.addEventListener("click", function () { selectAccent(b.dataset.name); });
  });
  $("save-general").addEventListener("click", function () { saveGeneral(); });
  $("save-gpio").addEventListener("click", function () { saveGpio(); });
  $("save-updates").addEventListener("click", function () { saveUpdates(); });
  $("check").addEventListener("click", checkCode);
  $("update").addEventListener("click", updateCode);

  // ---- Bluetooth: on/off, pairing window with the code check, paired phones ----
  function btMessage(text, bad) {
    $("bt-message").className = bad ? "status bad" : "muted";
    $("bt-message").textContent = text;
  }

  function drawBluetooth(state) {
    if (!state.pending) shownCode = null;  // the pairing is over: the next code will show again
    showMatch(state.pending);
    setOn($("toggle-bluetooth"), !!state.powered);
    $("bt-details").hidden = !state.powered;  // nothing else is shown while Bluetooth is off
    $("bt-status").textContent = state.powered ? "on" : "off";
    $("bt-status").className = "status " + (state.powered ? "ok" : "off");
    $("bt-name").textContent = state.name ? "Shown to phones as \"" + state.name + "\"." : "";
    const list = $("bt-devices");
    list.replaceChildren();
    if (!state.devices || state.devices.length === 0) {
      list.append(el("li", "muted", "No phones paired yet."));
      return;
    }
    state.devices.forEach(function (device) {
      const row = el("li", "row-toggle");
      row.append(el("span", "", device.name + "  " + device.address));
      const forget = el("button", "ctl small", "Forget");
      forget.type = "button";
      forget.addEventListener("click", function () { forgetPhone(device.address, device.name); });
      row.append(forget);
      list.append(row);
    });
  }

  async function loadBluetooth() {
    try {
      drawBluetooth(await api("/api/bluetooth"));
    } catch (err) {
      btMessage("Cannot read Bluetooth: " + err.message, true);
    }
  }

  async function setBluetooth(on) {
    try {
      drawBluetooth(await api("/api/bluetooth/power", { body: { on: on } }));
      btMessage(on ? "Bluetooth is on. Playing it stops Spotify, radio and AirPlay." : "Bluetooth is off.", false);
    } catch (err) {
      btMessage(err.message, true);
      loadBluetooth();
    }
  }

  // a phone is pairing: its code is shown here, and the user says whether it matches
  let shownCode = null;
  function showMatch(pending) {
    if (!pending) return;
    if (shownCode === pending.code && $("match-dialog").open) return;
    shownCode = pending.code;
    $("match-code").textContent = pending.code.slice(0, 3) + " " + pending.code.slice(3);
    $("match-error").textContent = "";
    if (!$("match-dialog").open) $("match-dialog").showModal();
  }

  async function answerMatch(match) {
    try {
      await api("/api/bluetooth/decision", { body: { match: match } });
      $("match-dialog").close();  // shownCode stays set, so the poll does not reopen this code
      btMessage(match ? "Pairing confirmed." : "Pairing refused.", !match);
      loadBluetooth();
    } catch (err) {
      $("match-error").textContent = err.message;
    }
  }

  async function pairPhone() {
    $("bt-pair").disabled = true;
    try {
      drawBluetooth(await api("/api/bluetooth/pair", { method: "POST" }));
      $("bt-pair-note").textContent = "Open Bluetooth on the phone and choose this box. Compare the code on the phone with the code shown here. The window closes in 2 minutes.";
    } catch (err) {
      btMessage(err.message, true);
    } finally {
      $("bt-pair").disabled = false;
    }
  }

  async function forgetPhone(address, name) {
    if (!window.confirm("Forget " + name + "? It must pair again to play.")) return;
    try {
      drawBluetooth(await api("/api/bluetooth/forget", { body: { address: address } }));
      btMessage(name + " was forgotten.", false);
    } catch (err) {
      btMessage(err.message, true);
    }
  }

  $("toggle-bluetooth").addEventListener("click", function () { setBluetooth(!isOn(this)); });
  $("match-yes").addEventListener("click", function () { answerMatch(true); });
  $("match-no").addEventListener("click", function () { answerMatch(false); });
  $("bt-pair").addEventListener("click", pairPhone);
  loadBluetooth();
  setInterval(loadBluetooth, 2000);  // shows a pairing code as soon as a phone asks for it

  loadConfig().catch(function (err) { showError($("general-status"), err); });
  loadHardware().catch(function (err) { showError($("gpio-status"), err); });
  setInterval(refreshSpotifyStatus, 15000);
  setInterval(refreshAirplayStatus, 15000);
  checkCode();
})();
