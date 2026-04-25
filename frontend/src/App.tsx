import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';

function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/cards" replace />} />
          <Route path="/cards" element={<div style={{ padding: 24 }}>卡牌浏览（开发中）</div>} />
          <Route path="/login" element={<div style={{ padding: 24 }}>登录页（开发中）</div>} />
          <Route path="*" element={<div style={{ padding: 24 }}>页面不存在</div>} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
