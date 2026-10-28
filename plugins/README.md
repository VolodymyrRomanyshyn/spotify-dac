# Plugins

Add-ons for the Pi: a case (exactly one, chosen from a selector) and any number of other plugins
(for example the fan).

Each plugin is a folder with a `plugin.json` manifest, its scripts in `bin/` and its systemd units in
`systemd/`. The manifest lists the settings, their limits and the rules. See
[../docs/web-ui/plugins.md](../docs/web-ui/plugins.md) for the settings model and
[../docs/structure.md](../docs/structure.md) for the layout.

Folders:
- `cases/` — case plugins (`none`, `nespi`, …). Exactly one is enabled.
- `fans/` — fan plugins. Any number, each enabled or disabled.
