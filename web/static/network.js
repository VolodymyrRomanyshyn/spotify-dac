// Wi-Fi page: shows the Pi's network state and lets you save a Wi-Fi network.
// Reads and changes go through the /api/network routes (web/api/wifi.py).
(function () {
  // what the Pi reported last
  const state = { mode: "none", current: null, ethernet: false, hotspot: { on: false, name: "device" }, saved: [], nearby: [] };
  let pending = null;  // the nearby network whose Save dialog is open

  const $ = (id) => document.getElementById(id);

  // signal strength as four bars (filled up to the level)
  function signalBars(signal) {
    const level = signal >= 70 ? 4 : signal >= 50 ? 3 : signal >= 30 ? 2 : 1;
    const box = el("span", "signal");
    box.setAttribute("aria-label", "signal " + level + " of 4");
    for (let i = 1; i <= 4; i++) box.append(el("i", i <= level ? "on" : ""));
    return box;
  }

  // hotspot card: the switch decides; the controls show only when it is on
  function drawHotspot() {
    const h = state.hotspot;
    const allowed = !!h.allowed;
    const toggle = $("hotspot-allowed");
    toggle.setAttribute("aria-pressed", String(allowed));
    toggle.querySelector(".state").textContent = allowed ? "On" : "Off";
    $("hotspot-controls").hidden = !allowed;
    if (!allowed) {
      $("hotspot-status").textContent = "Off. The box will not start a hotspot, even with no network or the reset button.";
      return;
    }
    $("hotspot-status").textContent = h.on
      ? "Running now. Join \"" + h.name + "\" on your phone to reach this page."
      : "On. It starts by itself when there is no network, or with the button below.";
    $("hotspot-toggle").textContent = h.on ? "Turn off hotspot" : "Turn on hotspot";
  }

  function drawCurrent() {
    if (state.mode === "hotspot") {
      $("current-name").textContent = "nothing (hotspot on)";
      $("current-type").textContent = "";
      $("current-note").textContent = "Save a network below to leave hotspot mode.";
      return;
    }
    if (state.mode === "ethernet") {
      $("current-name").textContent = "Ethernet cable";
      $("current-type").textContent = "online";
      $("current-type").className = "status ok";
      $("current-note").textContent = "You can also save a Wi-Fi network below. The cable keeps working.";
      return;
    }
    if (state.mode === "none") {
      $("current-name").textContent = "nothing";
      $("current-type").textContent = "offline";
      $("current-type").className = "status bad";
      $("current-note").textContent = "The hotspot starts after the fallback time.";
      return;
    }
    $("current-name").textContent = state.current || "Wi-Fi";
    $("current-type").textContent = "Wi-Fi";
    $("current-type").className = "status ok";
    $("current-note").textContent = "You can switch to another network below.";
  }

  // one row per network: name, secured or open, signal, and Save (or "saved")
  function drawNearby() {
    const list = $("nearby");
    list.replaceChildren();
    if (state.nearby.length === 0) {
      list.append(el("li", "muted", "No networks found. Press Scan again."));
      return;
    }
    state.nearby.forEach(function (net) {
      const row = el("li", "nearby-row");
      row.append(el("span", "nearby-name", net.name));
      row.append(el("span", "nearby-muted", net.secure ? "secured" : "open"));
      row.append(signalBars(net.signal));
      if (net.saved) {
        row.append(el("span", "nearby-muted nearby-action", "saved"));
      } else {
        const save = el("button", "ctl small nearby-action", "Save");
        save.type = "button";
        save.addEventListener("click", function () { openSave(net); });
        row.append(save);
      }
      list.append(row);
    });
  }

  // priority order: the Pi joins the first one it can see
  function drawPriority() {
    const list = $("priority");
    list.replaceChildren();
    if (state.saved.length === 0) {
      list.append(el("li", "muted", "No saved networks yet. Use Save next to a network above."));
      return;
    }
    state.saved.forEach(function (name, index) {
      const row = el("li", "saved-row");
      row.append(el("span", "saved-order", String(index + 1)));
      row.append(el("span", "saved-name", name));
      if (index === 0) row.append(el("span", "badge", "first"));
      const actions = el("span", "saved-actions");
      actions.append(
        smallButton("Up", index === 0, function () { moveNetwork(name, "up"); }),
        smallButton("Down", index === state.saved.length - 1, function () { moveNetwork(name, "down"); })
      );
      row.append(actions);
      list.append(row);
    });
  }

  // saved networks: connect now, or forget
  function drawSaved() {
    const list = $("saved");
    list.replaceChildren();
    if (state.saved.length === 0) {
      list.append(el("li", "muted", "Nothing saved."));
      return;
    }
    state.saved.forEach(function (name) {
      const row = el("li", "saved-row");
      row.append(el("span", "saved-name", name));
      if (name === state.current) row.append(el("span", "badge", "connected"));
      const actions = el("span", "saved-actions");
      actions.append(
        smallButton("Connect", name === state.current, function () { switchNetwork(name); }),
        smallButton("Forget", false, function () { forgetNetwork(name); })
      );
      row.append(actions);
      list.append(row);
    });
  }

  function smallButton(label, disabled, onClick) {
    const button = el("button", "ctl small", label);
    button.type = "button";
    button.disabled = disabled;
    button.addEventListener("click", onClick);
    return button;
  }

  function draw() {
    drawHotspot();
    drawCurrent();
    drawNearby();
    drawPriority();
    drawSaved();
  }

  // ---- talking to the Pi ----
  function apply(data) {
    state.mode = data.mode;
    state.current = data.current;
    state.ethernet = data.ethernet;
    state.hotspot = data.hotspot;
    state.saved = data.saved || [];
    state.nearby = data.nearby || state.nearby;
    draw();
  }

  async function load() {
    try {
      apply(await api("/api/network"));
    } catch (err) {
      $("scan-status").textContent = "Cannot read the Wi-Fi state: " + err.message;
    }
  }

  async function scan() {
    $("scan").disabled = true;
    $("scan-status").className = "muted";
    $("scan-status").textContent = "Scanning...";
    try {
      const data = await api("/api/network/scan", { method: "POST" });
      state.nearby = data.nearby || [];
      drawNearby();
      $("scan-status").textContent = "Found " + state.nearby.length + " networks.";
    } catch (err) {
      $("scan-status").className = "status bad";
      $("scan-status").textContent = err.message;
    } finally {
      $("scan").disabled = false;
    }
  }

  // the list changes at once; the Pi confirms the order in the background
  async function moveNetwork(name, direction) {
    const index = state.saved.indexOf(name);
    const target = direction === "up" ? index - 1 : index + 1;
    if (target < 0 || target >= state.saved.length) return;
    const order = state.saved.slice();
    order[index] = order[target];
    order[target] = name;
    state.saved = order;
    draw();
    try {
      const data = await api("/api/network/move", { body: { name: name, direction: direction } });
      state.saved = data.saved;
      drawPriority();
    } catch (err) {
      $("scan-status").className = "status bad";
      $("scan-status").textContent = err.message;
      await load();
    }
  }

  async function switchNetwork(name) {
    $("scan-status").className = "muted";
    $("scan-status").textContent = "Connecting to " + name + "...";
    try {
      const result = await api("/api/network/switch", { body: { name: name } });
      $("scan-status").className = "status ok";
      $("scan-status").textContent = "Connected to " + result.current + ".";
      await load();
    } catch (err) {
      $("scan-status").className = "status bad";
      $("scan-status").textContent = err.message;
      await load();
    }
  }

  async function forgetNetwork(name) {
    try {
      await api("/api/network/forget", { body: { name: name } });
      await load();
    } catch (err) {
      $("scan-status").className = "status bad";
      $("scan-status").textContent = err.message;
    }
  }

  function hotspotMessage(text, bad) {
    $("hotspot-message").className = bad ? "status bad" : "muted";
    $("hotspot-message").textContent = text;
  }

  // a yes/no question in a dialog; resolves true when the user continues
  function confirmAction(title, text, okLabel) {
    return new Promise(function (resolve) {
      const dialog = $("confirm-dialog");
      $("confirm-title").textContent = title;
      $("confirm-text").textContent = text;
      $("confirm-ok").textContent = okLabel;
      dialog.addEventListener("close", function onClose() {
        dialog.removeEventListener("close", onClose);
        resolve(dialog.returnValue === "ok");
      });
      dialog.showModal();
    });
  }

  async function setAllowed(allowed) {
    if (!allowed) {
      const sure = await confirmAction(
        "Turn off hotspot functionality?",
        "The hotspot will stop, and the box will not start one by itself or with the reset button. If the box has no network, you will reach it only by its home address.",
        "Turn off");
      if (!sure) { await load(); return; }
    }
    try {
      const data = await api("/api/network/hotspot-allowed", { body: { allowed: allowed } });
      state.hotspot = data;
      hotspotMessage(allowed ? "Hotspot functionality is on." : "Hotspot functionality is off.", false);
      draw();
    } catch (err) {
      hotspotMessage(err.message, true);
      await load();
    }
  }

  // a message with an OK button; the text may have several lines
  function showInfo(title, lines) {
    $("info-title").textContent = title;
    const box = $("info-text");
    box.replaceChildren();
    lines.forEach(function (line) { box.append(el("p", "", line)); });
    $("info-dialog").showModal();
  }

  async function toggleHotspot() {
    const turnOn = !state.hotspot.on;
    const sure = await confirmAction(
      turnOn ? "Turn on the hotspot?" : "Turn off the hotspot?",
      turnOn
        ? "This box will leave your home Wi-Fi and start the hotspot \"" + state.hotspot.name + "\". Your phone must join that network to reach this page. Continue?"
        : "This box will stop the hotspot. If it has no home Wi-Fi or cable, it cannot be reached until one is connected. Continue?",
      turnOn ? "Turn on" : "Turn off");
    if (!sure) return;
    try {
      await api("/api/network/hotspot", { body: { on: turnOn } });
      hotspotMessage(turnOn ? "Starting the hotspot." : "Hotspot off.", false);
      if (turnOn) {
        showInfo("Hotspot is starting", [
          "Wait about 10 seconds, then on your phone join the Wi-Fi network \"" + state.hotspot.name + "\".",
          "Use the hotspot password you set on this page.",
          "Then open http://10.42.0.1 (or https://" + location.hostname + ":8443) to reach this page.",
        ]);
      }
      setTimeout(load, turnOn ? 8000 : 0);
    } catch (err) {
      hotspotMessage(err.message, true);
    }
  }

  // change the password: type it twice, then confirm
  function openPassword() {
    $("password-new").value = "";
    $("password-repeat").value = "";
    $("password-show").checked = false;
    $("password-new").type = "password";
    $("password-repeat").type = "password";
    $("password-error").textContent = "";
    $("password-dialog").showModal();
    $("password-new").focus();
  }

  async function submitPassword(event) {
    event.preventDefault();
    const first = $("password-new").value;
    const second = $("password-repeat").value;
    const error = $("password-error");
    if (first.length < 8 || first.length > 63) { error.textContent = "The password must be 8 to 63 characters."; return; }
    if (first !== second) { error.textContent = "The two passwords do not match."; return; }
    $("password-submit").disabled = true;
    try {
      const data = await api("/api/network/hotspot-password", { body: { password: first } });
      state.hotspot = data;
      $("password-dialog").close();
      hotspotMessage("Hotspot password changed. It is used the next time the hotspot starts.", false);
      draw();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      $("password-submit").disabled = false;
    }
  }

  // ---- Save dialog ----
  function openSave(net) {
    pending = net;
    $("save-title").textContent = "Save " + net.name;
    $("save-name").textContent = net.secure ? "Enter the password for this network." : "This network is open, no password needed.";
    $("save-password-field").hidden = !net.secure;
    $("save-show-field").hidden = !net.secure;
    $("save-password").value = "";
    $("save-password").type = "password";
    $("save-show").checked = false;
    $("save-error").textContent = "";
    $("save-submit").disabled = false;
    $("save-dialog").showModal();
    if (net.secure) $("save-password").focus();
  }

  function closeSave() {
    $("save-dialog").close();
    pending = null;
  }

  // Save: the Pi tries the password on the network. If it is accepted, the network is saved and joined.
  async function submitSave(event) {
    event.preventDefault();
    if (!pending) return;
    const net = pending;
    const password = net.secure ? $("save-password").value : null;
    const error = $("save-error");
    error.className = "status bad";
    if (net.secure && (password.length < 8 || password.length > 63)) {
      error.textContent = "Password must be 8 to 63 characters.";
      return;
    }
    $("save-submit").disabled = true;
    error.className = "muted";
    error.textContent = "Connecting, this can take up to 30 seconds...";
    try {
      const result = await api("/api/network/save", { body: { name: net.name, password: password } });
      closeSave();
      $("scan-status").className = "status ok";
      $("scan-status").textContent = result.hotspot ? "Saved." : "Connected to " + net.name + ".";
      await load();
      await scan();
    } catch (err) {
      error.className = "status bad";
      error.textContent = err.message;
    } finally {
      $("save-submit").disabled = false;
    }
  }

  $("save-show").addEventListener("change", function () {
    $("save-password").type = this.checked ? "text" : "password";
  });
  $("save-cancel").addEventListener("click", closeSave);
  $("save-form").addEventListener("submit", submitSave);
  $("scan").addEventListener("click", scan);
  $("hotspot-allowed").addEventListener("click", function () {
    setAllowed(this.getAttribute("aria-pressed") !== "true");
  });
  $("hotspot-toggle").addEventListener("click", toggleHotspot);
  $("hotspot-password-open").addEventListener("click", openPassword);
  $("password-form").addEventListener("submit", submitPassword);
  $("password-cancel").addEventListener("click", function () { $("password-dialog").close(); });
  $("password-show").addEventListener("change", function () {
    const type = this.checked ? "text" : "password";
    $("password-new").type = type;
    $("password-repeat").type = type;
  });

  // the saved list is shown right away; the nearby list needs a scan
  $("saved").replaceChildren(el("li", "muted", "Loading…"));
  $("nearby").replaceChildren(el("li", "muted", "Loading…"));
  load().then(scan);
})();
