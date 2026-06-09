// Spotify Overlay — Electron main process.
// Responsibilities: the always-on-top window, Spotify OAuth (PKCE, no secret),
// token storage/refresh, polling "now playing", logging history, and stats.

const { app, BrowserWindow, ipcMain, shell, globalShortcut, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const crypto = require('crypto');

const REDIRECT_PORT = 8888;
const REDIRECT_URI = `http://127.0.0.1:${REDIRECT_PORT}/callback`;
const SCOPES = [
  'user-read-currently-playing',
  'user-read-playback-state',
  'user-modify-playback-state',
  'user-read-recently-played',
].join(' ');

const POLL_MS = 3000;

// Pre-filled so there's nothing to paste on first run. A Spotify *Client ID* is
// a public identifier (it's in the login URL anyway, safe to ship). The Client
// Secret is NOT public and is never used here — this app uses the PKCE flow.
// Blank this or override it in the UI to use a different Spotify app.
const DEFAULT_CLIENT_ID = 'dbf3623663944f53ac121ec628e024ab';

const CONFIG_PATH = () => path.join(app.getPath('userData'), 'config.json');
const TOKENS_PATH = () => path.join(app.getPath('userData'), 'tokens.json');
const HISTORY_PATH = () => path.join(app.getPath('userData'), 'history.jsonl');

let win = null;
let pollTimer = null;
let authServer = null;
let lastLoggedTrackId = null;
let interactive = true;

// ---------- tiny persistence helpers ----------
function readJSON(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return fallback; }
}
function writeJSON(p, obj) {
  try { fs.writeFileSync(p, JSON.stringify(obj, null, 2)); } catch (e) { console.error('writeJSON', e); }
}
function getConfig() {
  const c = readJSON(CONFIG_PATH(), {});
  if (!c.clientId && DEFAULT_CLIENT_ID) c.clientId = DEFAULT_CLIENT_ID;
  return c;
}
function setConfig(patch) { const c = { ...getConfig(), ...patch }; writeJSON(CONFIG_PATH(), c); return c; }
function getTokens() { return readJSON(TOKENS_PATH(), null); }
function setTokens(t) { writeJSON(TOKENS_PATH(), t); }
function clearTokens() { try { fs.unlinkSync(TOKENS_PATH()); } catch { /* none */ } }

// ---------- PKCE ----------
function b64url(buf) {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function makeVerifier() { return b64url(crypto.randomBytes(64)); }
function challengeFromVerifier(v) { return b64url(crypto.createHash('sha256').update(v).digest()); }

// ---------- token management ----------
async function exchangeCode(code, verifier, clientId) {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: REDIRECT_URI,
    client_id: clientId,
    code_verifier: verifier,
  });
  const res = await fetch('https://accounts.spotify.com/api/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!res.ok) throw new Error('Token exchange failed: ' + res.status + ' ' + (await res.text()));
  const data = await res.json();
  setTokens({
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: Date.now() + (data.expires_in - 60) * 1000,
  });
}

async function refreshTokens() {
  const t = getTokens();
  const { clientId } = getConfig();
  if (!t || !t.refresh_token || !clientId) throw new Error('Not authenticated');
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: t.refresh_token,
    client_id: clientId,
  });
  const res = await fetch('https://accounts.spotify.com/api/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!res.ok) throw new Error('Token refresh failed: ' + res.status);
  const data = await res.json();
  setTokens({
    access_token: data.access_token,
    refresh_token: data.refresh_token || t.refresh_token, // Spotify may omit a new one
    expires_at: Date.now() + (data.expires_in - 60) * 1000,
  });
}

async function getAccessToken() {
  let t = getTokens();
  if (!t) return null;
  if (Date.now() >= t.expires_at) {
    await refreshTokens();
    t = getTokens();
  }
  return t.access_token;
}

// Spotify API call that auto-attaches the token and retries once on 401.
async function spotify(pathname, opts = {}) {
  const token = await getAccessToken();
  if (!token) throw new Error('Not authenticated');
  const call = (tok) => fetch('https://api.spotify.com/v1' + pathname, {
    ...opts,
    headers: { Authorization: 'Bearer ' + tok, ...(opts.headers || {}) },
  });
  let res = await call(token);
  if (res.status === 401) {
    await refreshTokens();
    res = await call((getTokens() || {}).access_token);
  }
  return res;
}

// ---------- now playing + history ----------
async function fetchNowPlaying() {
  const res = await spotify('/me/player/currently-playing');
  if (res.status === 204 || res.status === 202) return { playing: false };
  if (!res.ok) return { playing: false, error: 'Spotify ' + res.status };
  const data = await res.json().catch(() => null);
  if (!data || !data.item) return { playing: false };
  const item = data.item;
  const img = item.album && item.album.images && item.album.images[0];
  return {
    playing: true,
    isPlaying: data.is_playing,
    trackId: item.id,
    name: item.name,
    artists: (item.artists || []).map((a) => a.name).join(', '),
    album: item.album ? item.album.name : '',
    image: img ? img.url : null,
    durationMs: item.duration_ms,
    progressMs: data.progress_ms,
    fetchedAt: Date.now(),
    url: item.external_urls ? item.external_urls.spotify : null,
  };
}

function appendHistory(rec) {
  try { fs.appendFileSync(HISTORY_PATH(), JSON.stringify(rec) + '\n'); } catch (e) { console.error('history', e); }
}

function logPlay(np) {
  if (!np.playing || !np.trackId || np.trackId === lastLoggedTrackId) return;
  lastLoggedTrackId = np.trackId;
  appendHistory({
    t: Date.now(),
    id: np.trackId,
    name: np.name,
    artist: np.artists,
    album: np.album,
    durationMs: np.durationMs,
    image: np.image,
  });
}

async function pollOnce() {
  try {
    const np = await fetchNowPlaying();
    if (np.playing) logPlay(np);
    if (win && !win.isDestroyed()) win.webContents.send('np-update', np);
  } catch (e) {
    if (win && !win.isDestroyed()) win.webContents.send('np-update', { playing: false, error: String(e.message || e) });
  }
}

function startPolling() {
  stopPolling();
  pollOnce();
  pollTimer = setInterval(pollOnce, POLL_MS);
}
function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }

function loadHistory() {
  try {
    return fs.readFileSync(HISTORY_PATH(), 'utf8')
      .split('\n').filter(Boolean)
      .map((l) => { try { return JSON.parse(l); } catch { return null; } })
      .filter(Boolean);
  } catch { return []; }
}

// Pull the last 50 plays from Spotify on connect so stats aren't blank.
async function backfillRecent() {
  try {
    const res = await spotify('/me/player/recently-played?limit=50');
    if (!res.ok) return;
    const data = await res.json();
    // Dedupe at minute granularity against what we already have.
    const seen = new Set(loadHistory().map((r) => r.id + '|' + Math.floor(r.t / 60000)));
    const lines = [];
    for (const it of (data.items || [])) {
      const tr = it.track;
      if (!tr) continue;
      const t = new Date(it.played_at).getTime();
      const key = tr.id + '|' + Math.floor(t / 60000);
      if (seen.has(key)) continue;
      seen.add(key);
      const img = tr.album && tr.album.images && tr.album.images[0];
      lines.push(JSON.stringify({
        t, id: tr.id, name: tr.name,
        artist: (tr.artists || []).map((a) => a.name).join(', '),
        album: tr.album ? tr.album.name : '',
        durationMs: tr.duration_ms,
        image: img ? img.url : null,
      }));
    }
    if (lines.length) fs.appendFileSync(HISTORY_PATH(), lines.join('\n') + '\n');
  } catch (e) { console.error('backfill', e); }
}

function computeStats() {
  const hist = loadHistory();
  const byArtist = new Map();
  const byTrack = new Map();
  const byDay = new Map();
  let totalMs = 0;
  for (const r of hist) {
    totalMs += r.durationMs || 0;
    byArtist.set(r.artist, (byArtist.get(r.artist) || 0) + 1);
    const key = r.id || (r.name + '|' + r.artist);
    if (!byTrack.has(key)) byTrack.set(key, { name: r.name, artist: r.artist, count: 0 });
    byTrack.get(key).count++;
    const day = new Date(r.t).toISOString().slice(0, 10);
    byDay.set(day, (byDay.get(day) || 0) + 1);
  }
  const topArtists = [...byArtist.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count).slice(0, 8);
  const topTracks = [...byTrack.values()].sort((a, b) => b.count - a.count).slice(0, 8);
  const days = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    days.push({ day: key, count: byDay.get(key) || 0 });
  }
  return {
    totalPlays: hist.length,
    uniqueTracks: byTrack.size,
    uniqueArtists: byArtist.size,
    totalMinutes: Math.round(totalMs / 60000),
    topArtists, topTracks, days,
  };
}

// ---------- OAuth (PKCE) via loopback redirect ----------
function startAuth() {
  const { clientId } = getConfig();
  if (!clientId) { send('auth-changed', { state: 'need-client-id' }); return; }

  const verifier = makeVerifier();
  const challenge = challengeFromVerifier(verifier);
  const stateParam = b64url(crypto.randomBytes(16));

  if (authServer) { try { authServer.close(); } catch { /* none */ } authServer = null; }
  authServer = http.createServer(async (req, res) => {
    if (!req.url.startsWith('/callback')) { res.writeHead(404); res.end(); return; }
    const u = new URL(req.url, REDIRECT_URI);
    const code = u.searchParams.get('code');
    const err = u.searchParams.get('error');
    const st = u.searchParams.get('state');
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end('<!doctype html><meta charset="utf-8"><body style="font-family:system-ui;background:#121212;color:#1db954;display:flex;align-items:center;justify-content:center;height:100vh;margin:0"><h2>&#10003; Connected — you can close this tab and return to the overlay.</h2></body>');
    try { authServer.close(); } catch { /* none */ }
    authServer = null;
    if (err || !code || st !== stateParam) {
      send('auth-changed', { state: 'error', message: err || 'Authorization failed' });
      return;
    }
    try {
      await exchangeCode(code, verifier, clientId);
      send('auth-changed', { state: 'connected' });
      await backfillRecent();
      startPolling();
    } catch (e) {
      send('auth-changed', { state: 'error', message: String(e.message || e) });
    }
  });
  authServer.on('error', (e) => {
    send('auth-changed', { state: 'error', message: 'Port ' + REDIRECT_PORT + ' busy (' + e.message + ')' });
  });
  authServer.listen(REDIRECT_PORT, '127.0.0.1', () => {
    const url = 'https://accounts.spotify.com/authorize?' + new URLSearchParams({
      client_id: clientId,
      response_type: 'code',
      redirect_uri: REDIRECT_URI,
      code_challenge_method: 'S256',
      code_challenge: challenge,
      state: stateParam,
      scope: SCOPES,
    }).toString();
    shell.openExternal(url);
  });
}

// ---------- window ----------
function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

function createWindow() {
  win = new BrowserWindow({
    width: 340,
    height: 152,
    minWidth: 300,
    minHeight: 120,
    frame: false,
    transparent: true,
    resizable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    fullscreenable: false,
    maximizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.setAlwaysOnTop(true, 'screen-saver'); // stay above fullscreen apps too
  if (process.platform === 'darwin') {
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  }
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  const { workArea } = screen.getPrimaryDisplay();
  win.setPosition(workArea.x + workArea.width - 360, workArea.y + 24);

  win.webContents.on('did-finish-load', () => { if (getTokens()) startPolling(); });
}

// ---------- IPC ----------
function registerIpc() {
  ipcMain.handle('get-state', async () => {
    const { clientId } = getConfig();
    return { hasClientId: !!clientId, connected: !!getTokens(), redirectUri: REDIRECT_URI };
  });
  ipcMain.handle('set-client-id', async (_e, id) => { setConfig({ clientId: (id || '').trim() }); return true; });
  ipcMain.handle('start-auth', async () => { startAuth(); return true; });
  ipcMain.handle('logout', async () => { clearTokens(); stopPolling(); lastLoggedTrackId = null; return true; });
  ipcMain.handle('get-stats', async () => computeStats());
  ipcMain.handle('open-external', (_e, url) => { if (url) shell.openExternal(url); });
  ipcMain.handle('win-close', () => app.quit());
  ipcMain.handle('win-min', () => { if (win) win.minimize(); });
  ipcMain.handle('set-size', (_e, { w, h }) => {
    if (win && !win.isDestroyed()) win.setSize(Math.round(w), Math.round(h), false);
  });
  ipcMain.handle('control', async (_e, action) => {
    const map = {
      play: ['/me/player/play', 'PUT'],
      pause: ['/me/player/pause', 'PUT'],
      next: ['/me/player/next', 'POST'],
      previous: ['/me/player/previous', 'POST'],
    };
    const m = map[action];
    if (!m) return { ok: false, message: 'unknown action' };
    try {
      const res = await spotify(m[0], { method: m[1] });
      setTimeout(pollOnce, 400); // reflect the change quickly
      if (!res.ok && res.status !== 204) {
        if (res.status === 404) return { ok: false, message: 'No active Spotify device — start playback once in the app.' };
        if (res.status === 403) return { ok: false, message: 'Controls need Spotify Premium.' };
        return { ok: false, message: 'Spotify ' + res.status };
      }
      return { ok: true };
    } catch (e) {
      return { ok: false, message: String(e.message || e) };
    }
  });
}

// ---------- lifecycle ----------
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (win) { win.show(); win.focus(); } });

  app.whenReady().then(() => {
    registerIpc();
    createWindow();

    // Toggle click-through so you can click the app *behind* the overlay.
    globalShortcut.register('CommandOrControl+Shift+Space', () => {
      if (!win) return;
      interactive = !interactive;
      win.setIgnoreMouseEvents(!interactive, { forward: true });
      send('interactive-changed', interactive);
    });
    // Show / hide the overlay.
    globalShortcut.register('CommandOrControl+Shift+S', () => {
      if (!win) return;
      if (win.isVisible()) win.hide(); else win.show();
    });
  });

  app.on('will-quit', () => globalShortcut.unregisterAll());
  app.on('window-all-closed', () => app.quit());
}
