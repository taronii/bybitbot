# ビルドステージ
FROM node:16-alpine as build

WORKDIR /app

# 依存関係をコピー
COPY package*.json ./

# 依存関係をインストール
RUN npm ci --only=production

# アプリケーションコードをコピー
COPY . .

# ビルド引数
ARG REACT_APP_API_URL=http://localhost:8000

# 環境変数を設定
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV GENERATE_SOURCEMAP=false

# ビルド
RUN npm run build

# 実行ステージ
FROM nginx:alpine

# Nginxの設定
COPY --from=build /app/build /usr/share/nginx/html

# カスタムNginx設定
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ { \
        expires 1y; \
        add_header Cache-Control "public, immutable"; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]