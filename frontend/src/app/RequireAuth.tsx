import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth, type Role } from '@/store/auth';

interface Props {
  children: React.ReactNode;
  roles?: Role[];
}

export function RequireAuth({ children, roles }: Props) {
  const { user, accessToken, clear } = useAuth();
  const loc = useLocation();

  useEffect(() => {
    const onLogout = () => clear();
    window.addEventListener('auth:logout', onLogout);
    return () => window.removeEventListener('auth:logout', onLogout);
  }, [clear]);

  if (!accessToken || !user) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  if (roles && roles.length > 0 && !roles.includes(user.role)) {
    return <Navigate to="/forbidden" replace />;
  }
  return <>{children}</>;
}
