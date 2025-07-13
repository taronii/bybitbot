# タブレット対応ガイド

## 方法1: クラウドデプロイメント（推奨）

### メリット
- タブレットの性能に依存しない
- 24時間稼働可能
- どこからでもアクセス可能
- バックアップとセキュリティが充実

### デプロイ先オプション

#### 1. Heroku（簡単・無料枠あり）
```bash
# Herokuデプロイ用ファイル作成
# backend/Procfile
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT

# backend/runtime.txt
python-3.9.16

# frontend/static.json（React用）
{
  "root": "build/",
  "routes": {
    "/**": "index.html"
  }
}
```

#### 2. Railway（より簡単）
- GitHubリポジトリと連携
- 自動デプロイ
- 環境変数の管理が簡単

#### 3. Google Cloud Run（本格的）
- 自動スケーリング
- 従量課金制
- 高い信頼性

## 方法2: ローカルネットワーク経由

### 設定手順
1. PCでシステムを起動
2. ローカルIPアドレスを確認
3. タブレットから`http://[PCのIP]:3000`でアクセス

```bash
# backend/app/main.py の修正
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ローカルネットワーク用
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# frontend/.env.development
REACT_APP_API_URL=http://[PCのIP]:8000
```

## 方法3: タブレット最適化

### フロントエンドの軽量化