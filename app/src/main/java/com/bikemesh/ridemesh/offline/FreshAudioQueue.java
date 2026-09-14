package com.bikemesh.ridemesh.offline;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.ArrayDeque;

/** Short FIFO per speaker; round-robin fairness and an age cap prevent stale speech. */
public final class FreshAudioQueue {
    private static final class Frame {
        final byte[] bytes; final long at;
        Frame(byte[] bytes, long at) { this.bytes = bytes; this.at = at; }
    }
    private final LinkedHashMap<String, ArrayDeque<Frame>> frames = new LinkedHashMap<>();
    private long dropped;
    public synchronized void offer(String origin, byte[] bytes, long now) {
        ArrayDeque<Frame> speaker = frames.computeIfAbsent(origin, key -> new ArrayDeque<>());
        while (!speaker.isEmpty() && (now - speaker.peekFirst().at > 120 || speaker.size() >= 6)) {
            speaker.removeFirst(); dropped++;
        }
        speaker.addLast(new Frame(bytes, now));
        while (frames.size() > 8) { dropped += frames.remove(frames.keySet().iterator().next()).size(); }
    }
    public synchronized byte[] poll(long now) {
        while (!frames.isEmpty()) {
            String key = frames.keySet().iterator().next();
            ArrayDeque<Frame> speaker = frames.remove(key);
            Frame frame = speaker.removeFirst();
            if (!speaker.isEmpty()) frames.put(key, speaker);
            if (now - frame.at <= 120) return frame.bytes;
            dropped++;
        }
        return null;
    }
    public synchronized long droppedCount() { return dropped; }
    public synchronized int size() { return frames.values().stream().mapToInt(ArrayDeque::size).sum(); }
}
