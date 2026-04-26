import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button } from 'antd';
import { useAuth } from '../hooks/useAuth';
import { ProtectedRoute, AdminRoute, ReviewerRoute } from './ProtectedRoute';
import CardBrowserPage from '../pages/CardBrowserPage';
import ReviewPage from '../pages/ReviewPage';
import MyErrataPage from '../pages/MyErrataPage';
import MappingPage from '../pages/MappingPage';
import PublishPage from '../pages/PublishPage';
import UserManagementPage from '../pages/UserManagementPage';

const { Header, Content } = Layout;

export default function AppLayout() {
  const { canAdmin, canReview, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    { key: '/cards', label: '卡牌浏览' },
    { key: '/my-errata', label: '我的勘误' },
    ...(canReview ? [
      { key: '/admin/review', label: '勘误审核' },
    ] : []),
    ...(canAdmin ? [
      { key: '/admin/mapping', label: '映射管理' },
      { key: '/admin/publish', label: '发布管理' },
      { key: '/admin/users', label: '用户管理' },
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
          <Route path="/errata/:arkhamdbId" element={<ProtectedRoute><CardBrowserPage /></ProtectedRoute>} />
          <Route path="/my-errata" element={<ProtectedRoute><MyErrataPage /></ProtectedRoute>} />
          <Route path="/admin/review" element={<ReviewerRoute><ReviewPage /></ReviewerRoute>} />
          <Route path="/admin/mapping" element={<AdminRoute><MappingPage /></AdminRoute>} />
          <Route path="/admin/publish" element={<AdminRoute><PublishPage /></AdminRoute>} />
          <Route path="/admin/users" element={<AdminRoute><UserManagementPage /></AdminRoute>} />
        </Routes>
      </Content>
    </Layout>
  );
}
