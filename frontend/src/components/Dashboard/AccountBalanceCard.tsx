import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  useTheme,
} from '@mui/material';
import {
  AccountBalance as BalanceIcon,
} from '@mui/icons-material';

interface AccountBalanceCardProps {
  balance: number;
}

const AccountBalanceCard: React.FC<AccountBalanceCardProps> = ({ balance }) => {
  const theme = useTheme();

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('ja-JP', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  return (
    <Card
      sx={{
        background: `linear-gradient(135deg, ${theme.palette.primary.main}20 0%, ${theme.palette.primary.main}10 100%)`,
        border: `1px solid ${theme.palette.primary.main}30`,
      }}
    >
      <CardContent>
        <Box display="flex" alignItems="center" mb={1}>
          <BalanceIcon sx={{ mr: 1, color: theme.palette.primary.main }} />
          <Typography variant="h6" component="div">
            アカウント残高
          </Typography>
        </Box>
        <Typography 
          variant="h3" 
          component="div" 
          fontWeight="bold"
          color={theme.palette.primary.main}
          sx={{ mb: 1 }}
        >
          {formatCurrency(balance)}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          総資産
        </Typography>
      </CardContent>
    </Card>
  );
};

export default AccountBalanceCard;