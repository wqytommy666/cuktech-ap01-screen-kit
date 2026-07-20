import SwiftUI
import AppKit
import Foundation
import UniformTypeIdentifiers

private func bundledSetting(_ key: String, fallback: String) -> String {
    if let value = Bundle.main.object(forInfoDictionaryKey: key) as? String, !value.isEmpty {
        return value
    }
    return fallback
}

private let projectRoot = URL(fileURLWithPath: bundledSetting(
    "CUKTECHRuntimePath",
    fallback: FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/CUKTECH Screen Controller/runtime").path
))
private let artifacts = projectRoot.appendingPathComponent("artifacts")
private let modeFile = artifacts.appendingPathComponent("ap01-mode")
private let customGIF = artifacts.appendingPathComponent("custom-screen.gif")
private let quotaGIF = artifacts.appendingPathComponent("quota-dashboard.gif")
private let otaURLFile = artifacts.appendingPathComponent("ap01-ota-url.txt")
private let launchLabel = bundledSetting(
    "CUKTECHLaunchLabel",
    fallback: "io.github.wqytommy666.cuktech-screen-controller.bridge"
)
private let otaGuideURL = URL(string: "https://github.com/wqytommy666/cuktech-screen-controller/blob/main/docs/AP01_FDS_NO_GATEWAY_SOLUTION.zh-CN.md")!

private func runProcess(_ executable: String, _ arguments: [String]) throws -> String {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.standardOutput = pipe
    process.standardError = pipe
    try process.run()
    process.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    let output = String(data: data, encoding: .utf8) ?? ""
    if process.terminationStatus != 0 {
        throw NSError(domain: "AP01Controller", code: Int(process.terminationStatus), userInfo: [NSLocalizedDescriptionKey: output])
    }
    return output
}

private func redactedNetworkText(_ text: String) -> String {
    guard let expression = try? NSRegularExpression(pattern: #"https?://[^\s]+"#) else { return text }
    var result = text
    let range = NSRange(result.startIndex..., in: result)
    for match in expression.matches(in: result, range: range).reversed() {
        guard let swiftRange = Range(match.range, in: result) else { continue }
        let raw = String(result[swiftRange])
        if var components = URLComponents(string: raw), components.query != nil {
            components.query = nil
            components.fragment = nil
            result.replaceSubrange(swiftRange, with: (components.string ?? raw) + "?••••")
        }
    }
    return result
}

final class StreamingProcessRunner {
    private var process: Process?
    private var outputPipe: Pipe?

    var isRunning: Bool { process?.isRunning ?? false }

    func run(
        executable: String,
        arguments: [String],
        onOutput: @escaping (String) -> Void,
        completion: @escaping (Result<Int32, Error>) -> Void
    ) throws {
        guard process == nil else {
            throw NSError(domain: "AP01Controller", code: 1, userInfo: [NSLocalizedDescriptionKey: "已有部署任务正在运行"])
        }

        let task = Process()
        let pipe = Pipe()
        task.executableURL = URL(fileURLWithPath: executable)
        task.arguments = arguments
        task.standardOutput = pipe
        task.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            onOutput(text)
        }

        task.terminationHandler = { [weak self] finished in
            pipe.fileHandleForReading.readabilityHandler = nil
            let remaining = pipe.fileHandleForReading.readDataToEndOfFile()
            if !remaining.isEmpty, let text = String(data: remaining, encoding: .utf8) {
                onOutput(text)
            }
            DispatchQueue.main.async {
                self?.process = nil
                self?.outputPipe = nil
                if finished.terminationStatus == 0 {
                    completion(.success(finished.terminationStatus))
                } else {
                    completion(.failure(NSError(
                        domain: "AP01Controller",
                        code: Int(finished.terminationStatus),
                        userInfo: [NSLocalizedDescriptionKey: "命令退出码 \(finished.terminationStatus)"]
                    )))
                }
            }
        }

        process = task
        outputPipe = pipe
        do {
            try task.run()
        } catch {
            pipe.fileHandleForReading.readabilityHandler = nil
            process = nil
            outputPipe = nil
            throw error
        }
    }

    func cancel() {
        process?.terminate()
    }
}

@MainActor
final class OTADeployModel: ObservableObject {
    @Published var firmwareURL: URL?
    @Published var firmwareSHA256 = ""
    @Published var firmwareSize = ""
    @Published var firmwareValid = false
    @Published var ticketURL: URL?
    @Published var fdsDID = ""
    @Published var fdsModel = ""
    @Published var showAdvanced = false
    @Published var busy = false
    @Published var status = "等待选择 BFNP 固件"
    @Published var logText = ""
    @Published var verificationPassed = false

    private let runner = StreamingProcessRunner()

    var ticketReady: Bool {
        guard let ticketURL else { return false }
        return FileManager.default.fileExists(atPath: ticketURL.path)
    }

    var gatewayFieldsValid: Bool {
        fdsDID.isEmpty == fdsModel.isEmpty
    }

    func chooseFirmware() {
        let panel = NSOpenPanel()
        panel.title = "选择 AP01 screen-realtime.bin"
        panel.prompt = "选择固件"
        panel.allowedContentTypes = [.data]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }

        busy = true
        status = "正在校验 BFNP 与 SHA-256…"
        verificationPassed = false
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                let handle = try FileHandle(forReadingFrom: url)
                let header = try handle.read(upToCount: 4) ?? Data()
                try handle.close()
                guard header == Data("BFNP".utf8) else {
                    throw NSError(domain: "AP01Controller", code: 2, userInfo: [NSLocalizedDescriptionKey: "文件头不是 BFNP，已拒绝使用"])
                }
                let values = try url.resourceValues(forKeys: [.fileSizeKey])
                let hashOutput = try runProcess("/usr/bin/shasum", ["-a", "256", url.path])
                let hash = hashOutput.split(separator: " ").first.map(String.init) ?? ""
                guard hash.count == 64 else {
                    throw NSError(domain: "AP01Controller", code: 3, userInfo: [NSLocalizedDescriptionKey: "无法计算 SHA-256"])
                }
                let bytes = Int64(values.fileSize ?? 0)
                let formatted = ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
                DispatchQueue.main.async {
                    self?.firmwareURL = url
                    self?.firmwareSHA256 = hash
                    self?.firmwareSize = formatted
                    self?.firmwareValid = true
                    self?.busy = false
                    self?.status = "固件预检通过 · BFNP · \(formatted)"
                    self?.appendLog("✓ 固件预检通过\nSHA-256  \(hash)\n")
                }
            } catch {
                DispatchQueue.main.async {
                    self?.firmwareURL = url
                    self?.firmwareSHA256 = ""
                    self?.firmwareSize = ""
                    self?.firmwareValid = false
                    self?.busy = false
                    self?.status = error.localizedDescription
                    self?.appendLog("✗ \(error.localizedDescription)\n")
                }
            }
        }
    }

    func chooseTicket() {
        let panel = NSOpenPanel()
        panel.title = "导入临时 OTA 链接文件"
        panel.prompt = "导入票据"
        panel.allowedContentTypes = [.plainText]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        guard let value = try? String(contentsOf: url, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines),
              let parsed = URL(string: value),
              parsed.scheme == "https" else {
            status = "票据文件不是有效的 HTTPS URL"
            appendLog("✗ 票据文件无效\n")
            return
        }
        ticketURL = url
        verificationPassed = false
        status = "已导入临时 OTA 票据"
        appendLog("✓ 已导入票据：\(parsed.host ?? "未知主机")\(parsed.path)\n")
    }

    func generateTicket() {
        guard let firmwareURL, firmwareValid else {
            status = "请先选择并通过固件预检"
            return
        }
        guard gatewayFieldsValid else {
            status = "FDS DID 与 Model 必须同时填写或同时留空"
            return
        }

        try? FileManager.default.removeItem(at: otaURLFile)
        var arguments = [
            projectRoot.appendingPathComponent("ap01_install_firmware.py").path,
            firmwareURL.path,
            "--upload-only",
            "--url-output", otaURLFile.path
        ]
        if !fdsDID.isEmpty {
            arguments += ["--fds-did", fdsDID, "--fds-model", fdsModel]
        }
        begin(
            title: "正在通过有 FDS 能力的米家网关生成票据…",
            arguments: arguments
        ) { [weak self] in
            guard let self else { return }
            guard FileManager.default.fileExists(atPath: otaURLFile.path) else {
                self.status = "命令完成，但没有生成票据文件"
                return
            }
            self.ticketURL = otaURLFile
            self.status = "临时 OTA 票据已生成，请尽快验证"
            self.appendLog("✓ 票据保存在本机 artifacts 目录（日志已隐藏签名）\n")
        }
    }

    func verifyDownload() {
        guard let firmwareURL, firmwareValid else {
            status = "请先选择并通过固件预检"
            return
        }
        guard let ticketURL, ticketReady else {
            status = "请先生成或导入 OTA 票据"
            return
        }
        verificationPassed = false
        begin(
            title: "正在让 AP01 仅下载并校验（不会安装）…",
            arguments: [
                projectRoot.appendingPathComponent("ap01_install_firmware.py").path,
                firmwareURL.path,
                "--download-only",
                "--ota-url-file", ticketURL.path,
                "--timeout", "360"
            ]
        ) { [weak self] in
            self?.verificationPassed = true
            self?.status = "下载校验完成 · 未安装、未切换启动分区"
            self?.appendLog("✓ AP01 下载验证通过；本次没有安装固件\n")
        }
    }

    func copyTicket() {
        guard let ticketURL,
              let value = try? String(contentsOf: ticketURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else {
            status = "没有可复制的票据"
            return
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(value, forType: .string)
        status = "完整临时链接已复制；请勿公开分享"
    }

    func openGuide() {
        NSWorkspace.shared.open(otaGuideURL)
    }

    func cancel() {
        runner.cancel()
        status = "正在取消…"
    }

    private func begin(title: String, arguments: [String], onSuccess: @escaping () -> Void) {
        busy = true
        status = title
        appendLog("\n— \(title)\n")
        do {
            try runner.run(
                executable: projectRoot.appendingPathComponent(".venv/bin/python").path,
                arguments: arguments,
                onOutput: { [weak self] chunk in
                    let safe = redactedNetworkText(chunk)
                    DispatchQueue.main.async { self?.appendLog(safe) }
                },
                completion: { [weak self] result in
                    guard let self else { return }
                    self.busy = false
                    switch result {
                    case .success:
                        onSuccess()
                    case .failure(let error):
                        self.status = "任务失败：\(error.localizedDescription)"
                        self.appendLog("✗ \(error.localizedDescription)\n")
                    }
                }
            )
        } catch {
            busy = false
            status = "无法启动：\(error.localizedDescription)"
            appendLog("✗ \(error.localizedDescription)\n")
        }
    }

    private func appendLog(_ text: String) {
        logText += text
        if logText.count > 24_000 { logText = String(logText.suffix(24_000)) }
    }
}

@MainActor
final class AP01Model: ObservableObject {
    @Published var online = false
    @Published var statusText = "正在检查服务…"
    @Published var mode = "quota"
    @Published var fit = "contain"
    @Published var localURL = "http://Mac局域网IP:8765/screen.gif"
    @Published var preview: NSImage?
    @Published var logText = ""
    @Published var busy = false
    @Published var toast = ""
    @Published var showingDeployment = false

    private var timer: Timer?

    init() {
        mode = (try? String(contentsOf: modeFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)) ?? "quota"
        updateLocalURL()
        loadPreview()
        refreshStatus()
        timer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshStatus() }
        }
    }

    deinit { timer?.invalidate() }

    func updateLocalURL() {
        let ip = (try? runProcess("/usr/sbin/ipconfig", ["getifaddr", "en0"]))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let ip, !ip.isEmpty { localURL = "http://\(ip):8765/screen.gif" }
    }

    func refreshStatus() {
        guard let url = URL(string: "http://127.0.0.1:8765/health") else { return }
        var request = URLRequest(url: url)
        request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            DispatchQueue.main.async {
                guard let self else { return }
                if let error {
                    self.online = false
                    self.statusText = "服务未运行：\(error.localizedDescription)"
                } else if let data,
                          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    let ok = object["ok"] as? Bool ?? false
                    // Reaching /health proves that the bridge process is alive.
                    // `ok=false` can mean only that the latest Claude/Codex
                    // refresh failed; it should not be shown as a dead service.
                    self.online = true
                    if let problem = object["error"] as? String, !problem.isEmpty {
                        self.statusText = "服务运行中 · 数据刷新失败：\(problem)"
                    } else if let requests = object["requests"] as? Int {
                        self.statusText = "自定义画面服务正常 · 已请求 \(requests) 次"
                    } else {
                        self.statusText = ok ? "额度服务正常 · 每 5 分钟自动刷新" : "服务运行中 · 等待下一次刷新"
                    }
                }
                self.loadPreview()
                self.loadLog()
            }
        }.resume()
    }

    func loadPreview() {
        let path = mode == "custom" ? customGIF : quotaGIF
        if let image = NSImage(contentsOf: path) { preview = image }
    }

    func loadLog() {
        let path = artifacts.appendingPathComponent("ap01_launchd.log")
        guard let text = try? String(contentsOf: path, encoding: .utf8) else { return }
        logText = text.split(separator: "\n").suffix(7).joined(separator: "\n")
    }

    func chooseImage() {
        let panel = NSOpenPanel()
        panel.title = "选择要显示的图片或 GIF"
        panel.allowedContentTypes = [.png, .jpeg, .gif, .heic, .tiff, .webP]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let source = panel.url else { return }
        busy = true
        toast = "正在转换为 AP01 画面…"
        let fitMode = fit
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                _ = try runProcess(projectRoot.appendingPathComponent(".venv/bin/python").path, [
                    projectRoot.appendingPathComponent("ap01_prepare_screen.py").path,
                    source.path,
                    customGIF.path,
                    "--fit", fitMode,
                    "--background", "#01040B",
                    "--max-bytes", "90000",
                    "--max-frames", "8",
                    "--min-frame-ms", "120"
                ])
                try "custom\n".write(to: modeFile, atomically: true, encoding: .utf8)
                try self?.restartServiceSync()
                DispatchQueue.main.async {
                    self?.mode = "custom"
                    self?.busy = false
                    self?.toast = "已切换为自定义画面；屏幕将在下一次轮询时更新"
                    self?.loadPreview()
                    self?.refreshStatus()
                }
            } catch {
                DispatchQueue.main.async {
                    self?.busy = false
                    self?.toast = "转换失败：\(error.localizedDescription)"
                }
            }
        }
    }

    func useQuotaMode() {
        busy = true
        toast = "正在获取最新 Claude / Codex 额度…"
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                try "quota\n".write(to: modeFile, atomically: true, encoding: .utf8)
                try self?.restartServiceSync()
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                    self?.mode = "quota"
                    self?.busy = false
                    self?.toast = "额度模式已启动"
                    self?.loadPreview()
                    self?.refreshStatus()
                }
            } catch {
                DispatchQueue.main.async {
                    self?.busy = false
                    self?.toast = "启动失败：\(error.localizedDescription)"
                }
            }
        }
    }

    func restartService() {
        busy = true
        toast = "正在重启服务…"
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                try self?.restartServiceSync()
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    self?.busy = false
                    self?.toast = "服务已重启"
                    self?.refreshStatus()
                }
            } catch {
                DispatchQueue.main.async {
                    self?.busy = false
                    self?.toast = "重启失败：\(error.localizedDescription)"
                }
            }
        }
    }

    nonisolated private func restartServiceSync() throws {
        let domain = "gui/\(getuid())/\(launchLabel)"
        _ = try runProcess("/bin/launchctl", ["kickstart", "-k", domain])
    }

    func openArtifacts() { NSWorkspace.shared.open(artifacts) }
    func copyURL() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(localURL, forType: .string)
        toast = "局域网地址已复制"
    }
}

struct StatusPill: View {
    let online: Bool
    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(online ? Color.green : Color.red).frame(width: 9, height: 9)
            Text(online ? "服务运行中" : "服务未运行").font(.system(size: 13, weight: .semibold))
        }
        .padding(.horizontal, 13).padding(.vertical, 7)
        .background(.white.opacity(0.07), in: Capsule())
    }
}

struct OTADeploymentView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model = OTADeployModel()

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.01, green: 0.03, blue: 0.07), Color(red: 0.02, green: 0.08, blue: 0.13)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ).ignoresSafeArea()

            VStack(spacing: 16) {
                deploymentHeader
                ScrollView {
                    VStack(spacing: 14) {
                        safetyNotice
                        HStack(alignment: .top, spacing: 14) {
                            firmwareCard
                            ticketCard
                        }
                        verificationCard
                        deploymentLog
                    }
                    .padding(.bottom, 4)
                }
            }
            .padding(22)
        }
        .preferredColorScheme(.dark)
        .frame(width: 900, height: 720)
    }

    private var deploymentHeader: some View {
        HStack(spacing: 13) {
            Image(systemName: "shippingbox.and.arrow.backward.fill")
                .font(.system(size: 25, weight: .semibold))
                .foregroundStyle(.cyan)
                .frame(width: 48, height: 48)
                .background(Color.cyan.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 9) {
                    Text("首次部署 / OTA 交接").font(.system(size: 22, weight: .bold, design: .rounded))
                    Text("GitHub 新功能")
                        .font(.caption.bold())
                        .foregroundStyle(.cyan)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Color.cyan.opacity(0.12), in: Capsule())
                }
                Text("适用于 AP01 1.0.2_0031 · 上传账号与 AP01 账号可以分离")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
            Button("查看完整说明") { model.openGuide() }.buttonStyle(.bordered)
            Button("完成") { dismiss() }.buttonStyle(.borderedProminent).tint(.cyan)
        }
    }

    private var safetyNotice: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "memorychip.fill").foregroundStyle(.green).font(.title3)
            VStack(alignment: .leading, spacing: 3) {
                Text("当前页面不会自动安装固件").font(.subheadline.bold())
                Text("只提供生成临时票据与“仅下载验证”。已经能实时显示的设备无需再次 OTA；日常图片/额度刷新仍写入 RAM，不会反复写 Flash。")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
        }
        .padding(14)
        .background(Color.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 15).stroke(Color.green.opacity(0.2)))
    }

    private var firmwareCard: some View {
        VStack(alignment: .leading, spacing: 13) {
            stepTitle("1", "固件预检", "同一个 BIN 必须用于上传与下载")
            Button { model.chooseFirmware() } label: {
                Label("选择 screen-realtime.bin", systemImage: "doc.badge.gearshape")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.borderedProminent).tint(.orange).disabled(model.busy)

            if let url = model.firmwareURL {
                valueRow("文件", url.lastPathComponent)
                valueRow("文件头", model.firmwareValid ? "BFNP ✓" : "无效")
                if !model.firmwareSize.isEmpty { valueRow("大小", model.firmwareSize) }
                if !model.firmwareSHA256.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("SHA-256").font(.caption).foregroundStyle(.secondary)
                        Text(model.firmwareSHA256)
                            .font(.system(size: 10, design: .monospaced))
                            .textSelection(.enabled)
                            .lineLimit(2)
                    }
                }
            } else {
                Text("软件会检查 BFNP 文件头、文件大小和 SHA-256。")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .deploymentCard()
    }

    private var ticketCard: some View {
        VStack(alignment: .leading, spacing: 13) {
            stepTitle("2", "临时 OTA 票据", "票据有时效，不会写入普通日志")

            Button { model.generateTicket() } label: {
                Label("有 FDS 网关：生成票据", systemImage: "key.horizontal.fill")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.borderedProminent).tint(.cyan)
            .disabled(model.busy || !model.firmwareValid || !model.gatewayFieldsValid)

            Button { model.chooseTicket() } label: {
                Label("无网关：导入票据文件", systemImage: "square.and.arrow.down")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.bordered).disabled(model.busy)

            DisclosureGroup("高级：手动指定 FDS 网关", isExpanded: $model.showAdvanced) {
                VStack(alignment: .leading, spacing: 8) {
                    TextField("网关 DID", text: $model.fdsDID)
                    TextField("lumi.gateway.xxxx", text: $model.fdsModel)
                    if !model.gatewayFieldsValid {
                        Label("DID 与 Model 必须成对填写", systemImage: "exclamationmark.triangle.fill")
                            .font(.caption).foregroundStyle(.orange)
                    }
                }.padding(.top, 8)
            }
            .font(.caption)

            if model.ticketReady {
                HStack {
                    Label("票据已就绪", systemImage: "checkmark.seal.fill")
                        .font(.caption.bold()).foregroundStyle(.green)
                    Spacer()
                    Button("复制完整链接") { model.copyTicket() }.buttonStyle(.link)
                }
            }
            Spacer(minLength: 0)
        }
        .deploymentCard()
    }

    private var verificationCard: some View {
        HStack(spacing: 15) {
            VStack(alignment: .leading, spacing: 5) {
                stepTitle("3", "AP01 下载验证", "只下载、校验 MD5，不安装、不切换启动分区")
                Text(model.status).font(.caption).foregroundStyle(model.verificationPassed ? Color.green : Color.secondary)
                    .lineLimit(2).fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
            if model.busy {
                ProgressView().controlSize(.small)
                Button("取消") { model.cancel() }.buttonStyle(.bordered)
            }
            Button { model.verifyDownload() } label: {
                Label("仅下载验证（不会安装）", systemImage: "checkmark.shield.fill")
            }
            .buttonStyle(.borderedProminent).tint(.green)
            .disabled(model.busy || !model.firmwareValid || !model.ticketReady)
        }
        .padding(16)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var deploymentLog: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("部署日志").font(.subheadline.bold())
                Spacer()
                Text("签名 URL 已自动脱敏").font(.caption2).foregroundStyle(.secondary)
            }
            ScrollView {
                Text(model.logText.isEmpty ? "等待操作…" : model.logText)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .frame(height: 112)
        }
        .padding(14)
        .background(.black.opacity(0.3), in: RoundedRectangle(cornerRadius: 15, style: .continuous))
    }

    private func stepTitle(_ number: String, _ title: String, _ subtitle: String) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Text(number)
                .font(.caption.bold()).foregroundStyle(.black)
                .frame(width: 22, height: 22)
                .background(Color.cyan, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text(subtitle).font(.caption2).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func valueRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundStyle(.secondary)
            Spacer()
            Text(value).lineLimit(1).truncationMode(.middle)
        }.font(.caption)
    }
}

private extension View {
    func deploymentCard() -> some View {
        self
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 245, alignment: .topLeading)
            .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.07)))
    }
}

struct AP01ContentView: View {
    @StateObject private var model = AP01Model()

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.01, green: 0.03, blue: 0.07), Color(red: 0.02, green: 0.09, blue: 0.14)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()
            VStack(spacing: 18) {
                header
                HStack(alignment: .top, spacing: 18) {
                    previewCard
                    controlsCard
                }
                logCard
            }
            .padding(24)
        }
        .preferredColorScheme(.dark)
        .frame(minWidth: 900, minHeight: 650)
        .sheet(isPresented: $model.showingDeployment) {
            OTADeploymentView()
        }
    }

    private var header: some View {
        HStack {
            if let logoURL = Bundle.main.url(forResource: "AP01Logo", withExtension: "png"),
               let logo = NSImage(contentsOf: logoURL) {
                Image(nsImage: logo)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
                    .frame(width: 64, height: 64)
                    .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
                    .shadow(color: .cyan.opacity(0.2), radius: 12)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("CUKTECH Screen Controller").font(.system(size: 26, weight: .bold, design: .rounded))
                Text("酷态科万向屏 · 本地实时内容控制").foregroundStyle(.secondary)
            }
            Spacer()
            StatusPill(online: model.online)
        }
    }

    private var previewCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("当前画面").font(.headline)
                Spacer()
                Text(model.mode == "custom" ? "自定义" : "Claude / Codex")
                    .font(.caption.bold()).foregroundStyle(Color.cyan)
            }
            ZStack {
                RoundedRectangle(cornerRadius: 16).fill(Color.black.opacity(0.65))
                if let image = model.preview {
                    Image(nsImage: image).resizable().interpolation(.high).scaledToFit().padding(10)
                } else {
                    Text("暂无预览").foregroundStyle(.secondary)
                }
            }
            .aspectRatio(4/3, contentMode: .fit)
            Text(model.localURL).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                .textSelection(.enabled)
            Button("复制屏幕地址") { model.copyURL() }.buttonStyle(.bordered)
        }
        .padding(18).frame(maxWidth: .infinity)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))
    }

    private var controlsCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("显示内容").font(.headline)
            Button {
                model.useQuotaMode()
            } label: {
                Label("显示 Claude / Codex 额度", systemImage: "chart.donut")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.borderedProminent).tint(.cyan).disabled(model.busy)

            Divider()
            Text("自定义图片适配方式").font(.subheadline).foregroundStyle(.secondary)
            Picker("适配", selection: $model.fit) {
                Text("完整显示").tag("contain")
                Text("铺满裁切").tag("cover")
                Text("拉伸").tag("stretch")
            }.pickerStyle(.segmented)

            Button {
                model.chooseImage()
            } label: {
                Label("选择图片并推送", systemImage: "photo.badge.plus")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.borderedProminent).tint(.orange).disabled(model.busy)

            Divider()
            Button { model.restartService() } label: {
                Label("重启并立即刷新", systemImage: "arrow.clockwise")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }.buttonStyle(.bordered).disabled(model.busy)
            Button { model.openArtifacts() } label: {
                Label("打开输出文件夹", systemImage: "folder")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }.buttonStyle(.bordered)

            Divider()
            Button { model.showingDeployment = true } label: {
                Label("首次部署 / OTA 交接…", systemImage: "shippingbox.and.arrow.backward")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.bordered)
            Text("GitHub 新增：支持无网关账号之间传递临时 OTA 票据")
                .font(.caption2).foregroundStyle(.secondary)

            if model.busy { ProgressView().controlSize(.small) }
            if !model.toast.isEmpty {
                Text(model.toast).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
            Label("已设置登录自动启动", systemImage: "power.circle.fill")
                .font(.caption).foregroundStyle(.green)
        }
        .padding(18).frame(width: 340).frame(minHeight: 400)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))
    }

    private var logCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("运行状态").font(.headline)
                Spacer()
                Text(model.statusText).font(.caption).foregroundStyle(model.online ? Color.green : Color.orange)
            }
            ScrollView {
                Text(model.logText.isEmpty ? "等待 AP01 请求…" : model.logText)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }.frame(height: 78)
        }
        .padding(16).background(.black.opacity(0.28), in: RoundedRectangle(cornerRadius: 16))
    }
}

@main
struct AP01ScreenControllerApp: App {
    var body: some Scene {
        WindowGroup { AP01ContentView() }
            .windowStyle(.hiddenTitleBar)
            .defaultSize(width: 960, height: 700)
    }
}
