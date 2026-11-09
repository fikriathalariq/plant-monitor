import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AccessDenied from './AccessDenied';

// pageCode opsional: jika diisi, route ini juga di-guard berdasarkan
// allowed_pages posisi user (meniru decorator position_required di Django).
const ProtectedRoute = ({ children, pageCode }) => {
  const { user, canAccess } = useAuth();
  const location = useLocation();

  if (!user) {
    const currentPath = location.pathname + location.search;
    return <Navigate to={`/login?next=${encodeURIComponent(currentPath)}`} replace />;
  }

  if (pageCode && !canAccess(pageCode)) {
    return <AccessDenied pageCode={pageCode} />;
  }

  return children;
};

export default ProtectedRoute;
