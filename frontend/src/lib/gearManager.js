/**
 * BEZP Gear Manager — 4-Gear Network Adaptation System
 *
 * Classifies network quality into 4 gears and exports reactive config
 * that other modules (heartbeat, detection, video) read to adapt behavior.
 *
 * Gear 1: >10 Mbps, RTT <50ms  → full telemetry
 * Gear 2: 2-10 Mbps, RTT 50-150ms → bundle INFO events
 * Gear 3: 0.5-2 Mbps, RTT 150-500ms → drop INFO, throttle ML to 2fps
 * Gear 4: <0.5 Mbps, RTT >500ms → silence, IndexedDB buffer only
 */

// ── Gear Definitions ──
export const GEARS = {
  1: {
    label: 'Excellent',
    heartbeatMs: 5000,
    sendInfo: true,
    bundleInfo: false,
    inferenceFps: 10,
    videoResolution: { width: 1280, height: 720, quality: 0.8 },
    color: '#10b981', // emerald
  },
  2: {
    label: 'Good',
    heartbeatMs: 15000,
    sendInfo: true,
    bundleInfo: true, // INFO events batched with next heartbeat
    inferenceFps: 10,
    videoResolution: { width: 854, height: 480, quality: 0.6 },
    color: '#6366f1', // indigo
  },
  3: {
    label: 'Limited',
    heartbeatMs: 30000,
    sendInfo: false, // INFO events dropped entirely
    bundleInfo: false,
    inferenceFps: 2,
    videoResolution: { width: 640, height: 360, quality: 0.4 },
    color: '#f59e0b', // amber
  },
  4: {
    label: 'Offline',
    heartbeatMs: Infinity, // no heartbeats
    sendInfo: false,
    bundleInfo: false,
    inferenceFps: 0, // ML paused
    videoResolution: null, // no video upload
    color: '#ef4444', // red
  },
}

// ── State ──
let _currentGear = 1
let _listeners = []
let _assessInterval = null
let _consecutiveGearReadings = [] // smoothing: need 2 consecutive same-gear readings
let _remoteApiUrl = ''

/**
 * Get the remote API URL, handling both Electron and browser environments.
 */
function getRemoteApiUrl() {
  if (_remoteApiUrl) return _remoteApiUrl
  // Fallback: use the current page origin (for Vite dev proxy)
  return ''
}

/**
 * Initialize the gear manager.
 * @param {string} remoteApiUrl - The remote FastAPI server URL
 */
export function initGearManager(remoteApiUrl = '') {
  _remoteApiUrl = remoteApiUrl
  _currentGear = 1
  _consecutiveGearReadings = []

  // Use Navigator.connection API if available
  if (navigator.connection) {
    navigator.connection.addEventListener('change', () => {
      _assessFromNavigator()
    })
  }

  // Periodic assessment every 30 seconds
  _assessInterval = setInterval(() => {
    assessNetwork()
  }, 30000)

  // Initial assessment
  assessNetwork()
}

/**
 * Stop the gear manager.
 */
export function stopGearManager() {
  if (_assessInterval) {
    clearInterval(_assessInterval)
    _assessInterval = null
  }
  _listeners = []
}

/**
 * Get current gear (1-4).
 */
export function getCurrentGear() {
  return _currentGear
}

/**
 * Get the full config for the current gear.
 */
export function getGearConfig() {
  return GEARS[_currentGear]
}

/**
 * Subscribe to gear changes.
 * @param {Function} callback - Called with (newGear, oldGear, config)
 * @returns {Function} unsubscribe function
 */
export function onGearChange(callback) {
  _listeners.push(callback)
  return () => {
    _listeners = _listeners.filter(l => l !== callback)
  }
}

/**
 * Assess network quality and update gear.
 * Uses a combination of Navigator.connection API and a small probe fetch.
 */
export async function assessNetwork() {
  let measuredGear = 1

  // Method 1: Navigator.connection API (instant, no network cost)
  if (navigator.connection) {
    measuredGear = _assessFromNavigator()
  }

  // Method 2: Online/offline check
  if (!navigator.onLine) {
    measuredGear = 4
  }

  // Method 3: Probe fetch for RTT measurement (only if we think we're online)
  if (measuredGear < 4) {
    try {
      const probeGear = await _assessFromProbe()
      // Take the worse of the two assessments
      measuredGear = Math.max(measuredGear, probeGear)
    } catch {
      // Probe failed — likely offline or very slow
      measuredGear = Math.max(measuredGear, 3)
    }
  }

  // Smoothing: require 2 consecutive readings at the same gear before switching
  _consecutiveGearReadings.push(measuredGear)
  if (_consecutiveGearReadings.length > 3) {
    _consecutiveGearReadings.shift()
  }

  const last2 = _consecutiveGearReadings.slice(-2)
  if (last2.length === 2 && last2[0] === last2[1]) {
    _setGear(last2[0])
  }

  return _currentGear
}

// ── Internal Helpers ──

function _assessFromNavigator() {
  const conn = navigator.connection
  if (!conn) return 1

  const downlink = conn.downlink || 10 // Mbps
  const rtt = conn.rtt || 0 // ms

  if (downlink >= 10 && rtt < 50) return 1
  if (downlink >= 2 && rtt < 150) return 2
  if (downlink >= 0.5 && rtt < 500) return 3
  return 4
}

async function _assessFromProbe() {
  const url = `${getRemoteApiUrl()}/api/heartbeat/probe`
  const start = performance.now()

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 3000) // 3s timeout

  try {
    const resp = await fetch(url, {
      method: 'GET',
      signal: controller.signal,
      cache: 'no-store',
    })
    clearTimeout(timeout)

    const rtt = performance.now() - start

    if (!resp.ok) return 3

    // Estimate bandwidth from response size and time
    const body = await resp.arrayBuffer()
    const sizeBits = body.byteLength * 8
    const timeSec = rtt / 1000
    const mbps = (sizeBits / timeSec) / 1_000_000

    if (mbps >= 10 && rtt < 50) return 1
    if (mbps >= 2 && rtt < 150) return 2
    if (mbps >= 0.5 && rtt < 500) return 3
    return 4
  } catch {
    clearTimeout(timeout)
    return navigator.onLine ? 3 : 4
  }
}

function _setGear(newGear) {
  if (newGear === _currentGear) return
  const oldGear = _currentGear
  _currentGear = newGear

  console.log(`[GearManager] Gear ${oldGear} → ${newGear} (${GEARS[newGear].label})`)

  const config = GEARS[newGear]
  _listeners.forEach(cb => {
    try { cb(newGear, oldGear, config) } catch (e) { console.error(e) }
  })
}

/**
 * Check if a given event tier should be sent immediately based on current gear.
 * @param {'info'|'warning'|'flag'|'critical'} tier
 * @returns {'send'|'bundle'|'drop'|'buffer'}
 */
export function shouldSendEvent(tier) {
  const gear = _currentGear
  const config = GEARS[gear]

  if (gear === 4) {
    // Gear 4: everything goes to IndexedDB; only CRITICAL uses sendBeacon
    return tier === 'critical' ? 'beacon' : 'buffer'
  }

  if (tier === 'warning' || tier === 'flag' || tier === 'critical') {
    return 'send' // Always send WARNING+ immediately (Gear 1-3)
  }

  // INFO tier
  if (!config.sendInfo) return 'drop'      // Gear 3: drop INFO
  if (config.bundleInfo) return 'bundle'    // Gear 2: bundle with heartbeat
  return 'send'                             // Gear 1: send immediately
}

/**
 * Get the appropriate frame capture interval (ms) for the current gear.
 * This controls how often we send frames to the local sidecar.
 */
export function getFrameCaptureIntervalMs() {
  const fps = GEARS[_currentGear].inferenceFps
  if (fps <= 0) return Infinity // Gear 4: no frames
  return Math.round(1000 / fps)
}
