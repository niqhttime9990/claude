// Bridge between the sandboxed renderer and the main process.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  getState: () => ipcRenderer.invoke('get-state'),
  setClientId: (id) => ipcRenderer.invoke('set-client-id', id),
  startAuth: () => ipcRenderer.invoke('start-auth'),
  logout: () => ipcRenderer.invoke('logout'),
  control: (action) => ipcRenderer.invoke('control', action),
  getStats: () => ipcRenderer.invoke('get-stats'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  close: () => ipcRenderer.invoke('win-close'),
  minimize: () => ipcRenderer.invoke('win-min'),
  setSize: (w, h) => ipcRenderer.invoke('set-size', { w, h }),
  onNowPlaying: (cb) => ipcRenderer.on('np-update', (_e, d) => cb(d)),
  onAuthChanged: (cb) => ipcRenderer.on('auth-changed', (_e, d) => cb(d)),
  onInteractiveChanged: (cb) => ipcRenderer.on('interactive-changed', (_e, d) => cb(d)),
});
