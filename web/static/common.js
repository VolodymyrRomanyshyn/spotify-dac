// Shared by every page: the light/dark theme (an icon button) and a small API helper.
(function () {
  const root = document.documentElement;
  const themeButton = document.getElementById("theme");
  // moon: shown in light mode (click for dark); sun: shown in dark mode (click for light)
  const MOON = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="currentColor"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  const SUN = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';

  function isDark() {
    const chosen = root.getAttribute("data-theme");
    if (chosen) return chosen === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function drawThemeIcon() {
    if (!themeButton) return;
    const dark = isDark();
    themeButton.innerHTML = dark ? SUN : MOON;
    themeButton.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    themeButton.title = dark ? "Light mode" : "Dark mode";
  }
  function applyTheme(choice) {
    if (choice === "dark" || choice === "light") {
      root.setAttribute("data-theme", choice);
    } else {
      root.removeAttribute("data-theme");
    }
    drawThemeIcon();
  }

  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) { /* private mode: follow the system */ }
  applyTheme(saved);
  if (themeButton) {
    themeButton.addEventListener("click", function () {
      const next = isDark() ? "light" : "dark";
      applyTheme(next);
      try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
    });
  }
})();

// Header: the device name instead of a fixed title, and the menu button.
(function () {
  const brand = document.querySelector(".device");
  api("/api/device").then(function (d) {
    if (brand && d.name) brand.textContent = d.name;
  }).catch(function () { /* keep the placeholder */ });

  const burger = document.getElementById("burger");
  const menu = document.getElementById("menu");
  if (!burger || !menu) return;
  function setMenu(open) {
    menu.hidden = !open;
    burger.setAttribute("aria-expanded", String(open));
  }
  burger.addEventListener("click", function (event) {
    event.stopPropagation();
    setMenu(menu.hidden);
  });
  document.addEventListener("click", function (event) {
    if (!menu.contains(event.target)) setMenu(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setMenu(false);
  });
})();

// Calls the JSON API. Resolves with the "data" part, rejects with a readable message.
async function api(path, options) {
  const opts = Object.assign({ cache: "no-store", credentials: "same-origin" }, options || {});
  if (opts.body !== undefined) {
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.body = JSON.stringify(opts.body);
    opts.method = opts.method || "POST";
  }
  const response = await fetch(path, opts);
  let body = null;
  try { body = await response.json(); } catch (e) { body = null; }
  if (response.status === 401) throw new Error("sign in required");
  if (!body || !body.ok) throw new Error((body && body.error) || ("request failed (" + response.status + ")"));
  return body.data;
}
