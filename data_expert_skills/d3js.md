# Custom Data Visualizations with D3.js

Create powerful, custom data visualizations using D3.js for complete control over SVG elements, transitions, and data binding.

## Workflow

```
Setup Environment → Data Binding → Create Elements → Add Interactivity → Optimize & Validate
```

**Progress:**
- [ ] Step 1: Setup Environment
- [ ] Step 2: Data Binding & Scales
- [ ] Step 3: Create Visualization Elements
- [ ] Step 4: Add Interactivity & Animations
- [ ] Step 5: Optimize & Validate

## Step 1: Setup Environment

Initialize D3.js environment using CDN for quick prototyping or NPM for production applications.

```bash
# Install via NPM (recommended for production)
npm install d3
```

```javascript
// Import specific modules (ES6+)
import { select, scaleLinear, axisBottom } from 'd3';
```

| Setup Type | Implementation | Notes |
|-----------|----------------|-------|
| CDN | `<script src="https://d3js.org/d3.v7.min.js"></script>` | Quick start, no build tools needed |
| NPM | `npm install d3` + ES6 imports | Better for modular applications |

## Step 2: Data Binding & Scales

Bind data to DOM elements and create scales for data transformation.

```javascript
// Data binding example
const circles = d3.select('#chart')
  .selectAll('circle')
  .data(dataset)
  .enter()
  .append('circle')
  .attr('cx', d => xScale(d.x))
  .attr('cy', d => yScale(d.y));

// Scale creation
const xScale = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.x)])
  .range([0, width]);
```

## Step 3: Create Visualization Elements

Implement different visualization types with proper SVG elements.

```javascript
// Bar chart implementation
svg.selectAll('.bar')
  .data(data)
  .enter()
  .append('rect')
  .attr('class', 'bar')
  .attr('x', d => xScale(d.category))
  .attr('y', d => yScale(d.value))
  .attr('width', xScale.bandwidth())
  .attr('height', d => height - yScale(d.value));
```

## Step 4: Add Interactivity & Animations

Implement transitions and user interactions.

```javascript
// Tooltip implementation
const tooltip = d3.select('body')
  .append('div')
  .attr('class', 'tooltip')
  .style('opacity', 0);

// Add event listeners
circles
  .on('mouseover', function(event, d) {
    tooltip.transition().duration(200).style('opacity', .9);
    tooltip.html(`${d.category}: ${d.value}`)
      .style('left', (event.pageX + 10) + 'px');
  })
  .on('mouseout', function(d) {
    tooltip.transition().duration(500).style('opacity', 0);
  });
```

## Step 5: Optimize & Validate

Implement performance optimizations and accessibility features.

```javascript
// Error handling pattern
d3.csv('../data/timeseries.csv').then(data => {
  // Process data
}).catch(error => {
  console.error('Error loading data:', error);
});

// Responsive resize handler
function resize() {
  const container = d3.select('#chart').node();
  const width = container.getBoundingClientRect().width;
  xScale.range([0, width]);
  svg.attr('width', width);
}

window.addEventListener('resize', resize);
```

| Optimization | Implementation | Benefit |
|-------------|----------------|---------|
| Debouncing | `d3.throttle()` | Limits frequent events |
| Canvas | `d3.select('canvas')` | Better for large datasets |
| Web Workers | `new Worker()` | Offloads heavy computations |

## Complete Examples

### Force-Directed Network Graph (Complete)
```javascript
// Network data
const nodes = [
  { id: 'A', group: 1 },
  { id: 'B', group: 1 },
  { id: 'C', group: 2 },
  { id: 'D', group: 2 },
  { id: 'E', group: 3 }
];

const links = [
  { source: 'A', target: 'B', value: 1 },
  { source: 'B', target: 'C', value: 2 },
  { source: 'C', target: 'D', value: 1 },
  { source: 'D', target: 'E', value: 3 },
  { source: 'E', target: 'A', value: 2 }
];

// Create force simulation
const simulation = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(links).id(d => d.id))
  .force('charge', d3.forceManyBody().strength(-200))
  .force('center', d3.forceCenter(width / 2, height / 2));

// Draw links
const link = svg.append('g')
  .selectAll('line')
  .data(links)
  .enter()
  .append('line')
  .style('stroke', '#999')
  .style('stroke-width', d => Math.sqrt(d.value));

// Draw nodes
const node = svg.append('g')
  .selectAll('circle')
  .data(nodes)
  .enter()
  .append('circle')
  .attr('r', 10)
  .style('fill', d => d3.schemeCategory10[d.group])
  .call(d3.drag()
    .on('start', dragstarted)
    .on('drag', dragged)
    .on('end', dragended));

// Add labels
const label = svg.append('g')
  .selectAll('text')
  .data(nodes)
  .enter()
  .append('text')
  .text(d => d.id)
  .style('font-size', '12px')
  .attr('dx', 12)
  .attr('dy', 4);

// Update positions on tick
simulation.on('tick', () => {
  link
    .attr('x1', d => d.source.x)
    .attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y);

  node
    .attr('cx', d => d.x)
    .attr('cy', d => d.y);

  label
    .attr('x', d => d.x)
    .attr('y', d => d.y);
});

// Drag functions
function dragstarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x;
  d.fy = d.y;
}

function dragged(event, d) {
  d.fx = event.x;
  d.fy = event.y;
}

function dragended(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}
```

## Accessibility Considerations

1. Add ARIA labels to visualization elements
2. Ensure keyboard navigation support
3. Use colorblind-friendly palettes
4. Provide text alternatives for screen readers

```javascript
// Accessible element example
circle
  .attr('aria-label', d => `Value: ${d.value}`)
  .attr('role', 'img')
  .attr('tabindex', 0);
```