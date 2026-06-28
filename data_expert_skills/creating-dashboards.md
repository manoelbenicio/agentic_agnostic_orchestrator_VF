# Creating Dashboards

## Workflow

```
Plan Requirements → Choose Architecture → Implement Layout → Add Interactivity → Validate Accessibility
```

**Progress:**
- [ ] Step 1: Define Dashboard Requirements
- [ ] Step 2: Select Architecture & Tools
- [ ] Step 3: Implement Responsive Layout
- [ ] Step 4: Add Real-Time Interactivity
- [ ] Step 5: Validate Accessibility & Performance

## Step 1: Define Dashboard Requirements

Identify key metrics, data sources, and user needs before implementation. Create an inventory of required components:

| Component Type | Quantity | Data Source | Refresh Rate |
|----------------|----------|-------------|------------|
| KPI Cards      | 4        | PostgreSQL  | 5 min      |
| Line Charts    | 2        | REST API    | Real-time  |
| Data Tables    | 1        | CSV File    | Manual     |

### Accessibility Considerations
- Use semantic HTML for screen readers
- Ensure 4.5:1 color contrast ratio
- Add keyboard navigation support
- Provide text alternatives for visualizations

## Step 2: Select Architecture & Tools

### Library Comparison

| Feature                | Tremor               | react-grid-layout    | Combined Approach    |
|------------------------|----------------------|----------------------|----------------------|
| Pre-styled Components  | ✅                   | ❌                   | ✅                   |
| Drag-and-Drop Layout   | ❌                   | ✅                   | ✅                   |
| Responsive Grid        | ✅                   | ✅                   | ✅                   |
| Customization Flexibility | ❌ (Limited)       | ✅                   | ✅                   |

### Installation
```bash
# For Tremor (quick dashboards)
npm install @tremor/react

# For customizable layouts
npm install react-grid-layout
```

## Step 3: Implement Responsive Layout

### Base Layout Structure
```tsx
import { Grid } from '@tremor/react';
import { Responsive, WidthProvider } from 'react-grid-layout';

const ResponsiveGridLayout = WidthProvider(Responsive);

function DashboardLayout() {
  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={dashboardLayout}
      breakpoints={{ lg: 1200, md: 996, sm: 768 }}
      cols={{ lg: 12, md: 10, sm: 6 }}
      rowHeight={60}
    >
      <div key="kpi-1" data-grid={{ x: 0, y: 0, w: 3, h: 2 }}>
        <KPICard title="Revenue" value="$1.2M" trend="15.3%" />
      </div>
      <div key="chart-1" data-grid={{ x: 3, y: 0, w: 6, h: 4 }}>
        <ResponsiveChart data={revenueData} />
      </div>
    </ResponsiveGridLayout>
  );
}
```

### Responsive Breakpoints
```css
/* Custom media queries for consistent layout */
@media (min-width: 1200px) {
  .dashboard-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
@media (max-width: 768px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
```

## Step 4: Add Real-Time Interactivity

### Data Fetching with Error Handling
```tsx
function useDashboardData() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('/api/dashboard-data');
        if (!response.ok) throw new Error('Network response failed');
        
        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err.message);
        console.error('Dashboard data fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  return { data, error, loading };
}
```

### Real-Time Updates with SSE
```tsx
function setupRealTimeUpdates(onUpdate) {
  const eventSource = new EventSource('/api/updates');
  
  eventSource.addEventListener('dashboard', (event) => {
    const update = JSON.parse(event.data);
    onUpdate(update);
  });

  eventSource.onerror = () => {
    console.log('SSE connection lost. Reconnecting...');
    setTimeout(() => setupRealTimeUpdates(onUpdate), 5000);
  };

  return () => eventSource.close();
}
```

## Step 5: Validate Accessibility & Performance

### Accessibility Testing Checklist
- [ ] All interactive elements keyboard accessible
- [ ] Screen reader announcements for dynamic updates
- [ ] Sufficient color contrast across components
- [ ] Semantic HTML structure (ARIA roles where needed)
- [ ] Resize text capability up to 200%

### Performance Metrics
Run performance analysis:
```bash
# Analyze dashboard performance
python scripts/optimize-dashboard-performance.py --analyze dashboard-config.json
```

### Validation Code
```tsx
// Test real-time updates
function testRealTimeUpdates() {
  const mockData = { widgetId: 'kpi-1', data: { value: '$1.5M', trend: '20%' } };
  const updateHandler = jest.fn();
  
  const cleanup = setupRealTimeUpdates(updateHandler);
  simulateSSEMessage(mockData);
  
  expect(updateHandler).toHaveBeenCalledWith(mockData);
  cleanup();
}
```

## Complete Implementation Example

### Full Dashboard Component
```tsx
import { Card, Grid, Metric, Text, BadgeDelta } from '@tremor/react';
import { useState, useEffect } from 'react';

function SalesDashboard() {
  const [revenue, setRevenue] = useState(0);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/sales-data');
      const data = await response.json();
      setRevenue(data.revenue);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching sales data:', error);
      setLoading(false);
    }
  };

  return (
    <Grid numItems={1} numItemsSm={2} numItemsLg={4} className="gap-4 p-4">
      <Card>
        <Text>Sales Revenue</Text>
        <Metric>{loading ? 'Loading...' : `$${revenue.toLocaleString()}`}</Metric>
        <BadgeDelta deltaType="increase">+12.5%</BadgeDelta>
      </Card>
      
      {/* Add more widgets here */}
      
      <div className="lg:col-span-4 mt-8">
        <Text>Performance Trends</Text>
        {/* Add chart component here */}
      </div>
    </Grid>
  );
}
```

## Maintenance & Optimization

### Performance Optimization Patterns
```tsx
// Lazy loading for non-critical widgets
const LazyWidget = ({ widgetType, data }) => {
  const [loaded, setLoaded] = useState(false);
  
  useEffect(() => {
    const timer = setTimeout(() => setLoaded(true), 500);
    return () => clearTimeout(timer);
  }, []);

  if (!loaded) return <WidgetSkeleton />;
  
  return <WidgetRenderer type={widgetType} data={data} />;
};
```

### Error Handling Best Practices
```tsx
// Global error boundary for widgets
class WidgetErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    logErrorToMyService(error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-state">
          <h3>Something went wrong.</h3>
          <button onClick={() => this.setState({ hasError: false })}>Try again</button>
        </div>
      );
    }

    return this.props.children;
  }
}
```