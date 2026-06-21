/**
 * BEZP Heartbeat Service — Exception-Based Telemetry
 *
 * Normal behavior: Sends tiny ~50-byte heartbeat JSON at gear-defined intervals.
 * State change: Immediately fires event updates for WARNING/FLAG/CRITICAL.
 * Gear 2: Bundles INFO events with the next heartbeat.
 * Gear 4: Uses navigator.sendBeacon() for CRITICAL-only emergency alerts.
 *
 * All communication is over HTTPS/WSS (TLS 1.3) — no application-layer encryption.
 */

import { getCurrentGear, getGearConfig, shouldSendEvent, onGearChange } from './gearManager.js'
import { bufferEvent, bufferGaze } from './offlineBuffer.js'

let _heartbeatTimer = null
let _sessionId = null
let _remoteApiUrl = ''
let _trustScore = 1.0
let _bundledInfoEvents = [] // Gear 2: queued INFO events
let _onEventSent = null     // Callback for UI updates
let _unsubGear = null

// ── Trust Score Rules ──
const TRUST_PENALTIES = {
  tab_switch: -0.05,
  window_blur: -0.03,
  fullscreen_exit: -0.05,
  phone_detected: -0.20,
  multiple_persons: -0.25,
  no_face: -0.10,
  identity_mismatch: -0.30,
  gaze_anomaly: -0.10,
  background_changed: -0.10,
  multiple_speakers: -0.05,
  composite_critical: -0.30,
}
const TRUST_RECOVERY_PER_MINUTE = 0.01

/**
 * Initialize the heartbeat service.
 * @param {string} sessionId - The exam session ID
 * @param {string} remoteApiUrl - The remote FastAPI server URL
 * @param {Function} onEventSent - Callback when an event is sent to the server
 */
export function initHeartbeat(sessionId, remoteApiUrl = '', onEventSent = null) {
  _sessionId = sessionId
  _remoteApiUrl = remoteApiUrl
  _onEventSent = onEventSent
  _trustScore = 1.0
  _bundledInfoEvents = []

  // Start heartbeat loop
  _scheduleNextHeartbeat()

  // Re-schedule when gear changes
  _unsubGear = onGearChange((newGear) => {
    _scheduleNextHeartbeat()
  })

  // Trust recovery timer (slow recovery for clean behavior)
  setInterval(() => {
    _trustScore = Math.min(1.0, _trustScore + TRUST_RECOVERY_PER_MINUTE / 60)
  }, 1000)
}

/**
 * Stop the heartbeat service.
 */
export function stopHeartbeat() {
  if (_heartbeatTimer) {
    clearTimeout(_heartbeatTimer)
    _heartbeatTimer = null
  }
  if (_unsubGear) {
    _unsubGear()
    _unsubGear = null
  }
  // Flush any remaining bundled events
  if (_bundledInfoEvents.length > 0) {
    _sendBundledEvents()
  }
}

/**
 * Get the current trust score.
 */
export function getTrustScore() {
  return _trustScore
}

/**
 * Report a detection signal from the sidecar or browser events.
 * Routes through the gear system to decide: send / bundle / drop / buffer / beacon.
 *
 * @param {Object} signal - { event_type, tier, confidence, metadata, requires_clip }
 */
export function reportEvent(signal) {
  // Apply trust penalty
  const penalty = TRUST_PENALTIES[signal.event_type] || -0.02
  _trustScore = Math.max(0, _trustScore + penalty)

  const action = shouldSendEvent(signal.tier)

  switch (action) {
    case 'send':
      _sendEventToServer(signal)
      break
    case 'bundle':
      _bundledInfoEvents.push(signal)
      break
    case 'drop':
      // Gear 3: INFO events silently dropped
      break
    case 'buffer':
      // Gear 4: write to IndexedDB
      bufferEvent(_sessionId, signal)
      break
    case 'beacon':
      // Gear 4 CRITICAL: emergency sendBeacon
      _sendEmergencyBeacon(signal)
      bufferEvent(_sessionId, signal) // also buffer it
      break
  }

  // Notify UI
  if (_onEventSent) {
    _onEventSent(signal, action)
  }
}

/**
 * Report gaze data for the proctor timeline.
 * Only sends in Gear 1-2; buffers in Gear 3-4.
 */
export function reportGaze(gazeData) {
  const gear = getCurrentGear()
  if (gear <= 2) {
    _sendGazeToServer(gazeData)
  } else if (gear === 3) {
    // Gear 3: drop gaze telemetry (bandwidth conservation)
  } else {
    // Gear 4: buffer for later
    bufferGaze(_sessionId, gazeData)
  }
}

// ── Internal: Heartbeat Loop ──

function _scheduleNextHeartbeat() {
  if (_heartbeatTimer) clearTimeout(_heartbeatTimer)

  const config = getGearConfig()
  if (config.heartbeatMs === Infinity) {
    // Gear 4: no heartbeats
    return
  }

  _heartbeatTimer = setTimeout(async () => {
    await _sendHeartbeat()
    _scheduleNextHeartbeat() // schedule next
  }, config.heartbeatMs)
}

async function _sendHeartbeat() {
  const gear = getCurrentGear()
  const payload = {
    sid: _sessionId,
    ts: Date.now(),
    gear: gear,
    trust: Math.round(_trustScore * 1000) / 1000,
  }

  // Gear 2: attach bundled INFO events
  if (_bundledInfoEvents.length > 0) {
    payload.bundled_info = _bundledInfoEvents.splice(0)
  }

  try {
    await fetch(`${_remoteApiUrl}/api/heartbeat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch (err) {
    console.debug('[Heartbeat] Send failed:', err.message)
  }
}

// ── Internal: Event Sending ──

async function _sendEventToServer(signal) {
  const payload = {
    session_id: _sessionId,
    event_type: signal.event_type,
    tier: signal.tier,
    confidence: signal.confidence || null,
    metadata_json: signal.metadata || null,
  }

  try {
    await fetch(`${_remoteApiUrl}/api/events/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch (err) {
    // Network failed — buffer for retry
    bufferEvent(_sessionId, signal)
    console.debug('[Heartbeat] Event send failed, buffered:', err.message)
  }
}

async function _sendGazeToServer(gazeData) {
  try {
    await fetch(`${_remoteApiUrl}/api/events/gaze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: _sessionId,
        head_yaw: gazeData.yaw,
        head_pitch: gazeData.pitch,
        anomaly_score: gazeData.anomaly_score,
      }),
    })
  } catch {
    // Gaze data is non-critical — silently drop on failure
  }
}

function _sendBundledEvents() {
  if (_bundledInfoEvents.length === 0) return
  const events = _bundledInfoEvents.splice(0)

  fetch(`${_remoteApiUrl}/api/heartbeat/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sid: _sessionId, events }),
  }).catch(() => {
    // Buffer on failure
    events.forEach(e => bufferEvent(_sessionId, e))
  })
}

function _sendEmergencyBeacon(signal) {
  const payload = JSON.stringify({
    sid: _sessionId,
    type: signal.event_type,
    tier: signal.tier,
    ts: Date.now(),
  })

  // navigator.sendBeacon guarantees delivery even on tab close
  const sent = navigator.sendBeacon(
    `${_remoteApiUrl}/api/heartbeat/emergency`,
    new Blob([payload], { type: 'application/json' })
  )

  if (!sent) {
    console.error('[Heartbeat] Emergency beacon failed')
  }
}
