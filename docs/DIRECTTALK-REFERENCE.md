# DirectTalk as a functional reference

Reviewed the user's Pasted markdown(10).md on September 14, 2026 and checked
https://apps.apple.com/in/app/directtalk-walkie-talkie-p2p/id6717587923 .

The developer advertises direct offline voice without a router, LAN extension,
full/half duplex, VOX, input/output selection, and background/locked operation.
Advertised direct range is normally 10 m, up to 30 m in ideal conditions. These
are developer claims, not RideMesh measurements. No published evidence reviewed
establishes true phone-to-phone multihop or Android interoperability. The codec,
Apple transport API, packet format and background implementation are unknown.
Do not infer those from marketing features or copy proprietary code/assets.

## RideMesh application of the reference

Protect the original online implementation. Build offline independently and keep
the normal conversation hands-free. A UI saying Connected is not a voice test.
Validate these checkpoints on devices, recording exact builds and phone models:

1. Two phones, same ride, no internet and no shared access point: both hear speech.
2. Simultaneous speech without push-to-talk; measure delay and missing audio.
3. Bluetooth helmet input/output, disconnect and reconnect without leaving ride.
4. Lock screens and test sustained conversation; test interruption and resumption.
5. Test LAN with its internet uplink removed separately from router-free operation.
6. Expand group size, then cross-platform transports, then actual relay chains.

The immediate user-requested build remains Android offline plus restored online
voice on both platforms. iPhone-only offline is a future isolated module; this
reference does not make the current iOS online-only build an offline intercom.

No unmeasured 100–200 m range or eight-rider audio guarantee is implied.
