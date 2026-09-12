package com.bikemesh.ridemesh.beta

object BetaWindow {
    const val DURATION_DAYS = 60L
    const val DAY_MS = 24L * 60L * 60L * 1000L
    const val DURATION_MS = DURATION_DAYS * DAY_MS

    fun expiresAt(firstLaunchMs: Long): Long = Long.MAX_VALUE
    fun isExpired(firstLaunchMs: Long, nowMs: Long): Boolean = false
    fun remainingDays(firstLaunchMs: Long, nowMs: Long): Long = DURATION_DAYS
    fun warningBucket(daysRemaining: Long): Int? = null
}
