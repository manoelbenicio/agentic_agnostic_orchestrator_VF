import React, { ReactNode, useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import './globals.css';

// --- Context Providers (Architectural Wrappers) ---

const AuthContext = React.createContext<{ isAuthenticated: boolean; login: () => void; logout: () => void }>({
  isAuthenticated: true,
  login: () => {},
  logout: () => {},
});

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Mocks authentication state seamlessly.
  const [isAuthenticated, setIsAuthenticated] = useState(true); 
  
  return (
    <AuthContext.Provider value={{ isAuthenticated, login: () => setIsAuthenticated(true), logout: () => setIsAuthenticated(false) }}>
      {children}
    </AuthContext.Provider>
  );
};

const ThemeContext = React.createContext<{ theme: string; toggleTheme: () => void }>({ theme: 'dark', toggleTheme: () => {} });

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState('dark');
  
  useEffect(() => {
    // Syncs theme globally to the root HTML DOM for Tailwind structural injection
    document.documentElement.classList.remove('light', 'dark');
    document.documentElement.classList.add(theme);
  }, [theme]);
  
  return (
    <ThemeContext.Provider value={{ theme, toggleTheme: () => setTheme(t => t === 'dark' ? 'light' : 'dark') }}>
      {children}
    </ThemeContext.Provider>
  );
};


// --- Global Error Boundary ---
// Catches and encapsulates critical React DOM rendering panics securely without breaking the entire UI.

class GlobalErrorBoundary extends React.Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("GlobalErrorBoundary intercepted a critical React crash:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] text-white p-6 font-sans">
          <div className="bg-red-950/20 border border-red-500/50 rounded-xl p-8 max-w-2xl w-full text-center shadow-2xl backdrop-blur-sm">
            <h1 className="text-3xl font-bold text-red-400 mb-4">Critical Interface Panic</h1>
            <p className="text-gray-300 mb-6">The Agnostic Orchestration Platform (AOP) encountered a fatal UI crash.</p>
            <pre className="bg-black/80 p-4 rounded-lg text-sm text-left overflow-auto text-red-200 border border-red-900/30">
              {this.state.error?.message || "Unknown segmentation/render logic execution occurred."}
            </pre>
            <button 
              onClick={() => window.location.reload()} 
              className="mt-8 px-6 py-3 bg-red-600 hover:bg-red-500 rounded-lg text-white font-medium transition-colors shadow-lg"
            >
              Reinitialize Dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}


// --- Layout & Navigation UI ---

const NavSidebar: React.FC = () => {
  const location = useLocation();
  
  const navItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/provisioning', label: 'Provisioning', icon: '⚡' },
    { path: '/topology', label: 'Topology Map', icon: '🕸️' },
    { path: '/registry', label: 'AI Registry', icon: '🧠' },
    { path: '/governance', label: 'Governance & Cost', icon: '🛡️' },
    { path: '/analytics', label: 'Analytics', icon: '📈' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
  ];

  return (
    <aside className="w-64 bg-[#0a0a0a] border-r border-gray-800/60 flex flex-col h-screen fixed left-0 top-0 text-gray-300 shadow-2xl z-40">
      {/* Branding Header */}
      <div className="h-16 flex items-center px-6 border-b border-gray-800/60">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center font-bold text-white shadow-[0_0_15px_rgba(99,102,241,0.4)]">
            A
          </div>
          <span className="text-xl font-bold text-white tracking-wide">AOP Control</span>
        </div>
      </div>
      
      {/* Navigation Router Links */}
      <div className="flex-1 overflow-y-auto py-6 px-4">
        <nav className="flex flex-col gap-1.5">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3 px-2">Navigation</p>
          {navItems.map((item) => (
            <Link 
              key={item.path} 
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                location.pathname === item.path 
                  ? 'bg-indigo-600/10 text-indigo-400 font-semibold shadow-inner border border-indigo-500/20' 
                  : 'hover:bg-gray-800/40 hover:text-white border border-transparent'
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              <span className="text-sm">{item.label}</span>
            </Link>
          ))}
        </nav>
      </div>
      
      {/* Active User Context Footer */}
      <div className="p-4 border-t border-gray-800/60 bg-gradient-to-t from-black/20 to-transparent">
        <div className="flex items-center gap-3 px-2 py-2 hover:bg-gray-800/30 rounded-lg cursor-pointer transition-colors">
          <div className="w-9 h-9 rounded-full bg-gray-800 flex items-center justify-center text-sm font-semibold border border-gray-700 text-gray-300">
            AD
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-white">Admin Identity</span>
            <span className="text-xs text-gray-500">Root Operator</span>
          </div>
        </div>
      </div>
    </aside>
  );
};


// --- Notification Overlay Component ---

const NotificationCenter: React.FC = () => {
  // Static mock UI for WebSocket alerts integration
  return (
    <div className="fixed top-6 right-6 z-50 flex flex-col gap-3 pointer-events-none">
      <div className="bg-[#121214] border border-green-500/30 shadow-[0_8px_30px_rgb(0,0,0,0.5)] rounded-xl p-4 w-80 transform transition-all duration-300 flex items-start gap-3 backdrop-blur-md">
        <div className="text-green-400 mt-0.5 text-lg">✓</div>
        <div className="flex flex-col">
          <span className="text-sm font-bold text-white tracking-wide">System Connected</span>
          <span className="text-xs text-gray-400 mt-1 leading-relaxed">Real-time control plane WebSockets are actively syncing securely.</span>
        </div>
      </div>
    </div>
  );
};


// --- Dynamic Page Render Mocks (Prevents React Router Crashes) ---

const PagePlaceholder: React.FC<{ title: string; description: string }> = ({ title, description }) => (
  <div className="p-8 h-full flex flex-col animate-fade-in">
    <h1 className="text-3xl font-bold text-white mb-2">{title}</h1>
    <p className="text-gray-400 mb-8">{description}</p>
    <div className="flex-1 border border-gray-800 border-dashed rounded-2xl flex items-center justify-center bg-[#121214]/50 shadow-inner">
      <div className="flex flex-col items-center gap-3">
        <span className="text-4xl">🏗️</span>
        <p className="text-gray-500 text-sm font-medium tracking-wide">Module Interface Pending Assembly</p>
      </div>
    </div>
  </div>
);


// --- Core Routing Architecture ---

const AppRouter: React.FC = () => {
  return (
    <div className="flex min-h-screen bg-[#0a0a0a] text-gray-100 font-sans selection:bg-indigo-500/30">
      <NavSidebar />
      <NotificationCenter />
      
      {/* Offset Main Content to account for fixed Sidebar */}
      <main className="flex-1 ml-64 relative bg-[#0f0f11] shadow-[-10px_0_30px_rgba(0,0,0,0.5)]">
        <Routes>
          <Route path="/" element={<PagePlaceholder title="Dashboard Overview" description="High-level platform telemetry, cluster utilization, and agent network health matrices." />} />
          <Route path="/provisioning" element={<PagePlaceholder title="Provisioning Hub" description="Manage active workspaces, IaC pipelines, and operational CI/CD integration targets." />} />
          <Route path="/topology" element={<PagePlaceholder title="Topology Map" description="Real-time live visual node graph of all registered adapters and physical control services." />} />
          <Route path="/registry" element={<PagePlaceholder title="AI Registry" description="Discover, benchmark, and route traffic to arbitrary LLM providers dynamically across the network." />} />
          <Route path="/governance" element={<PagePlaceholder title="Governance & Cost" description="RBAC configuration logic, exact Audit logging, and ML-extrapolated Spend forecasts." />} />
          <Route path="/analytics" element={<PagePlaceholder title="Analytics" description="Dense time-series mathematical reporting across token utilization density and network latency." />} />
          <Route path="/settings" element={<PagePlaceholder title="Platform Settings" description="Global system configurations, webhook endpoints, and cryptographic API key generation." />} />
          
          <Route path="*" element={
            <div className="p-12">
              <h1 className="text-4xl font-bold text-red-400">404 - Not Found</h1>
              <p className="text-gray-400 mt-4 text-lg">The requested virtual pathway does not exist within the React Routing manifest.</p>
              <Link to="/" className="inline-block mt-8 text-indigo-400 hover:text-indigo-300 font-medium hover:underline">
                &larr; Return to Dashboard Overview
              </Link>
            </div>
          } />
        </Routes>
      </main>
    </div>
  );
};


// --- Application Root Entrypoint ---

const App: React.FC = () => {
  return (
    <GlobalErrorBoundary>
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppRouter />
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </GlobalErrorBoundary>
  );
};

export default App;
