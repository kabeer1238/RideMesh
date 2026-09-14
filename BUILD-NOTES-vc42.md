# Android vc42: opt-in ONLINE Silero field test

This is an experimental capture gate, not a verified improvement or an offline jitter fix.
No iOS changes. No production branch changes. Billing remains absent from the debug test APK.

## What changes
- Settings has a separate ONLINE SILERO toggle (OFF by default).
- Enable, then end/rejoin the ride. Disable immediately bypasses filtering; rejoin removes the hook.
- Native WebRTC microphone-buffer callback with 100 ms lookahead and 500 ms speech hangover.
- Neural inference uses a bounded background worker, never the capture thread.
- 8/16/32/48 kHz mono PCM16, 10 ms capture frames supported; analysis copy converted to 16 kHz.
  Original PCM sample rate is retained for WebRTC. Unexpected formats bypass filtering.
- First second passes for warmup. Missing/slow model decisions pass audio.
  Three consecutive late decisions or a full queue disables filtering for the session.
- 8 ms gate gain ramps; input-only processing, no playback capture.
- Mute/call transitions invalidate buffered frames and model results. Existing track/focus logic retained.
- Baseline hashes remain unchanged. Verification reverses ONLY explicitly listed vc42 integration
  edits then checks the historical online implementations. This does not certify device audio behavior.

## Important limitations
- Adds approximately 100 ms to outgoing voice when enabled. Does not fix offline packet jitter.
- Silero detects speech presence; it does NOT remove wind mixed with actual speech.
- Quiet speech can be missed. No highway, Bluetooth, call-isolation, or latency test is claimed.
- SDK hook runs before WebRTC processing. Echo cancellation and Bluetooth compatibility require
  testing with this extra capture delay.
- Model failure falls back to ordinary microphone audio, not to a privacy bypass:
  existing mute/interruption track disable remains authoritative.
- iOS online/offline implementation and internet signaling/Opus/network policy are unchanged.
- Android's existing group limit is not changed by this audio-only experiment.

## Device acceptance checklist (stationary first)
1. Two Android phones online: test toggle OFF as control, then ON (end/rejoin).
2. Speak after 5 seconds silence, including soft starts and names. Check no clipped syllables.
3. Test both directions, overlaps, 30 minutes continuous session, and ON vs OFF latency.
4. Check ONLINE SILERO DIAGNOSTICS: gated frames during silence, passed during speech, no BYPASS.
5. Test wired/helmet audio and route disconnect/reconnect; verify no new echo or distortion.
6. Mute/unmute; take cellular and WhatsApp calls. Other rider must hear neither private side;
   no buffered snippet on resume. Stop/rejoin must not replay earlier speech.
7. Music stays personal, ducking and volume choice unchanged. Never test while riding alone.
8. Compare 2 then 6/8 online riders before broad release.
9. Disable filtering immediately if words are lost. Offline remains vc41 behavior.
