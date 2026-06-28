import React, { useState, useEffect } from 'react';

// --- Sub-components ---

const NotificationBell: React.FC<{ unreadCount: number }> = ({ unreadCount }) => (
  <button className="icon-btn notification-btn" aria-label="Notifications">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
      <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
    </svg>
    {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
  </button>
);

const DarkModeToggle: React.FC<{ isDark: boolean; toggleDark: () => void }> = ({ isDark, toggleDark }) => (
  <button onClick={toggleDark} className="icon-btn" aria-label="Toggle Dark Mode">
    {isDark ? (
      // Sun Icon for Dark Mode
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      </svg>
    ) : (
      // Moon Icon for Light Mode
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
    )}
  </button>
);

const Breadcrumbs: React.FC<{ paths: string[] }> = ({ paths }) => (
  <nav className="breadcrumbs" aria-label="Breadcrumb">
    <ol>
      {paths.map((path, index) => (
        <li key={index}>
          <a href="#">{path}</a>
          {index < paths.length - 1 && <span className="separator">/</span>}
        </li>
      ))}
    </ol>
  </nav>
);

// --- Main Layout Component ---

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);

  // Sync theme to root element for global styling (e.g. scrollbars)
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark-theme');
    } else {
      document.documentElement.classList.remove('dark-theme');
    }
  }, [isDark]);

  return (
    <div className={`dashboard-layout ${sidebarOpen ? 'sidebar-open' : ''} ${isDark ? 'dark' : 'light'}`}>
      
      {/* 
        Inline dynamic style block guaranteeing robust aesthetics 
        without enforcing Tailwind dependencies, utilizing CSS Grid
        and strict Mobile-First design paradigms.
      */}
      <style>{`
        :root {
          /* Light Theme Variables */
          --bg-color: #f3f4f6;
          --surface-color: #ffffff;
          --text-primary: #111827;
          --text-secondary: #6b7280;
          --border-color: #e5e7eb;
          --primary-color: #2563eb;
          --sidebar-width: 260px;
          --header-height: 70px;
        }

        .dark-theme {
          /* Dark Theme Variables */
          --bg-color: #030712;
          --surface-color: #111827;
          --text-primary: #f9fafb;
          --text-secondary: #9ca3af;
          --border-color: #1f2937;
        }

        body {
          margin: 0;
          background-color: var(--bg-color);
          color: var(--text-primary);
          font-family: system-ui, -apple-system, sans-serif;
          transition: background-color 0.3s ease, color 0.3s ease;
        }

        /* 
          CSS Grid Layout Implementation
          By default (mobile), 1 column grid with header on top.
        */
        .dashboard-layout {
          display: grid;
          grid-template-columns: 1fr;
          grid-template-rows: var(--header-height) 1fr;
          min-height: 100vh;
        }

        /* --- Sidebar & Drawer (Mobile First) --- */
        .sidebar {
          position: fixed;
          top: 0;
          left: -100%; /* Hidden by default on mobile */
          width: var(--sidebar-width);
          height: 100vh;
          background-color: var(--surface-color);
          border-right: 1px solid var(--border-color);
          z-index: 50;
          transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          padding: 1.5rem 1rem;
          display: flex;
          flex-direction: column;
        }

        .dashboard-layout.sidebar-open .sidebar {
          left: 0;
        }

        /* Backdrop overlay for mobile sidebar */
        .sidebar-overlay {
          display: none;
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          backdrop-filter: blur(2px);
          z-index: 40;
          opacity: 0;
          transition: opacity 0.3s ease;
        }

        .dashboard-layout.sidebar-open .sidebar-overlay {
          display: block;
          opacity: 1;
        }

        /* --- Header --- */
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 1.5rem;
          background-color: var(--surface-color);
          border-bottom: 1px solid var(--border-color);
          position: sticky;
          top: 0;
          z-index: 30;
        }

        .header-left, .header-right {
          display: flex;
          align-items: center;
          gap: 1.25rem;
        }

        /* --- Main Application Frame --- */
        .main-content {
          padding: 1rem;
          overflow-y: auto;
        }

        /* Navigation Links styling */
        .nav-link {
          display: flex;
          align-items: center;
          padding: 0.75rem 1rem;
          color: var(--text-secondary);
          text-decoration: none;
          border-radius: 8px;
          margin-bottom: 0.5rem;
          font-weight: 500;
          transition: all 0.2s ease;
        }
        .nav-link:hover {
          background-color: var(--bg-color);
          color: var(--text-primary);
        }
        .nav-link.active {
          background-color: var(--primary-color);
          color: white;
          box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
        }

        /* Reusable UI Elements */
        .icon-btn {
          background: none;
          border: none;
          color: var(--text-secondary);
          cursor: pointer;
          padding: 0.5rem;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background-color 0.2s ease, color 0.2s ease;
        }
        .icon-btn:hover {
          color: var(--text-primary);
          background-color: var(--bg-color);
        }

        /* Notification specific */
        .notification-btn {
          position: relative;
        }
        .notification-badge {
          position: absolute;
          top: 0;
          right: 0;
          background-color: #ef4444;
          color: white;
          font-size: 0.65rem;
          font-weight: bold;
          padding: 2px 6px;
          border-radius: 9999px;
          transform: translate(25%, -25%);
          border: 2px solid var(--surface-color);
        }

        /* Breadcrumbs specific */
        .breadcrumbs ol {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          align-items: center;
          font-size: 0.9rem;
        }
        .breadcrumbs li {
          display: flex;
          align-items: center;
        }
        .breadcrumbs a {
          color: var(--text-secondary);
          text-decoration: none;
          transition: color 0.2s;
        }
        .breadcrumbs a:hover {
          color: var(--primary-color);
        }
        .breadcrumbs .separator {
          margin: 0 0.75rem;
          color: var(--border-color);
        }

        /* --- MOBILE FIRST BREAKPOINTS --- */
        
        /* sm - Small devices (phones in landscape, >= 640px) */
        @media (min-width: 640px) {
          .main-content {
            padding: 1.5rem;
          }
        }

        /* md - Medium devices (tablets, >= 768px) */
        @media (min-width: 768px) {
          /* Lock the grid to two columns */
          .dashboard-layout {
            grid-template-columns: var(--sidebar-width) 1fr;
          }
          
          /* Lock sidebar into view */
          .sidebar {
            position: sticky;
            left: 0;
            height: 100vh;
          }
          
          /* Remove mobile elements safely */
          .sidebar-overlay {
            display: none !important;
          }
          .menu-toggle {
            display: none;
          }
        }

        /* lg - Large devices (desktops, >= 1024px) */
        @media (min-width: 1024px) {
          .main-content {
            padding: 2.5rem;
          }
        }

        /* xl - Extra large devices (large monitors, >= 1280px) */
        @media (min-width: 1280px) {
          .dashboard-layout {
            max-width: 2560px;
            margin: 0 auto;
            border-left: 1px solid var(--border-color);
            border-right: 1px solid var(--border-color);
          }
        }
      `}</style>

      {/* Mobile Drawer Overlay */}
      <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)}></div>

      {/* Navigation Sidebar */}
      <aside className="sidebar">
        <div style={{ padding: '0 0.5rem', marginBottom: '2.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '8px', backgroundColor: 'var(--primary-color)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
            </div>
            <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: '800', color: 'var(--text-primary)', letterSpacing: '-0.025em' }}>AOP Control</h2>
          </div>
          
          <button className="icon-btn menu-toggle" onClick={() => setSidebarOpen(false)} aria-label="Close Menu">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
        
        <nav style={{ flex: 1 }}>
          <a href="#" className="nav-link">Overview</a>
          <a href="#" className="nav-link active">Provisioning</a>
          <a href="#" className="nav-link">Tenant Registry</a>
          <a href="#" className="nav-link">Usage Analytics</a>
          <div style={{ margin: '1.5rem 0 0.5rem 0', padding: '0 1rem', fontSize: '0.75rem', fontWeight: '700', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Settings</div>
          <a href="#" className="nav-link">API Keys</a>
          <a href="#" className="nav-link">Configuration</a>
        </nav>

        {/* User Footer Profile */}
        <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: 'var(--bg-color)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold', color: 'var(--primary-color)' }}>AD</div>
          <div>
            <p style={{ margin: 0, fontSize: '0.9rem', fontWeight: '600' }}>Admin User</p>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>admin@aop.sys</p>
          </div>
        </div>
      </aside>

      {/* Main Content Column */}
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', width: '100%' }}>
        
        {/* Top Header */}
        <header className="header">
          <div className="header-left">
            <button className="icon-btn menu-toggle" onClick={() => setSidebarOpen(true)} aria-label="Open Menu">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
            </button>
            <Breadcrumbs paths={['Home', 'Control Plane', 'Provisioning']} />
          </div>

          <div className="header-right">
            <DarkModeToggle isDark={isDark} toggleDark={() => setIsDark(!isDark)} />
            <NotificationBell unreadCount={3} />
          </div>
        </header>

        {/* Dynamic Route Content */}
        <main className="main-content">
          {children}
        </main>
      </div>
      
    </div>
  );
};

export default DashboardLayout;
