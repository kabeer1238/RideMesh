# RideMesh Live Rider Location Protocol — RML1 / vc25 contact extension

The Live Rider Map uses a **separate room-scoped MQTT topic** from WebRTC audio/signaling:

`ridemesh/test/v3/<RIDE_CODE>/location`

Voice remains WebRTC/Opus and always has priority. Location/contact packets remain lightweight, QoS 0, and are published only during an active ride.

## Binary packet — version 1

All multibyte numeric values are **big-endian**. vc25 uses the Android-compatible optional phone tail so iOS and Android can share the number needed by the map Call/Message actions.

| Field | Bytes | Notes |
|---|---:|---|
| Magic | 4 | ASCII `RML1` (`0x524D4C31`) |
| Version | 1 | `1` |
| Rider UUID | 16 | Stable RideMesh node ID |
| Timestamp ms | 8 | Int64 Unix milliseconds |
| Latitude | 8 | Float64 |
| Longitude | 8 | Float64 |
| Speed km/h | 4 | Float32 |
| Heading degrees | 4 | Float32 |
| Connection quality | 1 | Android-compatible extended values: `1=excellent, 2=good, 3=poor, 4=reconnecting` |
| Display-name length | 1 | 0–48 bytes |
| Display name | N | UTF-8 |
| Phone length | 1 | `0` when the optional number is not shared; max 32 bytes |
| Phone number | P | UTF-8, normally international format such as `+919876543210` |

The iOS decoder remains backward-compatible with the earlier vc23/vc24 canonical packet that ended after the display name and used 0-based quality values.

## Privacy / lifetime

- Phone number is optional.
- The setup screen explains that the number is shared with the current active RideMesh group for Call/Message actions.
- Location/contact data is sent only on the current ride-code room topic.
- Stop GPS/contact publishing immediately on **END RIDE**.
- Never mix location or phone data into WebRTC/Opus audio packets.
- RideMesh does not auto-place calls or auto-send messages.
- WhatsApp actions open the rider's WhatsApp conversation; the user explicitly starts the call or sends the message.
