import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  useTheme,
} from '@mui/material';

interface PnLCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  isPositive: boolean;
}

const PnLCard: React.FC<PnLCardProps> = ({ title, value, icon, isPositive }) => {
  const theme = useTheme();

  const formatCurrency = (amount: number): string => {
    const formatted = new Intl.NumberFormat('ja-JP', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Math.abs(amount));
    
    return amount >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  const getColor = () => {
    return isPositive ? theme.palette.success.main : theme.palette.error.main;
  };

  const getBackgroundColor = () => {
    return isPositive ? theme.palette.success.main + '20' : theme.palette.error.main + '20';
  };

  const getBorderColor = () => {
    return isPositive ? theme.palette.success.main + '30' : theme.palette.error.main + '30';
  };

  return (
    <Card
      sx={{
        background: `linear-gradient(135deg, ${getBackgroundColor()} 0%, ${getBackgroundColor().slice(0, -2)}10 100%)`,
        border: `1px solid ${getBorderColor()}`,
      }}
    >
      <CardContent>
        <Box display="flex" alignItems="center" mb={1}>
          <Box sx={{ mr: 1, color: getColor() }}>
            {icon}
          </Box>
          <Typography variant="h6" component="div">
            {title}
          </Typography>
        </Box>
        <Typography 
          variant="h4" 
          component="div" 
          fontWeight="bold"
          color={getColor()}
          sx={{ mb: 1 }}
        >
          {formatCurrency(value)}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isPositive ? '利益' : '損失'}
        </Typography>
      </CardContent>
    </Card>
  );
};

export default PnLCard;