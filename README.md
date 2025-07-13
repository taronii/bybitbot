# Bybit Ultimate Trading Bot

高度な自動売買機能を備えたBybit取引ボット

## 機能

- 🚀 **スキャルピングモード**: 高頻度取引に対応
- 📊 **複数通貨同時取引**: 最大20通貨ペアの同時監視・取引
- 🎯 **AI駆動のエントリーシグナル**: 機械学習による高精度な売買判断
- 📱 **タブレット対応**: レスポンシブデザインでどこからでもアクセス可能
- 🔒 **リスク管理**: ポートフォリオ全体のリスクを自動管理

## クイックスタート

### 必要な環境

- Python 3.9+
- Node.js 16+
- Docker（オプション）

### インストール

1. リポジトリをクローン
```bash
git clone https://github.com/taronii/bybitbot.git
cd bybitbot
```

2. バックエンドのセットアップ
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. フロントエンドのセットアップ
```bash
cd ../frontend
npm install
```

### 起動方法

1. バックエンドの起動
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

2. フロントエンドの起動（別ターミナル）
```bash
cd frontend
npm start
```

3. ブラウザで `http://localhost:3000` にアクセス

## タブレットでの利用

詳細は [QUICK_START_TABLET.md](QUICK_START_TABLET.md) を参照してください。

## 設定

1. フロントエンドの設定画面でBybit APIキーを入力
2. 取引したい通貨ペアを選択
3. リスク管理設定を確認
4. 自動売買を開始

## セキュリティ

- APIキーは暗号化して保存されます
- 本番環境では必ずHTTPSを使用してください
- 定期的にAPIキーを更新することを推奨します

## ライセンス

MIT License

## サポート

問題が発生した場合は、Issuesにて報告してください。