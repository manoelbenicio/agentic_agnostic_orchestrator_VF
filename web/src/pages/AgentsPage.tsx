import React, { useState, useEffect } from 'react';

// --- Types & Interface Definitions ---

type AgentStatus = 'online' | 'offline' | 'busy' | 'restarting';

interface AgentData {
  id: string;
  name: string;
  model_identifier: string;
  status: AgentStatus;
  current_task: string | null;
  uptime_seconds: number;
  tokens_used_today: number;
}

// --- Structural Data Mocks ---

const MOCK_AGENTS: AgentData[] = [
  {
    id: "ag-001",
    name: "Customer Support Router",
    model_identifier: "gpt-4o-mini",
    status: "busy",
    current_task: "Classifying incoming structural ticket #8892...",
    uptime_seconds: 86400 * 3 + 4500, // 3 days, 1.25 hours
    tokens_used_today: 145200
  },
  {
    id: "ag-002",
    name: "RAG Document Parser",
    model_identifier: "claude-3-haiku",
    status: "online",
    current_task: null,
    uptime_seconds: 3600 * 12, // 12 hours
    tokens_used_today: 8900
  },
  {
    id: "ag-003",
    name: "Financial Data Analyzer",
    model_identifier: "gpt-4-turbo",
    status: "offline",
    current_task: null,
    uptime_seconds: 0,
    tokens_used_today: 0
  }
];

// --- Internal Helper Algorithms ---

const formatUptime = (seconds: number): string => {
  if (seconds === 0) return 'Offline';
  const d = Math.floor(seconds / (3600*24));
  const h = Math.floor(seconds % (3600*24) / 3600);
  const m = Math.floor(seconds % 3600 / 60);
  
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  parts.push(`${m}m`);
  
  return parts.join(' ');
};

const formatNumber = (num: number): string => {
  return new Intl.NumberFormat('en-US').format(num);
};


// --- Subcomponents ---

const StatusBadge: React.FC<{ status: AgentStatus }> = ({ status }) => {
  const config = {
    online: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', dot: 'bg-emerald-400', border: 'border-emerald-500/20' },
    busy: { bg: 'bg-amber-500/10', text: 'text-amber-400', dot: 'bg-amber-400 animate-pulse', border: 'border-amber-500/20' },
    offline: { bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-400', border: 'border-red-500/20' },
    restarting: { bg: 'bg-blue-500/10', text: 'text-blue-400', dot: 'bg-blue-400 animate-spin', border: 'border-blue-500/20' }
  };
  
  const active = config[status];
  
  return (
    <div className={`flex items-center gap-2 px-2.5 py-1 rounded-full ${active.bg} border ${active.border} shadow-inner`}>
      <div className={`w-2 h-2 rounded-full shadow-[0_0_8px_currentColor] ${active.text} ${active.dot}`} />
      <span className={`text-[10px] font-bold uppercase tracking-widest ${active.text}`}>
        {status}
      </span>
    </div>
  );
};


// --- Core Fleet Management Screen ---

export const AgentsPage: React.FC = () => {
  const [agents, setAgents] = useState<AgentData[]>(MOCK_AGENTS);

  // Simulates robust WebSocket Real-time synchronization native to AOP topology events
  useEffect(() => {
    const wsUrl = `wss://${window.location.host}/api/v1/topology/ws`;
    console.log("Mounting UI. Simulating persistent WebSocket TCP binding to:", wsUrl);
    
    // Simulate active heartbeat state mutations
    const interval = setInterval(() => {
      setAgents(currentAgents => 
        currentAgents.map(ag => {
          // Resolve restart loops natively
          if (ag.status === 'restarting') {
            return { ...ag, status: 'online', uptime_seconds: 1 };
          }
          // Simulate dynamic stochastic loads parsing RAG queries
          if (ag.id === 'ag-002' && Math.random() > 0.6) {
            const isNowBusy = ag.status === 'online';
            return { 
              ...ag, 
              status: isNowBusy ? 'busy' : 'online',
              current_task: isNowBusy ? 'Ingesting PDF neural array matrices...' : null,
              tokens_used_today: ag.tokens_used_today + (isNowBusy ? Math.floor(Math.random() * 500) : 0)
            };
          }
          // Increment chronological counters natively
          if (ag.status !== 'offline') {
            return { ...ag, uptime_seconds: ag.uptime_seconds + 5 };
          }
          return ag;
        })
      );
    }, 5000);
    
    return () => clearInterval(interval);
  }, []);

  const handleAction = (id: string, action: 'start' | 'stop' | 'restart') => {
    setAgents(current => 
      current.map(ag => {
        if (ag.id === id) {
          if (action === 'stop') return { ...ag, status: 'offline', current_task: null, uptime_seconds: 0 };
          if (action === 'start') return { ...ag, status: 'online', current_task: null, uptime_seconds: 1 };
          if (action === 'restart') return { ...ag, status: 'restarting', current_task: null, uptime_seconds: 0 };
        }
        return ag;
      })
    );
  };

  return (
    <div className="p-10 h-full flex flex-col animate-fade-in text-gray-200">
      
      {/* UI Architecture Header */}
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Agent Fleet Operations</h1>
          <p className="text-gray-400 text-sm">Actively monitor, scale, and orchestrate deployed neural network nodes executing autonomous tasks.</p>
        </div>
        
        <button className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-bold tracking-wide rounded-lg shadow-[0_4px_20px_rgba(79,70,229,0.3)] transition-all flex items-center gap-2 border border-indigo-400/30 hover:-translate-y-0.5">
          <span className="text-lg leading-none">+</span> Deploy Neural Node
        </button>
      </div>

      {/* Grid Network Topology */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {agents.map(agent => (
          <div key={agent.id} className="bg-[#121214] border border-gray-800/80 rounded-2xl p-6 shadow-2xl flex flex-col hover:border-gray-700 transition-all duration-300">
            
            {/* Card Header Structure */}
            <div className="flex items-start justify-between mb-5">
              <div className="pr-4">
                <h3 className="text-lg font-bold text-gray-100 tracking-wide leading-tight">{agent.name}</h3>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-[11px] font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                    {agent.model_identifier}
                  </span>
                  <span className="text-xs text-gray-600 font-mono">{agent.id}</span>
                </div>
              </div>
              <StatusBadge status={agent.status} />
            </div>
            
            {/* Live Numerical Metrics Block */}
            <div className="grid grid-cols-2 gap-3 mb-6 mt-2">
              <div className="bg-[#0a0a0a] rounded-xl p-3 border border-gray-800/50 shadow-inner">
                <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wider mb-1">Total Uptime</p>
                <p className="text-sm font-mono text-gray-300 font-medium">{formatUptime(agent.uptime_seconds)}</p>
              </div>
              <div className="bg-[#0a0a0a] rounded-xl p-3 border border-gray-800/50 shadow-inner">
                <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wider mb-1">Tokens (24h)</p>
                <p className="text-sm font-mono text-gray-300 font-medium">{formatNumber(agent.tokens_used_today)}</p>
              </div>
            </div>

            {/* Dynamic Real-time Context Trace */}
            <div className="flex-1 mb-6">
              <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wider mb-2">Active Execution Trace</p>
              <div className="h-16 bg-black/60 rounded-xl border border-gray-800/80 p-3 overflow-hidden relative shadow-inner">
                {agent.current_task ? (
                  <p className="text-sm text-indigo-300 font-mono flex items-start gap-2 leading-relaxed">
                    <span className="text-indigo-500 mt-0.5 animate-pulse">❯</span> {agent.current_task}
                  </p>
                ) : (
                  <p className="text-sm text-gray-600 font-mono italic flex items-center gap-2 h-full">
                    Awaiting operational dispatch network...
                  </p>
                )}
              </div>
            </div>
            
            {/* Infrastructure Execution Controls */}
            <div className="flex items-center gap-3 border-t border-gray-800/80 pt-5 mt-auto">
              <button 
                onClick={() => handleAction(agent.id, 'start')}
                disabled={agent.status !== 'offline'}
                className="flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-gray-800/50 hover:bg-gray-700 text-gray-300 border border-gray-700/50 hover:border-gray-600"
              >
                Start
              </button>
              
              <button 
                onClick={() => handleAction(agent.id, 'restart')}
                disabled={agent.status === 'offline' || agent.status === 'restarting'}
                className="flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-gray-800/50 hover:bg-gray-700 text-gray-300 border border-gray-700/50 hover:border-gray-600"
              >
                Restart
              </button>
              
              <button 
                onClick={() => handleAction(agent.id, 'stop')}
                disabled={agent.status === 'offline'}
                className="flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-red-950/30 hover:bg-red-900/40 text-red-400 border border-transparent hover:border-red-900/50"
              >
                Stop
              </button>
            </div>
            
          </div>
        ))}
      </div>
    </div>
  );
};

export default AgentsPage;
