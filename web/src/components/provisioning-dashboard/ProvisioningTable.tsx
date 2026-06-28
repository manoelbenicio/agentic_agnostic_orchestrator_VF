import React, { useState, useMemo } from 'react';

// --- Types ---
export interface ProvisioningRecord {
  id: string;
  tenant_id: string;
  status: 'PENDING' | 'ACTIVATING' | 'SUCCESS' | 'FAILED' | 'UNKNOWN';
  agent_type: string;
  created_at: string;
}

export interface ProvisioningTableProps {
  data: ProvisioningRecord[];
  onRowClick?: (record: ProvisioningRecord) => void;
  onActionClick?: (action: 'view' | 'retry', record: ProvisioningRecord) => void;
  rowsPerPage?: number;
}

type SortColumn = keyof ProvisioningRecord;
type SortDirection = 'asc' | 'desc';

// --- StatusBadge Component ---
export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  let bgColor = '#f3f4f6'; // gray-100
  let textColor = '#4b5563'; // gray-600

  switch (status.toUpperCase()) {
    case 'SUCCESS':
      bgColor = '#d1fae5'; // emerald-100
      textColor = '#065f46'; // emerald-800
      break;
    case 'FAILED':
      bgColor = '#fee2e2'; // red-100
      textColor = '#991b1b'; // red-800
      break;
    case 'ACTIVATING':
      bgColor = '#dbeafe'; // blue-100
      textColor = '#1e40af'; // blue-800
      break;
    case 'PENDING':
      bgColor = '#fef3c7'; // amber-100
      textColor = '#92400e'; // amber-800
      break;
  }

  return (
    <span style={{
      backgroundColor: bgColor,
      color: textColor,
      padding: '0.35rem 0.75rem',
      borderRadius: '9999px',
      fontSize: '0.75rem',
      fontWeight: '700',
      letterSpacing: '0.025em',
      textTransform: 'uppercase',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center'
    }}>
      {status}
    </span>
  );
};

// --- Main Table Component ---
export const ProvisioningTable: React.FC<ProvisioningTableProps> = ({ 
  data, 
  onRowClick,
  onActionClick,
  rowsPerPage = 10 
}) => {
  const [sortCol, setSortCol] = useState<SortColumn>('created_at');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Sorting Logic Pipeline
  const handleSort = (column: SortColumn) => {
    if (sortCol === column) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(column);
      setSortDir('asc');
    }
    // Automatically reset pagination when sort axis shifts
    setCurrentPage(1);
  };

  const sortedData = useMemo(() => {
    return [...data].sort((a, b) => {
      const valA = a[sortCol];
      const valB = b[sortCol];
      
      if (valA < valB) return sortDir === 'asc' ? -1 : 1;
      if (valA > valB) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [data, sortCol, sortDir]);

  // Pagination Logic Pipeline
  const totalPages = Math.max(1, Math.ceil(sortedData.length / rowsPerPage));
  const startIndex = (currentPage - 1) * rowsPerPage;
  const paginatedData = sortedData.slice(startIndex, startIndex + rowsPerPage);

  const SortIcon = ({ column }: { column: SortColumn }) => {
    if (sortCol !== column) return <span style={{ color: '#d1d5db', marginLeft: '6px', fontSize: '0.8rem' }}>↕</span>;
    return <span style={{ marginLeft: '6px', color: '#2563eb', fontSize: '0.9rem', fontWeight: 'bold' }}>{sortDir === 'asc' ? '↑' : '↓'}</span>;
  };

  return (
    <div style={{ backgroundColor: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)' }}>
      
      {/* Table Canvas */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.95rem' }}>
          <thead style={{ backgroundColor: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
            <tr>
              <th onClick={() => handleSort('id')} style={{ padding: '1rem 1.5rem', cursor: 'pointer', color: '#4b5563', userSelect: 'none', fontWeight: '600' }}>
                ID <SortIcon column="id" />
              </th>
              <th onClick={() => handleSort('tenant_id')} style={{ padding: '1rem 1.5rem', cursor: 'pointer', color: '#4b5563', userSelect: 'none', fontWeight: '600' }}>
                Tenant <SortIcon column="tenant_id" />
              </th>
              <th onClick={() => handleSort('status')} style={{ padding: '1rem 1.5rem', cursor: 'pointer', color: '#4b5563', userSelect: 'none', fontWeight: '600' }}>
                Status <SortIcon column="status" />
              </th>
              <th onClick={() => handleSort('agent_type')} style={{ padding: '1rem 1.5rem', cursor: 'pointer', color: '#4b5563', userSelect: 'none', fontWeight: '600' }}>
                Agent Type <SortIcon column="agent_type" />
              </th>
              <th onClick={() => handleSort('created_at')} style={{ padding: '1rem 1.5rem', cursor: 'pointer', color: '#4b5563', userSelect: 'none', fontWeight: '600' }}>
                Created At <SortIcon column="created_at" />
              </th>
              <th style={{ padding: '1rem 1.5rem', color: '#4b5563', fontWeight: '600' }}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {paginatedData.map((row) => (
              <tr 
                key={row.id} 
                onClick={() => onRowClick && onRowClick(row)}
                style={{ 
                  borderBottom: '1px solid #f3f4f6', 
                  cursor: onRowClick ? 'pointer' : 'default',
                  transition: 'background-color 0.15s ease'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f9fafb'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <td style={{ padding: '1rem 1.5rem', fontFamily: 'ui-monospace, monospace', color: '#4b5563', fontSize: '0.85rem' }}>{row.id.slice(0, 8)}</td>
                <td style={{ padding: '1rem 1.5rem', fontWeight: '600', color: '#111827' }}>{row.tenant_id}</td>
                <td style={{ padding: '1rem 1.5rem' }}><StatusBadge status={row.status} /></td>
                <td style={{ padding: '1rem 1.5rem', color: '#4b5563' }}>{row.agent_type}</td>
                <td style={{ padding: '1rem 1.5rem', color: '#6b7280', fontSize: '0.85rem' }}>{new Date(row.created_at).toLocaleString()}</td>
                
                {/* Actions Cell */}
                <td style={{ padding: '1rem 1.5rem' }} onClick={(e) => e.stopPropagation()}>
                  <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    <button 
                      onClick={() => onActionClick && onActionClick('view', row)}
                      style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: '0.25rem', fontWeight: '600', fontSize: '0.9rem' }}
                    >
                      View
                    </button>
                    {row.status === 'FAILED' && (
                      <button 
                        onClick={() => onActionClick && onActionClick('retry', row)}
                        style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', padding: '0.25rem', fontWeight: '600', fontSize: '0.9rem' }}
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            
            {/* Empty State */}
            {paginatedData.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: '4rem', textAlign: 'center', color: '#6b7280', fontSize: '1rem' }}>
                  No provisioning records available to display.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem 1.5rem', backgroundColor: '#fff', borderTop: '1px solid #e5e7eb' }}>
        <span style={{ fontSize: '0.85rem', color: '#6b7280', fontWeight: '500' }}>
          Showing {sortedData.length === 0 ? 0 : startIndex + 1} to {Math.min(startIndex + rowsPerPage, sortedData.length)} of {sortedData.length} records
        </span>
        
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button 
            disabled={currentPage === 1}
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            style={{ 
              padding: '0.4rem 0.8rem', 
              borderRadius: '6px', 
              border: '1px solid #d1d5db',
              backgroundColor: currentPage === 1 ? '#f9fafb' : '#ffffff',
              color: currentPage === 1 ? '#9ca3af' : '#374151',
              cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              fontSize: '0.85rem',
              transition: 'all 0.2s'
            }}
          >
            Previous
          </button>
          
          <div style={{ padding: '0 0.5rem', fontSize: '0.85rem', fontWeight: '600', color: '#374151' }}>
            Page {currentPage} of {totalPages}
          </div>

          <button 
            disabled={currentPage === totalPages || totalPages === 0}
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            style={{ 
              padding: '0.4rem 0.8rem', 
              borderRadius: '6px', 
              border: '1px solid #d1d5db',
              backgroundColor: (currentPage === totalPages || totalPages === 0) ? '#f9fafb' : '#ffffff',
              color: (currentPage === totalPages || totalPages === 0) ? '#9ca3af' : '#374151',
              cursor: (currentPage === totalPages || totalPages === 0) ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              fontSize: '0.85rem',
              transition: 'all 0.2s'
            }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};

export default ProvisioningTable;
