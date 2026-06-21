/**
 * BEZP Electron Preload Script
 *
 * Bridges Electron IPC to the renderer (React app) via contextBridge.
 * Exposes a safe `window.bezpElectron` API that the React code can call.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('bezpElectron', {
  /**
   * Get app configuration (sidecar URL, remote API URL, etc.)
   * @returns {Promise<{sidecarUrl: string, remoteApiUrl: string, isDev: boolean}>}
   */
  getConfig: () => ipcRenderer.invoke('get-config'),

  /**
   * Enable kiosk mode (blocks alt-tab, fullscreen, always-on-top)
   * Called when student starts an exam.
   */
  startKiosk: () => ipcRenderer.invoke('start-kiosk'),

  /**
   * Disable kiosk mode.
   * Called when student ends/submits an exam.
   */
  stopKiosk: () => ipcRenderer.invoke('stop-kiosk'),

  /**
   * Check sidecar health.
   * @returns {Promise<{status: string, active_sessions?: number}>}
   */
  sidecarHealth: () => ipcRenderer.invoke('sidecar-health'),

  /**
   * Listen for sidecar readiness from the main process.
   * @param {Function} callback
   */
  onSidecarReady: (callback) => {
    ipcRenderer.on('sidecar-ready', () => callback());
  },

  /**
   * Listen for sidecar errors.
   * @param {Function} callback
   */
  onSidecarError: (callback) => {
    ipcRenderer.on('sidecar-error', (_event, message) => callback(message));
  },

  /**
   * Check if running inside Electron (vs plain browser for dev).
   */
  isElectron: true,
});
