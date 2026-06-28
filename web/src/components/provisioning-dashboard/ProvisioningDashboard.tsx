import React, { useState, useEffect } from 'react';

// --- Types ---
export interface ProvisioningRequest {
  id: string;
  tenant_id: string;
  resource_type: string;
  status: 'PENDING' | 'ACTIVATING' | 'SUCCESS' | 'FAILED';
  created_at: string;
  updated_at: string;
}

// --- Subcomponents ---

const StatsCard: React.FC<{ title: string; value: number; color?: string }> = ({ title, value, color = '#333' }) => (
  <div style={{ 
    padding: '1.5rem', 
    border: '1px solid #eaeaea', 
    borderRadius: '12px', 
    flex: 1, 
    backgroundColor: '#fff', 
    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)' 
  }}>
    <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '0.85rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{title}</h3>
    <p style={{ margin: 0, fontSize: '2.5rem', fontWeight: '800', color }}>{value}</p>
  </div>
);

const SearchBar: React.FC<{ value: string; onChange: (v: string) => void }> = ({ value, onChange }) => (
  <input
    type="text"
    placeholder="Search by ID or Tenant..."
    value={value}
    onChange={(e) => onChange(e.target.value)}
    style={{ 
      padding: '0.6rem 1rem', 
      borderRadius: '8px', 
      border: '1px solid #d1d5db', 
      width: '100%',
      maxWidth: '350px',
      fontSize: '0.95rem',
      outline: 'none',
      transition: 'border-color 0.2s'
    }}
  />
);

const StatusFilter: React.FC<{ value: string; onChange: (v: string) => void }> = ({ value, onChange }) => (
  <select 
    value={value} 
    onChange={(e) => onChange(e.target.value)}
    style={{ 
      padding: '0.6rem 1rem', 
      borderRadius: '8px', 
      border: '1px solid #d1d5db', 
      fontSize: '0.95rem', 
      cursor: 'pointer',
      backgroundColor: '#fff',
      outline: 'none'
    }}
  >
    <option value="ALL">All Statuses</option>
    <option value="PENDING">Pending</option>
    <option value="ACTIVATING">Activating</option>
    <option value="SUCCESS">Success</option>
    <option value="FAILED">Failed</option>
  </select>
);

const RefreshButton: React.FC<{ onRefresh: () => void; autoRefresh: boolean; setAutoRefresh: (v: boolean) => void }> = ({ onRefresh, autoRefresh, setAutoRefresh }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', backgroundColor: '#f9fafb', padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid #eaeaea' }}>
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', cursor: 'pointer', color: '#4b5563', fontWeight: '500' }}>
      <input 
        type="checkbox" 
        checked={autoRefresh} 
        onChange={(e) => setAutoRefresh(e.target.checked)} 
        style={{ cursor: 'pointer', width: '16px', height: '16px' }}
      />
      Auto-refresh (5s)
    </label>
    <div style={{ width: '1px', height: '24px', backgroundColor: '#d1d5db' }}></div>
    <button 
      onClick={onRefresh}
      style={{ 
        padding: '0.5rem 1.2rem', 
        backgroundColor: '#2563eb', 
        color: 'white', 
        border: 'none', 
        borderRadius: '6px', 
        cursor: 'pointer', 
        fontWeight: '600',
        fontSize: '0.9rem',
        boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)'
      }}
    >
      Refresh Now
    </button>
  </div>
);

const ProvisioningTable: React.FC<{ data: ProvisioningRequest[]; onSort: (col: keyof ProvisioningRequest) => void }> = ({ data, onSort }) => {
  const getStatusColor = (status: string) => {
    switch(status) {
      case 'SUCCESS': return '#10b981'; // emerald
      case 'FAILED': return '#ef4444'; // red
      case 'ACTIVATING': return '#3b82f6'; // blue
      default: return '#f59e0b'; // amber
    }
  };

  return (
    <div style={{ overflowX: 'auto', border: '1px solid #eaeaea', borderRadius: '12px', marginTop: '1.5rem', backgroundColor: '#fff', boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.95rem' }}>
        <thead style={{ backgroundColor: '#f9fafb', borderBottom: '2px solid #eaeaea' }}>
          <tr>
            <th onClick={() => onSort('id')} style={{ padding: '1rem', cursor: 'pointer', color: '#374151', userSelect: 'none' }}>ID ↕</th>
            <th onClick={() => onSort('tenant_id')} style={{ padding: '1rem', cursor: 'pointer', color: '#374151', userSelect: 'none' }}>Tenant ID ↕</th>
            <th onClick={() => onSort('resource_type')} style={{ padding: '1rem', cursor: 'pointer', color: '#374151', userSelect: 'none' }}>Resource ↕</th>
            <th onClick={() => onSort('status')} style={{ padding: '1rem', cursor: 'pointer', color: '#374151', userSelect: 'none' }}>Status ↕</th>
            <th onClick={() => onSort('created_at')} style={{ padding: '1rem', cursor: 'pointer', color: '#374151', userSelect: 'none' }}>Created ↕</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.id} style={{ borderBottom: '1px solid #eaeaea', transition: 'background-color 0.15s' }} onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f9fafb'} onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#fff'}>
              <td style={{ padding: '1rem', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', color: '#4b5563' }}>{row.id.slice(0, 8)}...</td>
              <td style={{ padding: '1rem', fontWeight: '500', color: '#111827' }}>{row.tenant_id}</td>
              <td style={{ padding: '1rem', color: '#4b5563' }}>{row.resource_type}</td>
              <td style={{ padding: '1rem' }}>
                <span style={{ 
                  padding: '0.25rem 0.75rem', 
                  borderRadius: '9999px', 
                  fontSize: '0.75rem',
                  fontWeight: '700',
                  letterSpacing: '0.025em',
                  backgroundColor: `${getStatusColor(row.status)}15`,
                  color: getStatusColor(row.status)
                }}>
                  {row.status}
                </span>
              </td>
              <td style={{ padding: '1rem', color: '#6b7280', fontSize: '0.85rem' }}>{new Date(row.created_at).toLocaleString()}</td>
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td colSpan={5} style={{ padding: '3rem', textAlign: 'center', color: '#6b7280', fontSize: '1rem' }}>No provisioning requests found matching the criteria.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

// --- Main Dashboard Component ---

export const ProvisioningDashboard: React.FC = () => {
  const [data, setData] = useState<ProvisioningRequest[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [sortCol, setSortCol] = useState<keyof ProvisioningRequest>('created_at');
  const [sortDesc, setSortDesc] = useState(true);

  // Mock data fetching (in production this would hit /api/provisioning/requests)
  const fetchData = async () => {
    // console.log("Fetching provisioning data...");
    setData([
      { id: 'req-1a2b3c4d5e', tenant_id: 'tenant-alpha', resource_type: 'postgres-db', status: 'SUCCESS', created_at: '2024-03-10T10:00:00Z', updated_at: '2024-03-10T10:05:00Z' },
      { id: 'req-2b3c4d5e6f', tenant_id: 'tenant-beta', resource_type: 'redis-cache', status: 'PENDING', created_at: '2024-03-11T11:00:00Z', updated_at: '2024-03-11T11:00:00Z' },
      { id: 'req-3c4d5e6f7g', tenant_id: 'tenant-alpha', resource_type: 'llm-endpoint', status: 'FAILED', created_at: '2024-03-12T12:00:00Z', updated_at: '2024-03-12T12:01:00Z' },
      { id: 'req-4d5e6f7g8h', tenant_id: 'tenant-gamma', resource_type: 'postgres-db', status: 'ACTIVATING', created_at: '2024-03-12T13:00:00Z', updated_at: '2024-03-12T13:00:00Z' },
    ]);
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    // Set polling interval for auto-refresh
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const handleSort = (col: keyof ProvisioningRequest) => {
    if (sortCol === col) {
      setSortDesc(!sortDesc);
    } else {
      setSortCol(col);
      setSortDesc(false);
    }
  };

  // Filter & Sort Logic Pipeline
  const filteredData = data
    .filter(req => statusFilter === 'ALL' || req.status === statusFilter)
    .filter(req => 
      req.id.toLowerCase().includes(search.toLowerCase()) || 
      req.tenant_id.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      if (a[sortCol] < b[sortCol]) return sortDesc ? 1 : -1;
      if (a[sortCol] > b[sortCol]) return sortDesc ? -1 : 1;
      return 0;
    });

  const stats = {
    total: data.length,
    active: data.filter(d => d.status === 'ACTIVATING' || d.status === 'SUCCESS').length,
    pending: data.filter(d => d.status === 'PENDING').length,
    failed: data.filter(d => d.status === 'FAILED').length,
  };

  return (
    <div style={{ padding: '2.5rem', maxWidth: '1280px', margin: '0 auto', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2.5rem' }}>
        <div>
          <h1 style={{ margin: '0 0 0.25rem 0', fontSize: '2rem', color: '#111827', fontWeight: '800' }}>Provisioning Operations</h1>
          <p style={{ margin: 0, color: '#6b7280', fontSize: '1rem' }}>Monitor and manage automated tenant resource provisioning.</p>
        </div>
        <RefreshButton onRefresh={fetchData} autoRefresh={autoRefresh} setAutoRefresh={setAutoRefresh} />
      </header>

      {/* Analytics Cards Row */}
      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '2.5rem', flexWrap: 'wrap' }}>
        <StatsCard title="Total Requests" value={stats.total} />
        <StatsCard title="Active / Success" value={stats.active} color="#10b981" />
        <StatsCard title="Pending" value={stats.pending} color="#f59e0b" />
        <StatsCard title="Failed" value={stats.failed} color="#ef4444" />
      </div>

      {/* Dashboard Controls */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', alignItems: 'center' }}>
        <SearchBar value={search} onChange={setSearch} />
        <StatusFilter value={statusFilter} onChange={setStatusFilter} />
        <div style={{ flex: 1 }}></div>
        <span style={{ color: '#6b7280', fontSize: '0.9rem' }}>Showing {filteredData.length} records</span>
      </div>

      {/* Main Datagrid */}
      <ProvisioningTable data={filteredData} onSort={handleSort} />
      
    </div>
  );
};

export default ProvisioningDashboard;
