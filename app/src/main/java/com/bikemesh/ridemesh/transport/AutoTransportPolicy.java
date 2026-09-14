package com.bikemesh.ridemesh.transport;

/** Debounces OS-validated Internet changes using a monotonic clock. No audio ownership here. */
public final class AutoTransportPolicy {
    private boolean online;
    private Boolean candidate;
    private long since;
    public boolean reset(boolean validated, long now) {
        online = validated; candidate = null; since = now; return online;
    }
    public boolean update(boolean validated, long now) {
        if (validated == online) { candidate = null; return online; }
        if (candidate == null || candidate != validated) { candidate = validated; since = now; }
        // Fast outage fallback; slower return prevents flapping in marginal coverage.
        if (now - since >= (validated ? 8000L : 2000L)) {
            online = validated; candidate = null;
        }
        return online;
    }
}
