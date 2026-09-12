# RideMesh vc33 — eight-rider hybrid voice test

This test build adds a shared Opus packet path between Nearby mesh and WebRTC data channels. Five riders with working internet peer links can exchange voice with three locally reachable riders who have no internet. All participants must use vc33 and select **Settings > Voice connection > Hybrid — eight-rider test**. Old vc32 and production internet rooms are isolated from this protocol.

## Routing
- AudioEngine alone owns microphone capture, audio focus, headset routing and playback. Internet-only mode retains its original native WebRTC audio tracks. Hybrid WebRTC connections are data-only.
- Each ride uses one fresh UUID across local and internet transports. Message ID, origin, audio sequence and Opus payload survive forwarding. One shared receive router suppresses duplicates before playback.
- RME1 envelope version 2 adds an internet-crossing count. A packet may cross to internet once, then continue through local links, never re-enter internet. TTL 6 allows seven links across eight riders.
- A gateway advertises only OPEN internet data-channel destinations, every two seconds. Local-path gateway leases expire after six seconds. For each destination the lowest eligible UUID forwards relayed packets. Own packets use direct internet links. Multiple gateways during convergence are safe because reception is deduplicated.
- This initial election ranks eligibility and stable identity, not measured radio signal or bandwidth. Internet-downlink traffic may enter local mesh from more than one gateway; duplicate suppression bounds playback but does not eliminate all redundant radio traffic.
- Hybrid mode keeps Nearby discovery awake even with battery saver selected. Mute suppresses only the user's microphone; received packets still relay.
- Opus remains 16 kHz mono / 20 ms / 32 kbps. Nearby queues retain the latest frame per speaker (eight maximum) and discard local waits over 140 ms. Internet packets use unordered WebRTC data channels with zero retransmissions and a 4 KiB send-buffer cap. This is not an end-to-end latency guarantee.

## Installation and test
Download the latest successful **RideMesh Cyan Hybrid Eight Rider Test** artifact from the offline-mesh-v1 Actions page. Extract and install `RideMesh-hybrid8-vc33-debug.apk`. Google Billing remains disabled. The `.offline` application ID installs separately from production. GitHub runner debug signing keys may differ between builds, requiring removal of an earlier test installation if Android reports a signature conflict.

Use the same ride code and **Hybrid** mode on all eight phones. Existing vc32 preferences may retain Offline mode, so check this explicitly. Use NORMAL test role for the mixed group. Keep Wi-Fi and Bluetooth on and grant microphone/Nearby/location permissions as requested.

1. First verify two online phones show working internet links, not just signaling readiness.
2. Add the other three online phones. Verify voice each way.
3. On three other phones disable mobile data and disconnect internet Wi-Fi, keeping both radios enabled. Place them near one or more online phones. Verify all eight appear and every rider can speak and listen.
4. Move one offline phone so it needs another local rider to relay. Verify the hop diagnostics and voice both ways.
5. Disable internet on the elected gateway. Allow the six-second lease plus discovery/connection settling time; verify the backup gateway carries voice. Restore it and repeat.
6. Test one speaker, then two, then eight; mute, headset, screen-off, calls, and network transitions. Record observed dropouts and end-to-end audio delay.

For a forced eight-phone local chain, assign A–H (only adjacent roles connect). The mixed group normally uses NORMAL; roles constrain local links only and do not restrict internet links.

## Limits and validation
The automated HybridMeshTest simulates the actual router and gateway election for five online / three offline participants, all eight speaking in turn, redundant gateways, gateway lease expiry, explicit withdrawal, no internet re-entry, spoofed previous-hop rejection, and a seven-link local chain. Existing codec and offline tests remain enabled. The Actions workflow runs unit tests, compiles the APK, verifies its signature and launcher, and rejects a Billing permission.

Physical eight-phone performance and 100–200 m range are not verified. Nearby radio range and cellular coexistence depend on hardware. Internet signaling still uses the existing test MQTT service. ICE currently has STUN servers but no deployed TURN relay; restrictive mobile networks may fail to establish a peer data channel. Signaling connectivity alone is never considered a working gateway. A production TURN service and real-device validation are needed before claiming reliable operation on arbitrary carrier networks.

API reference used for the channel configuration: https://chromium.googlesource.com/external/webrtc/+/HEAD/sdk/android/api/org/webrtc/DataChannel.java
