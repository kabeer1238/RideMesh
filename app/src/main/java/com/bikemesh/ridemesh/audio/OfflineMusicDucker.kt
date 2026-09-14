package com.bikemesh.ridemesh.audio

import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.os.SystemClock

/** Volume control only; capture remains microphone-only in AudioEngine. */
internal class OfflineMusicDucker(private val manager: AudioManager) {
    private val handler = Handler(Looper.getMainLooper())
    private val policy = MusicDuckPolicy()
    @Volatile private var lastSpeechMs = -10000L
    private var enabled = false
    fun speech() { lastSpeechMs = SystemClock.elapsedRealtime() }
    private val tick = object : Runnable {
        override fun run() {
            if (!enabled) return
            val now = SystemClock.elapsedRealtime()
            runCatching {
                policy.tick(manager.getStreamVolume(AudioManager.STREAM_MUSIC), manager.isMusicActive,
                    now - lastSpeechMs <= 150, now)?.let {
                    manager.setStreamVolume(AudioManager.STREAM_MUSIC, it, 0)
                }
            }
            handler.postDelayed(this, 100)
        }
    }
    fun setEnabled(value: Boolean) {
        // Audio focus/capture callbacks may originate on different threads.
        handler.post {
            if (enabled == value) return@post
            enabled = value
            handler.removeCallbacks(tick)
            if (value) handler.post(tick)
            else {
                lastSpeechMs = -10000L
                runCatching {
                    policy.release(manager.getStreamVolume(AudioManager.STREAM_MUSIC))?.let {
                        manager.setStreamVolume(AudioManager.STREAM_MUSIC, it, 0)
                    }
                }
            }
        }
    }
}
