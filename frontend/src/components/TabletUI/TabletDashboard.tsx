import React, { useState } from 'react';
import {
  Box,
  Paper,
  Tab,
  Tabs,
  IconButton,
  Badge,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  Divider,
  Typography,
  useTheme,
  SwipeableDrawer,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  ShowChart as ChartIcon,
  Settings as SettingsIcon,
  Notifications as NotificationsIcon,
  Menu as MenuIcon,
  TrendingUp,
  AccountBalance,
} from '@mui/icons-material';
import { useTabletOptimization } from '../../hooks/useTabletOptimization';

interface TabletDashboardProps {
  children?: React.ReactNode;
}

export const TabletDashboard: React.FC<TabletDashboardProps> = ({ children }) => {
  const theme = useTheme();
  const { isTablet, isMobile, optimizedSettings } = useTabletOptimization();
  const [currentTab, setCurrentTab] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notifications, setNotifications] = useState(3);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setCurrentTab(newValue);
  };

  const toggleDrawer = (open: boolean) => (event: React.KeyboardEvent | React.MouseEvent) => {
    if (
      event &&
      event.type === 'keydown' &&
      ((event as React.KeyboardEvent).key === 'Tab' ||
        (event as React.KeyboardEvent).key === 'Shift')
    ) {
      return;
    }
    setDrawerOpen(open);
  };

  const drawerContent = (
    <Box sx={{ width: 250 }} role="presentation">
      <List>
        <ListItem>
          <ListItemIcon>
            <AccountBalance color="primary" />
          </ListItemIcon>
          <ListItemText 
            primary="口座残高" 
            secondary="$10,000.00"
            primaryTypographyProps={{ fontWeight: 'bold' }}
          />
        </ListItem>
        <ListItem>
          <ListItemIcon>
            <TrendingUp color="success" />
          </ListItemIcon>
          <ListItemText 
            primary="本日の損益" 
            secondary="+$250.00 (+2.5%)"
            secondaryTypographyProps={{ color: 'success.main' }}
          />
        </ListItem>
      </List>
      <Divider />
      <List>
        <ListItemButton>
          <ListItemText primary="ポートフォリオ" />
        </ListItemButton>
        <ListItemButton>
          <ListItemText primary="取引履歴" />
        </ListItemButton>
        <ListItemButton>
          <ListItemText primary="パフォーマンス分析" />
        </ListItemButton>
        <ListItemButton>
          <ListItemText primary="ヘルプ" />
        </ListItemButton>
      </List>
    </Box>
  );

  return (
    <Box sx={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100vh',
      overflow: 'hidden',
      backgroundColor: theme.palette.background.default,
    }}>
      {/* ヘッダー */}
      <Paper 
        elevation={2}
        sx={{ 
          p: 1, 
          display: 'flex', 
          alignItems: 'center',
          justifyContent: 'space-between',
          borderRadius: 0,
        }}
      >
        <IconButton onClick={toggleDrawer(true)} edge="start">
          <MenuIcon />
        </IconButton>
        
        <Box sx={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
          Bybit Trading Bot
        </Box>

        <Box sx={{ display: 'flex', gap: 1 }}>
          <IconButton>
            <Badge badgeContent={notifications} color="error">
              <NotificationsIcon />
            </Badge>
          </IconButton>
          <IconButton>
            <SettingsIcon />
          </IconButton>
        </Box>
      </Paper>

      {/* タブナビゲーション */}
      <Paper sx={{ borderRadius: 0 }}>
        <Tabs
          value={currentTab}
          onChange={handleTabChange}
          variant="fullWidth"
          scrollButtons={false}
          sx={{
            '& .MuiTab-root': {
              minHeight: 48,
              fontSize: isTablet ? '0.875rem' : '1rem',
            }
          }}
        >
          <Tab icon={<DashboardIcon />} label="ダッシュボード" />
          <Tab icon={<ChartIcon />} label="取引" />
          <Tab icon={<TrendingUp />} label="スキャルピング" />
        </Tabs>
      </Paper>

      {/* メインコンテンツ */}
      <Box sx={{ 
        flexGrow: 1, 
        overflow: 'auto',
        p: isTablet ? 1 : 2,
        WebkitOverflowScrolling: 'touch', // スムーズスクロール
      }}>
        {children || (
          <Box sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6">
              タブレット最適化されたコンテンツ
            </Typography>
          </Box>
        )}
      </Box>

      {/* スワイプ可能なドロワー */}
      <SwipeableDrawer
        anchor="left"
        open={drawerOpen}
        onClose={toggleDrawer(false)}
        onOpen={toggleDrawer(true)}
        sx={{
          '& .MuiDrawer-paper': {
            backgroundColor: theme.palette.background.paper,
          }
        }}
      >
        {drawerContent}
      </SwipeableDrawer>
    </Box>
  );
};