# Google Cloud Runへのデプロイガイド

## 前準備

### 1. Google Cloud アカウントの作成
- https://cloud.google.com にアクセス
- 無料トライアル（$300クレジット）を利用可能

### 2. Google Cloud CLIのインストール
```bash
# macOS
brew install google-cloud-sdk

# または公式インストーラー
curl https://sdk.cloud.google.com | bash
```

### 3. 初期設定
```bash
# ログイン
gcloud auth login

# プロジェクトの作成
gcloud projects create bybitbot-project --name="Bybit Trading Bot"

# プロジェクトIDを設定
export PROJECT_ID=bybitbot-project
gcloud config set project $PROJECT_ID

# 必要なAPIを有効化
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

## デプロイ方法

### 方法1: Cloud Buildを使用（推奨）

1. **GitHubと連携**
```bash
# Cloud Buildの設定
gcloud builds connections create github bybitbot-connection \
    --region=asia-northeast1

# リポジトリを接続
gcloud builds repositories create bybitbot-repo \
    --remote-uri=https://github.com/taronii/bybitbot.git \
    --connection=bybitbot-connection \
    --region=asia-northeast1
```

2. **自動デプロイの設定**
```bash
# トリガーの作成
gcloud builds triggers create github \
    --repo-name=bybitbot \
    --repo-owner=taronii \
    --branch-pattern=^main$ \
    --build-config=cloudbuild.yaml
```

3. **プッシュで自動デプロイ**
```bash
git add .
git commit -m "Add Cloud Build configuration"
git push
```

### 方法2: 手動デプロイ

1. **バックエンドのデプロイ**
```bash
cd backend

# Dockerイメージのビルド
gcloud builds submit --tag gcr.io/$PROJECT_ID/bybitbot-backend

# Cloud Runにデプロイ
gcloud run deploy bybitbot-backend \
    --image gcr.io/$PROJECT_ID/bybitbot-backend \
    --platform managed \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --set-env-vars ENCRYPTION_KEY=ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=
```

2. **フロントエンドのデプロイ**
```bash
cd ../frontend

# バックエンドのURLを取得
export BACKEND_URL=$(gcloud run services describe bybitbot-backend --platform managed --region asia-northeast1 --format 'value(status.url)')

# Dockerイメージのビルド（バックエンドURLを含む）
gcloud builds submit --tag gcr.io/$PROJECT_ID/bybitbot-frontend \
    --build-arg REACT_APP_API_URL=$BACKEND_URL

# Cloud Runにデプロイ
gcloud run deploy bybitbot-frontend \
    --image gcr.io/$PROJECT_ID/bybitbot-frontend \
    --platform managed \
    --region asia-northeast1 \
    --allow-unauthenticated
```

## アクセス方法

デプロイ完了後、以下のコマンドでURLを確認：

```bash
# フロントエンドのURL
gcloud run services describe bybitbot-frontend \
    --platform managed \
    --region asia-northeast1 \
    --format 'value(status.url)'
```

表示されたURLにブラウザでアクセスしてください。

## カスタムドメインの設定（オプション）

```bash
# ドメインマッピング
gcloud run domain-mappings create \
    --service bybitbot-frontend \
    --domain yourdomain.com \
    --region asia-northeast1
```

## コスト管理

### 無料枠
- 月200万リクエストまで無料
- 360,000 GB-秒のメモリ使用まで無料
- 180,000 vCPU-秒の CPU 使用まで無料

### コスト削減のヒント
1. 最小インスタンス数を0に設定（使用時のみ起動）
2. 同時実行数を制限
3. メモリを最小限に設定（512MB程度）

```bash
# リソースの調整
gcloud run services update bybitbot-backend \
    --min-instances=0 \
    --max-instances=10 \
    --memory=512Mi \
    --cpu=1 \
    --concurrency=100 \
    --region=asia-northeast1
```

## トラブルシューティング

### ログの確認
```bash
# バックエンドのログ
gcloud run logs read --service=bybitbot-backend --region=asia-northeast1

# フロントエンドのログ
gcloud run logs read --service=bybitbot-frontend --region=asia-northeast1
```

### 環境変数の更新
```bash
gcloud run services update bybitbot-backend \
    --update-env-vars KEY=VALUE \
    --region=asia-northeast1
```

## セキュリティ設定

本番環境では以下を推奨：

1. **Cloud Armorでの保護**
```bash
gcloud compute security-policies create bybitbot-policy \
    --description "Security policy for Bybit Bot"
```

2. **Identity-Aware Proxyの設定**
```bash
gcloud run services update bybitbot-frontend \
    --no-allow-unauthenticated \
    --region=asia-northeast1
```

3. **シークレットマネージャーの使用**
```bash
# APIキーをシークレットとして保存
echo -n "your-encryption-key" | gcloud secrets create encryption-key --data-file=-

# Cloud Runで使用
gcloud run services update bybitbot-backend \
    --set-secrets=ENCRYPTION_KEY=encryption-key:latest \
    --region=asia-northeast1
```