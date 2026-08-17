# RideMesh Beta 1 Tester Guide

Version: **0.4.0-beta1**

RideMesh Beta 1 is an Android field-test build for motorcycle group voice. It combines Internet group voice with an automatic local Nearby fallback and supports phone audio or compatible Bluetooth helmet/headset audio.

## Beta 1 features

- Hands-free group voice.
- Internet voice for riders in different locations using the same Ride Code.
- Automatic Internet reconnect after temporary 4G/5G loss while the ride session remains active.
- Nearby local voice fallback when Internet is unavailable and riders have a usable local radio path.
- Local multi-hop packet relay prototype.
- Automatic local rediscovery after complete connectivity loss.
- Battery Smart mode: keeps local mesh warm during handover, then sleeps it after Internet is stable.
- Android VOICE_COMMUNICATION capture path.
- Platform Acoustic Echo Canceler when available.
- Platform Noise Suppressor when available.
- Platform Automatic Gain Control when available.
- Adaptive voice activity detection / silence suppression.
- Software high-pass wind/road-rumble reduction before VAD.
- Bounded playback queue to discard stale audio instead of building seconds of delay.
- Create / join ride by code.
- Show and share RideMesh QR invite while a conversation is active.
- Find nearby RideMesh riders during an active **Internet** call without ending the conversation.
- QR and nearby invites remain available before a ride starts.
- WhatsApp bug-report group: https://chat.whatsapp.com/CGToJCBDG6XFGUpeTp7uKW
- Direct support fallback: +91 9188664823
- RideMesh community: https://chat.whatsapp.com/GTH7FA1uTUFGRXElnfDfdE

## Important live-invite behavior

Nearby Connections discovery is radio-intensive and can disrupt established local peer links. Beta 1 therefore does **not** start a second nearby invite scan while a local-only mesh call is carrying voice. In that case use **Show QR** or **Share QR**. When Internet voice is healthy, RideMesh can temporarily use the nearby invite channel while the existing conversation continues over Internet.

## Recommended test matrix

### Test A — two riders, different locations
1. Both phones use Beta 1.
2. Both have mobile data / Internet.
3. Join the same Ride Code.
4. Start the ride.
5. Verify hands-free voice and rider presence.

### Test B — three riders over Internet
1. A, B and C join the same Ride Code from different locations.
2. Speak one at a time first, then try short overlaps.
3. Check latency, clipping, echo and wind/background noise.

### Test C — Internet loss and recovery
1. Start an Internet ride.
2. Disable mobile data / Internet on a rider.
3. If riders are nearby, verify local fallback.
4. If riders are far apart, the rider should show reconnecting.
5. Restore 4G/5G and verify automatic Internet reconnection without rejoining the ride.

### Test D — local reconnect
1. Start nearby with Internet disabled but Wi-Fi and Bluetooth enabled.
2. Move riders out of local radio range until disconnected.
3. Move them back into usable local range.
4. Verify automatic nearby rediscovery/reconnect without pressing Join again.

### Test E — add riders during a call
1. Start with two riders on Internet voice.
2. Tap **INVITE**.
3. Test **Show QR**, **Share QR**, and **Find nearby RideMesh riders**.
4. Existing riders should continue hearing each other while the invite scan runs.
5. New rider joins the same Ride Code and enters the group.

### Test F — helmet compatibility
Repeat Internet and local tests using different Bluetooth helmet/headset brands. Record the exact brand/model and whether microphone + speaker routing works.

### Test G — battery / screen-off
1. Enable Battery Smart.
2. Lock the screen for 15–30 minutes during a ride.
3. Record whether voice, Bluetooth routing and automatic reconnect remain usable.
4. Record battery percentage before and after the test.

## What to report

Please include:
- Phone manufacturer and model.
- Android version.
- Helmet/intercom brand and model, if used.
- Number of riders.
- Internet / local mesh / reconnecting state.
- Approximate delay before the problem.
- Whether screen was on or locked.
- Battery level if relevant.
- Steps that reproduce the problem.

## Known Beta 1 limitations

- This is a test build, not a production safety system.
- Internet voice currently uses experimental public test relay infrastructure and is not end-to-end encrypted. Do not use Beta 1 for sensitive conversations.
- Local range depends on phone radios, rider spacing, obstacles and RF conditions; software cannot create a link when there is no usable radio path.
- Nearby invite scanning is deliberately restricted during a local-only voice call to avoid breaking that call.
- The current media format is still PCM + VAD rather than the planned Opus transport, so larger groups and overlapping speech remain important Beta 1 test areas.
- Screen-off/process-restart behavior varies by Android/OEM battery management and needs field testing.

## Tester safety

Do not operate the phone while the motorcycle is moving. Set up the ride, audio route and invitations while stopped. Normal ride audio is hands-free.
