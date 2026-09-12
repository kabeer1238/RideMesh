import AVFoundation
import SwiftUI
import UIKit

struct QRScannerView: UIViewControllerRepresentable {
    let onCode: (String) -> Void

    func makeUIViewController(context: Context) -> ScannerViewController {
        let controller = ScannerViewController()
        controller.onCode = onCode
        return controller
    }

    func updateUIViewController(_ uiViewController: ScannerViewController, context: Context) {}
}

final class ScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onCode: ((String) -> Void)?
    private let session = AVCaptureSession()
    private var preview: AVCaptureVideoPreviewLayer?
    private var didReturnCode = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        requestCameraAndConfigure()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        preview?.frame = view.bounds
    }

    private func requestCameraAndConfigure() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            configureScanner()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async {
                    guard granted else {
                        self?.showCameraUnavailable("Camera permission is required to scan RideMesh QR invites.")
                        return
                    }
                    self?.configureScanner()
                }
            }
        case .denied, .restricted:
            showCameraUnavailable("Camera access is disabled. Enable it in Settings to scan RideMesh QR invites.")
        @unknown default:
            showCameraUnavailable("Camera is unavailable on this device.")
        }
    }

    private func showCameraUnavailable(_ message: String) {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.text = message
        label.textColor = .white
        label.numberOfLines = 0
        label.textAlignment = .center
        label.font = .systemFont(ofSize: 15, weight: .medium)
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 28),
            label.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -28),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
    }

    private func configureScanner() {
        guard let camera = AVCaptureDevice.default(for: .video),
              let input = try? AVCaptureDeviceInput(device: camera),
              session.canAddInput(input) else { return }
        session.addInput(input)

        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else { return }
        session.addOutput(output)
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [.qr]

        let preview = AVCaptureVideoPreviewLayer(session: session)
        preview.videoGravity = .resizeAspectFill
        view.layer.insertSublayer(preview, at: 0)
        self.preview = preview

        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.text = "SCAN RIDEMESH QR"
        label.textColor = UIColor(red: 0, green: 0.898, blue: 0.831, alpha: 1)
        label.font = .systemFont(ofSize: 15, weight: .bold)
        label.textAlignment = .center
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
            label.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20),
            label.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 20)
        ])

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in self?.session.startRunning() }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject], from connection: AVCaptureConnection) {
        guard !didReturnCode,
              let object = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              let value = object.stringValue else { return }
        didReturnCode = true
        session.stopRunning()
        onCode?(value)
    }
}
