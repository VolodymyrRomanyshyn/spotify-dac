// Settings page: General, GPIO and Updates, each with its own save; plus the GitHub update check.
(function () {
  const $ = function (id) { return document.getElementById(id); };
  let loaded = {};
  let hardware = null;

  function showError(target, err) {
    target.textContent = err.message || String(err);
  }
  function restartText(restarted) {
    return restarted && restarted.length ? "applied: " + restarted.join(", ") : "saved";
  }
  function pinValue(id) {
    const text = $(id).value.trim();
    return text === "" ? null : Number(text);
  }
  function setHints(editable) {
    document.querySelectorAll("[data-hint]").forEach(function (hint) {
      const key = hint.getAttribute("data-hint");
      if (editable[key]) hint.textContent = editable[key];
    });
  }

  // ---- General: device name, default volume, audio device ----
  async function loadConfig() {
    const data = await api("/api/config");
    loaded = data.values;
    $("DEVICE_NAME").value = loaded.DEVICE_NAME || "";
    $("DEFAULT_VOLUME").value = loaded.DEFAULT_VOLUME || "";
    $("SOLOIST_UPDATE_AFTER_DAYS").value = loaded.SOLOIST_UPDATE_AFTER_DAYS || "";
    $("APT_UPGRADE_AFTER_DAYS").value = loaded.APT_UPGRADE_AFTER_DAYS || "";
    setHints(data.editable);
  }

  async function loadHardware() {
    hardware = await api("/api/hardware");
    const sinkSelect = $("sink");
    sinkSelect.replaceChildren(...hardware.audio.sinks.map(function (sink) {
      return new Option(sink.label, sink.name, false, sink.name === hardware.audio.selected);
    }));
    if (!hardware.audio.sinks.length) sinkSelect.append(new Option("No audio device found", ""));
    $("save-general").disabled = false;

    $("case").value = hardware.case;
    $("poweroff").value = hardware.poweroff;
    $("power_pin").value = hardware.pins.POWER_PIN;
    $("reset_pin").value = hardware.pins.RESET_PIN;
    $("led_pin").value = hardware.pins.LED_PIN;
    $("power_enable_pin").textContent = hardware.power_enable_pin;
    $("fan_enabled").checked = hardware.fan.enabled;
    $("fan_pin").value = hardware.fan.pin;
    $("hat-note").textContent = hardware.hat
      ? "The IQaudIO HAT uses GPIO " + hardware.hat_pins.join(", ") + ", so those pins can't be used here."
      : "";
    $("nespi-only").hidden = $("case").value !== "nespi";
  }

  async function saveGeneral() {
    const status = $("general-status");
    const body = {};
    if ($("DEVICE_NAME").value !== (loaded.DEVICE_NAME || "")) body.DEVICE_NAME = $("DEVICE_NAME").value;
    if ($("DEFAULT_VOLUME").value !== String(loaded.DEFAULT_VOLUME || "")) body.DEFAULT_VOLUME = $("DEFAULT_VOLUME").value;
    const sinkChanged = $("sink").value && $("sink").value !== hardware.audio.selected;
    if (!Object.keys(body).length && !sinkChanged) {
      status.textContent = "Nothing changed.";
      return;
    }
    $("save-general").disabled = true;
    try {
      const done = [];
      if (Object.keys(body).length) {
        const result = await api("/api/config", { body: body });
        if (result.restart && result.restart.length) {
          await api("/api/config/apply", { body: { services: result.restart } });
        }
        done.push("name and volume " + restartText(result.restart));
      }
      if (sinkChanged) {
        const result = await api("/api/hardware", { body: { sink: $("sink").value } });
        done.push("audio device " + restartText(result.restarted));
      }
      await loadConfig();
      await loadHardware();
      status.textContent = done.join("; ") + ".";
    } catch (err) {
      showError(status, err);
    } finally {
      $("save-general").disabled = false;
    }
  }

  // ---- GPIO: case, power switch, reset, LED, power-off mode, fan ----
  async function saveGpio() {
    const status = $("gpio-status");
    const body = {
      case: $("case").value,
      poweroff: $("poweroff").value,
      fan_enabled: $("fan_enabled").checked,
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
      status.textContent = "Saved; " + restartText(result.restarted) + ".";
    } catch (err) {
      showError(status, err);
    } finally {
      $("save-gpio").disabled = false;
    }
  }

  // ---- Updates: schedules for Soloist and system packages ----
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

  $("save-general").addEventListener("click", function () { saveGeneral(); });
  $("save-gpio").addEventListener("click", function () { saveGpio(); });
  $("save-updates").addEventListener("click", function () { saveUpdates(); });
  $("check").addEventListener("click", checkCode);
  $("update").addEventListener("click", updateCode);
  $("case").addEventListener("change", function () { $("nespi-only").hidden = $("case").value !== "nespi"; });

  loadConfig().catch(function (err) { showError($("general-status"), err); });
  loadHardware().catch(function (err) { showError($("general-status"), err); });
  checkCode();
})();
