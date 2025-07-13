import React, { useEffect, useState } from 'react';
import { useMediaQuery, useTheme } from '@mui/material';

// Window拡張の型定義
declare global {
  interface Window {
    WEBSOCKET_RECONNECT_INTERVAL?: number;
    CHART_UPDATE_INTERVAL?: number;
  }
}

export const useTabletOptimization = () => {
  const theme = useTheme();
  const isTablet = useMediaQuery(theme.breakpoints.between('sm', 'lg'));
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [isTouch, setIsTouch] = useState(false);

  useEffect(() => {
    // タッチデバイスの検出
    setIsTouch('ontouchstart' in window || navigator.maxTouchPoints > 0);

    // パフォーマンス最適化
    if (isTablet || isMobile) {
      // アニメーションを削減
      document.documentElement.style.setProperty('--animation-duration', '0.1s');
      
      // WebSocket接続の間隔を調整
      window.WEBSOCKET_RECONNECT_INTERVAL = 5000; // 5秒に延長
      
      // チャート更新頻度を下げる
      window.CHART_UPDATE_INTERVAL = 2000; // 2秒に延長
    }

    return () => {
      document.documentElement.style.removeProperty('--animation-duration');
    };
  }, [isTablet, isMobile]);

  return {
    isTablet,
    isMobile,
    isTouch,
    // タブレット用の最適化された設定
    optimizedSettings: {
      // データ更新間隔（ミリ秒）
      updateInterval: isTablet ? 2000 : 1000,
      // 同時表示する通貨数
      maxSymbols: isTablet ? 5 : 10,
      // チャートのキャンドル数
      chartCandles: isTablet ? 50 : 100,
      // WebSocket再接続間隔
      wsReconnectInterval: isTablet ? 5000 : 3000,
      // アニメーション有効/無効
      enableAnimations: !isTablet && !isMobile,
      // 詳細データの表示
      showDetailedData: !isMobile,
    }
  };
};

// タブレット用のレスポンシブ設定
export const tabletBreakpoints = {
  xs: 0,      // スマートフォン
  sm: 600,    // 小型タブレット
  md: 768,    // 標準タブレット（iPad）
  lg: 1024,   // 大型タブレット（iPad Pro）
  xl: 1280,   // デスクトップ
};

// TabletOptimizedContainerコンポーネントは別ファイル（TabletOptimizedContainer.tsx）に移動