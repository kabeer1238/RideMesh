import Combine
import CoreLocation
import MapKit
import SwiftUI
import UIKit

struct LiveRiderMapView: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @State private var now = Date()
    @State private var selectedRiderID: UUID?
    @State private var fitToken = 0
    @State private var lastPanelInteraction = Date()
    @State private var contactSubmenuOpen = false

    private let clock = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    private let panelAutoHideSeconds: TimeInterval = 9

    private var points: [RiderMapPoint] { model.riderMapPoints(now: now) }
    private var selectedRider: RiderMapPoint? { points.first(where: { $0.id == selectedRiderID }) }
    private var missingPositionCount: Int { max(0, model.groupRiderCount - points.count) }
    private var markerDensity: RiderMarkerDensity { RiderMarkerDensity(riderCount: max(model.groupRiderCount, points.count)) }
    private var mapQuality: RiderConnectionQuality {
        points.first(where: { $0.isYou })?.connectionQuality ?? .reconnecting
    }

    var body: some View {
        VStack(spacing: 0) {
            mapHeader

            ZStack(alignment: .bottom) {
                RideMapRepresentable(
                    points: points,
                    selectedID: selectedRiderID,
                    fitToken: fitToken,
                    density: markerDensity,
                    onSelect: selectRider,
                    onMapTap: dismissRiderPanel
                )
                .ignoresSafeArea(edges: .horizontal)

                VStack(spacing: 8) {
                    mapStatusStrip
                    Spacer(minLength: 0)
                    if let selectedRider, !selectedRider.isYou {
                        RiderMapCard(
                            rider: selectedRider,
                            now: now,
                            onClose: dismissRiderPanel,
                            onInteraction: recordPanelInteraction,
                            onMenuStateChanged: { isOpen in
                                contactSubmenuOpen = isOpen
                                if isOpen { recordPanelInteraction() }
                            }
                        )
                        .environmentObject(model)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
                .padding(.horizontal, 12)
                .padding(.top, 10)
                .padding(.bottom, 10)
            }
            .overlay(alignment: .trailing) {
                mapControl(symbol: "scope") {
                    dismissRiderPanel()
                    fitToken += 1
                }
                .padding(.trailing, 12)
                .padding(.top, 78)
                .frame(maxHeight: .infinity, alignment: .top)
            }
        }
        .background(RideMeshBackground())
        .animation(.easeInOut(duration: 0.2), value: selectedRiderID)
        .onReceive(clock) { value in
            now = value
            if let selectedRiderID, !points.contains(where: { $0.id == selectedRiderID }) {
                dismissRiderPanel()
            } else if selectedRiderID != nil,
                      !contactSubmenuOpen,
                      value.timeIntervalSince(lastPanelInteraction) >= panelAutoHideSeconds {
                dismissRiderPanel()
            }
        }
    }

    private func selectRider(_ id: UUID) {
        guard let rider = points.first(where: { $0.id == id }), !rider.isYou else { return }
        selectedRiderID = id
        contactSubmenuOpen = false
        lastPanelInteraction = Date()
    }

    private func dismissRiderPanel() {
        selectedRiderID = nil
        contactSubmenuOpen = false
        lastPanelInteraction = Date()
    }

    private func recordPanelInteraction() {
        lastPanelInteraction = Date()
    }

    private var mapHeader: some View {
        VStack(spacing: 2) {
            Image("RideMeshLogoExact")
                .resizable()
                .scaledToFit()
                .frame(width: 150, height: 36)
                .accessibilityLabel("RideMesh by Autopilot India")

            Text("RIDE MAP")
                .font(RideMeshTheme.condensed(23, weight: .bold))
                .tracking(1.0)
                .foregroundStyle(RideMeshTheme.white)

            HStack(spacing: 6) {
                Circle()
                    .fill(model.isLocationSharing ? RideMeshTheme.green : RideMeshTheme.amber)
                    .frame(width: 7, height: 7)
                Text("Live • \(model.groupRiderCount) Riders")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.whiteSoft)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 7)
        .padding(.bottom, 8)
        .rmPanel(radius: 0, fill: RideMeshTheme.surface, border: RideMeshTheme.border, glassTint: RideMeshTheme.surface.opacity(0.30))
    }

    private var mapStatusStrip: some View {
        HStack(spacing: 10) {
            Image(systemName: model.isLocationSharing ? "antenna.radiowaves.left.and.right" : "location.slash.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(model.isLocationSharing ? RideMeshTheme.green : RideMeshTheme.amber)

            VStack(alignment: .leading, spacing: 2) {
                Text(model.isLocationSharing ? "Location shared with \(model.groupRiderCount) riders" : locationStatusText)
                    .font(.system(size: 10.5, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.white)
                    .lineLimit(1)

                if missingPositionCount > 0 {
                    Text("Waiting for \(missingPositionCount) rider position • Voice has priority")
                        .font(.system(size: 7.5, weight: .semibold))
                        .foregroundStyle(RideMeshTheme.muted)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)
                }
            }

            Spacer(minLength: 4)

            VStack(alignment: .trailing, spacing: 3) {
                Text(mapQualityLabel)
                    .font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(qualityColor(mapQuality))
                QualityBars(quality: mapQuality)
            }
        }
        .padding(.horizontal, 13)
        .frame(minHeight: 52)
        .rmPanel(radius: 17, fill: RideMeshTheme.panel, border: RideMeshTheme.borderStrong, glassTint: RideMeshTheme.panel.opacity(0.36))
    }

    private func mapControl(symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(RideMeshTheme.white)
                .frame(width: 44, height: 44)
                .rmCircleGlass(tint: RideMeshTheme.panel, interactive: true)
        }
        .buttonStyle(.plain)
    }

    private var mapQualityLabel: String {
        switch mapQuality {
        case .excellent: return "Excellent"
        case .good: return "Good"
        case .poor: return "Poor"
        case .reconnecting: return "Reconnecting"
        }
    }

    private func qualityColor(_ quality: RiderConnectionQuality) -> Color {
        switch quality {
        case .excellent: return RideMeshTheme.green
        case .good: return RideMeshTheme.amber
        case .poor, .reconnecting: return RideMeshTheme.danger
        }
    }

    private var locationStatusText: String {
        switch model.location.authorizationStatus {
        case .denied, .restricted: return "Location off • Enable in iOS Settings"
        case .notDetermined: return "Waiting for location permission"
        default: return model.location.currentLocation == nil ? "Acquiring GPS…" : "Location ready"
        }
    }
}

private struct QualityBars: View {
    let quality: RiderConnectionQuality

    var body: some View {
        HStack(alignment: .bottom, spacing: 2) {
            ForEach(0..<4, id: \.self) { index in
                Capsule()
                    .fill(index < quality.bars ? barColor : RideMeshTheme.faint.opacity(0.55))
                    .frame(width: 3, height: CGFloat(4 + index * 3))
            }
        }
        .frame(height: 14, alignment: .bottom)
    }

    private var barColor: Color {
        switch quality {
        case .excellent: return RideMeshTheme.green
        case .good: return RideMeshTheme.amber
        case .poor, .reconnecting: return RideMeshTheme.danger
        }
    }
}

private enum RiderContactSubmenu: Equatable {
    case call
    case message
}

private struct RiderMapCard: View {
    @EnvironmentObject private var model: RideMeshViewModel
    let rider: RiderMapPoint
    let now: Date
    let onClose: () -> Void
    let onInteraction: () -> Void
    let onMenuStateChanged: (Bool) -> Void

    @State private var openSubmenu: RiderContactSubmenu?
    @State private var dragOffset: CGFloat = 0

    var body: some View {
        VStack(spacing: 12) {
            Capsule()
                .fill(RideMeshTheme.faintPlus.opacity(0.65))
                .frame(width: 42, height: 4)
                .padding(.top, -3)

            HStack(spacing: 12) {
                riderBadge

                VStack(alignment: .leading, spacing: 3) {
                    Text(rider.displayName.uppercased())
                        .font(RideMeshTheme.condensed(20, weight: .bold))
                        .foregroundStyle(RideMeshTheme.white)
                        .lineLimit(1)
                    Text(rider.isStale ? "LAST KNOWN POSITION" : statusText)
                        .font(.system(size: 8.5, weight: .bold))
                        .foregroundStyle(statusColor)
                }

                Spacer(minLength: 6)

                Text(lastUpdateText)
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(RideMeshTheme.muted)
                    .multilineTextAlignment(.trailing)
                    .lineLimit(2)
                    .padding(.trailing, 32)
            }

            HStack(spacing: 0) {
                metric(title: "SPEED", value: rider.speedText)
                metricDivider
                metric(title: "DISTANCE", value: compactDistanceText)
                metricDivider
                metric(title: "CONNECTION", value: rider.isStale ? "LAST KNOWN" : statusTitleCase)
                metricDivider
                metric(title: "UPDATE", value: shortLastUpdate)
            }

            if let phone = rider.phoneNumber, !phone.isEmpty {
                HStack(spacing: 9) {
                    Image(systemName: "phone.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(RideMeshTheme.muted)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("PHONE (OPTIONAL)")
                            .font(.system(size: 6.8, weight: .bold))
                            .foregroundStyle(RideMeshTheme.faintPlus)
                        Text(phone)
                            .font(.system(size: 10.5, weight: .semibold))
                            .foregroundStyle(RideMeshTheme.white)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 10)
                .frame(minHeight: 39)
                .rmPanel(radius: 12, fill: RideMeshTheme.panel2, border: RideMeshTheme.borderStrong, glassTint: RideMeshTheme.panel2.opacity(0.30))
                .onTapGesture { onInteraction() }
            }

            HStack(alignment: .top, spacing: 8) {
                VStack(spacing: 6) {
                    action(title: "NAVIGATE", subtitle: "Google Maps", symbol: "location.fill", color: RideMeshTheme.accent) {
                        onInteraction()
                        model.navigateExternally(to: rider)
                    }
                }
                .frame(maxWidth: .infinity)

                VStack(spacing: 6) {
                    menuToggle(
                        title: "CALL",
                        subtitle: hasPhone ? "Choose call type" : "No number",
                        symbol: "phone.fill",
                        color: RideMeshTheme.green,
                        isOpen: openSubmenu == .call
                    ) {
                        toggleSubmenu(.call)
                    }
                    .disabled(!hasPhone)
                    .opacity(hasPhone ? 1 : 0.48)

                    if openSubmenu == .call, hasPhone {
                        contactMenuItem(title: "Call via WhatsApp", symbol: "phone.arrow.up.right.fill", color: RideMeshTheme.green) {
                            openSubmenu = nil
                            onInteraction()
                            model.callRiderViaWhatsApp(rider)
                        }
                        contactMenuItem(title: "Normal Call", symbol: "phone.fill", color: RideMeshTheme.green) {
                            openSubmenu = nil
                            onInteraction()
                            model.callRider(rider)
                        }
                    }
                }
                .frame(maxWidth: .infinity)

                VStack(spacing: 6) {
                    menuToggle(
                        title: "MESSAGE",
                        subtitle: hasPhone ? "Choose message type" : "No number",
                        symbol: "message.fill",
                        color: RideMeshTheme.amber,
                        isOpen: openSubmenu == .message
                    ) {
                        toggleSubmenu(.message)
                    }
                    .disabled(!hasPhone)
                    .opacity(hasPhone ? 1 : 0.48)

                    if openSubmenu == .message, hasPhone {
                        contactMenuItem(title: "Message via WhatsApp", symbol: "message.fill", color: RideMeshTheme.green) {
                            openSubmenu = nil
                            onInteraction()
                            model.messageRiderViaWhatsApp(rider)
                        }
                        contactMenuItem(title: "Normal Message (SMS)", symbol: "text.bubble.fill", color: RideMeshTheme.amber) {
                            openSubmenu = nil
                            onInteraction()
                            model.messageRider(rider)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(14)
        .rmPanel(radius: 22, fill: RideMeshTheme.panel, border: RideMeshTheme.borderStrong, glassTint: RideMeshTheme.panel.opacity(0.42), interactive: true)
        .overlay(alignment: .topTrailing) {
            Button {
                onInteraction()
                onClose()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(RideMeshTheme.white)
                    .frame(width: 32, height: 32)
                    .rmCircleGlass(tint: RideMeshTheme.danger.opacity(0.16), interactive: true)
                    .overlay(Circle().stroke(RideMeshTheme.danger.opacity(0.80), lineWidth: 1))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Close rider details")
            .padding(.top, 10)
            .padding(.trailing, 10)
        }
        .offset(y: dragOffset)
        .simultaneousGesture(
            DragGesture(minimumDistance: 8)
                .onChanged { value in
                    guard value.translation.height > 0 else { return }
                    dragOffset = min(180, value.translation.height)
                    onInteraction()
                }
                .onEnded { value in
                    let shouldDismiss = value.translation.height > 80 || value.predictedEndTranslation.height > 135
                    if shouldDismiss {
                        onClose()
                    } else {
                        withAnimation(.spring(response: 0.28, dampingFraction: 0.86)) {
                            dragOffset = 0
                        }
                        onInteraction()
                    }
                }
        )
        .onTapGesture { onInteraction() }
        .onChange(of: openSubmenu) { value in
            onMenuStateChanged(value != nil)
        }
        .onChange(of: rider.id) { _ in
            openSubmenu = nil
            dragOffset = 0
            onMenuStateChanged(false)
            onInteraction()
        }
        .onDisappear { onMenuStateChanged(false) }
    }

    private func toggleSubmenu(_ menu: RiderContactSubmenu) {
        onInteraction()
        withAnimation(.easeInOut(duration: 0.16)) {
            openSubmenu = openSubmenu == menu ? nil : menu
        }
    }

    private var riderBadge: some View {
        ZStack {
            Circle()
                .fill(RideMeshTheme.surface)
                .overlay(Circle().stroke(statusColor, lineWidth: 2))
            Image(systemName: "figure.outdoor.cycle")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(RideMeshTheme.white)
        }
        .frame(width: 52, height: 52)
    }

    private var metricDivider: some View {
        Rectangle()
            .fill(RideMeshTheme.borderStrong)
            .frame(width: 1, height: 38)
    }

    private func metric(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 7, weight: .bold))
                .foregroundStyle(RideMeshTheme.faintPlus)
            Text(value)
                .font(.system(size: 9.5, weight: .bold))
                .foregroundStyle(RideMeshTheme.white)
                .lineLimit(1)
                .minimumScaleFactor(0.58)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 7)
    }

    private func action(title: String, subtitle: String, symbol: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            actionLabel(title: title, subtitle: subtitle, symbol: symbol, color: color, trailingSymbol: nil)
        }
        .buttonStyle(.plain)
    }

    private func menuToggle(title: String, subtitle: String, symbol: String, color: Color, isOpen: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            actionLabel(
                title: title,
                subtitle: subtitle,
                symbol: symbol,
                color: color,
                trailingSymbol: isOpen ? "chevron.up" : "chevron.down"
            )
        }
        .buttonStyle(.plain)
    }

    private func actionLabel(title: String, subtitle: String, symbol: String, color: Color, trailingSymbol: String?) -> some View {
        HStack(spacing: 7) {
            Image(systemName: symbol)
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(color)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 8.5, weight: .bold))
                    .foregroundStyle(RideMeshTheme.white)
                Text(subtitle)
                    .font(.system(size: 6.5, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.muted)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            Spacer(minLength: 0)
            if let trailingSymbol {
                Image(systemName: trailingSymbol)
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(RideMeshTheme.faintPlus)
            }
        }
        .padding(.horizontal, 8)
        .frame(maxWidth: .infinity, minHeight: 46)
        .rmPanel(radius: 13, fill: RideMeshTheme.panel2, border: RideMeshTheme.borderStrong, glassTint: RideMeshTheme.panel2.opacity(0.28), interactive: true)
    }

    private func contactMenuItem(title: String, symbol: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Image(systemName: symbol)
                    .font(.system(size: 10.5, weight: .bold))
                    .foregroundStyle(color)
                Text(title)
                    .font(.system(size: 7.2, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.whiteSoft)
                    .lineLimit(2)
                    .minimumScaleFactor(0.72)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, minHeight: 34)
            .rmPanel(radius: 11, fill: RideMeshTheme.surface, border: RideMeshTheme.borderStrong, glassTint: RideMeshTheme.surface.opacity(0.30), interactive: true)
        }
        .buttonStyle(.plain)
    }

    private var hasPhone: Bool {
        guard let phone = rider.phoneNumber else { return false }
        return !phone.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var compactDistanceText: String {
        rider.distanceText.replacingOccurrences(of: " from you", with: "")
    }

    private var statusText: String { statusTitleCase }

    private var statusTitleCase: String {
        switch rider.connectionQuality {
        case .excellent: return "Excellent"
        case .good: return "Good"
        case .poor: return "Poor"
        case .reconnecting: return "Reconnecting"
        }
    }

    private var statusColor: Color {
        if rider.isStale { return RideMeshTheme.muted }
        switch rider.connectionQuality {
        case .excellent: return RideMeshTheme.green
        case .good: return RideMeshTheme.amber
        case .poor, .reconnecting: return RideMeshTheme.danger
        }
    }

    private var lastUpdateText: String {
        let seconds = max(0, Int(now.timeIntervalSince(rider.timestamp)))
        if seconds <= 2 { return "LAST UPDATE\nNOW" }
        if seconds < 60 { return "LAST SEEN\n\(seconds) SEC AGO" }
        return "LAST SEEN\n\(seconds / 60) MIN AGO"
    }

    private var shortLastUpdate: String {
        let seconds = max(0, Int(now.timeIntervalSince(rider.timestamp)))
        if seconds <= 2 { return "Now" }
        if seconds < 60 { return "\(seconds)s ago" }
        return "\(seconds / 60)m ago"
    }
}

private enum RiderMarkerDensity {
    case roomy
    case compact
    case dense

    init(riderCount: Int) {
        switch riderCount {
        case ...6: self = .roomy
        case 7...10: self = .compact
        default: self = .dense
        }
    }

    var remoteSize: CGSize {
        switch self {
        case .roomy: return CGSize(width: 84, height: 34)
        case .compact: return CGSize(width: 74, height: 30)
        case .dense: return CGSize(width: 64, height: 27)
        }
    }

    var nameSize: CGFloat {
        switch self {
        case .roomy: return 8.6
        case .compact: return 7.7
        case .dense: return 6.9
        }
    }

    var detailSize: CGFloat {
        switch self {
        case .roomy: return 6.8
        case .compact: return 6.2
        case .dense: return 5.7
        }
    }
}

private struct RideMapRepresentable: UIViewRepresentable {
    let points: [RiderMapPoint]
    let selectedID: UUID?
    let fitToken: Int
    let density: RiderMarkerDensity
    let onSelect: (UUID) -> Void
    let onMapTap: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView(frame: .zero)
        map.delegate = context.coordinator
        map.overrideUserInterfaceStyle = .dark
        map.mapType = .standard
        map.showsCompass = false
        map.showsScale = false
        map.showsTraffic = false
        map.pointOfInterestFilter = .excludingAll
        map.isPitchEnabled = false
        map.register(RiderMapAnnotationView.self, forAnnotationViewWithReuseIdentifier: RiderMapAnnotationView.reuseID)
        map.register(RiderClusterAnnotationView.self, forAnnotationViewWithReuseIdentifier: RiderClusterAnnotationView.reuseID)

        let tap = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handleMapTap(_:)))
        tap.cancelsTouchesInView = false
        map.addGestureRecognizer(tap)
        return map
    }

    func updateUIView(_ map: MKMapView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.syncAnnotations(on: map)

        let incomingIDs = Set(points.map(\.id))
        let idsChanged = incomingIDs != context.coordinator.lastIDs
        let manualFit = context.coordinator.lastFitToken != fitToken
        let allCoordinates = context.coordinator.visibleCoordinates
        let allVisible = allCoordinates.allSatisfy { map.visibleMapRect.contains(MKMapPoint($0)) }
        let groupDriftedOutside = !allVisible && Date().timeIntervalSince(context.coordinator.lastAutoFitAt) > 8

        if idsChanged || manualFit || groupDriftedOutside {
            context.coordinator.lastIDs = incomingIDs
            context.coordinator.lastFitToken = fitToken
            context.coordinator.lastAutoFitAt = Date()
            context.coordinator.fit(map)
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var parent: RideMapRepresentable
        var lastIDs = Set<UUID>()
        var lastFitToken = -1
        var lastAutoFitAt = Date.distantPast
        var expandedClusterID: String?
        var collapseWorkItem: DispatchWorkItem?
        var programmaticMoveUntil = Date.distantPast
        var visibleCoordinates: [CLLocationCoordinate2D] = []

        init(parent: RideMapRepresentable) { self.parent = parent }

        func syncAnnotations(on map: MKMapView) {
            let groups = clusterGroups(from: parent.points)
            var annotations: [MKAnnotation] = []
            var coords: [CLLocationCoordinate2D] = []

            if let you = parent.points.first(where: { $0.isYou }) {
                let annotation = RiderMapAnnotation(point: you)
                annotations.append(annotation)
                coords.append(annotation.coordinate)
            }

            var expandedStillExists = false
            for group in groups {
                if group.members.count > 1 {
                    if expandedClusterID == group.id {
                        expandedStillExists = true
                        for (index, point) in group.members.enumerated() {
                            let annotation = RiderMapAnnotation(point: point, expandedIndex: index, expandedCount: group.members.count)
                            annotations.append(annotation)
                            coords.append(annotation.coordinate)
                        }
                    } else {
                        let annotation = RiderClusterAnnotation(group: group)
                        annotations.append(annotation)
                        coords.append(annotation.coordinate)
                    }
                } else if let point = group.members.first {
                    let annotation = RiderMapAnnotation(point: point)
                    annotations.append(annotation)
                    coords.append(annotation.coordinate)
                }
            }

            if expandedClusterID != nil && !expandedStillExists {
                expandedClusterID = nil
                collapseWorkItem?.cancel()
                collapseWorkItem = nil
            }

            let old = map.annotations.filter { !($0 is MKUserLocation) }
            map.removeAnnotations(old)
            map.addAnnotations(annotations)
            visibleCoordinates = coords
        }

        private func clusterGroups(from points: [RiderMapPoint]) -> [RiderMapClusterGroup] {
            var remaining = points.filter { !$0.isYou }
            var result: [RiderMapClusterGroup] = []

            while let seed = remaining.first {
                remaining.removeFirst()
                var members = [seed]
                var changed = true

                while changed {
                    changed = false
                    var retained: [RiderMapPoint] = []
                    for candidate in remaining {
                        let isNear = members.contains { member in
                            locationDistance(member, candidate) <= 8.0
                        }
                        if isNear {
                            members.append(candidate)
                            changed = true
                        } else {
                            retained.append(candidate)
                        }
                    }
                    remaining = retained
                }

                result.append(RiderMapClusterGroup(members: members))
            }

            return result
        }

        private func locationDistance(_ a: RiderMapPoint, _ b: RiderMapPoint) -> CLLocationDistance {
            CLLocation(latitude: a.latitude, longitude: a.longitude)
                .distance(from: CLLocation(latitude: b.latitude, longitude: b.longitude))
        }

        func fit(_ map: MKMapView) {
            guard !visibleCoordinates.isEmpty else { return }
            programmaticMoveUntil = Date().addingTimeInterval(0.8)

            if visibleCoordinates.count == 1, let coordinate = visibleCoordinates.first {
                let region = MKCoordinateRegion(center: coordinate, latitudinalMeters: 1800, longitudinalMeters: 1800)
                map.setRegion(region, animated: true)
                return
            }

            var rect = MKMapRect.null
            for coordinate in visibleCoordinates {
                let point = MKMapPoint(coordinate)
                let tiny = MKMapRect(x: point.x, y: point.y, width: 1, height: 1)
                rect = rect.isNull ? tiny : rect.union(tiny)
            }

            map.setVisibleMapRect(
                rect,
                edgePadding: UIEdgeInsets(
                    top: 92,
                    left: 42,
                    bottom: parent.selectedID == nil ? 70 : 310,
                    right: 42
                ),
                animated: true
            )
        }

        @objc func handleMapTap(_ gesture: UITapGestureRecognizer) {
            guard gesture.state == .ended, let map = gesture.view as? MKMapView else { return }
            let location = gesture.location(in: map)
            var hit: UIView? = map.hitTest(location, with: nil)
            while let view = hit {
                if view is MKAnnotationView { return }
                hit = view.superview
                if hit === map { break }
            }
            parent.onMapTap()
            map.selectedAnnotations.forEach { map.deselectAnnotation($0, animated: false) }
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if let annotation = annotation as? RiderMapAnnotation {
                let view = mapView.dequeueReusableAnnotationView(withIdentifier: RiderMapAnnotationView.reuseID, for: annotation) as! RiderMapAnnotationView
                view.annotation = annotation
                view.apply(
                    point: annotation.point,
                    selected: parent.selectedID == annotation.point.id,
                    density: parent.density,
                    expandedIndex: annotation.expandedIndex,
                    expandedCount: annotation.expandedCount
                )
                return view
            }

            if let cluster = annotation as? RiderClusterAnnotation {
                let view = mapView.dequeueReusableAnnotationView(withIdentifier: RiderClusterAnnotationView.reuseID, for: cluster) as! RiderClusterAnnotationView
                view.annotation = cluster
                view.apply(count: cluster.group.members.count)
                return view
            }

            return nil
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            if let cluster = view.annotation as? RiderClusterAnnotation {
                expand(cluster: cluster, on: mapView)
                return
            }

            guard let annotation = view.annotation as? RiderMapAnnotation else { return }
            if annotation.point.isYou {
                mapView.deselectAnnotation(annotation, animated: false)
                return
            }
            parent.onSelect(annotation.point.id)
            if let riderView = view as? RiderMapAnnotationView {
                riderView.apply(
                    point: annotation.point,
                    selected: true,
                    density: parent.density,
                    expandedIndex: annotation.expandedIndex,
                    expandedCount: annotation.expandedCount
                )
            }
        }

        func mapView(_ mapView: MKMapView, didDeselect view: MKAnnotationView) {
            guard let annotation = view.annotation as? RiderMapAnnotation,
                  let riderView = view as? RiderMapAnnotationView else { return }
            riderView.apply(
                point: annotation.point,
                selected: false,
                density: parent.density,
                expandedIndex: annotation.expandedIndex,
                expandedCount: annotation.expandedCount
            )
        }

        func mapView(_ mapView: MKMapView, regionWillChangeAnimated animated: Bool) {
            guard Date() >= programmaticMoveUntil else { return }
            if expandedClusterID != nil {
                collapseExpandedCluster(on: mapView)
            }
        }

        private func expand(cluster: RiderClusterAnnotation, on map: MKMapView) {
            expandedClusterID = cluster.group.id
            collapseWorkItem?.cancel()
            parent.onMapTap()
            syncAnnotations(on: map)

            let work = DispatchWorkItem { [weak self, weak map] in
                guard let self, let map else { return }
                self.collapseExpandedCluster(on: map)
            }
            collapseWorkItem = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 5, execute: work)
        }

        private func collapseExpandedCluster(on map: MKMapView) {
            guard expandedClusterID != nil else { return }
            expandedClusterID = nil
            collapseWorkItem?.cancel()
            collapseWorkItem = nil
            syncAnnotations(on: map)
        }
    }
}

private struct RiderMapClusterGroup {
    let members: [RiderMapPoint]

    var id: String {
        members.map { $0.id.uuidString }.sorted().joined(separator: "|")
    }

    var coordinate: CLLocationCoordinate2D {
        guard !members.isEmpty else { return CLLocationCoordinate2D(latitude: 0, longitude: 0) }
        let lat = members.reduce(0) { $0 + $1.latitude } / Double(members.count)
        let lon = members.reduce(0) { $0 + $1.longitude } / Double(members.count)
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }
}

private final class RiderClusterAnnotation: NSObject, MKAnnotation {
    let group: RiderMapClusterGroup
    @objc dynamic var coordinate: CLLocationCoordinate2D

    init(group: RiderMapClusterGroup) {
        self.group = group
        self.coordinate = group.coordinate
        super.init()
    }
}

private final class RiderClusterAnnotationView: MKAnnotationView {
    static let reuseID = "RideMeshRiderClusterAnnotation"

    private let circle = UIView()
    private let countLabel = UILabel()
    private let caption = UILabel()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        canShowCallout = false
        displayPriority = .required
        collisionMode = .circle

        circle.backgroundColor = UIColor(red: 0.02, green: 0.08, blue: 0.09, alpha: 0.97)
        circle.layer.borderWidth = 2
        circle.layer.borderColor = UIColor(red: 0, green: 0.90, blue: 0.83, alpha: 1).cgColor
        addSubview(circle)

        countLabel.textAlignment = .center
        countLabel.font = .systemFont(ofSize: 15, weight: .bold)
        countLabel.textColor = .white
        circle.addSubview(countLabel)

        caption.textAlignment = .center
        caption.font = .systemFont(ofSize: 7.5, weight: .bold)
        caption.textColor = .white
        caption.backgroundColor = UIColor(red: 0.01, green: 0.18, blue: 0.20, alpha: 0.96)
        caption.layer.cornerRadius = 7
        caption.clipsToBounds = true
        addSubview(caption)
    }

    required init?(coder: NSCoder) { nil }

    func apply(count: Int) {
        frame = CGRect(x: 0, y: 0, width: 64, height: 58)
        centerOffset = CGPoint(x: 0, y: -24)
        circle.frame = CGRect(x: 12, y: 0, width: 40, height: 40)
        circle.layer.cornerRadius = 20
        countLabel.frame = circle.bounds
        countLabel.text = "\(count)"
        caption.frame = CGRect(x: 7, y: 42, width: 50, height: 14)
        caption.text = "\(count) RIDERS"
    }
}

private final class RiderMapAnnotation: NSObject, MKAnnotation {
    var point: RiderMapPoint
    let expandedIndex: Int?
    let expandedCount: Int
    @objc dynamic var coordinate: CLLocationCoordinate2D

    init(point: RiderMapPoint, expandedIndex: Int? = nil, expandedCount: Int = 1) {
        self.point = point
        self.expandedIndex = expandedIndex
        self.expandedCount = expandedCount
        self.coordinate = CLLocationCoordinate2D(latitude: point.latitude, longitude: point.longitude)
        super.init()
    }
}

private final class RiderMapAnnotationView: MKAnnotationView {
    static let reuseID = "RideMeshCompactRiderMapAnnotation"

    private let card = UIView()
    private let directionRing = UIView()
    private let direction = UIImageView(image: UIImage(systemName: "location.north.fill"))
    private let nameLabel = UILabel()
    private let detailLabel = UILabel()
    private let statusDot = UIView()
    private let youBadge = UILabel()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        canShowCallout = false
        displayPriority = .required
        collisionMode = .circle

        card.layer.cornerRadius = 10
        card.layer.borderWidth = 1
        card.backgroundColor = UIColor(red: 0.035, green: 0.055, blue: 0.052, alpha: 0.94)
        addSubview(card)

        directionRing.layer.cornerRadius = 14
        directionRing.backgroundColor = UIColor(red: 0.03, green: 0.07, blue: 0.07, alpha: 0.98)
        directionRing.layer.borderWidth = 1.5
        card.addSubview(directionRing)

        direction.contentMode = .scaleAspectFit
        directionRing.addSubview(direction)

        nameLabel.font = .systemFont(ofSize: 9.5, weight: .bold)
        nameLabel.textColor = .white
        nameLabel.adjustsFontSizeToFitWidth = true
        nameLabel.minimumScaleFactor = 0.58
        card.addSubview(nameLabel)

        detailLabel.font = .systemFont(ofSize: 7.4, weight: .semibold)
        detailLabel.textColor = UIColor(white: 0.78, alpha: 1)
        detailLabel.adjustsFontSizeToFitWidth = true
        detailLabel.minimumScaleFactor = 0.62
        card.addSubview(detailLabel)

        statusDot.layer.cornerRadius = 3
        card.addSubview(statusDot)

        youBadge.text = "YOU"
        youBadge.font = .systemFont(ofSize: 8.5, weight: .bold)
        youBadge.textAlignment = .center
        youBadge.textColor = .white
        youBadge.backgroundColor = UIColor.systemBlue
        youBadge.layer.cornerRadius = 7
        youBadge.clipsToBounds = true
        addSubview(youBadge)
    }

    required init?(coder: NSCoder) { nil }

    func apply(
        point: RiderMapPoint,
        selected: Bool,
        density: RiderMarkerDensity,
        expandedIndex: Int? = nil,
        expandedCount: Int = 1
    ) {
        let color = markerColor(point: point, selected: selected)

        if point.isYou {
            applyYou(point: point, color: color)
        } else {
            applyRemote(
                point: point,
                selected: selected,
                color: color,
                density: density,
                expandedIndex: expandedIndex,
                expandedCount: expandedCount
            )
        }
    }

    private func applyYou(point: RiderMapPoint, color: UIColor) {
        let size = CGSize(width: 58, height: 70)
        frame = CGRect(origin: .zero, size: size)
        centerOffset = CGPoint(x: 0, y: -28)

        card.isHidden = false
        nameLabel.isHidden = true
        detailLabel.isHidden = true
        statusDot.isHidden = true
        youBadge.isHidden = false

        card.frame = CGRect(x: 7, y: 0, width: 44, height: 44)
        card.layer.cornerRadius = 22
        card.layer.borderColor = color.cgColor
        card.layer.borderWidth = 2
        card.backgroundColor = UIColor(red: 0.02, green: 0.09, blue: 0.13, alpha: 0.96)

        directionRing.frame = card.bounds.insetBy(dx: 6, dy: 6)
        directionRing.layer.cornerRadius = 16
        directionRing.layer.borderWidth = 0
        directionRing.backgroundColor = .clear
        direction.frame = directionRing.bounds.insetBy(dx: 5, dy: 4)
        direction.tintColor = color
        direction.transform = CGAffineTransform(rotationAngle: CGFloat(point.heading * .pi / 180))

        youBadge.frame = CGRect(x: 10, y: 48, width: 38, height: 15)
        transform = .identity
    }

    private func applyRemote(
        point: RiderMapPoint,
        selected: Bool,
        color: UIColor,
        density: RiderMarkerDensity,
        expandedIndex: Int?,
        expandedCount: Int
    ) {
        let base = density.remoteSize
        let size = selected ? CGSize(width: base.width + 8, height: base.height + 4) : base
        frame = CGRect(origin: .zero, size: size)

        if let expandedIndex, expandedCount > 1 {
            let angle = (2 * CGFloat.pi * CGFloat(expandedIndex) / CGFloat(expandedCount)) - (.pi / 2)
            let radius = min(CGFloat(115), CGFloat(52 + min(expandedCount, 10) * 6))
            centerOffset = CGPoint(
                x: cos(angle) * radius,
                y: sin(angle) * radius - size.height * 0.48
            )
        } else {
            centerOffset = CGPoint(x: 0, y: -size.height * 0.48)
        }

        card.isHidden = false
        nameLabel.isHidden = false
        detailLabel.isHidden = false
        statusDot.isHidden = false
        youBadge.isHidden = true

        card.frame = bounds
        card.layer.cornerRadius = selected ? 10 : 8
        card.layer.borderColor = color.cgColor
        card.layer.borderWidth = selected ? 2 : 1
        card.backgroundColor = UIColor(red: 0.035, green: 0.055, blue: 0.052, alpha: selected ? 0.98 : 0.93)

        let iconSide = max(16, min(23, size.height - 9))
        directionRing.frame = CGRect(x: 5, y: (size.height - iconSide) / 2, width: iconSide, height: iconSide)
        directionRing.layer.cornerRadius = iconSide / 2
        directionRing.layer.borderColor = color.cgColor
        directionRing.layer.borderWidth = 1.15
        directionRing.backgroundColor = UIColor(red: 0.02, green: 0.07, blue: 0.07, alpha: 0.98)
        direction.frame = directionRing.bounds.insetBy(dx: 4.5, dy: 4)
        direction.tintColor = color
        direction.transform = CGAffineTransform(rotationAngle: CGFloat(point.heading * .pi / 180))

        let textX = directionRing.frame.maxX + 5
        let rightPadding: CGFloat = 5
        let textWidth = max(35, size.width - textX - rightPadding)

        nameLabel.font = .systemFont(ofSize: selected ? density.nameSize + 0.8 : density.nameSize, weight: .bold)
        nameLabel.frame = CGRect(x: textX, y: 4, width: textWidth, height: 12)
        nameLabel.text = point.displayName.uppercased()

        detailLabel.font = .systemFont(ofSize: selected ? density.detailSize + 0.5 : density.detailSize, weight: .semibold)
        detailLabel.frame = CGRect(x: textX, y: size.height - 15, width: textWidth, height: 11)
        detailLabel.text = "\(point.speedText) • \(compactDistance(point))"
        detailLabel.textColor = point.isStale ? UIColor(white: 0.56, alpha: 1) : UIColor(white: 0.82, alpha: 1)

        statusDot.layer.cornerRadius = 2
        statusDot.frame = CGRect(x: size.width - 7, y: 4, width: 4, height: 4)
        statusDot.backgroundColor = color

        transform = .identity
    }

    private func compactDistance(_ point: RiderMapPoint) -> String {
        guard let distance = point.distanceMeters else { return "—" }
        if distance < 1000 { return "\(Int(distance.rounded()))m" }
        return String(format: "%.1fkm", distance / 1000)
    }

    private func markerColor(point: RiderMapPoint, selected: Bool) -> UIColor {
        if selected || point.isYou { return UIColor(red: 0, green: 0.898, blue: 0.831, alpha: 1) }
        if point.isStale { return UIColor(white: 0.48, alpha: 1) }
        switch point.connectionQuality {
        case .excellent: return UIColor(red: 0.24, green: 0.86, blue: 0.52, alpha: 1)
        case .good: return UIColor(red: 1.0, green: 0.70, blue: 0.0, alpha: 1)
        case .poor, .reconnecting: return UIColor(red: 1, green: 0.28, blue: 0.34, alpha: 1)
        }
    }
}
