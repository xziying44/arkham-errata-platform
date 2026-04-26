import { Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../hooks/useAuth';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { token, canAdmin, loading } = useAuth();
  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  if (!token) return <Navigate to="/login" replace />;
  if (!canAdmin) return <Navigate to="/cards" replace />;
  return <>{children}</>;
}

export function ReviewerRoute({ children }: { children: React.ReactNode }) {
  const { token, loading, canReview } = useAuth();
  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  if (!token) return <Navigate to="/login" replace />;
  if (!canReview) return <Navigate to="/cards" replace />;
  return <>{children}</>;
}
