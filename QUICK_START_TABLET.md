# タブレット用クイックスタートガイド

## 方法1: クラウド版（推奨 - 最も簡単）

### Railway.appでの展開（5分で完了）

1. **準備**
   ```bash
   # プロジェクトルートで実行
   git init
   git add .
   git commit -m "Initial commit"
   ```

2. **GitHubにプッシュ**
   - GitHubで新しいリポジトリを作成
   - `git remote add origin [your-repo-url]`
   - `git push -u origin main`

3. **Railway.appでデプロイ**
   - https://railway.app にアクセス
   - "Start a New Project" をクリック
   - "Deploy from GitHub repo" を選択
   - リポジトリを選択

4. **環境変数の設定**
   ```
   ENCRYPTION_KEY=ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=
   REACT_APP_API_URL=https://[your-app].railway.app
   ```

5. **タブレットからアクセス**
   - 提供されたURLにアクセス
   - API設定で本番用APIキーを入力

## 方法2: ローカルネットワーク版

### セットアップ（10分）

1. **PCで起動**
   ```bash
   # プロジェクトルートで
   docker-compose -f docker-compose.tablet.yml up -d
   ```

2. **PCのIPアドレスを確認**
   ```bash
   # Mac/Linux
   ifconfig | grep "inet " | grep -v 127.0.0.1
   
   # Windows
   ipconfig | findstr IPv4
   ```

3. **ファイアウォール設定**
   - ポート80, 3000, 8000を開放
   - Windows: Windows Defenderファイアウォールで許可
   - Mac: システム環境設定 > セキュリティとプライバシー

4. **タブレットでアクセス**
   - ブラウザで `http://[PCのIP]` を開く
   - 同じWi-Fiネットワークに接続していることを確認

## 方法3: モバイルアプリ化（上級者向け）

### PWA（Progressive Web App）として利用

1. **manifest.jsonの確認**
   - frontend/public/manifest.json が存在することを確認

2. **HTTPSの設定**（必須）
   - Let's Encryptで無料SSL証明書を取得
   - またはCloudflareのトンネルを使用

3. **タブレットでインストール**
   - ChromeまたはSafariでサイトにアクセス
   - 「ホーム画面に追加」を選択
   - アプリとして起動可能に

## トラブルシューティング

### 接続できない場合
1. PCとタブレットが同じネットワークにあるか確認
2. ファイアウォールの設定を確認
3. `http://` (httpsではない) を使用しているか確認

### 動作が遅い場合
1. タブレット最適化モードを有効化
2. 表示する通貨ペア数を減らす
3. チャート更新頻度を下げる

### エラーが発生する場合
1. PCのDockerログを確認: `docker-compose logs -f`
2. ブラウザの開発者ツールでエラーを確認
3. API接続設定を再確認

## セキュリティ注意事項

- 公開インターネットに公開する場合は必ずHTTPSを使用
- APIキーは環境変数で管理
- 定期的にセキュリティアップデートを実施