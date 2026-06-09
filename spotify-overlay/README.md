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

## 1. Make a Spotify app (one-time, ~2 min)

The overlay talks to **your** Spotify account, so Spotify needs to know about it.

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and **Create app**.
2. Under **Redirect URIs**, add exactly:

   ```
   http://127.0.0.1:8888/callback
   ```

3. For **Which API/SDKs** tick **Web API**, save.
4. Open the app → **Settings** → copy the **Client ID**.

> No client secret is needed — the app uses the PKCE flow.

## 2. Run it

```bash
cd spotify-overlay
npm install      # downloads Electron
npm start
```

On first launch, paste your **Client ID**, click **Save & connect**, and approve
in the browser tab that opens. That's it — the widget starts tracking.

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
  src/
    main.js              Electron main: window, OAuth, polling, history, stats
    preload.js           contextBridge API exposed to the renderer
    renderer/
      index.html         the four views (now playing / setup / connect / stats)
      styles.css         the glass overlay look
      app.js             UI logic + progress interpolation
```
