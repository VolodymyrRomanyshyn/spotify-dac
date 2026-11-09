// Wi-Fi page (prototype): the screens and actions, with sample data in place of the Pi.
// Open with ?state=wifi (default), ?state=ethernet, ?state=hotspot or ?state=none to see each mode.
(function () {
  const params = new URLSearchParams(window.location.search);

  // sample data
  const state = {
    mode: params.get("state") || "wifi",          // wifi | ethernet | hotspot | none
    current: params.get("state") === "ethernet" ? "" : "Home-WiFi",
    saved: ["Home-WiFi", "Office"],
    nearby: [
      { name: "Home-WiFi", signal: 82, secure: true },
      { name: "Neighbour 5G", signal: 55, secure: true },
      { name: "Cafe Free", signal: 40, secure: false },
      { name: "Office", signal: 30, secure: true },
    ],
  };

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
    $("hotspot-banner").hidden = state.mode !== "hotspot";
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
    $("current-name").textContent = state.current;
    $("current-type").textContent = "Wi-Fi";
    $("current-type").className = "status ok";
    $("current-note").textContent = "You can switch to another network below.";
  }

  // one row per network: name, secured or open, signal, and Save (or "saved")
  function drawNearby() {
    const list = $("nearby");
    list.replaceChildren();
    state.nearby.forEach(function (net) {
      const row = el("li", "nearby-row");
      row.append(el("span", "nearby-name", net.name));
      row.append(el("span", "nearby-muted", net.secure ? "secured" : "open"));
      row.append(signalBars(net.signal));
      if (state.saved.indexOf(net.name) !== -1) {
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
      forget.addEventListener("click", function () {
        state.saved = state.saved.filter(function (n) { return n !== name; });
        draw();
      });
      row.append(forget);
      list.append(row);
    });
  }

  function draw() {
    drawCurrent();
    drawNearby();
    drawSaved();
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

  // Save: check the password, "test" it (sample: "wrong-password" fails), then save the network.
  function submitSave(event) {
    event.preventDefault();
    if (!pending) return;
    const password = pending.secure ? $("save-password").value : "";
    const error = $("save-error");
    error.className = "status bad";
    if (pending.secure && (password.length < 8 || password.length > 63)) {
      error.textContent = "Password must be 8 to 63 characters.";
      return;
    }
    $("save-submit").disabled = true;
    error.className = "muted";
    error.textContent = "Testing the password...";
    const net = pending;
    setTimeout(function () {
      $("save-submit").disabled = false;
      if (password === "wrong-password") {
        error.className = "status bad";
        error.textContent = "Password not accepted. Try again.";
        return;
      }
      if (state.saved.indexOf(net.name) === -1) state.saved.push(net.name);
      state.current = net.name;
      state.mode = "wifi";
      closeSave();
      draw();
    }, 1500);
  }

  $("save-show").addEventListener("change", function () {
    $("save-password").type = this.checked ? "text" : "password";
  });
  $("save-cancel").addEventListener("click", closeSave);
  $("save-form").addEventListener("submit", submitSave);
  $("scan").addEventListener("click", function () {
    $("scan-status").textContent = "Sample list, nothing scanned.";
  });

  draw();
})();
