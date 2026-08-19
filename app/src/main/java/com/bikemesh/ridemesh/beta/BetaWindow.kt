package com.bikemesh.ridemesh.beta

object BetaWindow {
    const val DURATION_DAYS = 60L
    const val DAY_MS = 24L * 60L * 60L * 1000L
    const val DURATION_MS = DURATION_DAYS * DAY_MS

    fun expiresAt(firstLaunchMs: Long): Long = firstLaunchMs + DURATION_MS

    fun isExpired(firstLaunchMs: Long, nowMs: Long): Boolean =
        firstLaunchMs > 0L && nowMs >= expiresAt(firstLaunchMs)

    fun remainingDays(firstLaunchMs: Long, nowMs: Long): Long {
        if (firstLaunchMs <= 0L) return DURATION_DAYS
        val remainingMs = expiresAt(firstLaunchMs) - nowMs
        if (remainingMs <= 0L) return 0L
        return (remainingMs + DAY_MS - 1L) / DAY_MS
    }

    fun warningBucket(daysRemaining: Long): Int? = when {
        daysRemaining <= 0L -> null
        daysRemaining <= 1L -> 1
        daysRemaining <= 3L -> 3
        daysRemaining <= 7L -> 7
        daysRemaining <= 14L -> 14
        else -> null
    }
}
