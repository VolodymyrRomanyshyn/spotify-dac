---
name: feature-branch-workflow
description: How to develop changes for the Spotify DAC project on a feature branch, test them on the rpi-2 test Pi, and merge them to main once they work. Use when starting a new feature or fix, deploying a branch to rpi-2, or merging finished work to main.
---

# Feature branch workflow

`main` is what the installer and the other Pi (rpi-1) use. Nothing is developed directly on
`main`. Each change lives on its own branch until it works on rpi-2, and only then goes to `main`.

## 1. Start a branch from main

```bash
git switch main && git pull --ff-only origin main
git switch -c feature/<short-name>
```

Name the branch after the change: `feature/radio-page-fixes`, `fix/status-date`.

## 2. Develop and commit on the branch

- Make the change, check the syntax (`bash -n` for shell, `python3 -m py_compile` for Python,
  a brace and parenthesis count for JavaScript), then commit.
- Commit messages end with the line `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.
- Push the branch to GitHub when it is worth keeping: `git push -u origin feature/<short-name>`.
- Never push to `main` while a change is still in progress.

## 3. Test on rpi-2 from the branch

The test Pi is rpi-2 (`ssh rpi-2`). Its web files live in `/opt/spotify-dac/web` and
`/opt/spotify-dac/radio`, and the Pi keeps a clone in `~/spotify-dac`.

1. Put the clone on the branch:
   ```bash
   ssh rpi-2 'cd ~/spotify-dac && git fetch -q origin && git checkout -q feature/<short-name> && git merge -q --ff-only origin/feature/<short-name>'
   ```
2. Copy the web and radio files and restart the web service. Copying into `/opt` needs sudo,
   so run it in a terminal tab where the user types the password (`ssh -t rpi-2 '...'`):
   ```bash
   sudo cp -r web/. /opt/spotify-dac/web/
   sudo cp -r radio/. /opt/spotify-dac/radio/     # only if the radio files changed
   sudo systemctl restart spotify-dac-web
   ```
3. Check the result: `curl -sk https://127.0.0.1:8443/api/status` over ssh, and the page in a
   browser. Installer changes (`install.sh`, `bin/`, `files/`) need a full run on the Pi
   (`sudo bash install.sh` from the clone), not a copy.
4. Fix anything found on the branch, commit, and repeat from step 2.

Before the test, back up anything the change will overwrite on the Pi (for example the station
file: `sudo cp /etc/spotify-dac/radio.json /etc/spotify-dac/radio.json.bak-<name>`).

## 4. Merge to main when it works

Merge only after the user has confirmed the change works on rpi-2.

```bash
git switch main && git pull --ff-only origin main
git merge --no-ff feature/<short-name> -m "<what it does>

Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"
git push origin main
git push origin --delete feature/<short-name>
git branch -d feature/<short-name>
```

Then put the Pi clone back on `main`, so future updates from GitHub follow `main`:

```bash
ssh rpi-2 'cd ~/spotify-dac && git fetch -q origin && git checkout -q main && git merge -q --ff-only origin/main'
```

rpi-1 follows `main` through its Settings page (Update from GitHub) or the bootstrap script.

## Rules

- No pushes to `main` until the user says the change is done.
- Sudo passwords are typed by the user in a terminal tab. Never store them, and never use
  `sudo -n` for copies into `/opt` or `/etc`.
- `settings.md` is private notes and stays out of git (it is in `.gitignore`).
- Leave rpi-1 alone unless the user asks for it; it runs whatever `main` it was updated to.
