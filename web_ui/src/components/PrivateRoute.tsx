import { Navigate } from 'react-router-dom';
import { useAuth } from '../store/auth';
import type { UserRole } from '../types';

interface PrivateRouteProps {
  children: React.ReactNode;
  minRole: UserRole;
}

export default function PrivateRoute({ children, minRole }: PrivateRouteProps) {
  const { token, hasRole } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (!hasRole(minRole)) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-800 mb-2">权限不足</h2>
          <p className="text-gray-500">您没有访问此页面的权限（需要 {minRole} 角色）。</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
