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
    func setMuted(_ value: Bool) { work.async { self.muted = value; self.pcm.removeAll() } }
    func start() { work.async { self.startOnQueue() } }
    func stop() { work.sync { stopOnQueue() } }
    private func stopOnQueue() {
        generation = UUID(); timer?.cancel(); timer = nil
        engine?.inputNode.removeTap(onBus:0); engine?.stop(); engine = nil
        if let encoder { opus_encoder_destroy(encoder) }; encoder = nil
        decoders.values.forEach { opus_decoder_destroy($0) }; decoders.removeAll()
        pending.removeAll(); expected.removeAll(); losses.removeAll(); lastSeen.removeAll(); pcm.removeAll()
        ringLock.lock(); buffered = 0; readIndex = 0; writeIndex = 0; ringLock.unlock()
    }
    private func startOnQueue() {
        stopOnQueue()
        do {
            var error: Int32 = 0
            guard let encoder = opus_encoder_create(16000,1,2048,&error), error == 0 else { throw NSError(domain:"Opus",code:Int(error)) }
            self.encoder = encoder
            guard rm_configure_opus(UnsafeMutableRawPointer(encoder)) == 0 else { throw NSError(domain:"Opus configuration",code:1) }
            let engine = AVAudioEngine(); self.engine = engine
            try engine.inputNode.setVoiceProcessingEnabled(true)
            let input = engine.inputNode.outputFormat(forBus:0)
            guard input.sampleRate > 0, let converter = AVAudioConverter(from:input,to:format) else { throw NSError(domain:"Audio route",code:1) }
            let run = generation
            let source = AVAudioSourceNode(format:format) { [weak self] _,_,frames,list in
                guard let self else { return noErr }
                self.ringLock.lock(); defer { self.ringLock.unlock() }
                for buffer in UnsafeMutableAudioBufferListPointer(list) {
                    guard let out = buffer.mData?.assumingMemoryBound(to:Float.self) else { continue }
                    for i in 0..<Int(frames) {
                        out[i] = self.buffered > 0 ? self.ring[self.readIndex] : 0
                        if self.buffered > 0 { self.readIndex = (self.readIndex+1)%self.ring.count; self.buffered -= 1 }
                    }
                }
                return noErr
            }
            engine.attach(source); engine.connect(source,to:engine.mainMixerNode,format:format)
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
                    guard self.generation == run, conversionError == nil, !self.muted,
                          ProcessInfo.processInfo.systemUptime-capturedAt < 0.14,
                          let samples = converted.floatChannelData?[0] else { return }
                    self.pcm.append(contentsOf:UnsafeBufferPointer(start:samples,count:Int(converted.frameLength)))
                    while self.pcm.count >= 320 {
                        var packet = [UInt8](repeating:0,count:256)
                        let count = self.pcm.withUnsafeBufferPointer { opus_encode_float(encoder,$0.baseAddress,320,&packet,256) }
                        self.pcm.removeFirst(320)
                        if count > 0 {
                            var data = Data([0x4f,0x50,0x56,0x31,1,UInt8(count >> 8),UInt8(truncatingIfNeeded:count)])
                            data.append(contentsOf:packet.prefix(Int(count)))
                            DispatchQueue.main.async { [weak self] in
                                if ProcessInfo.processInfo.systemUptime-capturedAt < 0.14 { self?.encoded(data) }
                            }
                        }
                    }
                }
            }
            try engine.start()
            let timer = DispatchSource.makeTimerSource(queue:work)
            timer.schedule(deadline:.now()+0.04,repeating:0.02,leeway:.milliseconds(2))
            timer.setEventHandler { [weak self] in self?.playTick() }; self.timer = timer; timer.resume()
        } catch { stopOnQueue(); DispatchQueue.main.async { self.onError(error.localizedDescription) } }
    }
    func receive(_ p: HybridPacket) {
        let arrival = ProcessInfo.processInfo.systemUptime
        work.async {
            guard self.engine != nil, p.payload.count >= 8, p.payload.count <= 263,
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
        let now = ProcessInfo.processInfo.systemUptime
        var mixed = [Float](repeating:0,count:320); var speakers = 0
        for source in Array(pending.keys) {
            if now-lastSeen[source,default:0] > 8 {
                pending.removeValue(forKey:source); expected.removeValue(forKey:source); losses.removeValue(forKey:source)
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
            if count == 320 { speakers += 1; for i in 0..<320 { mixed[i] += output[i] } }
        }
        guard speakers > 0 else { return }
        let gain:Float = 1 / sqrt(Float(speakers))
        ringLock.lock(); defer { ringLock.unlock() }
        // Never accumulate more than 120 ms even if the output route stalls.
        if buffered+320 > ring.count { buffered = 0; readIndex = writeIndex }
        for sample in mixed { ring[writeIndex] = max(-1,min(1,sample*gain)); writeIndex = (writeIndex+1)%ring.count; buffered += 1 }
    }
}
