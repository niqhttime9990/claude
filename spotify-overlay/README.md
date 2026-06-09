# Spotify Overlay 🎵

A tiny **always-on-top** widget that floats over whatever app you're using. It
shows the song playing on Spotify (album art, artist, scrubbing progress bar,
play/pause/skip) **and** quietly logs your listening history so you get your own
top-artists / top-tracks / minutes-listened stats — a personal stats.fm.

Built with Electron, zero runtime dependencies, client-side OAuth (PKCE — no
server, no client secret).

| | |
|---|---|
| Floats over every app | always-on-top, frameless, draggable, stays above fullscreen |
| Live now playing | art, title, artist, smooth progress bar, transport controls |
| History & stats | logs every track, builds charts over the last 14 days |
| Click-through | a hotkey makes it ignore the mouse so you click the app behind it |

---

## Two ways to run it

- **No-install (easiest):** the web version in [`web/index.html`](web/index.html).
  Host it on GitHub Pages and just open the link in Chrome/Edge — no Node, no
  install. Click **⧉ Pop out** for an always-on-top mini-player. See
  [`web/README.md`](web/README.md).
- **Desktop app (true overlay):** the Electron version below — a frameless,
  always-on-top window with a click-through hotkey. Needs Node.js.

---

## 1. One-time Spotify setup (~1 min)

The Client ID is already baked in, so there's nothing to paste. You only need to
whitelist the redirect URI on the Spotify app it belongs to:

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) → your app → **Settings → Edit**.
2. Under **Redirect URIs**, add exactly this and save:

   ```
   http://127.0.0.1:8888/callback
   ```

> A Spotify **Client ID** is public (it rides in the login URL), so shipping it
> is fine. The **Client Secret** is never used — this app uses the PKCE flow. To
> point it at a different app, click *Change Client ID* in the overlay.

## 2. Run it

- **Windows:** double-click **`start.bat`**.
- **macOS / Linux:** run **`./start.sh`** (or `npm install && npm start`).

The launcher installs dependencies the first time, then opens the overlay. Click
**Connect Spotify**, approve in the browser tab, and it starts tracking.

> Requires [Node.js](https://nodejs.org) (LTS) installed once. The launcher tells
> you if it's missing.

## 3. Use it

- **Drag** it anywhere by the top bar.
- **▣▣▣** opens stats · **⚙** account / disconnect · **–** hide · **✕** quit.
- Click the **album art** to open the track in Spotify.

### Hotkeys (global)

| Shortcut | Action |
|---|---|
| `Ctrl/Cmd + Shift + Space` | Toggle **click-through** — overlay ignores the mouse so you can click the app underneath. Press again to interact with it. |
| `Ctrl/Cmd + Shift + S` | Show / hide the overlay |

## Notes

- **Now Playing + history** work on free Spotify. **Transport controls**
  (play/pause/skip) require **Spotify Premium** and an active device — start
  playback once in the Spotify app, then control it from the overlay.
- History is stored locally as `history.jsonl` in Electron's per-user data
  folder; on connect it also backfills your last 50 plays from Spotify so stats
  aren't empty.
- Nothing leaves your machine except the calls to Spotify's own API.

## Project layout

```
spotify-overlay/
  start.bat / start.sh   double-click launchers (install deps + run)
  src/
    main.js              Electron main: window, OAuth, polling, history, stats
    preload.js           contextBridge API exposed to the renderer
    renderer/
      index.html         the four views (now playing / setup / connect / stats)
      styles.css         the glass overlay look
      app.js             UI logic + progress interpolation
```
