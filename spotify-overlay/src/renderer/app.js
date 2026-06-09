// Renderer: drives the four views (now playing / setup / connect / stats),
// interpolates the progress bar between polls, and wires up controls.

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const SIZES = {
  np: [340, 152],
  setup: [360, 270],
  connect: [340, 180],
  stats: [384, 470],
};

let view = 'np';
let np = null;        // last now-playing payload
let baseline = null;  // { progressMs, fetchedAt, isPlaying, durationMs } for interpolation

function show(v) {
  view = v;
  $$('.view').forEach((el) => el.classList.toggle('active', el.dataset.view === v));
  const size = SIZES[v] || SIZES.np;
  window.api.setSize(size[0], size[1]);
}

function fmt(ms) {
  if (ms == null || ms < 0) ms = 0;
  const s = Math.floor(ms / 1000);
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function flash(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2800);
}

// ---- state routing ----
async function refreshState() {
  const st = await window.api.getState();
  $('#redirect').textContent = st.redirectUri;
  if (!st.hasClientId) return show('setup');
  if (!st.connected) return show('connect');
  show('np');
}

// ---- now playing ----
function renderNP() {
  if (!np || !np.playing) return;
  $('#np-title').textContent = np.name || '';
  $('#np-artist').textContent = np.artists || '';
  $('#np-art').style.backgroundImage = np.image ? `url("${np.image}")` : 'none';
  $('#play-toggle').innerHTML = (baseline && baseline.isPlaying) ? '&#10073;&#10073;' : '&#9654;';
  $('#np-dur').textContent = fmt(np.durationMs);
}

function renderIdle(err) {
  $('#np-title').textContent = err ? 'Spotify unavailable' : 'Nothing playing';
  $('#np-artist').textContent = err ? String(err) : 'Press play in Spotify';
  $('#np-art').style.backgroundImage = 'none';
  $('#np-progress-fill').style.width = '0%';
  $('#np-cur').textContent = '0:00';
  $('#np-dur').textContent = '0:00';
  $('#play-toggle').innerHTML = '&#9654;';
}

// Advance the progress bar locally so it moves smoothly between 3s polls.
setInterval(() => {
  if (!baseline || !np || !np.playing) return;
  let p = baseline.progressMs + (baseline.isPlaying ? Date.now() - baseline.fetchedAt : 0);
  p = Math.min(p, baseline.durationMs || p);
  const pct = baseline.durationMs ? (p / baseline.durationMs) * 100 : 0;
  $('#np-progress-fill').style.width = pct + '%';
  $('#np-cur').textContent = fmt(p);
}, 250);

window.api.onNowPlaying((d) => {
  np = d;
  if (d && d.playing) {
    baseline = {
      progressMs: d.progressMs,
      fetchedAt: d.fetchedAt || Date.now(),
      isPlaying: d.isPlaying,
      durationMs: d.durationMs,
    };
    renderNP();
  } else {
    baseline = null;
    renderIdle(d && d.error);
  }
});

window.api.onAuthChanged((d) => {
  if (d.state === 'connected') refreshState();
  else if (d.state === 'need-client-id') show('setup');
  else if (d.state === 'error') { $('#connect-msg').textContent = d.message || 'Auth error'; show('connect'); }
});

window.api.onInteractiveChanged((on) => {
  document.body.classList.toggle('clickthrough', !on);
});

// ---- stats ----
function bar(label, count, frac) {
  return `<div class="brow"><div class="brow-fill" style="width:${Math.round(frac * 100)}%"></div>`
    + `<span class="brow-label">${escapeHtml(label)}</span>`
    + `<span class="brow-count">${count}</span></div>`;
}

async function loadStats() {
  const s = await window.api.getStats();
  $('#stat-plays').textContent = s.totalPlays;
  $('#stat-tracks').textContent = s.uniqueTracks;
  $('#stat-artists').textContent = s.uniqueArtists;
  $('#stat-mins').textContent = s.totalMinutes;

  const maxD = Math.max(1, ...s.days.map((d) => d.count));
  $('#days').innerHTML = s.days
    .map((d) => `<div class="day" title="${d.day}: ${d.count}"><div class="day-bar" style="height:${Math.round((d.count / maxD) * 100)}%"></div><span>${d.day.slice(8)}</span></div>`)
    .join('');

  const empty = '<div class="muted">No plays logged yet — listen for a bit.</div>';
  const maxA = Math.max(1, ...s.topArtists.map((a) => a.count));
  $('#top-artists').innerHTML = s.topArtists.map((a) => bar(a.name, a.count, a.count / maxA)).join('') || empty;
  const maxT = Math.max(1, ...s.topTracks.map((t) => t.count));
  $('#top-tracks').innerHTML = s.topTracks.map((t) => bar(`${t.name} · ${t.artist}`, t.count, t.count / maxT)).join('') || empty;
}

// ---- wiring ----
$('#play-toggle').onclick = async () => {
  const playing = baseline && baseline.isPlaying;
  const r = await window.api.control(playing ? 'pause' : 'play');
  if (r && r.ok && baseline) { baseline.isPlaying = !playing; baseline.fetchedAt = Date.now(); renderNP(); }
  else if (r && !r.ok) flash(r.message || 'Playback control failed');
};
$('#next').onclick = async () => { const r = await window.api.control('next'); if (r && !r.ok) flash(r.message); };
$('#prev').onclick = async () => { const r = await window.api.control('previous'); if (r && !r.ok) flash(r.message); };
$('#np-art').onclick = () => { if (np && np.url) window.api.openExternal(np.url); };

$('#to-stats').onclick = async () => {
  if (view === 'stats') return show('np');
  await loadStats();
  show('stats');
};
$('#stats-back').onclick = () => show('np');
$('#gear').onclick = () => show('connect');
$('#min').onclick = () => window.api.minimize();
$('#close').onclick = () => window.api.close();

$('#save-id').onclick = async () => {
  const id = $('#client-id').value.trim();
  if (!id) return flash('Paste your Client ID first');
  await window.api.setClientId(id);
  $('#connect-msg').textContent = 'Opening Spotify login in your browser…';
  show('connect');
  await window.api.startAuth();
};
$('#connect-btn').onclick = async () => {
  $('#connect-msg').textContent = 'Opening Spotify login in your browser…';
  await window.api.startAuth();
};
$('#to-setup').onclick = () => show('setup');
$('#logout').onclick = async () => { await window.api.logout(); refreshState(); };
$('#open-dash').onclick = () => window.api.openExternal('https://developer.spotify.com/dashboard');

refreshState();
