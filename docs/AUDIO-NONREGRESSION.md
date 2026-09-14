# RideMesh audio acceptance requirements

Applies to Internet, local Android, future LAN and future multi-hop transports.
Priority: private/system call > RideMesh speech > personal music.

- Natural hands-free intercom, without PTT.
- Private cellular/VoIP calls suspend both RideMesh capture and playout, retain group membership,
  and resume the previous route/mute state after the OS interruption ends. Neither side of a
  private call may be transmitted to the group. Transport switching must wait for audio priority.
- Personal music stays local. Do not capture playback, loop back a media stream, or select call
  uplink/downlink recording sources. Acoustic pickup through an open microphone still requires
  real headset/speaker testing; software path separation alone does not prove acoustic isolation.
- Local or remote speech ducks music; approximately 900 ms of silence releases ducking. Allow
  600 ms of music-start stabilization and use noise-aware speech detection, not raw loudness alone.
- A user's volume adjustment overrides RideMesh's saved volume. Restore only changes RideMesh owns.
- Recover helmet connect/disconnect and phone fallback without ending the ride.

## Build 39 implementation and limits

Original Android InternetNode code is unchanged except one read-only isAudioInterrupted accessor.
verify-online-baseline.py removes exactly that accessor and verifies the original source hash.
All protected iOS online files are byte-identical. This is preservation of implementation, not
proof that every requirement is met by the existing implementations or every phone/VoIP app.

Offline capture uses VOICE_COMMUNICATION microphone input only, audio focus interruption gates,
and skips Android-silenced recording buffers. Focus loss closes capture before media recovery.
Call-style transient loss waits for focus gain. Permanent loss only attempts media recovery if
ordinary music is active and the system is in normal audio mode; private VoIP app behavior must
be verified, including apps using permanent focus loss. Handover consults interruption state,
releases the current engine, and defers if a system communication mode appears in the gap.

Offline software music ducking uses processed local VAD and received PCM voice activity. The
receiver energy check is not a complete wind/noise classifier; further field tuning is expected.
Android/helmet mixing restrictions and OS automatic ducking may affect the final volume heard.
Bluetooth route callbacks restore the stored preference only while RideMesh owns audio focus.

## Release gate: test on actual devices, both directions

For online and offline separately: start music before/after the ride; local speech; remote speech;
quiet intervals; wind/engine noise; manual media-volume changes during duck/recovery; headset
disconnect/reconnect; phone fallback; mute before/during/after an interruption; locked screen.
Call each phone using cellular and WhatsApp (FaceTime on iOS), speak distinctive private test words
on both sides, and verify no private words are heard or transmitted on the other RideMesh phone.
Change Internet availability during the call, then end it and verify automatic intercom recovery.
Include a call beginning during the transport handover delay, and End Ride during a call.

CI exercises deterministic queue, handover debounce and duck-volume ownership policies. It cannot
verify private-call isolation, audible jitter, physical routing, actual music coexistence or radio range.
Do not promote this candidate to production until those device gates pass.
