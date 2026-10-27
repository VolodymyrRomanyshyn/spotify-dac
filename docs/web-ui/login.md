# Login page

Shown only when `WEB_USE_PASSWORD=yes`. Any other page redirects here when there is no session.

## Layout

```
+------------------------------------+
|           RPI-PI-DAC+              |   device name from config
|                                    |
|   Password  [______________]       |
|                                    |
|            [ Sign in ]             |
|                                    |
|   Wrong password, try again.       |   shown only after a failed try
+------------------------------------+
```

- Centred card, max 360 px wide on a phone, full width minus margins.
- One password field with a show/hide toggle. The field is focused on load.
- Enter submits the form.

## States

| State | What the user sees |
|---|---|
| Idle | Empty password field, Sign in enabled |
| Submitting | Button shows "Signing in..." and is disabled |
| Wrong password | Red message under the button; field is cleared |
| Too many tries | "Wait 1 minute" message; button disabled (set by the backend) |
| Session expired | Same page, with "Your session ended. Sign in again." |

## Data

- Submits `{password}` to `POST /api/login`. The password is never put in the URL.
- On success the server sets the session cookie and the page goes to Home.
- The device name comes from `GET /api/status`, if the session is valid; otherwise the page shows
  the hostname.

## Dark mode

Same as the other pages: follows the system setting, with the toggle in the top corner.
