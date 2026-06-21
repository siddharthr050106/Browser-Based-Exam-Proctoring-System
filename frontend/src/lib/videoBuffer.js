/**
 * BEZP Video Buffer — 30-second rolling MediaRecorder ring buffer
 *
 * Continuously records the webcam stream in 1-second chunks, keeping
 * the last 30 in a circular array. When a FLAG/CRITICAL event fires,
 * the buffer is frozen, concatenated into a Blob, and either uploaded
 * or saved to IndexedDB (Gear 4).
 *
 * Video resolution is controlled by the Gear Manager.
 */

import { getCurrentGear, getGearConfig } from './gearManager.js'
import { bufferClip } from './offlineBuffer.js'

const BUFFER_SECONDS = 30
const CHUNK_INTERVAL_MS = 1000

let _recorder = null
let _chunks = []       // Circular buffer of Blob chunks
let _stream = null
let _isRecording = false
let _remoteApiUrl = ''
let _sessionId = null

/**
 * Initialize the video buffer with a media stream.
 * @param {MediaStream} stream - Webcam stream
 * @param {string} sessionId
 * @param {string} remoteApiUrl
 */
export function initVideoBuffer(stream, sessionId, remoteApiUrl = '') {
  _stream = stream
  _sessionId = sessionId
  _remoteApiUrl = remoteApiUrl
  _chunks = []

  _startRecording()
}

/**
 * Stop the video buffer and release resources.
 */
export function stopVideoBuffer() {
  _isRecording = false
  if (_recorder && _recorder.state !== 'inactive') {
    try { _recorder.stop() } catch {}
  }
  _recorder = null
  _chunks = []
}

/**
 * Capture the current 30-second buffer as a Blob.
 * Does NOT stop the recording — continues buffering after capture.
 * @returns {Blob|null}
 */
export function captureBuffer() {
  if (_chunks.length === 0) return null

  // Snapshot current chunks
  const snapshot = [..._chunks]
  return new Blob(snapshot, { type: 'video/webm' })
}

/**
 * Capture and upload the 30-second clip for a FLAG/CRITICAL event.
 * Routes through gear system: upload immediately (Gear 1-3) or buffer to IndexedDB (Gear 4).
 *
 * @param {string} eventType - The event that triggered clip capture
 * @returns {Promise<{uploaded: boolean, buffered: boolean}>}
 */
export async function captureAndUpload(eventType) {
  const clipBlob = captureBuffer()
  if (!clipBlob || clipBlob.size === 0) {
    return { uploaded: false, buffered: false }
  }

  const gear = getCurrentGear()

  if (gear === 4) {
    // Gear 4: save to IndexedDB for later upload
    await bufferClip(_sessionId, clipBlob, eventType)
    return { uploaded: false, buffered: true }
  }

  // Gear 1-3: upload immediately
  try {
    const form = new FormData()
    form.append('clip', clipBlob, 'clip.webm')

    await fetch(`${_remoteApiUrl}/api/clips/${_sessionId}/flag-${Date.now()}`, {
      method: 'POST',
      body: form,
    })
    return { uploaded: true, buffered: false }
  } catch (err) {
    // Upload failed — buffer for retry
    await bufferClip(_sessionId, clipBlob, eventType)
    return { uploaded: false, buffered: true }
  }
}

/**
 * Record a fresh 30-second clip starting NOW (used for proctor warnings).
 * Returns a promise that resolves with the clip Blob after 30 seconds.
 *
 * @returns {Promise<Blob>}
 */
export function recordWarningClip() {
  return new Promise((resolve, reject) => {
    if (!_stream || !_stream.active) {
      reject(new Error('Camera stream not active'))
      return
    }

    const warningChunks = []
    let warningRecorder

    try {
      warningRecorder = new MediaRecorder(_stream, { mimeType: 'video/webm' })
    } catch {
      try {
        warningRecorder = new MediaRecorder(_stream)
      } catch (e) {
        reject(e)
        return
      }
    }

    warningRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) warningChunks.push(e.data)
    }

    warningRecorder.onstop = () => {
      const blob = new Blob(warningChunks, { type: 'video/webm' })
      resolve(blob)
    }

    warningRecorder.onerror = (e) => reject(e)

    warningRecorder.start(CHUNK_INTERVAL_MS)

    // Stop after 30 seconds
    setTimeout(() => {
      if (warningRecorder.state !== 'inactive') {
        warningRecorder.stop()
      }
    }, BUFFER_SECONDS * 1000)
  })
}

// ── Internal ──

function _startRecording() {
  if (!_stream || !_stream.active) {
    console.warn('[VideoBuffer] Cannot start: stream not active')
    return
  }

  let options = { mimeType: 'video/webm;codecs=vp9' }
  if (!MediaRecorder.isTypeSupported(options.mimeType)) {
    options = { mimeType: 'video/webm;codecs=vp8' }
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      options = { mimeType: 'video/webm' }
    }
  }

  try {
    _recorder = new MediaRecorder(_stream, options)
  } catch {
    _recorder = new MediaRecorder(_stream)
  }

  _recorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      _chunks.push(event.data)
      // Keep only the last BUFFER_SECONDS chunks (circular buffer)
      while (_chunks.length > BUFFER_SECONDS) {
        _chunks.shift()
      }
    }
  }

  _recorder.onerror = (err) => {
    console.error('[VideoBuffer] Recorder error:', err)
    // Try to restart after a delay
    setTimeout(() => _startRecording(), 2000)
  }

  _recorder.start(CHUNK_INTERVAL_MS)
  _isRecording = true
}
