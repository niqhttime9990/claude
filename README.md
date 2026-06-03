# Nocturne 🌙

An original, procedural **engraved moonlit night** — a live wallpaper for the
dark, melancholic, Doré / Dark-Souls aesthetic. A vast starfield, a glowing
moon, a distant gothic spire and a lone hooded figure on misty, moonlit ground,
all rendered as a hand-stippled engraving. Drifting stars, the odd shooting
star, slow fog. Your cursor is a **lantern** that reveals the etching around it.

Not a copy of anything — it's a single hand-written WebGL shader.

## 👉 The wallpaper is **`index.html`**

| File | What it's for |
|------|---------------|
| **`index.html`** | **The wallpaper. This is the one.** |
| `LivelyProperties.json` | Settings panel in Lively |
| `project.json` | Settings panel in Wallpaper Engine |
| `preview.jpg` | Thumbnail / preview |

![preview](preview.jpg)

## Try it instantly

Open `index.html` in any browser (needs WebGL, on by default), or view it live:
https://htmlpreview.github.io/?https://github.com/niqhttime9990/claude/blob/main/index.html

Move your mouse — the lantern reveals the world, and the scene drifts with
parallax.

## Set it as your Windows wallpaper (Lively — free)

1. **Download** this repo: green **Code** button → **Download ZIP**, then unzip.
2. **Install Lively Wallpaper** (free): https://www.rocksdanister.github.io/lively/
3. In Lively: **＋ Add Wallpaper → Browse → pick `index.html` → click it to apply.**
4. Click the **⚙ / wrench** on the thumbnail for settings.

## Settings

| Setting | What it does |
|---|---|
| **Tone** | Moonlit · Sepia engraving · Ink (B&W) · Night blue |
| **Brightness** | Overall exposure |
| **Stipple density** | How dense the engraved dots are |
| **Film grain** | Subtle paper-grain texture |
| **Mouse parallax** | Scene shifts with the cursor for depth |
| **Cursor lantern** | A light that reveals the etching as you move |
| **React to music** | The moon breathes with system audio |

Single WebGL fragment shader, zero dependencies. Frame-rate capped and pauses
when the desktop is hidden. MIT.
