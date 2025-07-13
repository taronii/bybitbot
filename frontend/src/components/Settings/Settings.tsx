import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Switch,
  FormControlLabel,
  Alert,
  CircularProgress,
  Divider,
  InputAdornment,
  IconButton,
} from '@mui/material';
import {
  Visibility,
  VisibilityOff,
  Check as CheckIcon,
  Close as CloseIcon,
} from '@mui/icons-material';
import { ApiSettings } from '../../types';
import { apiService } from '../../services/api';
import TestConnection from './TestConnection';

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<ApiSettings>({
    apiKey: '',
    apiSecret: '',
    testnet: true,
  });
  const [hasExistingSecret, setHasExistingSecret] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const response = await apiService.get<any>('/api/settings');
      const data = response.data;
      setSettings({
        apiKey: data.apiKey,
        apiSecret: '', // 常に空文字列として設定（既存の値は表示しない）
        testnet: data.testnet,
      });
      setHasExistingSecret(data.hasApiSecret);
    } catch (error) {
      setMessage({ type: 'error', text: '設定の読み込みに失敗しました' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      // APIシークレットが空の場合は、そのまま空文字列を送信（バックエンドで既存の値を使用）
      await apiService.post('/api/settings', settings);
      setMessage({ type: 'success', text: '設定を保存しました' });
      
      // 保存後に設定を再読み込み
      await fetchSettings();
    } catch (error) {
      setMessage({ type: 'error', text: '設定の保存に失敗しました' });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // APIシークレットが空の場合は、そのまま空文字列を送信（バックエンドで既存の値を使用）
      const response = await apiService.post<{ success: boolean; message: string }>('/api/settings/test', settings);
      setTestResult(response.data);
    } catch (error: any) {
      setTestResult({ 
        success: false, 
        message: error.response?.data?.detail || '接続テストに失敗しました' 
      });
    } finally {
      setTesting(false);
    }
  };

  const handleChange = (field: keyof ApiSettings) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = field === 'testnet' ? event.target.checked : event.target.value;
    setSettings(prev => ({
      ...prev,
      [field]: value,
    }));
    setTestResult(null);
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" component="h1" gutterBottom fontWeight="bold">
        API設定
      </Typography>
      
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Bybit API認証情報
          </Typography>
          <Typography variant="body2" color="text.secondary" paragraph>
            Bybitの取引を行うためには、APIキーとシークレットキーが必要です。
            まずはテストネットで動作確認することをお勧めします。
          </Typography>

          <Box sx={{ mt: 3 }}>
            <FormControlLabel
              control={
                <Switch
                  checked={settings.testnet}
                  onChange={handleChange('testnet')}
                  color="primary"
                />
              }
              label={
                <Box>
                  <Typography variant="body1">
                    テストネットを使用
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {settings.testnet ? 'testnet.bybit.com' : 'api.bybit.com'}
                  </Typography>
                </Box>
              }
            />
          </Box>

          <Divider sx={{ my: 3 }} />

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="APIキー"
              value={settings.apiKey}
              onChange={handleChange('apiKey')}
              fullWidth
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              helperText={settings.testnet ? 
                "テストネット用のAPIキーを入力してください" : 
                "本番環境用のAPIキーを入力してください"
              }
            />

            <TextField
              label="APIシークレット"
              type={showSecret ? 'text' : 'password'}
              value={settings.apiSecret}
              onChange={handleChange('apiSecret')}
              fullWidth
              placeholder={hasExistingSecret ? "保存済み（変更する場合は新しい値を入力）" : "••••••••••••••••••••••••••••••••"}
              helperText={hasExistingSecret ? 
                "既存のAPIシークレットが保存されています。変更しない場合は空のままにしてください" : 
                "APIシークレットは暗号化されて保存されます"
              }
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowSecret(!showSecret)}
                      edge="end"
                    >
                      {showSecret ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
          </Box>

          {message && (
            <Alert severity={message.type} sx={{ mt: 2 }}>
              {message.text}
            </Alert>
          )}

          {testResult && (
            <Alert 
              severity={testResult.success ? 'success' : 'error'} 
              sx={{ mt: 2 }}
              icon={testResult.success ? <CheckIcon /> : <CloseIcon />}
            >
              <Typography variant="body2" fontWeight="bold">
                {testResult.success ? '接続成功' : '接続失敗'}
              </Typography>
              <Typography variant="body2">
                {testResult.message}
              </Typography>
            </Alert>
          )}

          <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
            <Button
              variant="contained"
              onClick={handleSave}
              disabled={saving || !settings.apiKey || !settings.apiSecret}
              startIcon={saving && <CircularProgress size={20} />}
            >
              {saving ? '保存中...' : '設定を保存'}
            </Button>

            <Button
              variant="outlined"
              onClick={handleTest}
              disabled={testing || !settings.apiKey || !settings.apiSecret}
              startIcon={testing && <CircularProgress size={20} />}
            >
              {testing ? 'テスト中...' : '接続テスト'}
            </Button>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            APIキーの取得方法
          </Typography>
          
          <Box component="ol" sx={{ pl: 2 }}>
            <Typography component="li" variant="body2" paragraph>
              {settings.testnet ? 
                'testnet.bybit.com にアクセスしてログイン' : 
                'bybit.com にアクセスしてログイン'
              }
            </Typography>
            <Typography component="li" variant="body2" paragraph>
              アカウント設定 → API管理 に移動
            </Typography>
            <Typography component="li" variant="body2" paragraph>
              「新しいキーの作成」をクリック
            </Typography>
            <Typography component="li" variant="body2" paragraph>
              以下の権限を付与:
              <Box component="ul" sx={{ mt: 1 }}>
                <Typography component="li" variant="body2">契約取引 - ポジション</Typography>
                <Typography component="li" variant="body2">契約取引 - 注文</Typography>
                <Typography component="li" variant="body2">ウォレット - 残高照会</Typography>
              </Box>
            </Typography>
            <Typography component="li" variant="body2">
              生成されたAPIキーとシークレットをコピーして上記フォームに入力
            </Typography>
          </Box>

          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body2">
              注意: APIシークレットは一度しか表示されません。必ず安全な場所に保管してください。
            </Typography>
          </Alert>
        </CardContent>
      </Card>

      <Box mt={3}>
        <TestConnection />
      </Box>
    </Box>
  );
};

export default Settings;