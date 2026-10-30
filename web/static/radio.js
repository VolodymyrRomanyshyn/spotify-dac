// Radio page: play a station, manage the station list, and search the built-in catalogs.
(function () {
  const $ = (id) => document.getElementById(id);
  const banner = $("banner"), nowTitle = $("now-title"), nowSub = $("now-sub"), nowControls = $("now-controls");
  const stationsBox = $("stations"), resultsBox = $("results"), searchInput = $("search"), searchNote = $("search-note");
  const formCard = $("form-card"), form = $("station-form"), formTitle = $("form-title"), formError = $("form-error");
  let stations = [];
  let playing = null;        // id of the station playing now
  let editingIndex = -1;     // -1 = adding
  let searchTimer = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function showError(message) { banner.textContent = message; banner.hidden = false; }
  function clearError() { banner.hidden = true; }
  function fail(err) { showError(err.message); }
  function iconButton(label, onClick, extra) {
    const b = el("button", "ctl small" + (extra ? " " + extra : ""), label);
    b.type = "button";
    b.setAttribute("aria-label", label);
    b.addEventListener("click", function (e) { e.stopPropagation(); onClick().catch(fail); });
    return b;
  }

  // ---- loading and saving ----
  async function load() {
    try {
      const data = await api("/api/radio/stations");
      stations = data.stations || [];
      playing = data.playing || null;
      draw();
      clearError();
    } catch (err) { fail(err); }
  }
  async function save(list) {
    const data = await api("/api/radio/stations", { method: "PUT", body: list });
    stations = data.stations;
    draw();
    return data;
  }

  // ---- now playing ----
  async function refreshNow() {
    try {
      const now = await api("/api/radio/now");
      playing = now.playing;
      const station = stations.find(function (s) { return s.id === playing; });
      if (playing && station) {
        nowTitle.textContent = station.name;
        const t = now.title;
        const fileish = t && /\.(m3u8?|mp3|aac|ogg|opus|pls)$/i.test(t);
        nowSub.textContent = (t && !fileish && t.toLowerCase() !== (station.name || "").toLowerCase()) ? t : "Live";
        nowControls.replaceChildren(iconButton("Stop", function () {
          return api("/api/radio/stop", { method: "POST" }).then(function () { playing = null; draw(); });
        }, "main"));
      } else {
        nowTitle.textContent = "Not playing";
        nowSub.textContent = "Tap a station to play it.";
        nowControls.replaceChildren();
      }
      drawStations();
    } catch (err) { /* keep the last values */ }
  }

  // ---- station list ----
  function play(station) {
    return api("/api/radio/play", { body: { id: station.id } }).then(function (data) {
      playing = data.playing;
      clearError();
      refreshNow();
    });
  }
  function move(index, delta) {
    const list = stations.slice();
    const target = index + delta;
    if (target < 0 || target >= list.length) return Promise.resolve();
    const tmp = list[index]; list[index] = list[target]; list[target] = tmp;
    return save(list);
  }
  function remove(index) {
    if (!window.confirm("Delete station \"" + stations[index].name + "\"?")) return Promise.resolve();
    const list = stations.slice();
    list.splice(index, 1);
    return save(list);
  }
  function drawStations() {
    stationsBox.replaceChildren(...stations.map(function (s, i) {
      const isPlaying = s.id === playing;
      const row = el("div", "station" + (isPlaying ? " playing" : ""));
      const info = el("button", "station-main");
      info.type = "button";
      info.setAttribute("aria-pressed", String(isPlaying));
      const info2 = el("div", "info");
      info2.append(el("span", "name", s.name), el("span", "muted small genre", s.genre || ""));
      info.append(info2);
      if (isPlaying) info.append(el("span", "badge", "Playing"));
      info.addEventListener("click", function () { play(s).catch(fail); });
      const actions = el("div", "row-actions");
      actions.append(
        iconButton("Up", function () { return move(i, -1); }),
        iconButton("Down", function () { return move(i, 1); }),
        iconButton("Edit", async function () { openForm(i); }),
        iconButton("Delete", function () { return remove(i); }, "danger")
      );
      row.append(info, actions);
      return row;
    }));
  }
  function draw() { drawStations(); refreshNow(); }

  // ---- add and edit form ----
  function openForm(index) {
    editingIndex = index;
    const s = index >= 0 ? stations[index] : { name: "", url: "", genre: "", logo: "", fallback: [] };
    formTitle.textContent = index >= 0 ? "Edit station" : "New station";
    form.name.value = s.name || "";
    form.url.value = s.url || "";
    form.genre.value = s.genre || "";
    form.logo.value = s.logo || "";
    form.fallback.value = (s.fallback || []).join("\n");
    formError.textContent = "";
    formCard.hidden = false;
    formCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function closeForm() { formCard.hidden = true; editingIndex = -1; }
  $("add-station").addEventListener("click", function () { openForm(-1); });
  $("form-cancel").addEventListener("click", closeForm);
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const record = {
      id: "",
      name: form.name.value.trim(),
      url: form.url.value.trim(),
      genre: form.genre.value.trim(),
      logo: form.logo.value.trim(),
      fallback: form.fallback.value.split("\n").map(function (x) { return x.trim(); }).filter(Boolean),
    };
    if (editingIndex >= 0) record.id = stations[editingIndex].id;
    else record.id = uniqueId(record.name);
    const list = stations.slice();
    if (editingIndex >= 0) list[editingIndex] = record; else list.push(record);
    save(list).then(function () { closeForm(); clearError(); }).catch(function (err) { formError.textContent = err.message; });
  });
  function uniqueId(name) {
    const base = name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "station";
    let id = base, n = 2;
    while (stations.some(function (s) { return s.id === id; })) { id = base + "-" + n; n++; }
    return id;
  }

  // ---- catalog search ----
  function drawResults(results) {
    resultsBox.replaceChildren(...results.map(function (r) {
      const row = el("div", "station");
      const info = el("div", "info");
      info.append(el("span", "name", r.name), el("span", "muted small genre", r.description || r.source || ""));
      row.append(info);
      if (r.added) {
        row.append(el("span", "badge", "Added"));
      } else {
        row.append(iconButton("Add", function () {
          const list = stations.concat([{ id: uniqueId(r.name), name: r.name, url: r.url, genre: r.description || "", logo: r.logo || "", fallback: r.fallback || [] }]);
          return save(list).then(function () { return runSearch(); });
        }, "main"));
      }
      return row;
    }));
  }
  async function runSearch() {
    const q = searchInput.value.trim();
    try {
      const data = await api("/api/radio/catalog?q=" + encodeURIComponent(q));
      drawResults(data.results);
      searchNote.textContent = data.results.length ? data.results.length + " found" + (data.results.length >= 60 ? " (first 60, refine the search)" : "") : "No stations found.";
    } catch (err) { fail(err); }
  }
  searchInput.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 300);
  });

  load();
  runSearch();
  setInterval(refreshNow, 3000);
})();
