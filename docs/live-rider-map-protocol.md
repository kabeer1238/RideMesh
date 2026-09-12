# RideMesh Live Rider Map protocol (RML1)

## Purpose

RML1 is the room-scoped rider-location packet used by the RideMesh Live Rider Map. It is a secondary service for group awareness only. It is not part of the WebRTC/Opus voice media path and must never be allowed to delay voice or reconnection work.

## Room transport

For ride code `<RIDE_CODE>`, location packets use the existing RideMesh room namespace:

`ridemesh/test/v3/<RIDE_CODE>/location`

Voice remains on WebRTC/SRTP. Presence and SDP/ICE signaling remain on their existing MQTT topics. Location is QoS-0 style lightweight room traffic and is published only while the rider is participating in the active ride.

Different ride codes therefore use different location topics. A client must discard packets whose room/session does not match its active RideMesh ride.

## Binary packet — RML1

All multi-byte numeric values are big-endian.

| Field | Type | Bytes | Notes |
| --- | --- | ---: | --- |
| magic | uint32 | 4 | `0x524D4C31` (`RML1`) |
| version | uint8 | 1 | `1` |
| riderId | UUID | 16 | Most-significant 64 bits then least-significant 64 bits |
| timestampMs | int64 | 8 | Unix epoch milliseconds |
| latitude | float64 | 8 | -90…90 |
| longitude | float64 | 8 | -180…180 |
| speedKmh | float32 | 4 | Clamped to 0…450 km/h |
| heading | float32 | 4 | Degrees, normalized 0…360 |
| connectionQuality | uint8 | 1 | 0 unknown, 1 Excellent, 2 Good, 3 Poor, 4 Reconnecting |
| displayNameLength | uint8 | 1 | Max 48 UTF-8 bytes |
| displayName | UTF-8 | variable | Rider-facing name only |
| phoneLength | uint8 | 1 | Max 32 UTF-8 bytes |
| phoneNumber | UTF-8 | variable | Optional; shared only during active ride |

The fixed packet size excluding the two variable strings is 56 bytes.

## Update policy

When moving on a healthy connection, Android targets about one transmitted location update per second. The client must reduce location publication before allowing map traffic to affect voice:

- stationary: approximately every 5 seconds
- app backgrounded: approximately every 3 seconds
- poor connection: approximately every 4 seconds
- reconnecting/signaling unavailable: defer location packets until the room connection is usable again
- Battery Smart enabled: reduce location network frequency while preserving useful group awareness

A significant movement can trigger an earlier update, subject to a short minimum interval.

## Receiver behavior

Receivers keep last-known rider positions rather than immediately deleting a rider when packets stop. The UI should show age such as `Last seen 15 sec ago` and change the marker to weak/offline styling. Fresh packets automatically restore the live marker.

Distance from the local rider is calculated locally as straight-line geodesic distance. No Google Routes, Directions or Distance Matrix API is needed.

## External actions

`Navigate` opens Google Maps using the selected rider's current coordinates. RideMesh does not provide route guidance. `Call` opens the native dialer. `Message` opens the native messaging UI. Neither action automatically calls or sends a message.

## iOS interoperability

iOS should publish and consume the same RML1 packet on the same room-scoped location topic, use Core Location for GPS data, and render the rider map with MapKit. This keeps Android and iPhone riders visible together without coupling the map provider to the RideMesh data protocol.
