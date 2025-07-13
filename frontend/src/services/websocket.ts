import { WebSocketMessage } from '../types';

type WebSocketEventHandler = (message: WebSocketMessage) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Map<string, WebSocketEventHandler[]> = new Map();
  private generalHandlers: ((data: any) => void)[] = [];
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private isManualClose = false;
  private pingInterval: NodeJS.Timeout | null = null;

  constructor() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.REACT_APP_WS_URL || 'localhost:8000';
    this.url = `${protocol}//${host}/ws`;
    console.log('WebSocket URL:', this.url);
  }

  // WebSocket接続を開始
  connect(): void {
    // 既に接続中または接続済みの場合は何もしない
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      console.log('WebSocketは既に接続中または接続済みです');
      return;
    }

    // 既存の接続がある場合は完全にクリーンアップ
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    // 既存の再接続タイマーをクリア
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    this.isManualClose = false;

    try {
      console.log('新しいWebSocket接続を作成します:', this.url);
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('WebSocket接続が確立されました');
        this.reconnectAttempts = 0;
        
        // 定期的なpingを開始
        this.startPing();
      };

      this.ws.onmessage = (event) => {
        try {
          // pongメッセージの処理
          if (event.data === 'pong') {
            console.log('WebSocket: pong received');
            return;
          }
          
          const message = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('WebSocketメッセージの解析に失敗:', error);
        }
      };

      this.ws.onclose = (event) => {
        this.stopPing();
        if (!this.isManualClose) {
          console.log('WebSocket接続が閉じられました:', {
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean
          });
          this.attemptReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocketエラー:', error);
      };
    } catch (error) {
      console.error('WebSocket接続に失敗:', error);
      this.attemptReconnect();
    }
  }

  // WebSocket接続を切断
  disconnect(): void {
    this.isManualClose = true;
    this.stopPing();
    
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.reconnectAttempts = 0;
  }
  
  // 定期的なpingを開始
  private startPing(): void {
    this.stopPing();
    // 最初のpingを少し遅らせる
    const timeoutId = setTimeout(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
      
      this.pingInterval = setInterval(() => {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send('ping');
        } else {
          // 接続が閉じられていたらpingを停止
          this.stopPing();
        }
      }, 30000); // 30秒ごと
    }, 1000); // 1秒後に開始
    
    // timeoutIdも管理する必要がある場合は、クラスのプロパティとして保存
  }
  
  // pingを停止
  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  // メッセージハンドラーを登録
  on(messageType: string, handler: WebSocketEventHandler): void {
    if (!this.handlers.has(messageType)) {
      this.handlers.set(messageType, []);
    }
    this.handlers.get(messageType)!.push(handler);
  }

  // メッセージハンドラーを削除
  off(messageType: string, handler: WebSocketEventHandler): void {
    const handlers = this.handlers.get(messageType);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  // メッセージを送信
  send(message: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected, attempting to reconnect...');
      this.connect();
    }
  }


  // 汎用メッセージハンドラーを追加
  onMessage(handler: (data: any) => void): void {
    this.generalHandlers.push(handler);
  }

  // 接続状態を確認
  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  // メッセージを処理
  private handleMessage(message: any): void {
    // 特定のタイプハンドラーを実行
    if (message.type) {
      const handlers = this.handlers.get(message.type);
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(message);
          } catch (error) {
            console.error(`Handler for ${message.type} failed:`, error);
          }
        });
      }
    }

    // 汎用ハンドラーも実行
    this.generalHandlers.forEach(handler => {
      try {
        handler(message);
      } catch (error) {
        console.error('General handler failed:', error);
      }
    });
  }

  // 再接続を試行
  private attemptReconnect(): void {
    if (this.isManualClose) {
      return;
    }

    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 10000); // 指数バックオフ、最大10秒
      
      console.log(`${delay}ms後にWebSocket再接続を試行します... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      
      this.reconnectTimeout = setTimeout(() => {
        if (!this.isManualClose) {
          this.connect();
        }
      }, delay);
    } else {
      console.error('WebSocketの最大再接続試行回数に達しました');
      // 最大試行回数に達したら、少し長い間隔で再度試行
      this.reconnectAttempts = 0;
      this.reconnectTimeout = setTimeout(() => {
        if (!this.isManualClose) {
          console.log('WebSocket接続を再開します');
          this.connect();
        }
      }, 30000); // 30秒後に再試行
    }
  }

}

// シングルトンインスタンス
const websocketService = new WebSocketService();

// 互換性のためのクライアント
const wsClient = {
  connect: () => websocketService.connect(),
  disconnect: () => websocketService.disconnect(),
  send: (data: any) => websocketService.send(data),
  on: (event: string, callback: (data: any) => void) => websocketService.on(event, callback),
  off: (event: string, callback: (data: any) => void) => websocketService.off(event, callback),
  isConnected: () => websocketService.isConnected(),
  onMessage: (callback: (data: any) => void) => {
    // 汎用メッセージハンドラーを登録
    websocketService.onMessage(callback);
  }
};

// エクスポート
export { websocketService, wsClient };

export default wsClient;