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
import { Trade } from '../../types';

interface RecentTradesTableProps {
  trades: Trade[];
}

const RecentTradesTable: React.FC<RecentTradesTableProps> = ({ trades }) => {
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
          最近の取引
        </Typography>
        {trades.length === 0 ? (
          <Box textAlign="center" py={4}>
            <Typography variant="body1" color="text.secondary">
              取引履歴がありません
            </Typography>
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>シンボル</TableCell>
                  <TableCell>方向</TableCell>
                  <TableCell align="right">数量</TableCell>
                  <TableCell align="right">価格</TableCell>
                  <TableCell align="right">手数料</TableCell>
                  <TableCell align="right">実現損益</TableCell>
                  <TableCell align="right">取引時刻</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {trades.map((trade) => (
                  <TableRow key={trade.id}>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {trade.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={trade.side === 'Buy' ? '買い' : '売り'}
                        size="small"
                        sx={{
                          backgroundColor: getSideColor(trade.side) + '20',
                          color: getSideColor(trade.side),
                          fontWeight: 'bold',
                        }}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {trade.quantity}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatCurrency(trade.price)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" color="text.secondary">
                        {formatCurrency(trade.fee)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography 
                        variant="body2" 
                        fontWeight="bold"
                        color={getPnLColor(trade.realizedPnL)}
                      >
                        {trade.realizedPnL >= 0 ? '+' : ''}{formatCurrency(trade.realizedPnL)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" color="text.secondary">
                        {formatTime(trade.timestamp)}
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

export default RecentTradesTable;