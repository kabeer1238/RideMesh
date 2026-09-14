package com.bikemesh.ridemesh.audio;

/** Owns only volume changes it made. No playback/call audio enters this policy. */
public final class MusicDuckPolicy {
    private Integer original, expected;
    private boolean wasMusic, manualOverride;
    private long musicSince, lastSpeech = -10000;

    public Integer tick(int volume, boolean music, boolean speech, long now) {
        if (expected != null && volume != expected) {
            original = null; expected = null; manualOverride = true;
        }
        if (!music) {
            wasMusic = false; manualOverride = false; lastSpeech = -10000;
            return release(volume);
        }
        if (!wasMusic) { wasMusic = true; musicSince = now; }
        if (now - musicSince < 600) return null;
        if (speech) lastSpeech = now;
        boolean talking = now - lastSpeech <= 900;
        if (!talking) manualOverride = false;
        if (talking && !manualOverride && (original != null || volume > 1)) {
            if (original == null) original = volume;
            int target = Math.max(1, (int)(original * 0.22));
            if (volume > target) { expected = target; return target; }
        } else if (!talking && original != null) {
            // Smooth recovery, one media-volume step per 100-ms tick.
            int next = Math.min(original, volume + 1);
            if (next >= original) { original = null; expected = null; }
            else expected = next;
            return next == volume ? null : next;
        }
        return null;
    }
    public Integer release(int volume) {
        Integer restore = expected != null && expected == volume ? original : null;
        original = null; expected = null; wasMusic = false; manualOverride = false;
        lastSpeech = -10000;
        return restore;
    }
}
