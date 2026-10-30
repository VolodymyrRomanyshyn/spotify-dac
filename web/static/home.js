// Home page. The source switch changes only when the user clicks it; the page never switches by itself.
(function () {
  const FAST_MS = 2000;     // now playing and volume
  const SLOW_MS = 30000;    // DAC status line (it runs several commands on the Pi)
  const $ = (id) => document.getElementById(id);
  const srcSpotify = $("src-spotify"), srcRadio = $("src-radio");
  const title = $("title"), subtitle = $("subtitle"), cover = $("cover"), controls = $("controls");
  const progress = $("progress"), elapsedText = $("elapsed"), remainingText = $("remaining");
  const progressCard = $("progress-card");
  const volume = $("volume"), volumeValue = $("volume-value");
  const banner = $("banner"), statusLine = $("status-line");
  const stationsCard = $("stations-card"), stationsBox = $("stations");

  let source = null;            // "spotify" or "radio", set by the user or on first load
  let stations = [];
  let lastStation = null;       // last station played from this page
  let spotify = null;           // last Spotify answer
  let spotifyPosition = null;   // ms, advanced locally between answers
  let spotifyAt = 0;            // when spotifyPosition was taken
  let volumeTimer = null, volumeDirty = false, seeking = false;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function showError(message) { banner.textContent = message; banner.hidden = false; }
  function clearError() { banner.hidden = true; }
  function fail(err) { showError(err.message); }
  function formatTime(ms) {
    if (ms === null || ms === undefined) return "-";
    const total = Math.floor(ms / 1000), m = Math.floor(total / 60), s = total % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  // icons as SVG paths (constant strings only)
  const ICONS = {
    prev: '<path d="M6 6h2v12H6zM20 6v12l-9-6z"/>',
    next: '<path d="M16 6h2v12h-2zM4 18V6l9 6z"/>',
    play: '<path d="M8 5v14l11-7z"/>',
    pause: '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>',
    stop: '<path d="M6 6h12v12H6z"/>'
  };
  function iconButton(name, label, onClick, extra) {
    const b = el("button", "ctl icon" + (extra ? " " + extra : ""));
    b.type = "button";
    b.setAttribute("aria-label", label);
    b.title = label;
    b.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" fill="currentColor">' + ICONS[name] + '</svg>';
    b.addEventListener("click", function () { onClick().catch(fail); });
    return b;
  }
  function button(label, onClick, extra) {
    const b = el("button", "ctl" + (extra ? " " + extra : ""), label);
    b.type = "button";
    b.addEventListener("click", function () { onClick().catch(fail); });
    return b;
  }

  // ---- source switch: the user decides; nothing else changes it ----
  function setSource(choice) {
    source = choice;
    srcSpotify.classList.toggle("selected", choice === "spotify");
    srcRadio.classList.toggle("selected", choice === "radio");
    srcSpotify.setAttribute("aria-pressed", String(choice === "spotify"));
    srcRadio.setAttribute("aria-pressed", String(choice === "radio"));
    stationsCard.hidden = choice !== "radio";
    progressCard.hidden = choice !== "spotify";
  }
  srcSpotify.addEventListener("click", function () {
    // only changes what the page shows; playback changes only when the user presses a control
    setSource("spotify");
    refreshFast();
  });
  srcRadio.addEventListener("click", function () {
    // only shows the station list; a station starts when the user presses its Play button
    setSource("radio");
    refreshFast();
  });
  async function playStation(id) {
    await api("/api/radio/play", { body: { id: id } });   // this also pauses Spotify
    lastStation = id;
    refreshFast();
  }

  // ---- stations ----
  // the whole row is the button: tap a station to play it
  function stationThumb(s) {
    const thumb = el("span", "thumb");
    if (s.logo) thumb.style.backgroundImage = 'url("' + s.logo + '")';
    else thumb.textContent = initials(s.name);
    return thumb;
  }
  function drawStations(playingId) {
    stationsBox.replaceChildren(...stations.map(function (s) {
      const playing = playingId === s.id;
      const row = el("button", "station" + (playing ? " playing" : ""));
      row.type = "button";
      row.setAttribute("aria-pressed", String(playing));
      const badge = el("span", "badge", "Playing");
      badge.classList.toggle("off", !playing);  // always present, so the row does not move
      const info = el("div", "info");
      info.append(el("span", "name", s.name), el("span", "muted small genre", s.genre || ""));
      row.append(stationThumb(s), info, badge);
      row.addEventListener("click", function () { playStation(s.id).catch(fail); });
      return row;
    }));
  }

  // ---- Spotify ----
  function drawSpotify(now) {
    const playing = now.status === "playing";
    title.textContent = now.name || "Nothing playing";
    subtitle.textContent = [now.artists && now.artists.length ? now.artists.join(", ") : null,
                            now.status ? "Spotify " + now.status : null].filter(Boolean).join(" - ");
    cover.style.backgroundImage = now.cover ? 'url("' + now.cover + '")' : "";
    cover.classList.toggle("empty", !now.cover);
    cover.classList.remove("initials", "radio-icon");
    cover.textContent = "";
    controls.replaceChildren(
      iconButton("prev", "Previous", function () { return api("/api/spotify/control", { body: { action: "prev" } }); }),
      iconButton(playing ? "pause" : "play", playing ? "Pause" : "Play", function () {
        // show the new state at once; the next poll confirms it
        spotify = Object.assign({}, spotify, { status: playing ? "paused" : "playing" });
        drawSpotify(spotify);
        return api("/api/spotify/control", { body: { action: playing ? "pause" : "play" } });
      }, "main"),
      iconButton("next", "Next", function () { return api("/api/spotify/control", { body: { action: "next" } }); })
    );
    if (!seeking) {
      const duration = now.duration_ms, position = currentPosition(now);
      progress.disabled = !duration;
      if (duration) {
        progress.value = Math.round(1000 * Math.min(position, duration) / duration);
        showTimes(position, duration);
      } else {
        showTimes(null, null);
      }
    }
    if (typeof now.volume === "number" && !volumeDirty) drawVolume(now.volume);
  }
  function currentPosition(now) {
    if (now.position_ms === null || now.position_ms === undefined) return 0;
    if (now.status !== "playing") return now.position_ms;
    return now.position_ms + (Date.now() - spotifyAt);  // move the bar between answers
  }
  function showTimes(position, duration) {
    if (!duration) { elapsedText.textContent = "-"; remainingText.textContent = "-"; return; }
    elapsedText.textContent = formatTime(position);
    remainingText.textContent = "-" + formatTime(Math.max(0, duration - position));
  }
  progress.addEventListener("pointerdown", function () { seeking = true; });
  progress.addEventListener("input", function () {
    seeking = true;
    const duration = spotify && spotify.duration_ms;
    if (duration) showTimes(duration * progress.value / 1000, duration);
  });
  progress.addEventListener("change", function () {
    const duration = spotify && spotify.duration_ms;
    seeking = false;
    if (!duration) return;
    const target = Math.round(duration * progress.value / 1000);
    api("/api/spotify/control", { body: { action: "seek", position_ms: target } })
      .then(function () { spotifyAt = Date.now(); spotify.position_ms = target; refreshFast(); })
      .catch(fail);
  });

  // ---- radio ----
  // a title that is only a file or mount name (playlist.m3u8, radiokrakow) is not a song
  function radioSubtitle(title, station) {
    if (!title) return "Live";
    if (/\.(m3u8?|mp3|aac|ogg|opus|pls)$/i.test(title)) return "Live";
    if (station && station.url) {
      const last = (station.url.split("?")[0].split("/").filter(Boolean).pop() || "").replace(/;?\.mp3$/i, "");
      if (last && title.toLowerCase() === last.toLowerCase()) return "Live";
    }
    return title;
  }
  function initials(name) {
    const words = (name || "Radio").split(/\s+/).filter(Boolean);
    return words.slice(0, 2).map(function (w) { return w.charAt(0).toUpperCase(); }).join("");
  }
  function drawRadio(radio, station) {
    title.textContent = station ? station.name : "Internet radio";
    subtitle.textContent = radio.playing ? radioSubtitle(radio.title, station) : "Not playing";
    if (station && station.logo) {
      cover.style.backgroundImage = 'url("' + station.logo + '")';
      cover.classList.remove("empty", "initials");
      cover.textContent = "";
    } else if (station) {
      cover.style.backgroundImage = "";
      cover.classList.add("initials");
      cover.classList.remove("empty");
      cover.textContent = initials(station.name);
    } else {
      // no station chosen yet: a radio icon instead of a letter
      cover.style.backgroundImage = "";
      cover.classList.remove("initials", "empty");
      cover.innerHTML = '<svg viewBox="0 0 24 24" width="72" height="72" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><rect x="3" y="8" width="18" height="12" rx="2"/><path d="M7 8l10-4"/><circle cx="16" cy="14" r="2.5"/><path d="M6 12h4"/></svg>';
      cover.classList.add("radio-icon");
    }
    controls.replaceChildren(
      radio.playing
        ? iconButton("stop", "Stop", function () { return api("/api/radio/stop", { method: "POST" }).then(refreshFast); }, "main")
        : el("p", "muted", "Choose a station below.")
    );
    progressCard.hidden = true;
  }

  // ---- volume: one level for both sources ----
  function drawVolume(percent) {
    volume.value = percent;
    volumeValue.textContent = percent + "%";
  }
  volume.addEventListener("pointerdown", function () { volumeDirty = true; });
  volume.addEventListener("input", function () {
    volumeDirty = true;
    volumeValue.textContent = volume.value + "%";
    clearTimeout(volumeTimer);
    volumeTimer = setTimeout(function () {
      api("/api/volume", { body: { percent: Number(volume.value) } })
        .then(function () { volumeDirty = false; })
        .catch(function (err) { volumeDirty = false; fail(err); });
    }, 300);
  });

  // ---- DAC status line (slow) ----
  async function refreshStatus() {
    try {
      const status = await api("/api/status");
      const running = status.dac.streams.filter(function (x) { return x.state === "RUNNING"; });
      const card = status.dac.cards.find(function (c) { return !/bcm2835|Headphones/i.test(c.driver + " " + c.name); });
      const playing = running.length ? "RUNNING" + (running[0].rate ? " " + running[0].rate + " Hz" : "") : "idle";
      statusLine.replaceChildren(
        document.createTextNode("DAC " + (card ? card.name : "not found") + ": " + playing + " - "),
        el("a", "", "Status")
      );
      statusLine.lastChild.setAttribute("href", "/status.html");
      if (status.overall !== "ok") showError("Check the Status page: " + (status.problems.concat(status.warnings).join(", ") || status.overall));
    } catch (err) { /* the status line is optional */ }
  }

  // ---- fast refresh: what plays, and the volume ----
  async function refreshFast() {
    try {
      const [radio, now, volumeNow] = await Promise.all([
        api("/api/radio/now"),
        api("/api/spotify/now").catch(function () { return null; }),
        api("/api/volume"),
      ]);
      spotify = now;
      if (now) { spotifyPosition = now.position_ms; spotifyAt = Date.now(); }
      if (source === null) setSource(radio.playing ? "radio" : "spotify");  // first load only
      if (source === "radio") {
        drawRadio(radio, stations.find(function (x) { return x.id === (radio.playing || lastStation); }) || null);
      } else if (now) {
        drawSpotify(now);
      } else {
        title.textContent = "Spotify not reachable";
        subtitle.textContent = "";
        controls.replaceChildren();
      }
      drawStations(radio.playing);
      if (!volumeDirty) drawVolume(volumeNow.percent);
      clearError();
    } catch (err) {
      showError("Cannot reach the Pi (" + err.message + ").");
    }
  }

  // stations load once and again after a change
  async function loadStations() {
    try {
      const data = await api("/api/radio/stations");
      stations = data.stations || [];
    } catch (err) { /* shown on the next refresh */ }
  }

  themeInit();
  loadStations().then(refreshFast);
  refreshStatus();
  setInterval(refreshFast, FAST_MS);
  setInterval(refreshStatus, SLOW_MS);

  function themeInit() { /* the theme is set up in common.js */ }
})();
