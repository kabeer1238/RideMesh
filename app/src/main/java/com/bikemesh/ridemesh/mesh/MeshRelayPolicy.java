package com.bikemesh.ridemesh.mesh;

/** Shared by the transport and dependency-free topology checks. */
public final class MeshRelayPolicy {
    // TTL counts remaining FORWARDS after the first direct transmission.
    public static final int INITIAL_TTL = 6;
    private MeshRelayPolicy() {}

    public static boolean allows(int localRole, int remoteRole) {
        if (localRole < 0 || localRole > 8 || remoteRole < 0 || remoteRole > 8) return false;
        if (localRole == 0 || remoteRole == 0) return localRole == remoteRole;
        return Math.abs(localRole - remoteRole) == 1;
    }

    public static boolean shouldForward(int ttl, boolean hasOtherPeer) {
        return ttl > 0 && ttl <= INITIAL_TTL && hasOtherPeer;
    }
}
