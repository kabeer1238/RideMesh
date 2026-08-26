package com.bikemesh.ridemesh.service

/**
 * Bridges the Android foreground RideService with the active RideMesh runtime.
 *
 * The active voice/location objects are currently owned by MainActivity. While a
 * ride is active we deliberately retain one shutdown callback so a deliberate
 * Recents swipe can synchronously release those resources before the foreground
 * service exits. The callback is cleared as soon as the ride ends.
 */
object RideShutdownCoordinator {
    @Volatile
    private var shutdownAction: (() -> Unit)? = null

    fun register(action: () -> Unit) {
        shutdownAction = action
    }

    fun clear() {
        shutdownAction = null
    }

    fun requestShutdown(): Boolean {
        val action = shutdownAction ?: return false
        return runCatching {
            action.invoke()
            true
        }.getOrDefault(false)
    }
}
