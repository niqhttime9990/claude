# Flow Universe

An interactive, dependency-free particle field that lives in your browser.

Thousands of particles ride an animated **value-noise flow field**, leaving
glowing additive trails. The whole thing is a single `index.html` — no build
step, no libraries, no network. Just open it.

![hint](https://img.shields.io/badge/deps-zero-8be9c0) ![hint](https://img.shields.io/badge/files-1-7aa2ff)

## See it (no coding needed)

**Easiest — instant, zero setup.** Click this link:

👉 https://htmlpreview.github.io/?https://github.com/niqhttime9990/claude/blob/main/index.html

**Best quality — your own live website (about 4 clicks).** Turn on free GitHub Pages:

1. Go to the repo's **Settings** tab → **Pages** (left sidebar).
2. Under *Branch*, pick **main** and **/ (root)**, then **Save**.
3. Wait ~1 minute, refresh. GitHub shows a link like
   `https://niqhttime9990.github.io/claude/` — that's your live page, shareable with anyone.

**On your own computer.** Download `index.html` and double-click it — it opens in your browser. That's it.

## Controls

| Input | Action |
|-------|--------|
| **Move mouse** | Warp the flow field; the cursor's motion adds swirl |
| **Click / tap** | Drop a spinning vortex that pulls particles into orbit |
| **Space** | Flip the cursor between attract and repel |
| **R** | Reset particles and clear vortices |
| **P** | Cycle colour palette (aurora · ember · nebula · ocean · magma · spring) |
| **S** | Save the current frame as a PNG |
| **H** | Hide / show the control panel |
| **F** | Fullscreen |

The side panel tunes particle count, flow speed, turbulence, trail length, and
hue drift live.

## How it works

- A custom **value-noise** generator (xorshift-seeded permutation table) is
  sampled at three octaves and advanced over time to make a field that curls
  and breathes.
- Each particle reads the field angle at its position, blends in forces from the
  mouse and any active vortices, and integrates with velocity damping.
- Rendering uses `globalCompositeOperation = 'lighter'` for additive glow, with a
  low-alpha fill each frame producing motion trails. Colour comes from each
  particle's local speed mapped onto the active palette.

All in ~300 lines of vanilla JS and Canvas 2D.
