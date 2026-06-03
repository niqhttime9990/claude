# Living Scenery — set it as your Windows live wallpaper

A beautiful scenic photo brought to life: slow cinematic drift + mouse parallax
for real depth, with layered interactive **weather** on top — snow, rain, storms
with lightning, drifting fog, sun god-rays, sparkle, fireflies, falling petals —
plus time-of-day colour grading and film grain for a cinematic look. Use a
built-in scene or **your own photo**. Everything is in this `wallpaper` folder.

## Step 1 — get the files onto your PC

Easiest: on the GitHub repo page, click the green **Code** button → **Download
ZIP**. Unzip it, and find the `wallpaper` folder inside. (Keep the whole folder
together — the wallpaper and its settings files live in it.)

## Step 2 — pick an app (both are fine)

### Option A · Lively Wallpaper — free, recommended
1. Install **Lively Wallpaper** (free) from the Microsoft Store, or from
   https://www.rocksdanister.github.io/lively/
2. Open Lively. Click the **＋ (Add Wallpaper)** tile.
3. Choose **Browse**, then select the **`index.html`** file inside the
   `wallpaper` folder. (Lively will pull in the whole folder and package it for
   you.) — *don't* use "Create Wallpaper"; that's for building one from scratch.
4. It appears in your library — **click it** to set it as your wallpaper. Done!
5. To customise, click the little **⚙ / "wrench"** on the wallpaper thumbnail.
   You'll get sliders and dropdowns: **Colour theme, Flow speed, Aurora
   intensity, Show starfield, React to music, Mouse interaction.**

> Tip: For the music-reactive mode, Lively listens to your system audio
> automatically — just play something and watch the aurora breathe.

> **Seeing "A LivelyInfo.json file was found… already packaged"?**
> That comes from the **Create Wallpaper** screen, which won't open an
> already-finished wallpaper. Two fixes — either one works:
> 1. Go back and use **＋ Add Wallpaper → Browse** (step 2–3 above) instead, **or**
> 2. If you grabbed an older copy of this folder, delete the file named
>    **`LivelyInfo.json`** inside it, then import again. Current downloads no
>    longer include that file, so this won't come up.


### Option B · Wallpaper Engine — if you own it on Steam
1. In Wallpaper Engine, open **Wallpaper Editor** → **Create Wallpaper**.
2. Choose **Web / HTML** and point it at the **`index.html`** in this folder
   (or just drag `index.html` onto the editor).
3. Apply it. The same settings (scene, weather, intensity, time of day, etc.)
   show up in the wallpaper's **Properties** panel.

## Use your OWN photo (recommended — this is where it shines)

1. Open the **`photos`** folder inside `wallpaper`.
2. Drop in your image and name it **`custom.jpg`** (the drone coastline shot you
   liked, a holiday pic, anything — landscape and high-res looks best).
3. In the wallpaper settings, set **Scene → "My Photo"**. Done — your photo now
   has drifting weather and cinematic lighting on top.

Prefer a web link? Set **Scene → "Custom URL"** and paste an image address into
the **Custom image URL** box.

## Step 3 — enjoy

- Move your mouse — the scene shifts with gentle **parallax** (real depth), and
  wind blows the snow/rain toward your cursor.
- **Click** the desktop for a ripple + a gust of wind.
- Pick a **Storm** and watch for lightning. Try **Sparkle** over water or
  **Fireflies** at night.
- Leave it alone and it drifts cinematically on its own.
- Launch a fullscreen game or video and it **pauses itself** to save your GPU
  and battery, then resumes when you're back.

> The built-in photo scenes stream from the internet the first time you pick
> them. If you're offline (or a scene won't load), it automatically shows the
> hand-drawn **Procedural Peaks** scene instead, so it's never blank.

## Just want to preview it first?

Double-click `index.html` to open it in your browser. (As a wallpaper it runs
the same, minus the browser window. In the browser you can also drag a photo
straight onto it — on the desktop, use the `photos/custom.jpg` method above.)

## Settings cheat-sheet

| Setting | What it does |
|---|---|
| **Scene** | Built-in scenic photos, your own photo, a custom URL, or the procedural fallback |
| **Custom image URL** | Paste any web image link (used when Scene = Custom URL) |
| **Weather** | None · Snow · Rain · Storm + lightning · Fog · Sun rays · Sparkle · Fireflies · Petals |
| **Weather intensity** | How heavy the weather is |
| **Time of day / mood** | Auto (real clock) or lock Dawn / Day / Golden hour / Dusk / Night |
| **Mouse parallax** | Scene depth + wind follow your cursor |
| **Film grain** | Subtle cinematic texture |
