import React, { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
} from '@mui/material';
import { apiService } from '../../services/api';

const TestConnection: React.FC = () => {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const response = await apiService.get<any>('/api/debug/test-connection');
      setResult(response.data);
    } catch (error) {
      setResult({ error: 'テスト接続に失敗しました' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          デバッグ情報
        </Typography>
        
        <Button
          variant="outlined"
          onClick={handleTest}
          disabled={testing}
          startIcon={testing && <CircularProgress size={20} />}
        >
          {testing ? 'テスト中...' : 'デバッグ接続テスト'}
        </Button>

        {result && (
          <Box mt={3}>
            {result.error ? (
              <Alert severity="error">{result.error}</Alert>
            ) : (
              <Box>
                <Alert severity={result.connection === 'success' ? 'success' : 'error'}>
                  接続状態: {result.connection}
                </Alert>
                <Box mt={2} p={2} bgcolor="background.paper" borderRadius={1}>
                  <Typography variant="body2" component="pre" style={{ whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(result, null, 2)}
                  </Typography>
                </Box>
              </Box>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default TestConnection;