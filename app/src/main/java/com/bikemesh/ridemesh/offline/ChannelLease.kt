package com.bikemesh.ridemesh.offline

/** Defers native disposal until active calls finish; never holds a monitor during native calls. */
class ChannelLease<T>(private val value: T, private val dispose: (T) -> Unit) {
    private val lock = Any()
    private var users = 0
    private var closing = false
    private var released = false
    fun <R> use(action: (T) -> R): R? {
        synchronized(lock) {
            if (closing) return null
            users++
        }
        try { return action(value) }
        finally {
            val release = synchronized(lock) {
                users--
                if (closing && users == 0 && !released) { released = true; true } else false
            }
            if (release) dispose(value)
        }
    }
    fun close() {
        val release = synchronized(lock) {
            closing = true
            if (users == 0 && !released) { released = true; true } else false
        }
        if (release) dispose(value)
    }
}
