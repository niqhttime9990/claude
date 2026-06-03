# Living Photo 🎞️

Turns a still image into a **cinematic live wallpaper**. Point it at a dark,
moody image you love (a Berserk blizzard, a rainy street, a moonlit forest) and
it comes alive: slow cinematic drift + mouse **parallax**, a **realistic blizzard
or rain** (depth-of-field, motion blur, gusting wind), drifting mist, plus
vignette, colour grade and film grain. It renders at your screen's **native
resolution** (4K on a 4K monitor). The realism comes from *your* image.

## 👉 The wallpaper is **`index.html`**

| File | What it's for |
|------|---------------|
| **`index.html`** | **The wallpaper.** |
| `LivelyProperties.json` / `project.json` | Settings panels (Lively / Wallpaper Engine) |
| `preview.jpg` | Thumbnail (a stand-in scene — yours will look better) |

![preview](preview.jpg)

## Use YOUR image — the whole point

1. **Drop a file:** save your picture next to `index.html` named **`bg.jpg`**.
   Done. (It's a background layer, not a GPU texture, so local files work as a
   desktop wallpaper.)
2. **Or paste a link:** put a **direct image URL** in the *"Your image URL"*
   setting.

**If your image is portrait/sideways** (like a phone wallpaper) and your monitor
is landscape, set **Fit → "Fit whole image"** so nothing is cropped, or rotate
the file to be upright first.

> Honest note: I can't fetch images or AI-upscale them from here, so I can't
> raise a low-res source to 4K — the wallpaper itself renders at full native
> resolution, but the source image is shown as-is. Use the highest-res version
> you have.

## Install on Windows (Lively — free)

1. **Download** this repo: green **Code** → **Download ZIP**, unzip.
2. Put your `bg.jpg` in the folder.
3. Install **Lively Wallpaper** (free): https://www.rocksdanister.github.io/lively/
4. Lively: **＋ Add Wallpaper → Browse → pick `index.html` → click to apply.**
5. **⚙ / wrench** on the thumbnail → settings.

## Settings

| Setting | What it does |
|---|---|
| **Your image URL** | Use any web image (or use `bg.jpg`) |
| **Fit** | Fill screen (crop) or Fit whole image (no crop) |
| **Weather** | Snow · Rain · Mist · Embers · None |
| **Weather intensity** | Light flurry → heavy blizzard |
| **Mist / haze** | Drifting atmosphere & blowing snow |
| **Wind** | Blows the snow/rain left or right (gusts on its own) |
| **Colour grade** | None · Cool · Warm · Noir |
| **Vignette / Film grain** | Cinematic finish |
| **Mouse parallax / Cinematic drift** | Subtle depth + slow zoom |

Smooth 60fps canvas, zero dependencies. Pauses when the desktop is hidden.
