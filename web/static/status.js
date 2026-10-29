// Status page: reads /api/status every 10 seconds and draws one card per group.
(function () {
  const REFRESH_MS = 10000;
  const root = document.documentElement;
  const cards = document.getElementById("cards");
  const banner = document.getElementById("banner");
  const overall = document.getElementById("overall");
  const overallText = document.getElementById("overall-text");
  const overallDetail = document.getElementById("overall-detail");
  const updated = document.getElementById("updated");

  // ---- helpers ----
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function row(label, value) {
    const r = el("div", "row");
    r.append(el("span", "", label), el("span", "", value === null || value === undefined || value === "" ? "-" : String(value)));
    return r;
  }
  function card(title, mark, body) {
    const c = el("section", "card");
    const h = el("h2");
    h.append(el("span", "mark " + mark), document.createTextNode(title));
    c.append(h, ...body);
    return c;
  }
  function uptimeText(seconds) {
    if (seconds === null || seconds === undefined) return "-";
    const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
    return (d ? d + " d " : "") + h + " h " + m + " min";
  }
  function isOnboard(card) {
    return card.driver.indexOf("bcm2835") === 0 || card.name.indexOf("Headphones") === 0;
  }
  function dacCardNames(dac) {
    const dacs = dac.cards.filter(c => !isOnboard(c)).map(c => c.name);
    return dacs.length ? dacs.join(", ") : null;
  }
  function onboardText(dac) {
    return dac.cards.some(isOnboard) ? "present, not used" : "none";
  }
  function dacMark(dac) {
    return dacCardNames(dac) ? "ok" : "error";
  }
  function playingText(dac) {
    const running = dac.streams.filter(x => x.state === "RUNNING");
    if (!running.length) return "idle";
    const first = running[0];
    return "RUNNING on " + first.card + (first.rate ? ", " + first.rate + " Hz" : "");
  }
  function yesNo(value) {
    return value === null || value === undefined ? "-" : (value ? "yes" : "no");
  }
  function soloistMark(sol) {
    if (!sol.version || !sol.api.reachable) return "error";
    if (sol.api.logged_in === false) return "warning";
    return "ok";
  }
  const MARK_TEXT = { ok: "OK", warning: "Warning", error: "Problem" };

  // ---- drawing ----
  function draw(s) {
    overall.className = "overall " + (s.overall === "error" ? "error" : s.overall === "warning" ? "warning" : "ok");
    overallText.textContent = MARK_TEXT[s.overall] || s.overall;
    const issues = [].concat(s.problems.map(p => "service not running: " + p), s.warnings);
    overallDetail.textContent = issues.length ? issues.join(" - ") : "Everything is running.";

    const services = s.services.map(function (svc) {
      let mark = "ok";
      if (svc.enabled === "enabled" && svc.active !== "active") mark = "error";
      if (svc.enabled !== "enabled" && svc.active === "active") mark = "warning";
      const r = el("div", "row");
      r.append(el("span", "", svc.name), el("span", "tag " + mark, svc.enabled + " / " + svc.active));
      return r;
    });

    const soloist = s.soloist.version ? "" : null;
    const cardsList = [
      card("Services", s.services.some(x => x.enabled === "enabled" && x.active !== "active") ? "error" : "ok", services),
      card("Soloist", soloistMark(s.soloist), [
        row("Version", s.soloist.version || "not found"),
        row("Local API (websocket)", s.soloist.api.websocket || "not listening"),
        row("API reachable", yesNo(s.soloist.api.reachable)),
        row("Logged in to Spotify", yesNo(s.soloist.api.logged_in)),
        row("Active device", yesNo(s.soloist.api.active_device)),
      ]),
      card("DAC", dacMark(s.dac), [
        row("Sound card", dacCardNames(s.dac) || "not found"),
        row("Onboard audio", onboardText(s.dac)),
        row("Playing", playingText(s.dac)),
      ]),
      card("Power and heat", s.power.flags && (s.power.flags.undervoltage_now) ? "error"
        : (s.power.flags && (s.power.flags.throttled_seen || s.power.flags.undervoltage_seen) ? "warning" : "ok"), [
        row("Undervoltage now", s.power.flags ? (s.power.flags.undervoltage_now ? "yes" : "no") : "not available"),
        row("Throttled earlier", s.power.flags ? (s.power.flags.throttled_seen || s.power.flags.undervoltage_seen ? "yes" : "no") : "-"),
        row("CPU temperature", s.power.temperature_c === null ? "-" : s.power.temperature_c + " C"),
      ]),
      card("System", (s.system.disk_used_percent || 0) > 90 ? "error" : (s.system.disk_used_percent || 0) > 80 ? "warning" : "ok", [
        row("Uptime", uptimeText(s.system.uptime_seconds)),
        row("Disk used", s.system.disk_used_percent === null ? "-" : s.system.disk_used_percent + " %"),
        row("Addresses", s.system.addresses.join(", ") || "-"),
      ]),
      card("Last update log", "ok", [
        s.last_update.length ? el("pre", "", s.last_update.join("\n")) : el("p", "muted", "No update log yet."),
      ]),
    ];
    cards.replaceChildren(...cardsList);
    void soloist;
  }

  // ---- loading ----
  async function load() {
    try {
      const response = await fetch("/api/status", { cache: "no-store", credentials: "same-origin" });
      const body = await response.json();
      if (response.status === 401) {
        showBanner("Sign in is required. The login page is not built yet.");
        return;
      }
      if (!body.ok) throw new Error(body.error || "request failed");
      banner.hidden = true;
      draw(body.data);
      updated.textContent = "Updated " + new Date().toLocaleTimeString();
    } catch (err) {
      showBanner("Cannot reach the Pi (" + err.message + "). Showing the last values.");
    }
  }
  function showBanner(text) {
    banner.textContent = text;
    banner.hidden = false;
  }

  document.getElementById("refresh").addEventListener("click", load);
  load();
  setInterval(load, REFRESH_MS);
})();
