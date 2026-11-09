import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const LayoutContext = createContext({
  sidebarCollapsed: false,
  viewportTier: 'desktop', // 'mobile' | 'desktop'
  
  toggleSidebar: () => {},
  
});

export function LayoutProvider({ children }) {
  const [userPreference, setUserPreference] = useState(() => {
    try {
      return localStorage.getItem('sidebarCollapsed') === 'true';
    } catch {
      return false;
    }
  });

  const getTier = (w) => (w < 640 ? 'mobile' : 'desktop');
  const [viewportTier, setViewportTier] = useState(() => getTier(window.innerWidth));
  

  // Debounced resize listener (150ms)
  useEffect(() => {
    let timeoutId = null;
    const handleResize = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        const nextTier = getTier(window.innerWidth);
        setViewportTier((prev) => {
          if (prev !== nextTier) {
            return nextTier;
          }
          return prev;
        });
      }, 150);
    };

    window.addEventListener('resize', handleResize);
    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const toggleSidebar = useCallback(() => {
    setUserPreference((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('sidebarCollapsed', String(next));
      } catch { /* ignore */ }
      return next;
    });
  }, []);

  

  // Evaluasi effective collapsed
  const sidebarCollapsed = userPreference;

  return (
    <LayoutContext.Provider
      value={{
        sidebarCollapsed,
        viewportTier,
        toggleSidebar,
      }}
    >
      {children}
    </LayoutContext.Provider>
  );
}

export function useLayout() {
  return useContext(LayoutContext);
}
