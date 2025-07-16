import { ApiSettings, DashboardData, SystemStatus } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://bybitbot-backend-731283498892.asia-northeast1.run.app';

class ApiService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = API_BASE_URL;
  }

  // 汎用的なGETリクエスト
  async get<T>(path: string): Promise<{ data: T }> {
    try {
      const response = await fetch(`${this.baseUrl}${path}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      return { data };
    } catch (error) {
      console.error(`GET ${path} failed:`, error);
      throw error;
    }
  }

  // 汎用的なPOSTリクエスト
  async post<T>(path: string, body: any): Promise<{ data: T }> {
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      return { data };
    } catch (error) {
      console.error(`POST ${path} failed:`, error);
      throw error;
    }
  }

  // システムステータスを取得
  async getSystemStatus(): Promise<SystemStatus> {
    try {
      const response = await fetch(`${this.baseUrl}/api/status`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Failed to fetch system status:', error);
      throw error;
    }
  }

  // ヘルスチェック
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/api/health`);
      return response.ok;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }

  // API設定をテスト
  async testApiConnection(settings: ApiSettings): Promise<{ success: boolean; message: string; details?: any }> {
    try {
      console.log('Testing API connection with settings:', { 
        ...settings, 
        api_secret: '***hidden***' 
      });
      
      const response = await fetch(`${this.baseUrl}/api/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });
      
      const responseText = await response.text();
      console.log('API response status:', response.status);
      console.log('API response headers:', response.headers);
      
      try {
        const data = JSON.parse(responseText);
        if (response.ok) {
          return { 
            success: true, 
            message: data.message || '接続成功',
            details: data
          };
        } else {
          return { 
            success: false, 
            message: data.detail || data.message || `エラー: ${response.status} ${response.statusText}`,
            details: data
          };
        }
      } catch (parseError) {
        console.error('Failed to parse response:', parseError);
        return {
          success: false,
          message: `サーバーからの応答が不正です: ${response.status} ${response.statusText}`,
          details: { responseText: responseText.substring(0, 200) }
        };
      }
    } catch (error) {
      console.error('API connection test failed:', error);
      
      // ネットワークエラーの詳細な診断
      let errorMessage = '接続に失敗しました: ';
      
      if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
        errorMessage += 'ネットワークエラー。インターネット接続を確認してください。';
        
        // タブレット特有の問題をチェック
        if (/iPad|Android/i.test(navigator.userAgent)) {
          errorMessage += ' タブレットのブラウザ設定でサイトへのアクセスが許可されているか確認してください。';
        }
      } else if (error instanceof Error) {
        errorMessage += error.message;
      } else {
        errorMessage += '不明なエラー';
      }
      
      return { 
        success: false, 
        message: errorMessage,
        details: { 
          error: error instanceof Error ? error.message : String(error),
          baseUrl: this.baseUrl,
          userAgent: navigator.userAgent
        }
      };
    }
  }

  // API設定を保存
  async saveApiSettings(settings: ApiSettings): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/api/settings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });
      return response.ok;
    } catch (error) {
      console.error('Failed to save API settings:', error);
      return false;
    }
  }

  // ダッシュボードデータを取得
  async getDashboardData(): Promise<DashboardData> {
    try {
      const response = await fetch(`${this.baseUrl}/api/dashboard`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
      throw error;
    }
  }
}

export const apiService = new ApiService();