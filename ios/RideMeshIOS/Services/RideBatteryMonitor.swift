import Foundation
import UIKit

@MainActor
final class RideBatteryMonitor: ObservableObject {
    @Published private(set) var currentPercent: Int?
    @Published private(set) var startPercent: Int?
    @Published private(set) var elapsedSeconds: TimeInterval = 0
    @Published private(set) var drainPercentPerHour: Double?
    @Published private(set) var lowPowerMode = ProcessInfo.processInfo.isLowPowerModeEnabled

    private var startedAt: Date?
    private var timer: Timer?
    private var tokens: [NSObjectProtocol] = []

    init() {
        UIDevice.current.isBatteryMonitoringEnabled = true
        refreshBattery()
        let center = NotificationCenter.default
        tokens.append(center.addObserver(
            forName: UIDevice.batteryLevelDidChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.refreshBattery() }
        })
        tokens.append(center.addObserver(
            forName: .NSProcessInfoPowerStateDidChange,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.lowPowerMode = ProcessInfo.processInfo.isLowPowerModeEnabled
            }
        })
    }

    deinit {
        timer?.invalidate()
        tokens.forEach(NotificationCenter.default.removeObserver)
    }

    func startSession() {
        refreshBattery()
        startedAt = Date()
        startPercent = currentPercent
        elapsedSeconds = 0
        drainPercentPerHour = nil
        timer?.invalidate()
        // A once-per-minute sample is enough for field diagnostics and avoids
        // turning battery monitoring itself into measurable background work.
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshSession() }
        }
    }

    func stopSession() {
        refreshSession()
        timer?.invalidate()
        timer = nil
    }

    func refreshSession() {
        refreshBattery()
        guard let startedAt else { return }
        elapsedSeconds = Date().timeIntervalSince(startedAt)
        guard elapsedSeconds >= 300,
              let startPercent,
              let currentPercent else {
            drainPercentPerHour = nil
            return
        }
        let drain = max(0, startPercent - currentPercent)
        drainPercentPerHour = Double(drain) / (elapsedSeconds / 3600)
    }

    var currentText: String {
        currentPercent.map { "\($0)%" } ?? "DEVICE TEST"
    }

    var sessionText: String {
        guard elapsedSeconds > 0 else { return "NOT STARTED" }
        let minutes = Int(elapsedSeconds / 60)
        if minutes < 60 { return "\(minutes) MIN" }
        return String(format: "%dH %02dM", minutes / 60, minutes % 60)
    }

    var drainText: String {
        guard let drainPercentPerHour else { return elapsedSeconds >= 300 ? "<1%/HR OR SAMPLING" : "MEASURING" }
        return String(format: "%.1f%%/HR", drainPercentPerHour)
    }

    private func refreshBattery() {
#if targetEnvironment(simulator)
        currentPercent = nil
#else
        let level = UIDevice.current.batteryLevel
        currentPercent = level >= 0 ? Int((level * 100).rounded()) : nil
#endif
    }
}
