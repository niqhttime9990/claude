# Spotify Overlay — web version (no install)

Open a link in your browser, click Connect, done. The Spotify **Client ID is
already baked in**. Works in any modern browser; the **⧉ Pop out** always-on-top
mini-player needs **Chrome or Edge**.

## Turn it on (one time)

1. **Enable GitHub Pages** for this repo:
   - GitHub → your repo → **Settings → Pages**.
   - Under **Build and deployment → Source**, pick **Deploy from a branch**.
   - **Branch:** select the branch that has this file (`main` once the PR is
     merged, or `claude/gracious-ramanujan-59ckix` to try it now) and folder
     **`/ (root)`**. Click **Save**.
   - Wait ~1 minute for it to publish.

2. Open the page (this is your permanent link — bookmark it):

   ```
   https://niqhttime9990.github.io/claude/spotify-overlay/web/
   ```

3. The page shows a **Redirect URI** at the top. Copy it, then in the
   [Spotify Dashboard](https://developer.spotify.com/dashboard) → your app →
   **Settings → Edit → Redirect URIs**, paste it and **Save**. (It will be
   exactly `https://niqhttime9990.github.io/claude/spotify-overlay/web/`.)

4. Back on the page, click **Connect Spotify** and approve. It starts tracking.

## Using it

- **⧉** — pop out into a small always-on-top window that floats over other apps
  (Chrome/Edge only).
- **▣▣▣** — listening stats (top artists/tracks, last 14 days). Stored in this
  browser.
- **⚙** — disconnect.
- Click the **album art** to open the track in Spotify.

## Notes

- Now-playing and stats work on free Spotify. Play/pause/skip need **Premium**
  and an active device.
- Everything runs in your browser; tokens and history live in this browser's
  local storage and nothing is sent anywhere except Spotify's own API.
