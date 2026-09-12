package com.bikemesh.ridemesh.offline;

import java.util.LinkedHashMap;
import java.util.Map;

/** One latest pending frame per speaker, FIFO between speakers. Local monotonic time only. */
public final class FreshAudioQueue {
    private static final class Frame {
        final byte[] bytes; final long at;
        Frame(byte[] bytes, long at) { this.bytes = bytes; this.at = at; }
    }
    private final LinkedHashMap<String, Frame> frames = new LinkedHashMap<>();
    private long dropped;
    public synchronized void offer(String origin, byte[] bytes, long now) {
        if (frames.put(origin, new Frame(bytes, now)) != null) dropped++;
        while (frames.size() > 6) { frames.remove(frames.keySet().iterator().next()); dropped++; }
    }
    public synchronized byte[] poll(long now) {
        while (!frames.isEmpty()) {
            String key = frames.keySet().iterator().next();
            Frame frame = frames.remove(key);
            if (now - frame.at <= 140) return frame.bytes;
            dropped++;
        }
        return null;
    }
    public synchronized long droppedCount() { return dropped; }
    public synchronized int size() { return frames.size(); }
}
