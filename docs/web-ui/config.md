# Config page

Every setting, in sections. Each section saves on its own. Hardware (pins, the case, the sound card)
is changed through the **Case** and **Plugins** sections, which are validated before saving.

## Layout

Phone (one section open at a time):

```
+------------------------------------+
| RPI-PI-DAC+            [Dark] [⚙]  |
+------------------------------------+
|  ▾ Spotify                         |
|    Enabled            [ on ]       |
|    Device name        [RPI-PI-DAC+] |
|    API key            set  [Replace] |
|    Soloist restart    [Apply now]  |
|                                    |
|  ▸ Internet radio                  |
|  ▸ Plugins                         |
|  ▸ Case                            |
|  ▸ Sound card (read only)          |
|  ▸ Updates                         |
|  ▸ Web interface                   |
+------------------------------------+
| Home   Spotify   Radio   Config    |
+------------------------------------+
```

Desktop: section list on the left, the open section on the right.

## Sections

### Spotify
- Enabled: on or off. When off, Spotify is hidden from Home and Soloist is stopped.
- Device name (`DEVICE_NAME`).
- API key: shows `set` or `not set`. Write-only; typing a new key replaces it.
- **Update after (days)** (`SOLOIST_UPDATE_AFTER_DAYS`, 1–89): automatic Soloist updates happen only when
  the installed build is at least this old. Builds expire after 90 days.
- **Soloist version:** shows the installed version and a **Check for update** button. The check compares
  the latest archive on Spotify's server with the installed one. If a newer build exists, **Update now**
  appears (asks to confirm, then installs and restarts Soloist).

### Internet radio
- Enabled: on or off. When off, the radio is hidden from Home.
- Station list: a link to the **Radio** page, where stations are added and changed.

### Plugins
- A list of installed plugins, each with enable/disable, edit and delete.
- **Add plugin** picks a type and opens its JSON form.
- Each plugin's settings are shown as a form, with a **Show JSON** view.
- See [plugins.md](plugins.md) for the format and the rules.

### Case
- A selector with one choice: `none`, `nespi` (RetroFlag NESPi Case+), and other cases as they are added.
- Choosing a case shows its JSON settings (power switch, reset, LED, power enable, safe shutdown,
  update trigger, poweroff mode).
- Changing the case or its pins needs the installer. The section shows the command and does not
  change hardware itself.

### Sound card (read only)
- Shows the DAC type and overlay. Changed with the installer.

### Updates
- Update trigger (`poweroff`, `boot`, `none`), Soloist update days, APT upgrade and its days.
- Changes are applied at the next update run.

### Web interface
- Port, and the web password (change; needs the current password).

## Save flow

1. Each section has its own **Save** button. Only that section's fields are sent.
2. The backend checks every value. Errors are shown under the fields; nothing is saved.
3. Saved values that need a restart show **Apply now**, which restarts only the affected service.
4. A plugin's enable/disable takes effect on save.

## Field rules

- **Device name:** 1–32 characters, letters, digits, spaces, `-`, `_`, `+`.
- **Soloist update days:** 1–89. **APT days:** 0–365.
- **Fan:** `offTemp` < `onTemp`, at least 5 °C apart. Pins 0–27, not used by another plugin or the HAT.
- **Pins:** whole numbers 0–27; no duplicates across plugins and the case.

## States

| State | What the user sees |
|---|---|
| Loading | Skeleton fields |
| Unsaved changes | Section's Save enabled; leaving the section asks to discard |
| Validation error | Red text under the field; nothing saved |
| Saved, restart needed | Green "Saved" with **Apply now** |
| Plugin cannot start | Red note with the service's error line |
