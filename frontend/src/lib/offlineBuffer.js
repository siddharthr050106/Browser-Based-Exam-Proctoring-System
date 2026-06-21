/**
 * BEZP Offline Buffer — IndexedDB event queue for Gear 4
 *
 * Uses the `idb` pattern (raw IndexedDB wrapper) to persist events and video
 * clips when the network is unavailable. A flush loop checks navigator.onLine
 * every 5 seconds and uploads buffered items when connectivity returns.
 *
 * Also enforces the 5-minute Gear 4 exam suspension rule.
 *
 * No Service Worker — runs entirely on the main thread.
 */

const DB_NAME = 'bezp_offline'
const DB_VERSION = 1
const STORE_EVENTS = 'events'
const STORE_CLIPS = 'clips'
const STORE_GAZE = 'gaze'

let _db = null
let _flushInterval = null
let _gear4StartTime = null
let _onSuspend = null    // Callback when 5-min Gear 4 triggers suspension
let _onResume = null     // Callback when network recovers
let _isSuspended = false
let _remoteApiUrl = ''

const GEAR4_SUSPENSION_MS = 5 * 60 * 1000 // 5 minutes

// ── IndexedDB Initialization ──

function _openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = (event) => {
      const db = event.target.result
      if (!db.objectStoreNames.contains(STORE_EVENTS)) {
        db.createObjectStore(STORE_EVENTS, { keyPath: 'id', autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(STORE_CLIPS)) {
        db.createObjectStore(STORE_CLIPS, { keyPath: 'id', autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(STORE_GAZE)) {
        db.createObjectStore(STORE_GAZE, { keyPath: 'id', autoIncrement: true })
      }
    }

    request.onsuccess = () => {
      _db = request.result
      resolve(_db)
    }

    request.onerror = () => reject(request.error)
  })
}

async function _getDB() {
  if (_db) return _db
  return _openDB()
}

// ── Public API ──

/**
 * Initialize the offline buffer.
 * @param {string} remoteApiUrl
 * @param {Function} onSuspend - Called when 5-min Gear 4 triggers exam suspension
 * @param {Function} onResume - Called when network recovers and queue flushes
 */
export async function initOfflineBuffer(remoteApiUrl, onSuspend, onResume) {
  _remoteApiUrl = remoteApiUrl
  _onSuspend = onSuspend
  _onResume = onResume
  _isSuspended = false
  _gear4StartTime = null

  await _getDB()

  // Flush loop: check every 5 seconds
  _flushInterval = setInterval(() => {
    _checkAndFlush()
  }, 5000)

  // Listen for online/offline events
  window.addEventListener('online', _onOnline)
  window.addEventListener('offline', _onOffline)
}

/**
 * Stop the offline buffer.
 */
export function stopOfflineBuffer() {
  if (_flushInterval) {
    clearInterval(_flushInterval)
    _flushInterval = null
  }
  window.removeEventListener('online', _onOnline)
  window.removeEventListener('offline', _onOffline)
}

/**
 * Buffer a detection event for later upload.
 */
export async function bufferEvent(sessionId, signal) {
  try {
    const db = await _getDB()
    const tx = db.transaction(STORE_EVENTS, 'readwrite')
    tx.objectStore(STORE_EVENTS).add({
      sessionId,
      signal,
      timestamp: Date.now(),
    })
  } catch (err) {
    console.error('[OfflineBuffer] Failed to buffer event:', err)
  }
}

/**
 * Buffer gaze data for later upload.
 */
export async function bufferGaze(sessionId, gazeData) {
  try {
    const db = await _getDB()
    const tx = db.transaction(STORE_GAZE, 'readwrite')
    tx.objectStore(STORE_GAZE).add({
      sessionId,
      gazeData,
      timestamp: Date.now(),
    })
  } catch (err) {
    console.error('[OfflineBuffer] Failed to buffer gaze:', err)
  }
}

/**
 * Buffer a video clip blob for later upload.
 */
export async function bufferClip(sessionId, clipBlob, eventType) {
  try {
    // Convert Blob to ArrayBuffer for IndexedDB storage
    const arrayBuffer = await clipBlob.arrayBuffer()
    const db = await _getDB()
    const tx = db.transaction(STORE_CLIPS, 'readwrite')
    tx.objectStore(STORE_CLIPS).add({
      sessionId,
      clipData: arrayBuffer,
      mimeType: clipBlob.type || 'video/webm',
      eventType,
      timestamp: Date.now(),
    })
  } catch (err) {
    console.error('[OfflineBuffer] Failed to buffer clip:', err)
  }
}

/**
 * Notify the buffer that we've entered Gear 4. Starts the 5-minute timer.
 */
export function enterGear4() {
  if (_gear4StartTime === null) {
    _gear4StartTime = Date.now()
    console.log('[OfflineBuffer] Entered Gear 4 — suspension timer started')
  }
}

/**
 * Notify the buffer that we've left Gear 4.
 */
export function exitGear4() {
  _gear4StartTime = null
  if (_isSuspended) {
    _isSuspended = false
    if (_onResume) _onResume()
    console.log('[OfflineBuffer] Exited Gear 4 — exam resumed')
  }
}

/**
 * Check if the exam is currently suspended due to Gear 4 timeout.
 */
export function isSuspended() {
  return _isSuspended
}

/**
 * Get the number of buffered items.
 */
export async function getBufferCounts() {
  try {
    const db = await _getDB()
    const eventCount = await _countStore(db, STORE_EVENTS)
    const clipCount = await _countStore(db, STORE_CLIPS)
    const gazeCount = await _countStore(db, STORE_GAZE)
    return { events: eventCount, clips: clipCount, gaze: gazeCount }
  } catch {
    return { events: 0, clips: 0, gaze: 0 }
  }
}

// ── Internal: Flush Logic ──

async function _checkAndFlush() {
  // Check Gear 4 suspension timer
  if (_gear4StartTime !== null) {
    const elapsed = Date.now() - _gear4StartTime
    if (elapsed >= GEAR4_SUSPENSION_MS && !_isSuspended) {
      _isSuspended = true
      console.warn('[OfflineBuffer] 5 minutes in Gear 4 — SUSPENDING EXAM')
      if (_onSuspend) _onSuspend()
    }
  }

  // Only flush if online
  if (!navigator.onLine) return

  try {
    await _flushEvents()
    await _flushGaze()
    await _flushClips()
  } catch (err) {
    console.debug('[OfflineBuffer] Flush failed:', err.message)
  }
}

async function _flushEvents() {
  const db = await _getDB()
  const tx = db.transaction(STORE_EVENTS, 'readonly')
  const store = tx.objectStore(STORE_EVENTS)

  const items = await _getAll(store)
  if (items.length === 0) return

  // Send in batch
  try {
    const resp = await fetch(`${_remoteApiUrl}/api/heartbeat/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sid: items[0].sessionId,
        events: items.map(i => i.signal),
      }),
    })

    if (resp.ok) {
      // Delete successfully sent items
      const deleteTx = db.transaction(STORE_EVENTS, 'readwrite')
      const deleteStore = deleteTx.objectStore(STORE_EVENTS)
      for (const item of items) {
        deleteStore.delete(item.id)
      }
      console.log(`[OfflineBuffer] Flushed ${items.length} buffered events`)
    }
  } catch {
    // Will retry next cycle
  }
}

async function _flushGaze() {
  const db = await _getDB()
  const tx = db.transaction(STORE_GAZE, 'readonly')
  const store = tx.objectStore(STORE_GAZE)

  const items = await _getAll(store)
  if (items.length === 0) return

  // Send gaze snapshots (best-effort, non-critical)
  try {
    for (const item of items) {
      await fetch(`${_remoteApiUrl}/api/events/gaze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: item.sessionId,
          head_yaw: item.gazeData.yaw,
          head_pitch: item.gazeData.pitch,
          anomaly_score: item.gazeData.anomaly_score,
        }),
      })
    }

    // Clear all gaze items
    const deleteTx = db.transaction(STORE_GAZE, 'readwrite')
    const deleteStore = deleteTx.objectStore(STORE_GAZE)
    for (const item of items) {
      deleteStore.delete(item.id)
    }
    console.log(`[OfflineBuffer] Flushed ${items.length} buffered gaze snapshots`)
  } catch {
    // Will retry next cycle
  }
}

async function _flushClips() {
  const db = await _getDB()
  const tx = db.transaction(STORE_CLIPS, 'readonly')
  const store = tx.objectStore(STORE_CLIPS)

  const items = await _getAll(store)
  if (items.length === 0) return

  for (const item of items) {
    try {
      const blob = new Blob([item.clipData], { type: item.mimeType })
      const form = new FormData()
      form.append('clip', blob, 'clip.webm')

      await fetch(`${_remoteApiUrl}/api/clips/${item.sessionId}/offline-${item.id}`, {
        method: 'POST',
        body: form,
      })

      // Delete on success
      const deleteTx = db.transaction(STORE_CLIPS, 'readwrite')
      deleteTx.objectStore(STORE_CLIPS).delete(item.id)
      console.log(`[OfflineBuffer] Flushed buffered clip ${item.id}`)
    } catch {
      // Will retry next cycle
      break // Don't try more clips if upload fails
    }
  }
}

// ── Helpers ──

function _countStore(db, storeName) {
  return new Promise((resolve) => {
    const tx = db.transaction(storeName, 'readonly')
    const req = tx.objectStore(storeName).count()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => resolve(0)
  })
}

function _getAll(store) {
  return new Promise((resolve) => {
    const req = store.getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => resolve([])
  })
}

function _onOnline() {
  console.log('[OfflineBuffer] Network recovered — flushing queue')
  _checkAndFlush()
}

function _onOffline() {
  console.log('[OfflineBuffer] Network lost')
}
