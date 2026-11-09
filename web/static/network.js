// Wi-Fi page (prototype): the screens and actions, with sample data in place of the Pi.
// Open with ?state=wifi (default), ?state=ethernet, ?state=hotspot or ?state=none to see each mode.
(function () {
  const params = new URLSearchParams(window.location.search);
  const HOTSPOT_NAME = "device";

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
      $("current-note").textContent = "Add a network below to leave hotspot mode.";
      return;
    }
    if (state.mode === "ethernet") {
      $("current-name").textContent = "Ethernet cable";
      $("current-type").textContent = "online";
      $("current-type").className = "status ok";
      $("current-note").textContent = "You can also add a Wi-Fi network below. The cable keeps working.";
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

  function drawNearby() {
    const list = $("nearby");
    list.replaceChildren();
    state.nearby.forEach(function (net) {
      const row = el("li", "");
      const pick = el("button", "nearby-row-btn");
      pick.type = "button";
      pick.append(
        el("span", "nearby-name", net.name),
        el("span", "nearby-muted", net.secure ? "secured" : "open"),
        signalBars(net.signal),
        el("span", "nearby-muted nearby-saved", state.saved.indexOf(net.name) !== -1 ? "saved" : "")
      );
      pick.addEventListener("click", function () {
        $("ssid").value = net.name;
        $("password").value = "";
        $("password").focus();
      });
      row.append(pick);
      list.append(row);
    });
  }

  function drawSaved() {
    const options = $("saved-networks");
    options.replaceChildren();
    state.saved.forEach(function (name) {
      const option = el("option", "", name);
      option.value = name;
      options.append(option);
    });
    const list = $("saved");
    list.replaceChildren();
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

  // Connect: check the name and password, then "test" the network (sample: the password "wrong-password" fails).
  function connect() {
    const name = $("ssid").value.trim();
    const password = $("password").value;
    const status = $("connect-status");
    status.className = "muted";
    if (!name || name.length > 32) { status.textContent = "Enter a network name (1 to 32 characters)."; return; }
    if (password && (password.length < 8 || password.length > 63)) { status.textContent = "Password must be 8 to 63 characters."; return; }
    const button = $("connect");
    button.disabled = true;
    status.textContent = "Testing the password...";
    setTimeout(function () {
      button.disabled = false;
      if (password === "wrong-password") {
        status.textContent = "Password not accepted. " +
          (state.mode === "hotspot" ? "The hotspot stays on, try again." : "The Pi stays on " + (state.current || "the previous network") + ".");
        status.className = "status bad";
        return;
      }
      state.current = name;
      if (state.saved.indexOf(name) === -1) state.saved.push(name);
      const wasHotspot = state.mode === "hotspot";
      state.mode = "wifi";
      status.textContent = wasHotspot ? "Connected to " + name + ". The hotspot is off." : "Connected to " + name + ".";
      status.className = "status ok";
      $("password").value = "";
      draw();
    }, 1500);
  }

  $("show-password").addEventListener("change", function () {
    $("password").type = this.checked ? "text" : "password";
  });
  $("connect").addEventListener("click", connect);
  $("scan").addEventListener("click", function () {
    $("scan-status").textContent = "Sample list, nothing scanned.";
  });

  draw();
})();
