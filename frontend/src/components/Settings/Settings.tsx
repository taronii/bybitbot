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
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; details?: any } | null>(null);

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
      // API接続テストを実行
      const result = await apiService.testApiConnection(settings);
      setTestResult(result);
      
      // デバッグ情報をコンソールに出力（タブレットでのデバッグ用）
      if (!result.success && result.details) {
        console.error('Connection test failed with details:', result.details);
      }
    } catch (error: any) {
      console.error('Unexpected error during connection test:', error);
      setTestResult({ 
        success: false, 
        message: '予期しないエラーが発生しました。コンソールログを確認してください。' 
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
              
              {/* タブレット用の追加情報 */}
              {!testResult.success && /iPad|Android/i.test(navigator.userAgent) && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" display="block" sx={{ fontStyle: 'italic' }}>
                    タブレットでの接続に関する注意:
                  </Typography>
                  <Typography component="ul" sx={{ pl: 2, mt: 0.5 }}>
                    <Typography component="li" variant="caption">
                      ブラウザがサイトへのアクセスを許可しているか確認してください
                    </Typography>
                    <Typography component="li" variant="caption">
                      プライベートブラウジングモードを無効にしてください
                    </Typography>
                    <Typography component="li" variant="caption">
                      Wi-Fi接続を確認し、必要に応じて再接続してください
                    </Typography>
                    <Typography component="li" variant="caption">
                      APIキーとシークレットキーが正しく入力されているか確認してください
                    </Typography>
                  </Typography>
                </Box>
              )}
              
              {/* デバッグ情報の表示 */}
              {!testResult.success && testResult.details && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" display="block" sx={{ fontWeight: 'bold' }}>
                    デバッグ情報:
                  </Typography>
                  <Typography variant="caption" component="pre" sx={{ 
                    whiteSpace: 'pre-wrap', 
                    wordBreak: 'break-word',
                    bgcolor: 'grey.100',
                    p: 1,
                    borderRadius: 1,
                    fontSize: '0.7rem'
                  }}>
                    {JSON.stringify(testResult.details, null, 2)}
                  </Typography>
                </Box>
              )}
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