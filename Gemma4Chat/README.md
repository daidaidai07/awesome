# Gemma 4 Chat - iPhone App

Gemma 4をオンデバイスで動かすiPhoneチャットアプリです。
MediaPipe LLM Inference APIを使用してローカル推論を行います。

## セットアップ

### 1. 依存関係のインストール

```bash
cd Gemma4Chat
pod install
```

インストール後は `Gemma4Chat.xcworkspace` を開いてください（`.xcodeproj` ではなく）。

### 2. モデルファイルの準備

Gemma 4のモデルを `.task` 形式に変換してプロジェクトに追加する必要があります。

#### 方法A: Kaggleから直接ダウンロード（推奨）

1. [Kaggle - Gemma](https://www.kaggle.com/models/google/gemma-4) からMediaPipe形式のモデルをダウンロード
2. ダウンロードした `.task` ファイルを `gemma4.task` にリネーム
3. Xcodeプロジェクトにドラッグ＆ドロップで追加（"Copy items if needed" にチェック）

#### 方法B: HuggingFaceモデルから変換

1. HuggingFaceからGemma 4モデルをダウンロード
2. MediaPipeの変換ツールで `.task` 形式に変換:

```bash
pip install mediapipe-model-maker
python -m mediapipe.tasks.genai.converter \
  --input_path=<model_dir> \
  --output_path=gemma4.task \
  --quantization=int8
```

3. 変換した `gemma4.task` をXcodeプロジェクトに追加

### 3. ビルド＆実行

- Xcode 15.4以上が必要
- iOS 16.0以上のiPhone実機で実行（シミュレータでは動作しません）
- Apple Developerアカウントでコード署名が必要

## プロジェクト構成

```
Gemma4Chat/
├── Gemma4Chat/
│   ├── Gemma4ChatApp.swift      # アプリエントリーポイント
│   ├── Views/
│   │   └── ChatView.swift       # チャットUI
│   ├── ViewModels/
│   │   └── ChatViewModel.swift  # チャットロジック
│   ├── Services/
│   │   └── GemmaService.swift   # MediaPipe推論サービス
│   ├── Models/
│   │   └── ChatMessage.swift    # メッセージモデル
│   └── Assets.xcassets/
├── Podfile                      # CocoaPods依存関係
└── README.md
```

## 推奨モデル

| モデル | サイズ | 推奨デバイス |
|--------|--------|-------------|
| Gemma 4 E2B (int4) | ~1.2GB | iPhone 15以上 |
| Gemma 4 E2B (int8) | ~2.4GB | iPhone 15 Pro以上 |

## 注意事項

- 初回のモデル読み込みには数秒〜十数秒かかります
- メモリ使用量が多いため、他のアプリを閉じることを推奨します
- バッテリー消費が大きくなるため、充電中の使用を推奨します
