import React, { useState } from 'react';

// --- Global Types ---
type TabIdentifier = 'RBAC' | 'AUDIT' | 'COST';

// --- Mock Data Payloads ---
const ROLES = ['Super Admin', 'Tenant Owner', 'Developer', 'Viewer'];
const PERMISSIONS = [
  'manage_users', 
  'manage_keys', 
  'view_metrics', 
  'use_llm', 
  'provision_resources',
  'view_audit_logs'
];

const AUDIT_LOGS = [
  { id: 'log-1', actor: 'admin@aop.sys', action: 'CREATE_KEY', resource: 'tenant-a-key-prod', timestamp: '2024-03-12T10:00:00Z' },
  { id: 'log-2', actor: 'dev@tenant.com', action: 'PROVISION_DB', resource: 'postgres-analytics', timestamp: '2024-03-12T10:15:00Z' },
  { id: 'log-3', actor: 'admin@aop.sys', action: 'UPDATE_ROLE', resource: 'user_123', timestamp: '2024-03-13T11:00:00Z' },
  { id: 'log-4', actor: 'viewer@tenant.com', action: 'VIEW_DASHBOARD', resource: 'metrics_dashboard', timestamp: '2024-03-13T12:00:00Z' },
  { id: 'log-5', actor: 'system', action: 'REVOKE_KEY', resource: 'tenant-b-key-dev', timestamp: '2024-03-14T09:30:00Z' },
];

const COST_DATA = [
  { entity: 'Tenant Alpha', cost: 12450.50, type: 'tenant' },
  { entity: 'Tenant Beta', cost: 8900.20, type: 'tenant' },
  { entity: 'Project Phoenix', cost: 5400.00, type: 'project' },
  { entity: 'Project Apollo', cost: 3100.00, type: 'project' },
  { model: 'GPT-4o', cost: 9500.00, type: 'model' },
  { model: 'Claude 3 Opus', cost: 6200.00, type: 'model' },
  { model: 'Gemini 1.5 Pro', cost: 4300.00, type: 'model' },
];

// --- Sub-components ---

const RBACTab: React.FC = () => {
  return (
    <div style={{ backgroundColor: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '2rem', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ margin: '0 0 0.25rem 0', fontSize: '1.25rem', color: '#111827', fontWeight: '700' }}>Role-Based Access Control Matrix</h2>
        <p style={{ margin: 0, color: '#6b7280', fontSize: '0.9rem' }}>Comprehensive overview of capability mapping across structural platform roles.</p>
      </div>

      <div style={{ overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: '8px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'center', fontSize: '0.9rem' }}>
          <thead>
            <tr>
              <th style={{ padding: '1.25rem 1rem', borderBottom: '2px solid #e5e7eb', textAlign: 'left', color: '#374151', backgroundColor: '#f9fafb', fontWeight: '600' }}>Platform Permission</th>
              {ROLES.map(role => (
                <th key={role} style={{ padding: '1.25rem 1rem', borderBottom: '2px solid #e5e7eb', color: '#374151', backgroundColor: '#f9fafb', fontWeight: '600' }}>{role}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PERMISSIONS.map(perm => (
              <tr key={perm} style={{ borderBottom: '1px solid #f3f4f6', transition: 'background-color 0.15s' }} onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f9fafb'} onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#fff'}>
                <td style={{ padding: '1.25rem 1rem', textAlign: 'left', fontFamily: 'ui-monospace, monospace', color: '#111827', fontWeight: 500, fontSize: '0.85rem' }}>{perm}</td>
                {ROLES.map(role => {
                  // Basic mockup of logical RBAC allocations
                  let hasPerm = false;
                  if (role === 'Super Admin') hasPerm = true;
                  else if (role === 'Tenant Owner' && perm !== 'provision_resources') hasPerm = true;
                  else if (role === 'Developer' && ['view_metrics', 'use_llm', 'manage_keys'].includes(perm)) hasPerm = true;
                  else if (role === 'Viewer' && perm === 'view_metrics') hasPerm = true;

                  return (
                    <td key={role} style={{ padding: '1rem' }}>
                      {hasPerm ? (
                        <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '24px', height: '24px', backgroundColor: '#d1fae5', color: '#059669', borderRadius: '50%', fontWeight: 'bold' }}>✓</div>
                      ) : (
                        <span style={{ color: '#d1d5db', fontWeight: 'bold' }}>—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};


const AuditTab: React.FC = () => {
  const [search, setSearch] = useState('');
  
  const filtered = AUDIT_LOGS.filter(log => 
    log.actor.toLowerCase().includes(search.toLowerCase()) || 
    log.action.toLowerCase().includes(search.toLowerCase()) ||
    log.resource.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ backgroundColor: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '2rem', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ margin: '0 0 0.25rem 0', fontSize: '1.25rem', color: '#111827', fontWeight: '700' }}>System Audit Trail</h2>
          <p style={{ margin: 0, color: '#6b7280', fontSize: '0.9rem' }}>Immutable ledger tracking critical platform interactions.</p>
        </div>
        <input 
          type="text" 
          placeholder="Search actor, action, or resource..." 
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: '0.6rem 1rem', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', maxWidth: '350px', outline: 'none', fontSize: '0.95rem' }}
        />
      </div>
      
      <div style={{ overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: '8px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
          <thead style={{ backgroundColor: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
            <tr>
              <th style={{ padding: '1rem', color: '#374151', fontWeight: '600' }}>Timestamp</th>
              <th style={{ padding: '1rem', color: '#374151', fontWeight: '600' }}>Actor</th>
              <th style={{ padding: '1rem', color: '#374151', fontWeight: '600' }}>Action Event</th>
              <th style={{ padding: '1rem', color: '#374151', fontWeight: '600' }}>Target Resource</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(log => (
              <tr key={log.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '1rem', color: '#6b7280', fontSize: '0.85rem' }}>{new Date(log.timestamp).toLocaleString()}</td>
                <td style={{ padding: '1rem', fontWeight: 600, color: '#111827' }}>{log.actor}</td>
                <td style={{ padding: '1rem', fontFamily: 'ui-monospace, monospace', color: '#2563eb', fontSize: '0.85rem' }}>{log.action}</td>
                <td style={{ padding: '1rem', color: '#4b5563' }}>{log.resource}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} style={{ padding: '3rem', textAlign: 'center', color: '#6b7280' }}>
                  No matching audit logs found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};


const CostAllocationTab: React.FC = () => {
  const [dateRange, setDateRange] = useState('Last 30 Days');

  // Renders a pure CSS bar chart layout utilizing standard divs
  const renderBarChart = (type: string, title: string) => {
    const data = COST_DATA.filter(d => d.type === type);
    // Determine the ceiling for relative bar lengths
    const max = Math.max(...data.map(d => d.cost));

    return (
      <div style={{ flex: '1 1 300px', backgroundColor: '#f9fafb', padding: '1.5rem', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
        <h3 style={{ margin: '0 0 1.5rem 0', fontSize: '1.05rem', color: '#111827', fontWeight: '600' }}>{title}</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {data.map(item => {
            const width = `${(item.cost / max) * 100}%`;
            return (
              <div key={item.entity || item.model}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem', fontSize: '0.9rem' }}>
                  <span style={{ fontWeight: 600, color: '#374151' }}>{item.entity || item.model}</span>
                  <span style={{ color: '#4b5563', fontFamily: 'monospace' }}>
                    ${item.cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div style={{ width: '100%', height: '10px', backgroundColor: '#e5e7eb', borderRadius: '999px', overflow: 'hidden' }}>
                  <div style={{ width, height: '100%', backgroundColor: '#3b82f6', borderRadius: '999px', transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)' }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div style={{ backgroundColor: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '2rem', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ margin: '0 0 0.25rem 0', fontSize: '1.25rem', color: '#111827', fontWeight: '700' }}>Cost Allocation & Spend Dynamics</h2>
          <p style={{ margin: 0, fontSize: '0.9rem', color: '#6b7280' }}>Track token usage and aggregated infrastructure costs across logical bounds.</p>
        </div>
        <select 
          value={dateRange}
          onChange={(e) => setDateRange(e.target.value)}
          style={{ padding: '0.6rem 1rem', borderRadius: '8px', border: '1px solid #d1d5db', outline: 'none', backgroundColor: '#fff', fontSize: '0.95rem', cursor: 'pointer' }}
        >
          <option>Last 7 Days</option>
          <option>Last 30 Days</option>
          <option>This Quarter</option>
          <option>Year to Date</option>
        </select>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2rem' }}>
        {renderBarChart('tenant', 'Spend by Tenant')}
        {renderBarChart('project', 'Spend by Project')}
        {renderBarChart('model', 'Spend by LLM Model')}
      </div>
    </div>
  );
};


// --- Main Orchestration Page ---
export const GovernancePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabIdentifier>('RBAC');

  const tabs: { id: TabIdentifier; label: string; icon: string }[] = [
    { id: 'RBAC', label: 'Role-Based Access', icon: '🛡️' },
    { id: 'AUDIT', label: 'Audit Trail', icon: '📜' },
    { id: 'COST', label: 'Cost Allocation', icon: '💸' },
  ];

  return (
    <div style={{ padding: '2.5rem', maxWidth: '1440px', margin: '0 auto', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      
      {/* Page Header */}
      <header style={{ marginBottom: '3rem' }}>
        <h1 style={{ margin: '0 0 0.5rem 0', fontSize: '2.5rem', fontWeight: 800, color: '#111827', letterSpacing: '-0.025em' }}>
          Platform Governance
        </h1>
        <p style={{ margin: 0, color: '#6b7280', fontSize: '1.1rem' }}>
          Centralized oversight of security policies, system auditing, and financial reporting.
        </p>
      </header>

      {/* Tabs Navigation */}
      <div style={{ display: 'flex', gap: '1rem', borderBottom: '2px solid #e5e7eb', marginBottom: '2.5rem', overflowX: 'auto' }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0.85rem 1.5rem',
              backgroundColor: 'transparent',
              border: 'none',
              borderBottom: activeTab === tab.id ? '3px solid #2563eb' : '3px solid transparent',
              color: activeTab === tab.id ? '#2563eb' : '#6b7280',
              fontWeight: activeTab === tab.id ? 700 : 500,
              fontSize: '1.05rem',
              cursor: 'pointer',
              marginBottom: '-2px', // Pull down to cover border perfectly
              transition: 'all 0.2s ease',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              whiteSpace: 'nowrap'
            }}
          >
            <span>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Render Active Tab Context */}
      <div style={{ animation: 'fadeIn 0.3s ease-in-out' }}>
        <style>{`
          @keyframes fadeIn {
            from { opacity: 0; transform: translateY(5px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}</style>
        
        {activeTab === 'RBAC' && <RBACTab />}
        {activeTab === 'AUDIT' && <AuditTab />}
        {activeTab === 'COST' && <CostAllocationTab />}
      </div>
      
    </div>
  );
};

export default GovernancePage;
