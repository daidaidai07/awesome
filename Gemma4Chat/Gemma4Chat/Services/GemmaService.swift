import Foundation
import MediaPipeTasksGenai

/// Gemma 4モデルのオンデバイス推論サービス
final class GemmaService {
    private var llmInference: LlmInference?
    private(set) var isLoaded = false

    /// モデルをロードする
    func loadModel() async throws {
        guard let modelPath = Bundle.main.path(forResource: "gemma4", ofType: "task") else {
            throw GemmaError.modelNotFound
        }

        let options = LlmInference.Options()
        options.modelPath = modelPath
        options.maxTokens = 2048
        options.temperature = 0.7
        options.topK = 40

        llmInference = try LlmInference(options: options)
        isLoaded = true
    }

    /// プロンプトからレスポンスを生成する（ストリーミング）
    func generateResponseStream(prompt: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            guard let inference = llmInference else {
                continuation.finish(throwing: GemmaError.modelNotLoaded)
                return
            }

            Task {
                do {
                    let resultStream = inference.generateResponseAsync(inputText: prompt)
                    for try await partial in resultStream {
                        continuation.yield(partial)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// プロンプトからレスポンスを生成する（一括）
    func generateResponse(prompt: String) async throws -> String {
        guard let inference = llmInference else {
            throw GemmaError.modelNotLoaded
        }
        return try inference.generateResponse(inputText: prompt)
    }
}

enum GemmaError: LocalizedError {
    case modelNotFound
    case modelNotLoaded
    case generationFailed(String)

    var errorDescription: String? {
        switch self {
        case .modelNotFound:
            return "gemma4.taskファイルがバンドルに見つかりません。モデルファイルを追加してください。"
        case .modelNotLoaded:
            return "モデルがまだロードされていません。"
        case .generationFailed(let message):
            return "生成エラー: \(message)"
        }
    }
}
