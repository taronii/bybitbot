import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Box,
  useTheme,
} from '@mui/material';
import { Position } from '../../types';

interface PositionsTableProps {
  positions: Position[];
}

const PositionsTable: React.FC<PositionsTableProps> = ({ positions }) => {
  const theme = useTheme();

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('ja-JP', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const formatTime = (timestamp: string): string => {
    return new Date(timestamp).toLocaleString('ja-JP');
  };

  const getSideColor = (side: 'Buy' | 'Sell') => {
    return side === 'Buy' ? theme.palette.success.main : theme.palette.error.main;
  };

  const getPnLColor = (pnl: number) => {
    return pnl >= 0 ? theme.palette.success.main : theme.palette.error.main;
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" component="div" mb={2}>
          オープンポジション
        </Typography>
        {positions.length === 0 ? (
          <Box textAlign="center" py={4}>
            <Typography variant="body1" color="text.secondary">
              現在、オープンポジションはありません
            </Typography>
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>シンボル</TableCell>
                  <TableCell>方向</TableCell>
                  <TableCell align="right">サイズ</TableCell>
                  <TableCell align="right">エントリー価格</TableCell>
                  <TableCell align="right">現在価格</TableCell>
                  <TableCell align="right">未実現損益</TableCell>
                  <TableCell align="right">開始時刻</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {positions.map((position) => (
                  <TableRow key={position.id}>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {position.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={position.side === 'Buy' ? '買い' : '売り'}
                        size="small"
                        sx={{
                          backgroundColor: getSideColor(position.side) + '20',
                          color: getSideColor(position.side),
                          fontWeight: 'bold',
                        }}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {position.size}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatCurrency(position.entryPrice)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatCurrency(position.currentPrice)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography 
                        variant="body2" 
                        fontWeight="bold"
                        color={getPnLColor(position.unrealizedPnL)}
                      >
                        {position.unrealizedPnL >= 0 ? '+' : ''}{formatCurrency(position.unrealizedPnL)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" color="text.secondary">
                        {formatTime(position.timestamp)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
};

export default PositionsTable;