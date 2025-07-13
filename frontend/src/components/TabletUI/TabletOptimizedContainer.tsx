import React from 'react';
import { useTabletOptimization } from '../../hooks/useTabletOptimization';

// タブレット最適化コンテナコンポーネント
export const TabletOptimizedContainer: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isTablet, isMobile } = useTabletOptimization();

  return (
    <div style={{
      padding: isTablet ? '8px' : '16px',
      maxWidth: isTablet ? '100%' : '1400px',
      margin: '0 auto',
      overflowX: isMobile ? 'auto' : 'visible',
    }}>
      {children}
    </div>
  );
};