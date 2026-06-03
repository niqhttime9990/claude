# Living Photo 🎞️

Turns a still image into a **cinematic live wallpaper**. Point it at a dark,
moody night photo you love and it comes alive: a slow cinematic drift + mouse
**parallax**, real **falling rain or snow**, **drifting fog**, floating
dust/embers, plus vignette, colour grade and film grain. The realism comes from
*your* image — so the graphics are as high as the photo you choose.

## 👉 The wallpaper is **`index.html`**

| File | What it's for |
|------|---------------|
| **`index.html`** | **The wallpaper. This is the one.** |
| `LivelyProperties.json` | Settings panel in Lively |
| `project.json` | Settings panel in Wallpaper Engine |
| `preview.jpg` | Thumbnail / preview (a stand-in scene) |

![preview](preview.jpg)

## Use YOUR image (this is the whole point)

**Two easy ways:**
1. **Drop a file:** put your picture next to `index.html` and name it
   **`bg.jpg`**. That's it. (Works as a desktop wallpaper because the image is a
   background layer, not a GPU texture.)
2. **Paste a link:** in the wallpaper's settings, paste a **direct image URL**
   into the *"Your image URL"* box.

Pick something dark and atmospheric — a rainy street, a moonlit forest, a
foggy city, the knight-and-cathedral vibe. High-resolution looks best.

## Install on Windows (Lively — free)

1. **Download** this repo: green **Code** button → **Download ZIP**, unzip.
2. Put your `bg.jpg` in the folder (optional but recommended).
3. **Install Lively Wallpaper** (free): https://www.rocksdanister.github.io/lively/
4. In Lively: **＋ Add Wallpaper → Browse → pick `index.html` → click to apply.**
5. Click the **⚙ / wrench** on the thumbnail for settings.

## Try it in a browser

Open `index.html` (it shows a stand-in dark scene until you add `bg.jpg`), or
view live: https://htmlpreview.github.io/?https://github.com/niqhttime9990/claude/blob/main/index.html

## Settings

| Setting | What it does |
|---|---|
| **Your image URL** | Use any web image (or use `bg.jpg`) |
| **Weather** | Rain · Snow · Fog · Embers · None |
| **Weather intensity** | How heavy it falls |
| **Fog / mist** | Drifting atmosphere |
| **Wind** | Blows the rain/snow left or right |
| **Colour grade** | None · Cool · Warm · Noir |
| **Vignette / Film grain** | Cinematic finish |
| **Mouse parallax** | Photo shifts with the cursor for depth |
| **Cinematic drift** | Slow continuous zoom/pan (Ken Burns) |

Smooth 60fps canvas, zero dependencies. Pauses when the desktop is hidden.
