from pathlib import Path
import re


def once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"{label}: anchor not found")
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# Beta5.4 / vc23: smart overlap clustering + temporary rider bottom sheet.
# Keeps Beta5.3 compact markers, phone sharing and call/message choices intact.
# -----------------------------------------------------------------------------
p = Path("app/build.gradle.kts")
s = p.read_text()
s = s.replace("versionCode = 22", "versionCode = 23")
s = s.replace(
    'versionName = "1.0.0-beta5.3-compact-map-contacts"',
    'versionName = "1.0.0-beta5.4-cluster-bottomsheet"',
)
p.write_text(s)

p = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = p.read_text()

# State for cluster markers, expanded cluster fan-out and rider detail bottom sheet.
state_anchor = "    private var selectedMapRiderId: String? = null\n"
state_add = r'''    private var selectedMapRiderId: String? = null
    private val riderClusterMarkers = mutableMapOf<String, Marker>()
    private var expandedClusterIds: Set<String> = emptySet()
    private var activeRiderDetailDialog: Dialog? = null
    private var activeRiderSheetExpanded = false
    private val riderDetailAutoHideRunnable = Runnable { dismissLiveRiderDetail() }
    private val clusterAutoCollapseRunnable = Runnable {
        if (expandedClusterIds.isNotEmpty()) {
            expandedClusterIds = emptySet()
            if (liveMapVisible) renderLiveRiderMap(fitGroup = false)
        }
    }
'''
if "private val riderClusterMarkers" not in s:
    s = once(s, state_anchor, state_add, "map interaction state")

# Google Map listeners: cluster expansion, map-tap dismiss/collapse, zoom-aware reclustering.
map_ready_pattern = re.compile(
    r'''    private fun ensureGoogleMapReady\(\) \{.*?\n    \}\n\n    private fun renderLiveRiderMap''',
    re.S,
)
map_ready_replacement = r'''    private fun ensureGoogleMapReady() {
        if (liveMap != null) return
        val host = liveMapHost ?: return
        if (!mapsApiKeyConfigured()) {
            host.removeAllViews()
            host.addView(TextView(this).apply {
                gravity = Gravity.CENTER
                text = "GOOGLE MAPS KEY REQUIRED\nVoice and rider location sharing remain available."
                textSize = 14f
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
            }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            return
        }
        val tag = LIVE_MAP_FRAGMENT_TAG
        val fragment = supportFragmentManager.findFragmentByTag(tag) as? SupportMapFragment
            ?: SupportMapFragment.newInstance()
        if (!fragment.isAdded) {
            supportFragmentManager.beginTransaction().replace(host.id, fragment, tag).commitNowAllowingStateLoss()
        }
        fragment.getMapAsync { map ->
            liveMap = map
            map.uiSettings.apply {
                isCompassEnabled = true
                isMapToolbarEnabled = false
                isZoomControlsEnabled = false
                isMyLocationButtonEnabled = false
                isIndoorLevelPickerEnabled = false
            }
            runCatching { map.setMapStyle(MapStyleOptions(DARK_MAP_STYLE_JSON)) }

            map.setOnMarkerClickListener { marker ->
                val tagValue = marker.tag as? String ?: return@setOnMarkerClickListener false
                if (tagValue.startsWith("cluster:")) {
                    val ids = tagValue.removePrefix("cluster:")
                        .split(',')
                        .map { it.trim() }
                        .filter { it.isNotBlank() }
                        .toSet()
                    if (ids.isNotEmpty()) {
                        dismissLiveRiderDetail()
                        selectedMapRiderId = null
                        expandedClusterIds = ids
                        mainHandler.removeCallbacks(clusterAutoCollapseRunnable)
                        mainHandler.postDelayed(clusterAutoCollapseRunnable, MAP_CLUSTER_EXPAND_TIMEOUT_MS)
                        renderLiveRiderMap(fitGroup = false)
                    }
                    return@setOnMarkerClickListener true
                }

                val riderId = tagValue
                val mine = myLiveLocation?.riderId?.toString()
                if (riderId == mine) {
                    myLiveLocation?.let(::showLiveRiderCard)
                } else {
                    selectedMapRiderId = riderId
                    riderLocations[riderId]?.let(::showLiveRiderCard)
                }
                renderLiveRiderMap(fitGroup = false)
                true
            }

            map.setOnMapClickListener {
                dismissLiveRiderDetail()
                selectedMapRiderId = null
                if (expandedClusterIds.isNotEmpty()) {
                    expandedClusterIds = emptySet()
                    mainHandler.removeCallbacks(clusterAutoCollapseRunnable)
                }
                renderLiveRiderMap(fitGroup = false)
            }

            map.setOnCameraIdleListener {
                if (liveMapVisible) renderLiveRiderMap(fitGroup = false)
            }
            renderLiveRiderMap(fitGroup = true)
        }
    }

    private fun renderLiveRiderMap'''
s, count = map_ready_pattern.subn(map_ready_replacement, s, count=1)
if count != 1:
    raise SystemExit(f"ensureGoogleMapReady replacement count={count}")

# Smart screen-space clustering. Remote rider cards collapse when their rendered
# rectangles would overlap. YOU is always kept visible. Cluster tap fans the riders
# out temporarily around the real location, then automatically collapses.
render_pattern = re.compile(
    r'''    private fun renderLiveRiderMap\(fitGroup: Boolean\) \{.*?\n    \}\n\n    private fun fitMapToRiders''',
    re.S,
)
render_replacement = r'''    private fun renderLiveRiderMap(fitGroup: Boolean) {
        val map = liveMap ?: return
        val mine = myLiveLocation
        val now = System.currentTimeMillis()
        val all = buildList {
            mine?.let { add(it) }
            addAll(riderLocations.values.sortedBy { it.displayName.lowercase(Locale.ROOT) })
        }
        if (all.isEmpty()) return

        val projection = map.projection
        val mineId = mine?.riderId?.toString()
        val peerQuality = internetNode.remotePeers().associateBy({ it.id.toString() }, { it.qualityLabel })
        val shownRiderIds = mutableSetOf<String>()
        val activeClusterKeys = mutableSetOf<String>()

        fun showRider(location: InternetNode.RiderLocation, displayPosition: LatLng) {
            val id = location.riderId.toString()
            val self = id == mineId
            val age = (now - location.timestampMs).coerceAtLeast(0L)
            val quality = if (self) "You" else peerQuality[id] ?: location.connectionQuality
            val offline = !self && age >= MAP_OFFLINE_AFTER_MS
            val selected = selectedMapRiderId == id
            val statusColor = markerStatusColor(self, selected, quality, offline, age)
            val distance = if (self || mine == null) null else distanceMeters(mine, location)
            val icon = BitmapDescriptorFactory.fromBitmap(
                createRiderMarkerBitmap(
                    name = if (self) "YOU" else location.displayName.ifBlank { "RIDER" },
                    speedKmh = location.speedKmh,
                    distanceMeters = distance,
                    heading = location.heading,
                    statusColor = statusColor,
                    stale = offline,
                )
            )
            val marker = riderMapMarkers[id]
            if (marker == null) {
                riderMapMarkers[id] = map.addMarker(
                    MarkerOptions()
                        .position(displayPosition)
                        .icon(icon)
                        .anchor(0.5f, 1f)
                        .zIndex(if (self) 8f else if (selected) 7f else 4f)
                )!!.apply { tag = id }
            } else {
                marker.position = displayPosition
                marker.setIcon(icon)
                marker.tag = id
                marker.zIndex = if (self) 8f else if (selected) 7f else 4f
                marker.isVisible = true
            }
            shownRiderIds += id
        }

        // YOU is never swallowed by a cluster.
        mine?.let { showRider(it, LatLng(it.latitude, it.longitude)) }

        val remote = all.filter { it.riderId.toString() != mineId }
        val clusterRadiusPx = dp(MAP_CLUSTER_RADIUS_DP)
        val clusterRadiusSq = clusterRadiusPx * clusterRadiusPx
        val groups = mutableListOf<MutableList<InternetNode.RiderLocation>>()

        remote.forEach { location ->
            val point = projection.toScreenLocation(LatLng(location.latitude, location.longitude))
            val group = groups.firstOrNull { existing ->
                val first = existing.first()
                val firstPoint = projection.toScreenLocation(LatLng(first.latitude, first.longitude))
                val dx = point.x - firstPoint.x
                val dy = point.y - firstPoint.y
                dx * dx + dy * dy <= clusterRadiusSq
            }
            if (group == null) groups += mutableListOf(location) else group += location
        }

        val selfPoint = mine?.let { projection.toScreenLocation(LatLng(it.latitude, it.longitude)) }
        var expandedClusterStillExists = false

        groups.forEach { group ->
            val nearSelf = selfPoint != null && group.any { location ->
                val point = projection.toScreenLocation(LatLng(location.latitude, location.longitude))
                val dx = point.x - selfPoint.x
                val dy = point.y - selfPoint.y
                dx * dx + dy * dy <= clusterRadiusSq
            }
            val shouldCluster = group.size >= 2 || nearSelf
            if (!shouldCluster) {
                group.forEach { showRider(it, LatLng(it.latitude, it.longitude)) }
                return@forEach
            }

            val ids = group.map { it.riderId.toString() }.sorted()
            val idSet = ids.toSet()
            val clusterKey = ids.joinToString(",")
            val expanded = expandedClusterIds == idSet
            if (expanded) expandedClusterStillExists = true

            if (expanded) {
                val centerLat = group.map { it.latitude }.average()
                val centerLon = group.map { it.longitude }.average()
                val centerPoint = projection.toScreenLocation(LatLng(centerLat, centerLon))
                val hostWidth = liveMapHost?.width?.takeIf { it > 0 } ?: resources.displayMetrics.widthPixels
                val hostHeight = liveMapHost?.height?.takeIf { it > 0 } ?: resources.displayMetrics.heightPixels

                group.sortedBy { it.displayName.lowercase(Locale.ROOT) }.forEachIndexed { index, location ->
                    val column = (index % 3) - 1
                    val row = (index / 3) + 1
                    val desiredX = centerPoint.x + column * dp(118)
                    val desiredY = centerPoint.y - row * dp(66)
                    val x = desiredX.coerceIn(dp(70), (hostWidth - dp(70)).coerceAtLeast(dp(70)))
                    val y = desiredY.coerceIn(dp(54), (hostHeight - dp(40)).coerceAtLeast(dp(54)))
                    val displayPosition = projection.fromScreenLocation(android.graphics.Point(x, y))
                    showRider(location, displayPosition)
                }
            } else {
                // Hide the individual cards while collapsed.
                ids.forEach { riderMapMarkers[it]?.isVisible = false }

                val centerLat = group.map { it.latitude }.average()
                val centerLon = group.map { it.longitude }.average()
                var clusterPosition = LatLng(centerLat, centerLon)
                if (nearSelf && selfPoint != null) {
                    val shifted = android.graphics.Point(selfPoint.x, selfPoint.y - dp(62))
                    clusterPosition = projection.fromScreenLocation(shifted)
                }

                val clusterIcon = BitmapDescriptorFactory.fromBitmap(
                    createRiderClusterBitmap(group.size, nearSelf)
                )
                val existing = riderClusterMarkers[clusterKey]
                if (existing == null) {
                    riderClusterMarkers[clusterKey] = map.addMarker(
                        MarkerOptions()
                            .position(clusterPosition)
                            .icon(clusterIcon)
                            .anchor(0.5f, 1f)
                            .zIndex(if (nearSelf) 9f else 6f)
                    )!!.apply { tag = "cluster:$clusterKey" }
                } else {
                    existing.position = clusterPosition
                    existing.setIcon(clusterIcon)
                    existing.tag = "cluster:$clusterKey"
                    existing.zIndex = if (nearSelf) 9f else 6f
                    existing.isVisible = true
                }
                activeClusterKeys += clusterKey
            }
        }

        if (expandedClusterIds.isNotEmpty() && !expandedClusterStillExists) {
            expandedClusterIds = emptySet()
            mainHandler.removeCallbacks(clusterAutoCollapseRunnable)
        }

        riderMapMarkers.forEach { (id, marker) ->
            if (id !in shownRiderIds) marker.isVisible = false
        }
        riderClusterMarkers.keys.filter { it !in activeClusterKeys }.toList().forEach { key ->
            riderClusterMarkers.remove(key)?.remove()
        }

        if (fitGroup && now - lastMapFitMs >= MAP_AUTO_FIT_COOLDOWN_MS) {
            fitMapToRiders(all)
            lastMapFitMs = now
        }
    }

    private fun fitMapToRiders'''
s, count = render_pattern.subn(render_replacement, s, count=1)
if count != 1:
    raise SystemExit(f"renderLiveRiderMap replacement count={count}")

# Add cluster badge renderer before distanceMeters. Small footprint with a pointer stem.
cluster_anchor = "    private fun distanceMeters(a: InternetNode.RiderLocation, b: InternetNode.RiderLocation): Float {\n"
if "private fun createRiderClusterBitmap" not in s:
    cluster_helper = r'''    private fun createRiderClusterBitmap(count: Int, nearSelf: Boolean): Bitmap {
        val width = dp(72)
        val height = dp(58)
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val accent = Color.parseColor(if (nearSelf) "#00E5FF" else "#37D67A")
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#F0060B0B") }
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = accent
            style = Paint.Style.STROKE
            strokeWidth = dp(2).toFloat()
        }
        canvas.drawCircle(dp(36).toFloat(), dp(25).toFloat(), dp(22).toFloat(), bg)
        canvas.drawCircle(dp(36).toFloat(), dp(25).toFloat(), dp(22).toFloat(), stroke)
        canvas.drawLine(dp(36).toFloat(), dp(47).toFloat(), dp(36).toFloat(), dp(56).toFloat(), stroke)

        val number = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = dp(16).toFloat()
            textAlign = Paint.Align.CENTER
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = accent
            textSize = dp(6).5f
            textAlign = Paint.Align.CENTER
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        canvas.drawText(count.toString(), dp(36).toFloat(), dp(27).toFloat(), number)
        canvas.drawText(if (nearSelf) "NEARBY" else "RIDERS", dp(36).toFloat(), dp(39).toFloat(), label)
        return bitmap
    }

'''
    s = once(s, cluster_anchor, cluster_helper + cluster_anchor, "cluster bitmap")

# Rider detail becomes a bottom sheet with three states:
# hidden -> compact preview -> expanded details. X/outside tap/swipe-down closes;
# swipe-up or VIEW DETAILS expands; idle auto-hides.
rider_card_pattern = re.compile(
    r'''    private fun showLiveRiderCard\(location: InternetNode\.RiderLocation\) \{.*?\n    \}\n\n    private fun mapActionButton''',
    re.S,
)
rider_card_replacement = r'''    private fun dismissLiveRiderDetail() {
        mainHandler.removeCallbacks(riderDetailAutoHideRunnable)
        activeRiderDetailDialog?.dismiss()
        activeRiderDetailDialog = null
        activeRiderSheetExpanded = false
    }

    private fun scheduleRiderDetailAutoHide() {
        mainHandler.removeCallbacks(riderDetailAutoHideRunnable)
        mainHandler.postDelayed(riderDetailAutoHideRunnable, RIDER_DETAIL_AUTO_HIDE_MS)
    }

    private fun addRiderSheetStat(
        parent: LinearLayout,
        label: String,
        value: String,
        highlight: Boolean = false,
    ) {
        val cell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(7), dp(8), dp(7))
        }
        cell.addView(TextView(this).apply {
            text = label.uppercase(Locale.ROOT)
            textSize = 8f
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
        })
        cell.addView(TextView(this).apply {
            text = value
            textSize = 13f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, if (highlight) R.color.accent else R.color.white))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(2)
        })
        parent.addView(cell, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
    }

    private fun showLiveRiderCard(location: InternetNode.RiderLocation) {
        dismissLiveRiderDetail()

        val mine = myLiveLocation
        val self = mine?.riderId == location.riderId
        val distance = if (self) null else mine?.let { distanceMeters(it, location) }
        val peer = internetNode.remotePeers().firstOrNull { it.id == location.riderId }
        val age = System.currentTimeMillis() - location.timestampMs
        val connection = if (self) {
            internetNode.currentConnectionQualityLabel()
        } else if (age >= MAP_OFFLINE_AFTER_MS) {
            "Last known"
        } else {
            peer?.qualityLabel ?: location.connectionQuality
        }

        val dialog = Dialog(this)
        activeRiderDetailDialog = dialog
        activeRiderSheetExpanded = false

        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(14))
            background = GradientDrawable().apply {
                cornerRadii = floatArrayOf(
                    dp(24).toFloat(), dp(24).toFloat(),
                    dp(24).toFloat(), dp(24).toFloat(),
                    0f, 0f, 0f, 0f,
                )
                setColor(Color.parseColor("#FA050909"))
                setStroke(dp(1), Color.parseColor("#30403E"))
            }
        }

        shell.addView(View(this).apply {
            background = GradientDrawable().apply {
                cornerRadius = dp(3).toFloat()
                setColor(Color.parseColor("#7C8A88"))
            }
        }, LinearLayout.LayoutParams(dp(48), dp(4)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            bottomMargin = dp(8)
        })

        val titleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        titleRow.addView(TextView(this).apply {
            text = if (self) "${location.displayName.ifBlank { "YOU" }.uppercase(Locale.ROOT)}  •  YOU" else location.displayName.ifBlank { "RIDER" }.uppercase(Locale.ROOT)
            textSize = 19f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        titleRow.addView(MaterialButton(this).apply {
            text = "✕"
            textSize = 16f
            minWidth = 0
            minimumWidth = 0
            insetTop = 0
            insetBottom = 0
            cornerRadius = dp(20)
            backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.panel2))
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
            setOnClickListener { dismissLiveRiderDetail() }
        }, LinearLayout.LayoutParams(dp(42), dp(42)))
        shell.addView(titleRow)

        val previewStats = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            background = panelCardBackground(highlight = self)
        }
        addRiderSheetStat(previewStats, "Speed", "${location.speedKmh.roundToInt()} km/h", highlight = true)
        addRiderSheetStat(previewStats, "Distance", if (self) "YOU" else distance?.let(::formatMapDistance)?.replace(" from you", "") ?: "GPS…")
        shell.addView(previewStats, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(6)
        })

        val details = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }

        val detailStats = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        addRiderSheetStat(detailStats, "Connection", connection)
        addRiderSheetStat(detailStats, "Last update", if (self) "Now" else formatLastUpdate(location.timestampMs))
        details.addView(detailStats, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(4)
        })

        val phone = normalizeRiderPhone(location.phoneNumber)
        if (phone.isNotBlank()) {
            val phoneCard = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(12), dp(9), dp(12), dp(9))
                background = panelCardBackground()
            }
            phoneCard.addView(TextView(this).apply {
                text = "PHONE (OPTIONAL)"
                textSize = 8f
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
            })
            phoneCard.addView(TextView(this).apply {
                text = phone
                textSize = 14f
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
            })
            details.addView(phoneCard, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(6)
            })
        }

        if (!self) {
            val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            actions.addView(mapActionButton("NAVIGATE") {
                dismissLiveRiderDetail()
                openExternalNavigation(location)
            }, LinearLayout.LayoutParams(0, dp(50), 1f))
            actions.addView(mapActionButton("CALL") {
                dismissLiveRiderDetail()
                showRiderCallOptions(location.phoneNumber)
            }, LinearLayout.LayoutParams(0, dp(50), 1f).apply {
                marginStart = dp(5); marginEnd = dp(5)
            })
            actions.addView(mapActionButton("MESSAGE") {
                dismissLiveRiderDetail()
                showRiderMessageOptions(location.phoneNumber)
            }, LinearLayout.LayoutParams(0, dp(50), 1f))
            details.addView(actions, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)).apply {
                topMargin = dp(7)
            })
        }

        val expandButton = MaterialButton(this).apply {
            text = "VIEW DETAILS  ▲"
            textSize = 10f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            cornerRadius = dp(12)
            strokeWidth = dp(1)
            strokeColor = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.border))
            backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.panel2))
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.accent))
        }

        fun setExpanded(expanded: Boolean) {
            activeRiderSheetExpanded = expanded
            details.visibility = if (expanded) View.VISIBLE else View.GONE
            expandButton.text = if (expanded) "HIDE DETAILS  ▼" else "VIEW DETAILS  ▲"
            scheduleRiderDetailAutoHide()
        }
        expandButton.setOnClickListener { setExpanded(!activeRiderSheetExpanded) }

        shell.addView(details)
        shell.addView(expandButton, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)).apply {
            topMargin = dp(7)
        })
        shell.addView(TextView(this).apply {
            text = "Tap outside or swipe down to close • Auto hides after 10 seconds"
            textSize = 8.5f
            gravity = Gravity.CENTER
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(5)
        })

        var downY = 0f
        shell.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    downY = event.rawY
                    scheduleRiderDetailAutoHide()
                }
                android.view.MotionEvent.ACTION_UP -> {
                    val delta = event.rawY - downY
                    when {
                        delta > dp(72) && activeRiderSheetExpanded -> setExpanded(false)
                        delta > dp(72) -> dismissLiveRiderDetail()
                        delta < -dp(60) && !activeRiderSheetExpanded -> setExpanded(true)
                    }
                }
            }
            false
        }

        dialog.setContentView(shell)
        dialog.setCancelable(true)
        dialog.setCanceledOnTouchOutside(true)
        dialog.setOnDismissListener {
            mainHandler.removeCallbacks(riderDetailAutoHideRunnable)
            if (activeRiderDetailDialog === dialog) activeRiderDetailDialog = null
            activeRiderSheetExpanded = false
        }
        dialog.show()
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            clearFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            setGravity(Gravity.BOTTOM)
            setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        scheduleRiderDetailAutoHide()
    }

    private fun mapActionButton'''
s, count = rider_card_pattern.subn(rider_card_replacement, s, count=1)
if count != 1:
    raise SystemExit(f"showLiveRiderCard replacement count={count}")

# Clean map interaction state when ride ends.
if "riderClusterMarkers.values.forEach" not in s:
    end_anchor = "        riderMapMarkers.clear()\n"
    end_new = "        riderMapMarkers.clear()\n        riderClusterMarkers.values.forEach { it.remove() }\n        riderClusterMarkers.clear()\n        expandedClusterIds = emptySet()\n        dismissLiveRiderDetail()\n"
    if end_anchor in s:
        s = once(s, end_anchor, end_new, "cluster cleanup")

# Constants.
const_anchor = '        private const val MAP_AUTO_FIT_COOLDOWN_MS = 5_000L\n'
const_add = '''        private const val MAP_AUTO_FIT_COOLDOWN_MS = 5_000L\n        private const val MAP_CLUSTER_RADIUS_DP = 88\n        private const val MAP_CLUSTER_EXPAND_TIMEOUT_MS = 10_000L\n        private const val RIDER_DETAIL_AUTO_HIDE_MS = 10_000L\n'''
if "MAP_CLUSTER_RADIUS_DP" not in s[s.rfind("companion object"):]:
    s = once(s, const_anchor, const_add, "map interaction constants")

p.write_text(s)
print("Beta5.4 vc23 smart clusters + temporary three-state rider bottom sheet applied")
