# Aurora Drift — set it as your Windows live wallpaper

A calm, glowing aurora that drifts over a starry sky, shifts colour with the
time of day, follows your mouse, and can pulse to your music. Everything is in
this `wallpaper` folder.

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
3. Apply it. The same settings (theme, speed, intensity, stars, music, mouse)
   show up in the wallpaper's **Properties** panel.

## Step 3 — enjoy

- Move your mouse over the desktop — the aurora glows toward your cursor and the
  stars drift with a little parallax.
- **Click** the desktop for a soft ripple.
- Leave it alone and it stays gently alive on its own.
- Launch a fullscreen game or video and it **pauses itself** to save your GPU
  and battery, then resumes when you're back.

## Just want to preview it first?

Double-click `index.html` to open it in your browser, or click the live link in
the main project README. (As a wallpaper it runs the same, minus the browser
window.)

## Settings cheat-sheet

| Setting | What it does |
|---|---|
| **Colour theme** | Auto (changes with time of day), Aurora, Sunset, Ocean, Nebula, Mono |
| **Flow speed** | How fast the curtains drift |
| **Aurora intensity** | Brightness / strength of the aurora |
| **Show starfield** | Toggle the stars |
| **React to music** | Aurora pulses with your system audio |
| **Mouse interaction** | Cursor glow, parallax, and click ripples |
