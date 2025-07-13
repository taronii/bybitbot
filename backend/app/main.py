from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import asyncio
from typing import Dict, List
import uvicorn
import logging
from datetime import datetime
import numpy as np
from app.routers import settings, dashboard, debug, trading, scalping

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bybit最強完全自動売買ツール",
    description="世界最高水準の自動売買システム",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化"""
    logger.info("Starting Bybit Trading Bot...")
    
    # 保存された設定を読み込んでBybitクライアントを初期化
    try:
        from app.routers.settings import load_settings
        from app.services.bybit_client import create_bybit_client
        
        settings = load_settings()
        if settings and settings.apiKey and settings.apiSecret:
            create_bybit_client(settings.apiKey, settings.apiSecret, settings.testnet)
            logger.info("Bybit client initialized from saved settings")
        else:
            logger.info("No saved settings found. Please configure API settings first.")
    except Exception as e:
        logger.error(f"Failed to initialize Bybit client: {e}")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ルーターを登録
app.include_router(settings.router)
app.include_router(dashboard.router)
app.include_router(debug.router)
app.include_router(trading.router, prefix="/api/trading", tags=["trading"])
app.include_router(scalping.router)

# WebSocket接続管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# ルート定義
@app.get("/")
async def root():
    return {"message": "Bybit最強完全自動売買ツール API"}

@app.get("/api/status")
async def get_status():
    return {
        "status": "running",
        "version": "1.0.0",
        "system": "healthy"
    }

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "timestamp": asyncio.get_event_loop().time()}

@app.get("/health")
async def health():
    """Cloud Run用のヘルスチェックエンドポイント"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# WebSocketエンドポイント
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    logger.info("WebSocket client connected")
    
    try:
        while True:
            # クライアントからのメッセージを待つ（タイムアウトなし）
            try:
                data = await websocket.receive_text()
                logger.info(f"Received from client: {data}")
                
                # pingに対してpongを返す
                if data == "ping":
                    await websocket.send_text("pong")
                    logger.info("Sent pong")
                else:
                    # その他のメッセージの処理
                    try:
                        message = json.loads(data)
                        logger.info(f"Received message: {message}")
                        # 必要に応じてメッセージを処理
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {data}")
                    
            except asyncio.CancelledError:
                # 接続がキャンセルされた場合
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                break
                    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)
        logger.info("WebSocket client cleanup completed")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True, log_level="info")