# Liquid Light 🌊

A real-time **GPU fluid simulation** live wallpaper. Move your mouse to push
glowing, swirling ink — real fluid physics (incompressible Navier–Stokes with
vorticity) rendered with HDR bloom. It stirs itself when idle, drifts through
colour, and can react to music.

## 👉 The wallpaper is **`index.html`**

That is the only file you open or import. Everything else is just a helper:

| File | What it's for |
|------|---------------|
| **`index.html`** | **The wallpaper. This is the one.** |
| `LivelyProperties.json` | Adds the settings panel in Lively |
| `project.json` | Adds the settings panel in Wallpaper Engine |
| `preview.jpg` | The thumbnail / a preview of how it looks |

![preview](preview.jpg)

## Try it instantly

Open `index.html` in any browser (needs WebGL, which is on by default), or view
it live: https://htmlpreview.github.io/?https://github.com/niqhttime9990/claude/blob/main/index.html

## Set it as your Windows wallpaper (Lively — free)

1. **Download** this repo: green **Code** button → **Download ZIP**, then unzip.
2. **Install Lively Wallpaper** (free): https://www.rocksdanister.github.io/lively/
3. In Lively: **＋ Add Wallpaper → Browse → pick `index.html` → click it to apply.**
4. Click the **⚙ / wrench** on the thumbnail for settings.

## Settings

Colour theme (Spectrum · Fire · Ocean · Neon · Pastel · Mono) · Swirliness ·
Fade speed · Brush size · Glow (bloom) · Quality · Self-stir when idle · React to
music · 3D shading.

Single file, zero dependencies. Stam *Stable Fluids* method, GPU-accelerated. MIT.
