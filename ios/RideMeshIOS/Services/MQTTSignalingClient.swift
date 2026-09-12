import Foundation
import Network

final class MQTTSignalingClient {
    enum State: Equatable {
        case stopped
        case connecting
        case connected
        case reconnecting
        case failed(String)
    }

    var onState: ((State) -> Void)?
    var onPublish: ((String, Data) -> Void)?

    private let host: NWEndpoint.Host
    private let port: NWEndpoint.Port
    private let queue = DispatchQueue(label: "RideMesh.MQTT")
    private var connection: NWConnection?
    private var receiveBuffer = Data()
    private var reconnectAttempt = 0
    private var stopped = true
    private var clientID = ""
    private var subscriptionTopic = ""
    private var pingTimer: DispatchSourceTimer?
    private var reconnectWorkItem: DispatchWorkItem?

    init(host: String = "broker.hivemq.com", port: UInt16 = 8883) {
        self.host = NWEndpoint.Host(host)
        self.port = NWEndpoint.Port(rawValue: port)!
    }

    func start(clientID: String, subscriptionTopic: String) {
        queue.async {
            self.stopped = false
            self.clientID = clientID
            self.subscriptionTopic = subscriptionTopic
            self.reconnectAttempt = 0
            self.connect()
        }
    }

    func stop() {
        queue.async {
            self.stopped = true
            self.stopPingTimer()
            self.reconnectWorkItem?.cancel()
            self.reconnectWorkItem = nil
            self.connection?.cancel()
            self.connection = nil
            self.receiveBuffer.removeAll(keepingCapacity: false)
            self.emit(.stopped)
        }
    }

    func publish(topic: String, payload: Data) {
        queue.async {
            guard !self.stopped else { return }
            var body = Data()
            body.appendMQTTString(topic)
            body.append(payload)
            var packet = Data([0x30]) // PUBLISH QoS 0
            packet.appendMQTTRemainingLength(body.count)
            packet.append(body)
            self.send(packet)
        }
    }

    /// Move signaling onto a newly-available network path immediately. Used for
    /// Wi-Fi <-> cellular handover so RideMesh does not wait for a stale socket timeout.
    func forceReconnect() {
        queue.async {
            guard !self.stopped else { return }
            self.reconnectWorkItem?.cancel()
            self.reconnectWorkItem = nil
            self.stopPingTimer()
            self.connection?.stateUpdateHandler = nil
            self.connection?.cancel()
            self.connection = nil
            self.receiveBuffer.removeAll(keepingCapacity: true)
            self.emit(.reconnecting)
            self.queue.asyncAfter(deadline: .now() + 0.15) { [weak self] in
                guard let self, !self.stopped else { return }
                self.connect()
            }
        }
    }

    private func connect() {
        guard !stopped else { return }
        emit(reconnectAttempt == 0 ? .connecting : .reconnecting)

        let tls = NWProtocolTLS.Options()
        let tcp = NWProtocolTCP.Options()
        tcp.connectionTimeout = 5
        let parameters = NWParameters(tls: tls, tcp: tcp)
        let conn = NWConnection(host: host, port: port, using: parameters)
        connection = conn

        conn.stateUpdateHandler = { [weak self, weak conn] state in
            guard let self, let conn, conn === self.connection else { return }
            self.queue.async {
                switch state {
                case .ready:
                    self.receiveBuffer.removeAll(keepingCapacity: true)
                    self.sendConnectPacket()
                    self.receiveNext()
                case .failed(let error):
                    self.handleDisconnect("\(error)")
                case .cancelled:
                    if !self.stopped { self.handleDisconnect("Connection cancelled") }
                default:
                    break
                }
            }
        }
        conn.start(queue: queue)
    }

    private func sendConnectPacket() {
        var variable = Data()
        variable.appendMQTTString("MQTT")
        variable.append(0x04) // MQTT 3.1.1
        variable.append(0x02) // clean session
        variable.append(contentsOf: [0x00, 0x2D]) // 45 second keepalive

        var payload = Data()
        payload.appendMQTTString(clientID)

        let body = variable + payload
        var packet = Data([0x10])
        packet.appendMQTTRemainingLength(body.count)
        packet.append(body)
        send(packet)
    }

    private func sendSubscribePacket() {
        var body = Data([0x00, 0x01]) // packet identifier
        body.appendMQTTString(subscriptionTopic)
        body.append(0x00) // requested QoS 0

        var packet = Data([0x82])
        packet.appendMQTTRemainingLength(body.count)
        packet.append(body)
        send(packet)
    }

    private func send(_ data: Data) {
        guard let connection else { return }
        connection.send(content: data, completion: .contentProcessed { [weak self] error in
            guard let self, let error else { return }
            self.queue.async { self.handleDisconnect("Send: \(error)") }
        })
    }

    private func receiveNext() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            self.queue.async {
                if let data, !data.isEmpty {
                    self.receiveBuffer.append(data)
                    self.parsePackets()
                }
                if let error {
                    self.handleDisconnect("Receive: \(error)")
                } else if isComplete {
                    self.handleDisconnect("Broker closed connection")
                } else if !self.stopped {
                    self.receiveNext()
                }
            }
        }
    }

    private func parsePackets() {
        while receiveBuffer.count >= 2 {
            guard let decoded = decodeRemainingLength(in: receiveBuffer, start: 1) else { return }
            let headerLength = 1 + decoded.bytesUsed
            let total = headerLength + decoded.value
            guard receiveBuffer.count >= total else { return }

            let first = receiveBuffer[receiveBuffer.startIndex]
            let bodyStart = receiveBuffer.index(receiveBuffer.startIndex, offsetBy: headerLength)
            let bodyEnd = receiveBuffer.index(receiveBuffer.startIndex, offsetBy: total)
            let body = Data(receiveBuffer[bodyStart..<bodyEnd])
            receiveBuffer.removeSubrange(receiveBuffer.startIndex..<bodyEnd)
            handlePacket(firstByte: first, body: body)
        }
    }

    private func handlePacket(firstByte: UInt8, body: Data) {
        let type = firstByte >> 4
        switch type {
        case 2: // CONNACK
            guard body.count >= 2, body[body.index(body.startIndex, offsetBy: 1)] == 0 else {
                handleDisconnect("MQTT broker rejected connection")
                return
            }
            sendSubscribePacket()

        case 9: // SUBACK
            reconnectAttempt = 0
            emit(.connected)
            startPingTimer()

        case 3: // PUBLISH
            guard body.count >= 2 else { return }
            let topicLength = Int(body.readBEUInt16(at: 0) ?? 0)
            guard topicLength > 0, body.count >= 2 + topicLength else { return }
            let topicData = body.subdata(in: 2..<(2 + topicLength))
            guard let topic = String(data: topicData, encoding: .utf8) else { return }
            let payload = body.subdata(in: (2 + topicLength)..<body.count)
            onPublish?(topic, payload)

        case 13: // PINGRESP
            break
        default:
            break
        }
    }

    private func startPingTimer() {
        stopPingTimer()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + 30, repeating: 30)
        timer.setEventHandler { [weak self] in self?.send(Data([0xC0, 0x00])) }
        timer.resume()
        pingTimer = timer
    }

    private func stopPingTimer() {
        pingTimer?.cancel()
        pingTimer = nil
    }

    private func handleDisconnect(_ message: String) {
        guard !stopped else { return }
        stopPingTimer()
        connection?.stateUpdateHandler = nil
        connection?.cancel()
        connection = nil
        emit(.failed(message))

        // Fast first retry, then progressively back off to avoid radio/CPU churn
        // during long coverage gaps. Jitter prevents a group of riders reconnecting in lock-step.
        let exponent = Swift.min(reconnectAttempt, 5)
        let base = Swift.min(30.0, pow(2.0, Double(exponent)))
        reconnectAttempt = Swift.min(reconnectAttempt + 1, 10)
        let jitter = Double.random(in: 0...0.9)
        reconnectWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.stopped else { return }
            self.reconnectWorkItem = nil
            self.connect()
        }
        reconnectWorkItem = work
        queue.asyncAfter(deadline: .now() + base + jitter, execute: work)
    }

    private func emit(_ state: State) {
        DispatchQueue.main.async { [weak self] in self?.onState?(state) }
    }

    private func decodeRemainingLength(in data: Data, start: Int) -> (value: Int, bytesUsed: Int)? {
        var multiplier = 1
        var value = 0
        var index = start
        var used = 0

        while index < data.count, used < 4 {
            let byte = data[data.index(data.startIndex, offsetBy: index)]
            value += Int(byte & 0x7F) * multiplier
            used += 1
            if (byte & 0x80) == 0 { return (value, used) }
            multiplier *= 128
            index += 1
        }
        return nil
    }
}

private extension Data {
    mutating func appendMQTTString(_ value: String) {
        let bytes = Data(value.utf8)
        let count = UInt16(Swift.min(bytes.count, Int(UInt16.max)))
        append(UInt8((count >> 8) & 0xFF))
        append(UInt8(count & 0xFF))
        append(bytes.prefix(Int(count)))
    }

    mutating func appendMQTTRemainingLength(_ value: Int) {
        var x = value
        repeat {
            var digit = UInt8(x % 128)
            x /= 128
            if x > 0 { digit |= 0x80 }
            append(digit)
        } while x > 0
    }

    func readBEUInt16(at offset: Int) -> UInt16? {
        guard count >= offset + 2 else { return nil }
        let a = UInt16(self[index(startIndex, offsetBy: offset)])
        let b = UInt16(self[index(startIndex, offsetBy: offset + 1)])
        return (a << 8) | b
    }
}
