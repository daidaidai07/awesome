import Foundation
import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var inputText = ""
    @Published var isGenerating = false
    @Published var isModelLoaded = false
    @Published var isLoadingModel = false
    @Published var errorMessage: String?

    private let gemmaService = GemmaService()

    func loadModel() {
        guard !isLoadingModel else { return }
        isLoadingModel = true
        errorMessage = nil

        Task {
            do {
                try await gemmaService.loadModel()
                isModelLoaded = true
                messages.append(ChatMessage(role: .system, content: "Gemma 4モデルの読み込みが完了しました。"))
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoadingModel = false
        }
    }

    func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isGenerating else { return }

        inputText = ""
        messages.append(ChatMessage(role: .user, content: text))
        isGenerating = true
        errorMessage = nil

        // 会話履歴からプロンプトを構築
        let prompt = buildPrompt(for: text)

        Task {
            var responseText = ""
            // ストリーミングで途中結果を表示
            let placeholder = ChatMessage(role: .assistant, content: "")
            messages.append(placeholder)
            let responseIndex = messages.count - 1

            do {
                for try await partial in gemmaService.generateResponseStream(prompt: prompt) {
                    responseText += partial
                    messages[responseIndex] = ChatMessage(role: .assistant, content: responseText)
                }
            } catch {
                if responseText.isEmpty {
                    messages[responseIndex] = ChatMessage(role: .assistant, content: "エラーが発生しました: \(error.localizedDescription)")
                }
            }

            isGenerating = false
        }
    }

    func clearChat() {
        messages.removeAll()
        if isModelLoaded {
            messages.append(ChatMessage(role: .system, content: "チャットをクリアしました。"))
        }
    }

    private func buildPrompt(for userMessage: String) -> String {
        // Gemma形式のプロンプトテンプレート
        var prompt = ""
        let recentMessages = messages.suffix(10).filter { $0.role != .system }

        for message in recentMessages {
            switch message.role {
            case .user:
                prompt += "<start_of_turn>user\n\(message.content)<end_of_turn>\n"
            case .assistant:
                prompt += "<start_of_turn>model\n\(message.content)<end_of_turn>\n"
            case .system:
                break
            }
        }

        prompt += "<start_of_turn>model\n"
        return prompt
    }
}
