# Petrichor — Rain on Glass 🌧️

A beautiful night seen through a wet, fogged-up window. Animated raindrops bead
and refract the lights behind the glass, trails slide down, the pane is softly
frosted — and **your cursor wipes the fog clear**, like a hand on a misted
window. Calm, moody, cinematic.

Built for a dark, atmospheric, rainy-night aesthetic. It ships with dreamy
**bokeh city-light** scenes so it looks great instantly, and you can point it at
your own image.

## 👉 The wallpaper is **`index.html`**

| File | What it's for |
|------|---------------|
| **`index.html`** | **The wallpaper. This is the one.** |
| `LivelyProperties.json` | Settings panel in Lively |
| `project.json` | Settings panel in Wallpaper Engine |
| `preview.jpg` | Thumbnail / preview |

![preview](preview.jpg)

## Try it instantly

Open `index.html` in any browser (needs WebGL2, on by default), or view it live:
https://htmlpreview.github.io/?https://github.com/niqhttime9990/claude/blob/main/index.html

Move your mouse to wipe the fog.

## Set it as your Windows wallpaper (Lively — free)

1. **Download** this repo: green **Code** button → **Download ZIP**, then unzip.
2. **Install Lively Wallpaper** (free): https://www.rocksdanister.github.io/lively/
3. In Lively: **＋ Add Wallpaper → Browse → pick `index.html` → click it to apply.**
4. Click the **⚙ / wrench** on the thumbnail for settings.

## Using your own image

The built-in scenes (City lights, Blue hour, Amber, Neon, Forest) need no
internet. To use your own picture, paste a **direct image URL** into the
**"Your image URL"** box in settings — that's the most reliable way, because
desktop wallpaper hosts block loading local files into the graphics layer for
security. (Tip: any dark, moody night photo with lights looks incredible behind
the rain.)

## Settings

| Setting | What it does |
|---|---|
| **Scene** | Built-in bokeh palettes: City lights · Blue hour · Amber · Neon · Forest |
| **Your image URL** | Use any web image instead of a built-in scene |
| **Rain amount** | How much rain runs down the glass |
| **Fogged glass** | How frosted/misted the window is |
| **Background zoom** | Push the lights in/out of focus |
| **Brightness / Vignette / Film grain** | Mood and grade |
| **Tone** | Natural · Warm · Mono · Cool |
| **Mouse parallax** | Scene drifts with the cursor |
| **Cursor wipes the fog** | Clear the mist where your cursor moves |

Single WebGL2 shader, zero dependencies. Rain-on-glass technique after
BigWIngs' "Heartfelt" (Shadertoy). Frame-rate capped, pauses when hidden. MIT.
