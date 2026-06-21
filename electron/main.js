/**
 * BEZP Electron Main Process
 *
 * Responsibilities:
 * - Spawns the Python sidecar (detection + audio on 127.0.0.1:8765)
 * - Creates the renderer window (loads the Vite React app)
 * - Enforces kiosk mode during active exam sessions
 * - Auto-restarts the sidecar on crash
 */

const { app, BrowserWindow, globalShortcut, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

// ── Configuration ──
const IS_DEV = process.env.NODE_ENV !== 'production';
const VITE_DEV_URL = 'http://localhost:5173';
const SIDECAR_PORT = 8765;
const SIDECAR_HOST = '127.0.0.1';
const REMOTE_API_URL = process.env.BEZP_API_URL || 'http://localhost:8000';

let mainWindow = null;
let pythonProcess = null;
let isExamActive = false; // Kiosk lockdown only during exam

// ── Python Sidecar Management ──

function getSidecarCommand() {
  if (IS_DEV) {
    // In dev, run the sidecar directly with Python
    return {
      cmd: 'python',
      args: [path.join(__dirname, '..', 'sidecar', 'main.py')],
      cwd: path.join(__dirname, '..'),
    };
  }
  // In production, use the PyInstaller-bundled executable
  const sidecarPath = path.join(process.resourcesPath, 'sidecar', 'main.exe');
  return { cmd: sidecarPath, args: [], cwd: path.dirname(sidecarPath) };
}

function startSidecar() {
  const { cmd, args, cwd } = getSidecarCommand();

  console.log(`[Main] Starting sidecar: ${cmd} ${args.join(' ')}`);

  pythonProcess = spawn(cmd, args, {
    cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, SIDECAR_PORT: String(SIDECAR_PORT) },
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Sidecar] ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Sidecar:err] ${data.toString().trim()}`);
  });

  pythonProcess.on('exit', (code) => {
    console.error(`[Main] Sidecar exited with code ${code}`);
    pythonProcess = null;
    // Auto-restart after 2 seconds (unless app is quitting)
    if (!app.isQuitting) {
      console.log('[Main] Restarting sidecar in 2s...');
      setTimeout(startSidecar, 2000);
    }
  });

  pythonProcess.on('error', (err) => {
    console.error('[Main] Failed to start sidecar:', err.message);
  });
}

function waitForSidecar(maxRetries = 30, interval = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      const req = http.get(`http://${SIDECAR_HOST}:${SIDECAR_PORT}/health`, (res) => {
        if (res.statusCode === 200) {
          console.log(`[Main] Sidecar ready after ${attempts} attempts`);
          resolve();
        } else {
          retry();
        }
      });
      req.on('error', retry);
      req.setTimeout(500, retry);
    };
    const retry = () => {
      if (attempts >= maxRetries) {
        reject(new Error('Sidecar did not start in time'));
      } else {
        setTimeout(check, interval);
      }
    };
    check();
  });
}

// ── Window Creation ──

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    title: 'BEZP — Exam Proctoring',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // Allow webcam/mic access
      permissions: ['media'],
    },
    // Start windowed; kiosk enabled when exam starts
    kiosk: false,
    fullscreen: false,
  });

  // Load the app
  if (IS_DEV) {
    mainWindow.loadURL(VITE_DEV_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'));
  }

  // Auto-grant camera/microphone permissions
  mainWindow.webContents.session.setPermissionRequestHandler(
    (webContents, permission, callback) => {
      const allowed = ['media', 'mediaKeySystem', 'fullscreen'];
      callback(allowed.includes(permission));
    }
  );

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── Kiosk Lockdown (only during active exam) ──

function enableKiosk() {
  if (!mainWindow) return;
  isExamActive = true;

  mainWindow.setKiosk(true);
  mainWindow.setFullScreen(true);
  mainWindow.setAlwaysOnTop(true, 'screen-saver');

  // Block common escape shortcuts
  globalShortcut.register('Alt+Tab', () => {});
  globalShortcut.register('Alt+F4', () => {});
  globalShortcut.register('CommandOrControl+Tab', () => {});
  globalShortcut.register('CommandOrControl+W', () => {});
  globalShortcut.register('CommandOrControl+Q', () => {});
  globalShortcut.register('Super', () => {});                 // Windows key
  globalShortcut.register('CommandOrControl+Shift+I', () => {}); // DevTools

  console.log('[Main] Kiosk mode ENABLED — exam active');
}

function disableKiosk() {
  if (!mainWindow) return;
  isExamActive = false;

  mainWindow.setKiosk(false);
  mainWindow.setFullScreen(false);
  mainWindow.setAlwaysOnTop(false);

  globalShortcut.unregisterAll();

  console.log('[Main] Kiosk mode DISABLED — exam ended');
}

// ── IPC Handlers (renderer ↔ main) ──

ipcMain.handle('get-config', () => ({
  sidecarUrl: `http://${SIDECAR_HOST}:${SIDECAR_PORT}`,
  remoteApiUrl: REMOTE_API_URL,
  isDev: IS_DEV,
}));

ipcMain.handle('start-kiosk', () => enableKiosk());
ipcMain.handle('stop-kiosk', () => disableKiosk());

ipcMain.handle('sidecar-health', async () => {
  try {
    const resp = await fetch(`http://${SIDECAR_HOST}:${SIDECAR_PORT}/health`);
    return await resp.json();
  } catch {
    return { status: 'offline' };
  }
});

// ── App Lifecycle ──

app.whenReady().then(async () => {
  startSidecar();
  createWindow();

  // Wait for sidecar to be ready (non-blocking for the window)
  try {
    await waitForSidecar();
    mainWindow?.webContents.send('sidecar-ready');
  } catch (err) {
    console.error('[Main] Sidecar failed to start:', err.message);
    mainWindow?.webContents.send('sidecar-error', err.message);
  }
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('before-quit', () => {
  app.isQuitting = true;
  globalShortcut.unregisterAll();
  if (pythonProcess) {
    pythonProcess.kill('SIGTERM');
    pythonProcess = null;
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
