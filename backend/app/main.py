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
from app.routers import settings, dashboard, debug, trading, scalping, conservative

# ログ設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)
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
        from app.services.position_sync import position_sync_service
        
        settings = load_settings()
        if settings and settings.apiKey and settings.apiSecret:
            create_bybit_client(settings.apiKey, settings.apiSecret, settings.testnet)
            logger.info("Bybit client initialized from saved settings")
            
            # ポジション同期サービスを開始
            await position_sync_service.start_sync()
            logger.info("Position sync service started")
        else:
            logger.info("No saved settings found. Please configure API settings first.")
            
        # スキャルピングモードを確実に有効化
        from app.trading.modes.trading_mode_manager import trading_mode_manager, TradingMode
        result = trading_mode_manager.toggle_mode(TradingMode.SCALPING, True)
        logger.info(f"Scalping mode initialization: {result}")
        logger.info(f"Current scalping mode status: {trading_mode_manager.is_mode_active(TradingMode.SCALPING)}")
    except Exception as e:
        logger.error(f"Failed to initialize Bybit client: {e}")

# CORS設定（Cloud Run用に更新）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 全オリジンを許可（本番環境では特定のドメインのみにすることを推奨）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# リクエストログミドルウェア
@app.middleware("http")
async def log_requests(request, call_next):
    # リクエスト情報をログ
    logger.info(f"Request: {request.method} {request.url.path}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Client: {request.client}")
    
    # User-Agentをチェックしてタブレットを検出
    user_agent = request.headers.get("user-agent", "")
    if "iPad" in user_agent or "Android" in user_agent:
        logger.info(f"Tablet detected: {user_agent}")
    
    # レスポンスを処理
    response = await call_next(request)
    
    # レスポンス情報をログ
    logger.info(f"Response status: {response.status_code}")
    
    return response

# ルーターを登録
app.include_router(settings.router)
app.include_router(dashboard.router)
app.include_router(debug.router)
app.include_router(trading.router, prefix="/api/trading", tags=["trading"])
app.include_router(scalping.router)
app.include_router(conservative.router)

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
    try:
        await manager.connect(websocket)
        logger.info(f"WebSocket client connected from {websocket.client}")
        
        # 接続成功メッセージを送信
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "message": "WebSocket connection established"
        })
        
        while True:
            # クライアントからのメッセージを待つ（タイムアウトあり）
            try:
                # タイムアウトを設定して、定期的にヘルスチェックを可能にする
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                logger.debug(f"Received from client: {data}")
                
                # pingに対してpongを返す
                if data == "ping":
                    await websocket.send_text("pong")
                    logger.debug("Sent pong")
                else:
                    # その他のメッセージの処理
                    try:
                        message = json.loads(data)
                        logger.info(f"Received message: {message}")
                        # 必要に応じてメッセージを処理
                        
                        # エコーバック（デバッグ用）
                        await websocket.send_json({
                            "type": "echo",
                            "original": message,
                            "timestamp": datetime.now().isoformat()
                        })
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {data}")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Invalid JSON format"
                        })
                        
            except asyncio.TimeoutError:
                # タイムアウトした場合、接続が生きているか確認
                try:
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception:
                    logger.warning("Failed to send heartbeat, connection may be dead")
                    break
                    
            except asyncio.CancelledError:
                # 接続がキャンセルされた場合
                logger.info("WebSocket connection cancelled")
                break
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                break
                    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        try:
            manager.disconnect(websocket)
            logger.info("WebSocket client cleanup completed")
        except Exception as e:
            logger.error(f"Error during WebSocket cleanup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時のクリーンアップ"""
    logger.info("Shutting down Bybit Trading Bot...")
    
    try:
        from app.services.position_sync import position_sync_service
        
        # ポジション同期サービスを停止
        await position_sync_service.stop_sync()
        logger.info("Position sync service stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True, log_level="info")