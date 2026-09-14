import Foundation
import AVFoundation
import Copus

/// Serial codec/planning queue; the render callback reads a bounded PCM ring only.
final class HybridAudio {
    private let work = DispatchQueue(label:"ridemesh.hybrid.audio",qos:.userInteractive)
    private let captureSlots = DispatchSemaphore(value:2)
    private let ringLock = NSLock()
    private var ring = [Float](repeating:0,count:1920)
    private var readIndex = 0
    private var writeIndex = 0
    private var buffered = 0
    private var engine: AVAudioEngine?
    private var wantsAudio = false
    private var tapInstalled = false
    private var retry: DispatchWorkItem?
    private var recovery = HybridAudioRecovery()
    private var startupStage = "Stopped"
    private var readyReported = false
    private var renderedSamples = 0
    private var outputRate: Double = 0
    private var captureCount = 0
    private var encodedCount = 0
    private var receivedCount = 0
    private var decodedCount = 0
    private var codecErrors = 0
    private var conversionErrors = 0
    private var microphoneLevel: Float = 0
    private var lastCapture: TimeInterval = 0
    private var silentRestarts = 0
    private var toneFrames = 0
    private var tonePhase = 0
    var onDiagnostics: (String) -> Void = { _ in }
    var onHealth: (Bool, Bool) -> Void = { _,_ in }
    func refreshDiagnostics() {
        work.async {
            let session = AVAudioSession.sharedInstance()
            let running = self.engine?.isRunning == true
            let capturing = running && self.readyReported && ProcessInfo.processInfo.systemUptime-self.lastCapture < 3
            self.ringLock.lock(); let rendered = self.renderedSamples; self.ringLock.unlock()
            let text = "Audio engine: \(self.engine?.isRunning == true ? "on" : "off") • mic buffers: \(self.captureCount) • level: \(Int(self.microphoneLevel * 1000))"
                + "\nEncoded: \(self.encodedCount) • received: \(self.receivedCount) • decoded: \(self.decodedCount) • codec errors: \(self.codecErrors) • conversion errors: \(self.conversionErrors)"
                + "\nOutput: \(session.currentRoute.outputs.map { $0.portName }.joined(separator:", ")) • \(Int(self.outputRate)) Hz • rendered samples: \(rendered)"
                + "\nAudio mode: \(self.recovery.useVoiceProcessing ? "echo cancellation" : "compatibility") • \(self.startupStage)"
            DispatchQueue.main.async { [weak self] in self?.onDiagnostics(text); self?.onHealth(running,capturing) }
            if self.wantsAudio && self.engine?.isRunning == true && self.toneFrames == 0 && ProcessInfo.processInfo.systemUptime-self.lastCapture > 3 && self.silentRestarts < 2 {
                self.silentRestarts += 1; self.recovery.failedOrStalled(); self.startOnQueue()
            } else if self.wantsAudio && !running && self.retry == nil && self.recovery.canRetry {
                self.recovery.failedOrStalled(); self.startOnQueue()
            }
        }
    }
    func sendTestTone() { work.async { if self.wantsAudio && self.engine?.isRunning == true && !self.muted { self.pcm.removeAll(); self.toneFrames = 100; self.tonePhase = 0 } } }
    private var encoder: OpaquePointer?
    private var decoders: [UUID:OpaquePointer] = [:]
    private var pending: [UUID:[UInt32:(Data,TimeInterval)]] = [:]
    private var expected: [UUID:UInt32] = [:]
    private var losses: [UUID:Int] = [:]
    private var lastSeen: [UUID:TimeInterval] = [:]
    private var pcm = [Float]()
    private var timer: DispatchSourceTimer?
    private var muted = false
    private var generation = UUID()
    private let format = AVAudioFormat(commonFormat:.pcmFormatFloat32,sampleRate:16000,channels:1,interleaved:false)!
    var encoded: (Data) -> Void = { _ in }
    var onError: (String) -> Void = { _ in }
    var onReady: () -> Void = {}
    func setMuted(_ value: Bool) { work.async { self.muted = value; self.pcm.removeAll(); if value { self.toneFrames = 0 } } }
    func start() { work.async {
        self.wantsAudio = true; self.recovery = HybridAudioRecovery(); self.silentRestarts = 0
        self.captureCount = 0; self.encodedCount = 0; self.receivedCount = 0; self.decodedCount = 0
        self.codecErrors = 0; self.conversionErrors = 0; self.startOnQueue()
    } }
    func recoverStoppedRoute() {
        work.async {
            // Failed startup also leaves engine nil. Explicit stop must still win.
            if self.wantsAudio && self.engine?.isRunning != true && self.retry == nil && self.recovery.canRetry {
                self.recovery.failedOrStalled()
                self.startOnQueue()
            }
        }
    }
    func stop() { work.sync { wantsAudio = false; stopOnQueue(); startupStage = "Stopped" } }
    private func stopOnQueue() {
        generation = UUID(); timer?.cancel(); timer = nil
        retry?.cancel(); retry = nil
        toneFrames = 0
        readyReported = false
        if tapInstalled { engine?.inputNode.removeTap(onBus:0) }; tapInstalled = false
        engine?.stop(); engine = nil
        if let encoder { opus_encoder_destroy(encoder) }; encoder = nil
        decoders.values.forEach { opus_decoder_destroy($0) }; decoders.removeAll()
        pending.removeAll(); expected.removeAll(); losses.removeAll(); lastSeen.removeAll(); pcm.removeAll()
        ringLock.lock(); buffered = 0; readIndex = 0; writeIndex = 0; renderedSamples = 0; ringLock.unlock()
    }
    private func startOnQueue() {
        guard wantsAudio, recovery.beginAttempt() else { return }
        stopOnQueue()
        do {
            startupStage = "Activating audio session"
            // Re-activate after WebRTC teardown or a transient headset route change.
            // AudioSessionManager retains ownership of category and route selection.
            try AVAudioSession.sharedInstance().setActive(true)
            var error: Int32 = 0
            guard let encoder = opus_encoder_create(16000,1,2048,&error), error == 0 else { throw NSError(domain:"Opus",code:Int(error)) }
            self.encoder = encoder
            guard rm_configure_opus(UnsafeMutableRawPointer(encoder)) == 0 else { throw NSError(domain:"Opus configuration",code:1) }
            let engine = AVAudioEngine(); self.engine = engine
            startupStage = "Configuring \(recovery.useVoiceProcessing ? "voice processing" : "standard input/output")"
            if recovery.useVoiceProcessing { try engine.inputNode.setVoiceProcessingEnabled(true) }
            let input = engine.inputNode.outputFormat(forBus:0)
            guard input.sampleRate > 0, input.channelCount > 0,
                  let converter = AVAudioConverter(from:input,to:format) else {
                throw NSError(domain:"Audio route",code:1,userInfo:[NSLocalizedDescriptionKey:
                    "Microphone route unavailable (\(input.sampleRate) Hz, \(input.channelCount) channels), attempt \(recovery.attempts)/4"])
            }
            // Convert the 16 kHz network audio in the mixer. Never implicitly ask
            // the hardware output (especially VoiceProcessingIO) to run at 16 kHz.
            let hardware = engine.outputNode.inputFormat(forBus:0)
            guard hardware.sampleRate > 0, hardware.channelCount > 0 else {
                throw NSError(domain:"Audio route",code:2,userInfo:[NSLocalizedDescriptionKey:"Speaker route unavailable"])
            }
            outputRate = hardware.sampleRate
            let run = generation
            let source = AVAudioSourceNode(format:format) { [weak self] isSilence,_,frames,list in
                guard let self else { return noErr }
                self.ringLock.lock(); defer { self.ringLock.unlock() }
                isSilence.pointee = ObjCBool(self.buffered == 0)
                for i in 0..<Int(frames) {
                    let sample = self.buffered > 0 ? self.ring[self.readIndex] : 0
                    if self.buffered > 0 {
                        self.readIndex = (self.readIndex+1)%self.ring.count; self.buffered -= 1
                        self.renderedSamples += 1
                    }
                    for buffer in UnsafeMutableAudioBufferListPointer(list) {
                        guard let out = buffer.mData?.assumingMemoryBound(to:Float.self) else { continue }
                        for channel in 0..<Int(buffer.mNumberChannels) { out[i*Int(buffer.mNumberChannels)+channel] = sample }
                    }
                }
                return noErr
            }
            engine.attach(source); engine.connect(source,to:engine.mainMixerNode,format:format)
            engine.connect(engine.mainMixerNode,to:engine.outputNode,format:hardware)
            engine.inputNode.installTap(onBus:0,bufferSize:960,format:input) { [weak self] buffer,_ in
                guard let self, self.captureSlots.wait(timeout:.now()) == .success else { return }
                let capacity = AVAudioFrameCount(Double(buffer.frameLength)*16000/input.sampleRate+32)
                guard let converted = AVAudioPCMBuffer(pcmFormat:self.format,frameCapacity:capacity) else { self.captureSlots.signal(); return }
                var supplied = false; var conversionError: NSError?
                converter.convert(to:converted,error:&conversionError) { _,status in
                    if supplied { status.pointee = .noDataNow; return nil }
                    supplied = true; status.pointee = .haveData; return buffer
                }
                let capturedAt = ProcessInfo.processInfo.systemUptime
                self.work.async {
                    defer { self.captureSlots.signal() }
                    guard self.generation == run else { return }
                    self.captureCount += 1; self.lastCapture = capturedAt
                    if !self.readyReported && self.engine?.isRunning == true {
                        self.readyReported = true; self.recovery.capturedAudio(); self.startupStage = "Microphone running"
                        DispatchQueue.main.async { [weak self] in self?.onReady() }
                    }
                    if conversionError != nil || converted.frameLength == 0 { self.conversionErrors += 1; return }
                    guard !self.muted, self.toneFrames == 0,
                          ProcessInfo.processInfo.systemUptime-capturedAt < 0.14,
                          let samples = converted.floatChannelData?[0] else { return }
                    self.pcm.append(contentsOf:UnsafeBufferPointer(start:samples,count:Int(converted.frameLength)))
                    self.microphoneLevel = (0..<Int(converted.frameLength)).reduce(Float(0)) { max($0,abs(samples[$1])) }
                    while self.pcm.count >= 320 {
                        var packet = [UInt8](repeating:0,count:256)
                        let count = self.pcm.withUnsafeBufferPointer { opus_encode_float(encoder,$0.baseAddress!,320,&packet,256) }
                        self.pcm.removeFirst(320)
                        if count > 0 {
                            self.encodedCount += 1
                            var data = Data([0x4f,0x50,0x56,0x31,1,UInt8(count >> 8),UInt8(truncatingIfNeeded:count)])
                            data.append(contentsOf:packet.prefix(Int(count)))
                            DispatchQueue.main.async { [weak self] in
                                if ProcessInfo.processInfo.systemUptime-capturedAt < 0.14 { self?.encoded(data) }
                            }
                        } else { self.codecErrors += 1 }
                    }
                }
            }
            tapInstalled = true
            startupStage = "Starting audio engine"
            engine.prepare()
            try engine.start()
            startupStage = "Waiting for microphone"
            lastCapture = ProcessInfo.processInfo.systemUptime
            let timer = DispatchSource.makeTimerSource(queue:work)
            timer.schedule(deadline:.now()+0.04,repeating:0.02,leeway:.milliseconds(2))
            timer.setEventHandler { [weak self] in self?.playTick() }; self.timer = timer; timer.resume()
        } catch {
            let stage = startupStage
            let nsError = error as NSError
            stopOnQueue()
            recovery.failedOrStalled()
            startupStage = recovery.canRetry ? "Retrying compatibility audio" : "Audio unavailable"
            let message = "\(stage): \(nsError.localizedDescription) [\(nsError.domain) \(nsError.code)]"
            DispatchQueue.main.async { [weak self] in self?.onError(message) }
            if wantsAudio && recovery.canRetry {
                let retry = DispatchWorkItem { [weak self] in self?.startOnQueue() }
                self.retry = retry
                work.asyncAfter(deadline:.now()+0.75,execute:retry)
            }
        }
    }
    func receive(_ p: HybridPacket) {
        let arrival = ProcessInfo.processInfo.systemUptime
        work.async {
            self.receivedCount += 1
            guard self.engine?.isRunning == true, p.payload.count >= 8, p.payload.count <= 263,
                  p.payload.starts(with:[0x4f,0x50,0x56,0x31,1]),
                  Int(p.payload[5])*256+Int(p.payload[6]) == p.payload.count-7,
                  self.pending.count < 7 || self.pending[p.origin] != nil else { return }
            if self.pending[p.origin] == nil { self.pending[p.origin] = [:] }
            if let e = self.expected[p.origin], p.sequence < e { return }
            self.pending[p.origin]![p.sequence] = (Data(p.payload.dropFirst(7)),arrival)
            self.lastSeen[p.origin] = arrival
            while self.pending[p.origin]!.count > 6 {
                if let first = self.pending[p.origin]!.keys.min() { self.pending[p.origin]!.removeValue(forKey:first) }
            }
        }
    }
    private func playTick() {
        guard wantsAudio, engine?.isRunning == true else { return }
        if toneFrames > 0 && !muted, let encoder {
            let samples = (0..<320).map { i in Float(0.08 * sin(2 * Double.pi * 440 * Double(tonePhase+i) / 16000)) }
            tonePhase += 320; toneFrames -= 1
            var packet = [UInt8](repeating:0,count:256)
            let count = samples.withUnsafeBufferPointer { opus_encode_float(encoder,$0.baseAddress!,320,&packet,256) }
            if count > 0 {
                encodedCount += 1
                var data = Data([0x4f,0x50,0x56,0x31,1,UInt8(count >> 8),UInt8(truncatingIfNeeded:count)])
                data.append(contentsOf:packet.prefix(Int(count)))
                DispatchQueue.main.async { [weak self] in self?.encoded(data) }
            } else { codecErrors += 1 }
        }
        let now = ProcessInfo.processInfo.systemUptime
        var mixed = [Float](repeating:0,count:320); var speakers = 0
        for source in Array(pending.keys) {
            if now-lastSeen[source,default:0] > 8 {
                pending.removeValue(forKey:source); expected.removeValue(forKey:source); losses.removeValue(forKey:source); lastSeen.removeValue(forKey:source)
                if let d = decoders.removeValue(forKey:source) { opus_decoder_destroy(d) }; continue
            }
            pending[source] = pending[source]!.filter { now-$0.value.1 < 0.14 }
            if expected[source] == nil {
                guard let first = pending[source]?.keys.min(), pending[source]!.count >= 2 || now-pending[source]![first]!.1 >= 0.04 else { continue }
                expected[source] = first
            }
            guard let seq = expected[source] else { continue }
            let frame = pending[source]?.removeValue(forKey:seq)?.0
            if frame == nil && losses[source,default:0] >= 2 { expected[source] = nil; losses[source] = 0; continue }
            if decoders[source] == nil { var error:Int32 = 0; decoders[source] = opus_decoder_create(16000,1,&error) }
            guard let decoder = decoders[source] else { continue }
            var output = [Float](repeating:0,count:320)
            let count: Int32
            if let frame { count = frame.withUnsafeBytes { opus_decode_float(decoder,$0.bindMemory(to:UInt8.self).baseAddress,Int32(frame.count),&output,320,0) }; losses[source] = 0 }
            else { count = opus_decode_float(decoder,nil,0,&output,320,0); losses[source,default:0] += 1 }
            expected[source] = seq &+ 1
            if count == 320 { if frame != nil { decodedCount += 1 }; speakers += 1; for i in 0..<320 { mixed[i] += output[i] } }
            else { codecErrors += 1 }
        }
        guard speakers > 0 else { return }
        let gain:Float = 1 / sqrt(Float(speakers))
        ringLock.lock(); defer { ringLock.unlock() }
        // Never accumulate more than 120 ms even if the output route stalls.
        if buffered+320 > ring.count { buffered = 0; readIndex = writeIndex }
        for sample in mixed { ring[writeIndex] = max(-1,min(1,sample*gain)); writeIndex = (writeIndex+1)%ring.count; buffered += 1 }
    }
}
