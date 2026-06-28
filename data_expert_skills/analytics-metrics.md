# Analytics & Metrics Dashboards

Build enterprise-grade analytics interfaces with Recharts and TypeScript. Complete implementation includes responsive layouts, data formatting utilities, and error handling patterns.

## Workflow

```
Setup Environment → Create Components → Prepare Data → Integrate Dashboard → Validate
```

**Progress:**
- [ ] Step 1: Setup Recharts environment
- [ ] Step 2: Implement chart components
- [ ] Step 3: Prepare formatted data
- [ ] Step 4: Build dashboard layout
- [ ] Step 5: Validate implementation

## Step 1: Setup Recharts Environment

Install required dependencies and configure TypeScript support.

```bash
npm install recharts
npm install @types/recharts --save-dev
```

| Config | Value | Notes |
|--------|-------|-------|
| React Version | 18.2+ | Required for hooks |
| TypeScript | 4.9+ | Enables type safety |
| Peer Dependencies | react-dom, d3-scale | Automatically installed |

## Step 2: Implement Chart Components

### Line Chart with Multiple Metrics

```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface RevenueData {
  month: string;
  revenue: number;
  users: number;
}

function RevenueChart({ data }: { data: RevenueData[] }) {
  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="month" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Line
          type="monotone"
          dataKey="revenue"
          stroke="#3b82f6"
          strokeWidth={2}
          name="Revenue"
        />
        <Line
          type="monotone"
          dataKey="users"
          stroke="#10b981"
          strokeWidth={2}
          name="Users"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

### Error Handling Wrapper

```tsx
function ChartErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full w-full">
      {children}
      <div className="text-center text-gray-500 py-4">
        No data available or invalid data format
      </div>
    </div>
  );
}
```

## Step 3: Prepare Formatted Data

### Sample Sales Data Implementation

```tsx
const salesData = [
  { name: 'Electronics', sales: 4500 },
  { name: 'Clothing', sales: 3200 },
  { name: 'Home', sales: 2800 },
  { name: 'Beauty', sales: 1500 },
];

const pieData = [
  { name: 'Q1', value: 25 },
  { name: 'Q2', value: 35 },
  { name: 'Q3', value: 15 },
  { name: 'Q4', value: 25 },
];
```

## Step 4: Build Dashboard Layout

### Complete Responsive Implementation

```tsx
function Dashboard() {
  return (
    <div className="p-6 space-y-6">
      {/* KPI Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Total Revenue"
          value="$45,231"
          change={12.5}
          trend="up"
        />
        <KPICard
          title="Active Users"
          value="2,345"
          change={8.2}
          trend="up"
        />
        <KPICard
          title="Conversion Rate"
          value="3.2%"
          change={-2.1}
          trend="down"
        />
        <KPICard
          title="Avg. Order Value"
          value="$142"
          change={5.4}
          trend="up"
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg p-6 shadow-sm border lg:col-span-2">
          <h3 className="text-lg font-medium mb-4">Revenue Over Time</h3>
          <RevenueChart data={revenueData} />
        </div>

        <div className="bg-white rounded-lg p-6 shadow-sm border">
          <h3 className="text-lg font-medium mb-4">Sales Distribution</h3>
          <DistributionChart data={pieData} />
        </div>

        <div className="bg-white rounded-lg p-6 shadow-sm border lg:col-span-3">
          <h3 className="text-lg font-medium mb-4">Sales by Category</h3>
          <SalesChart data={salesData} />
        </div>
      </div>
    </div>
  );
}
```

## Step 5: Validate Implementation

### Success Criteria
- All charts render without errors
- Dashboard layout adjusts correctly at different screen sizes
- KPI cards display proper trend indicators
- Data visualizations update with new data input

### Verification Steps
1. Run application locally: `npm run dev`
2. Open browser at http://localhost:3000
3. Verify all components render without console errors
4. Test with different data sets to ensure flexibility
5. Confirm responsive layout works on mobile devices

## Additional Features

### Data Formatting Utilities

```tsx
export function formatNumber(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toLocaleString();
}

export function formatCurrency(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}
```

### Chart Type Comparison

| Chart Type | Best For | Features |
|-----------|----------|----------|
| Line Chart | Trend analysis | Multi-series support, time-based data |
| Bar Chart | Category comparison | Responsive sizing, color coding |
| Pie Chart | Proportional data | Interactive slices, legend support |
| KPI Card | Key metrics | Trend indicators, formatted values |