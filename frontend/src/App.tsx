import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './hooks/useAuth';
import LoginPage from './pages/LoginPage';
import AppLayout from './components/AppLayout';

function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/*" element={<AppLayout />} />
            <Route path="/" element={<Navigate to="/cards" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ConfigProvider>
  );
}
export default App;
