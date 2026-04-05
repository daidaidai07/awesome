import SwiftUI

struct ChatView: View {
    @StateObject private var viewModel = ChatViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if !viewModel.isModelLoaded {
                    modelLoadingView
                } else {
                    chatContent
                }
            }
            .navigationTitle("Gemma 4 Chat")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: viewModel.clearChat) {
                        Image(systemName: "trash")
                    }
                    .disabled(!viewModel.isModelLoaded)
                }
            }
        }
        .onAppear {
            viewModel.loadModel()
        }
    }

    // MARK: - モデル読み込み画面

    private var modelLoadingView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "brain")
                .font(.system(size: 60))
                .foregroundStyle(.blue)

            Text("Gemma 4")
                .font(.largeTitle.bold())

            if viewModel.isLoadingModel {
                ProgressView("モデルを読み込み中...")
                    .progressViewStyle(.circular)
            } else if let error = viewModel.errorMessage {
                VStack(spacing: 12) {
                    Text(error)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)

                    Button("再試行") {
                        viewModel.loadModel()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

            Spacer()
        }
    }

    // MARK: - チャット画面

    private var chatContent: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(viewModel.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: viewModel.messages.count) {
                    if let lastMessage = viewModel.messages.last {
                        withAnimation(.easeOut(duration: 0.3)) {
                            proxy.scrollTo(lastMessage.id, anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            inputBar
        }
    }

    // MARK: - 入力バー

    private var inputBar: some View {
        HStack(spacing: 12) {
            TextField("メッセージを入力...", text: $viewModel.inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...5)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .onSubmit {
                    viewModel.sendMessage()
                }

            Button(action: viewModel.sendMessage) {
                Image(systemName: viewModel.isGenerating ? "stop.circle.fill" : "arrow.up.circle.fill")
                    .font(.title2)
                    .foregroundStyle(viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !viewModel.isGenerating ? .gray : .blue)
            }
            .disabled(viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !viewModel.isGenerating)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }
}

// MARK: - メッセージバブル

struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 60) }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                if message.role == .system {
                    Text(message.content)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                } else {
                    Text(message.content)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(bubbleColor)
                        .foregroundStyle(message.role == .user ? .white : .primary)
                        .clipShape(RoundedRectangle(cornerRadius: 18))
                }
            }

            if message.role == .assistant { Spacer(minLength: 60) }
        }
    }

    private var bubbleColor: Color {
        switch message.role {
        case .user: return .blue
        case .assistant: return Color(.systemGray5)
        case .system: return .clear
        }
    }
}

#Preview {
    ChatView()
}
