const { app, BrowserWindow, ipcMain, screen } = require("electron");

function createWindow() {
  const { workArea } = screen.getPrimaryDisplay();
  const w = 300, h = 240;
  const win = new BrowserWindow({
    width: w,
    height: h,
    x: workArea.x + workArea.width - w - 16,   // park top-right by default
    y: workArea.y + 16,
    minWidth: 220,
    minHeight: 150,
    frame: false,
    resizable: true,
    alwaysOnTop: true,
    skipTaskbar: false,
    title: "Exam Countdown",
    backgroundColor: "#15131f",
    webPreferences: { nodeIntegration: true, contextIsolation: false }
  });
  win.setAlwaysOnTop(true, "screen-saver"); // stay above normal windows
  win.loadFile("widget.html");

  ipcMain.on("win-close", () => win.close());
  ipcMain.on("win-min", () => win.minimize());
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
