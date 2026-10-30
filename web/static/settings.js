// Settings page: change the simple settings, and update the web interface when GitHub is ahead.
(function () {
  const FIELDS = ["DEVICE_NAME", "DEFAULT_VOLUME", "SOLOIST_UPDATE_AFTER_DAYS", "APT_UPGRADE_AFTER_DAYS"];
  const saveButton = document.getElementById("save");
  const saveStatus = document.getElementById("save-status");
  const codeStatus = document.getElementById("code-status");
  const commitList = document.getElementById("code-commits");
  const checkButton = document.getElementById("check");
  const updateButton = document.getElementById("update");
  let loaded = {};

  function showError(target, err) {
    target.textContent = err.message || String(err);
  }

  async function loadSettings() {
    const data = await api("/api/config");
    loaded = data.values;
    FIELDS.forEach(function (key) {
      const input = document.getElementById(key);
      if (input) input.value = loaded[key] || "";
      const hint = document.querySelector('[data-hint="' + key + '"]');
      if (hint && data.editable[key]) hint.textContent = data.editable[key];
    });
  }

  async function save() {
    const body = {};
    FIELDS.forEach(function (key) {
      const input = document.getElementById(key);
      if (input && input.value !== String(loaded[key] || "")) body[key] = input.value;
    });
    if (!Object.keys(body).length) {
      saveStatus.textContent = "Nothing changed.";
      return;
    }
    saveButton.disabled = true;
    try {
      const result = await api("/api/config", { body: body });
      if (result.restart && result.restart.length) {
        await api("/api/config/apply", { body: { services: result.restart } });
      }
      await loadSettings();
      saveStatus.textContent = "Saved.";
    } catch (err) {
      showError(saveStatus, err);
    } finally {
      saveButton.disabled = false;
    }
  }

  async function checkCode() {
    checkButton.disabled = true;
    updateButton.disabled = true;
    codeStatus.textContent = "Checking GitHub...";
    commitList.replaceChildren();
    try {
      const info = await api("/api/code/update");
      if (info.update_available) {
        codeStatus.textContent = "Update available on " + info.branch + ": " + info.current + " to " + info.latest + ".";
        info.commits.forEach(function (subject) {
          const item = document.createElement("li");
          item.textContent = subject;
          commitList.append(item);
        });
        updateButton.disabled = false;
      } else {
        codeStatus.textContent = "Up to date (" + info.branch + ", " + info.current + ").";
      }
    } catch (err) {
      showError(codeStatus, err);
    } finally {
      checkButton.disabled = false;
    }
  }

  async function updateCode() {
    if (!window.confirm("Update the web interface from GitHub now? The page reloads in a few seconds.")) return;
    updateButton.disabled = true;
    checkButton.disabled = true;
    codeStatus.textContent = "Updating...";
    try {
      await api("/api/code/update", { body: { confirm: true } });
      codeStatus.textContent = "Updated. Restarting the web service...";
      setTimeout(function () { window.location.reload(); }, 6000);
    } catch (err) {
      showError(codeStatus, err);
      checkButton.disabled = false;
    }
  }

  saveButton.addEventListener("click", function () { save().catch(function (err) { showError(saveStatus, err); }); });
  checkButton.addEventListener("click", checkCode);
  updateButton.addEventListener("click", updateCode);

  loadSettings().catch(function (err) { showError(saveStatus, err); });
  checkCode();
})();
