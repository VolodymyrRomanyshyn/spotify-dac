// Wi-Fi page: shows the Pi's network state and lets you save a Wi-Fi network.
// Reads and changes go through the /api/network routes (web/api/wifi.py).
(function () {
  // what the Pi reported last
  const state = { mode: "none", current: null, ethernet: false, hotspot: { on: false, name: "device" }, saved: [], nearby: [] };
  let pending = null;  // the nearby network whose Save dialog is open

  const $ = (id) => document.getElementById(id);

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  // signal strength as four bars (filled up to the level)
  function signalBars(signal) {
    const level = signal >= 70 ? 4 : signal >= 50 ? 3 : signal >= 30 ? 2 : 1;
    const box = el("span", "signal");
    box.setAttribute("aria-label", "signal " + level + " of 4");
    for (let i = 1; i <= 4; i++) box.append(el("i", i <= level ? "on" : ""));
    return box;
  }

  function drawCurrent() {
    $("hotspot-banner").hidden = !state.hotspot.on;
    $("hotspot-name").textContent = state.hotspot.name || "device";
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

  function drawSaved() {
    const list = $("saved");
    list.replaceChildren();
    if (state.saved.length === 0) {
      list.append(el("li", "muted", "No saved networks yet. Use Save next to a network above."));
      return;
    }
    state.saved.forEach(function (name) {
      const row = el("li", "row-toggle");
      row.append(el("span", "", name));
      const forget = el("button", "ctl small", "Forget");
      forget.type = "button";
      forget.addEventListener("click", function () { forgetNetwork(name); });
      row.append(forget);
      list.append(row);
    });
  }

  function draw() {
    drawCurrent();
    drawNearby();
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

  async function forgetNetwork(name) {
    try {
      await api("/api/network/forget", { body: { name: name } });
      await load();
    } catch (err) {
      $("scan-status").className = "status bad";
      $("scan-status").textContent = err.message;
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

  // the saved list is shown right away; the nearby list needs a scan
  load().then(scan);
})();
