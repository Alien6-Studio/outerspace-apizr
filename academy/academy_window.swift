// Native source input for the optional, manually authorized Academy recorder.
// Never capture a display or fall back to an ordinary editor window.
import AppKit
import CoreGraphics
import Foundation
import ScreenCaptureKit

struct Candidate: Codable {
    let id: UInt32
    let pid: Int32
    let title: String
    let bundle: String
}
struct Receipt: Codable {
    let window: Candidate
    let preview: String
    let width: Int
    let height: Int
    let desktopIncluded: Bool
}
struct Failure: Error { let reason: String }
func select(_ windows: [Candidate], id: UInt32?, pid: Int32?) throws -> Candidate {
    let matching = windows.filter { $0.bundle == "com.microsoft.VSCode" && $0.title.hasPrefix("Apizr Academy XII") }
    guard matching.count == 1 else { throw Failure(reason: "Missing or ambiguous Academy window; refusing capture") }
    let window = matching[0]
    guard (id == nil || id == window.id) && (pid == nil || pid == window.pid) else {
        throw Failure(reason: "Window identity changed; refusing capture")
    }
    return window
}
func json<T: Encodable>(_ value: T, to path: String) throws {
    let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(value).write(to: URL(fileURLWithPath: path), options: .atomic)
}
final class Finished: NSObject, SCRecordingOutputDelegate {
    private let lock = NSLock()
    private var done = false
    private var failure: Error?
    func recordingOutputDidFinishRecording(_ recordingOutput: SCRecordingOutput) {
        lock.lock(); done = true; lock.unlock()
    }
    func recordingOutput(_ recordingOutput: SCRecordingOutput, didFailWithError error: Error) {
        lock.lock(); failure = error; done = true; lock.unlock()
    }
    func state() -> (Bool, Error?) { lock.lock(); defer { lock.unlock() }; return (done, failure) }
}
@main @MainActor struct Capture {
    static func main() async {
        do { try await run() }
        catch { fputs("Capture refused: \(error)\n", stderr); exit(1) }
    }
    static func run() async throws {
        let arguments = Array(CommandLine.arguments.dropFirst())
        if arguments == ["--self-test"] {
            let academy = Candidate(id: 2, pid: 3, title: "Apizr Academy XII — example.py", bundle: "com.microsoft.VSCode")
            let ordinary = Candidate(id: 4, pid: 5, title: "outerspace-apizr", bundle: "com.microsoft.VSCode")
            let admitted = try select([academy, ordinary], id: 2, pid: 3)
            assert(admitted.id == 2)
            for (windows, id, pid) in [([ordinary], UInt32(2), Int32(3)), ([academy, academy], 2, 3), ([academy], 4, 3), ([academy], 2, 5)] {
                do { _ = try select(windows, id: id, pid: pid); throw Failure(reason: "Invalid window admitted") }
                catch let error as Failure { assert(error.reason != "Invalid window admitted") }
            }
            print("PASS exact Academy selection; missing/ambiguous/changed identities refused; no display fallback")
            return
        }
        _ = NSApplication.shared
        if arguments == ["--request-access"] {
            print(CGRequestScreenCaptureAccess() ? "Screen capture permission available" : "Screen capture permission must be granted in macOS")
            return
        }
        guard CGPreflightScreenCaptureAccess() else { throw Failure(reason: "macOS screen recording permission is unavailable; no capture attempted") }
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
        let candidates = content.windows.map { Candidate(id: $0.windowID, pid: $0.owningApplication?.processID ?? -1, title: $0.title ?? "", bundle: $0.owningApplication?.bundleIdentifier ?? "") }
        let selected = try select(candidates, id: nil, pid: nil)
        if arguments == ["--inventory"] {
            let encoder = JSONEncoder()
            print(String(decoding: try encoder.encode(selected), as: UTF8.self))
            return
        }
        guard arguments.count == 2, ["--preview", "--record"].contains(arguments[0]) else { throw Failure(reason: "Use --preview OUTPUT or --record RECEIPT") }
        guard let window = content.windows.first(where: { $0.windowID == selected.id }) else { throw Failure(reason: "Selected window disappeared") }
        NSRunningApplication(processIdentifier: selected.pid)?.activate()
        try await Task.sleep(nanoseconds: 700_000_000)
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let config = SCStreamConfiguration()
        config.width = Int(window.frame.width * 2)
        config.height = Int(window.frame.height * 2)
        config.showsCursor = true
        config.capturesAudio = false
        config.captureMicrophone = false
        config.includeChildWindows = false
        config.ignoreShadowsSingleWindow = true
        config.minimumFrameInterval = CMTime(value: 1, timescale: 24)
        if arguments[0] == "--preview" {
            let path = arguments[1]
            guard !FileManager.default.fileExists(atPath: path) else { throw Failure(reason: "Preview already exists") }
            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
            guard let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else { throw Failure(reason: "No preview image") }
            try data.write(to: URL(fileURLWithPath: path), options: .atomic)
            try json(Receipt(window: selected, preview: path, width: config.width, height: config.height, desktopIncluded: false), to: path + ".json")
            print("Academy-only preview ready: \(path)")
            return
        }
        let receipt = try JSONDecoder().decode(Receipt.self, from: Data(contentsOf: URL(fileURLWithPath: arguments[1])))
        _ = try select(candidates, id: receipt.window.id, pid: receipt.window.pid)
        guard !receipt.desktopIncluded, FileManager.default.fileExists(atPath: receipt.preview) else { throw Failure(reason: "Missing verified preview") }
        let output = receipt.preview + ".mov"
        guard !FileManager.default.fileExists(atPath: output) else { throw Failure(reason: "Recording already exists") }
        let recordingConfig = SCRecordingOutputConfiguration()
        recordingConfig.outputURL = URL(fileURLWithPath: output)
        recordingConfig.videoCodecType = .h264
        recordingConfig.outputFileType = .mov
        let finished = Finished()
        let recording = SCRecordingOutput(configuration: recordingConfig, delegate: finished)
        let stream = SCStream(filter: filter, configuration: config, delegate: nil)
        try stream.addRecordingOutput(recording)
        try await stream.startCapture()
        print("Recording only window \(selected.id), PID \(selected.pid)")
        fflush(stdout)
        // Explicit file signal is supplied by the owned qualification driver.
        let stop = receipt.preview + ".stop"
        let deadline = Date().addingTimeInterval(180)
        while !FileManager.default.fileExists(atPath: stop), Date() < deadline {
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        try await stream.stopCapture()
        for _ in 0..<100 {
            let state = finished.state()
            if let error = state.1 { throw error }
            if state.0 { print("Academy-only recording saved: \(output)"); return }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        throw Failure(reason: "Recording did not finalize")
    }
}
