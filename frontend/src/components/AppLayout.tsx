import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button } from 'antd';
import { useAuth } from '../hooks/useAuth';
import { ProtectedRoute, AdminRoute } from './ProtectedRoute';
import CardBrowserPage from '../pages/CardBrowserPage';

const { Header, Content } = Layout;

export default function AppLayout() {
  const { isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    { key: '/cards', label: '卡牌浏览' },
    { key: '/my-errata', label: '我的勘误' },
    ...(isAdmin ? [
      { key: '/admin/review', label: '勘误审核' },
      { key: '/admin/mapping', label: '映射管理' },
      { key: '/admin/publish', label: '发布管理' },
    ] : []),
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1 }}
        />
        <Button type="text" style={{ color: '#fff' }} onClick={logout}>退出</Button>
      </Header>
      <Content style={{ padding: 24 }}>
        <Routes>
          <Route path="/cards" element={<ProtectedRoute><CardBrowserPage /></ProtectedRoute>} />
          <Route path="/my-errata" element={<ProtectedRoute><div style={{ padding: 24 }}>我的勘误（开发中）</div></ProtectedRoute>} />
          <Route path="/admin/review" element={<AdminRoute><div style={{ padding: 24 }}>勘误审核（开发中）</div></AdminRoute>} />
          <Route path="/admin/mapping" element={<AdminRoute><div style={{ padding: 24 }}>映射管理（开发中）</div></AdminRoute>} />
          <Route path="/admin/publish" element={<AdminRoute><div style={{ padding: 24 }}>发布管理（开发中）</div></AdminRoute>} />
        </Routes>
      </Content>
    </Layout>
  );
}
