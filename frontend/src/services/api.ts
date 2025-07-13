import { ApiSettings, DashboardData, SystemStatus } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

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
  async testApiConnection(settings: ApiSettings): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/api/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });
      return response.ok;
    } catch (error) {
      console.error('API connection test failed:', error);
      return false;
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