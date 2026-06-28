---
name: "Tableau"
description: "Master Tableau Public/Desktop for creating sophisticated visualizations, dashboards, and compelling data storytelling"
category: "Visualization"
level: "Intermediate"
duration: "5-7 weeks"
---

# Tableau

## Quick Start

Tableau is industry-leading for visualization and data storytelling. Within your first week, you'll load data and create interactive visualizations. By week four, you'll build story-driven dashboards that guide users to insights.

**First Task (30 minutes):**
1. Download Tableau Public (free)
2. Load a sample CSV dataset
3. Create a bar chart and geographic map
4. Add filters and interactive dashboard
5. Publish to Tableau Public for sharing

## Key Concepts

### 1. Data Connection & Preparation
**What it is:** Connecting to data sources and preparing for analysis.

**Supported Data Sources:**
```
Files:
- Excel, CSV, JSON, PDF
- Spatial files (shapefiles)

Databases:
- SQL Server, PostgreSQL, MySQL
- Oracle, Google BigQuery
- Snowflake, Redshift

Cloud Services:
- Salesforce, Google Analytics
- Marketo, ServiceNow
- Cloud data warehouses

Real-time:
- REST APIs with continuous refresh
- Live database connections
```

**Data Preparation:**
```
Tableau Prep Builder:
- Visual ETL tool (alternative to Power Query)
- Clean and shape data before connecting
- Remove nulls, fix data types
- Join and union multiple datasets
- Create new fields

In Tableau Desktop:
- Data Source page: Set field roles
- Calculated fields: Create new metrics
- Sets & Groups: Segment data
- Filters: Exclude data during analysis
```

### 2. Dimensions vs. Measures
**What it is:** Data is categorized as descriptive (dimensions) or numeric (measures).

**Dimensions (Categorical):**
```
Qualitative attributes - answer "What?"
- Region, Product, Date, Category
- Customer Name, Country
- Create rows/columns in visualizations
- Typically discrete (separate values)

In Tableau:
- Shown in blue color by default
- Create axis labels and groups
```

**Measures (Quantitative):**
```
Numeric values - answer "How Much?"
- Sales, Profit, Quantity, Price
- Count, Percentage, Average
- Create axes in visualizations
- Typically continuous (ranges)

In Tableau:
- Shown in green color by default
- Aggregated (SUM, AVG, COUNT)
- Create scales and trends
```

**Example:**
```
Dimension: Product Category (Furniture, Technology, Office Supplies)
Measure: Sales Revenue ($)

Visualization:
Bar chart with Product on axis, Revenue as height
Each bar = sum of revenue for that category
```

### 3. Building Visualizations
**What it is:** Creating charts and graphs tailored to your data story.

**Common Chart Types:**
```
Comparison (Categorical):
- Bar chart: Rank categories
- Grouped bar: Compare across multiple dimensions
- Bullet chart: Progress vs. target

Trends (Time-based):
- Line chart: Sales over months
- Area chart: Cumulative trends
- Combination: Line + Bar for comparison

Part-to-Whole:
- Pie/Donut: Market share
- Treemap: Hierarchical breakdown
- Stacked bar: Composition breakdown

Relationship:
- Scatter plot: Correlation
- Bubble: Three dimensions (x, y, size)
- Highlight table: Heatmap

Geographic:
- Map: Regional analysis
- Filled map: Choropleth (color by value)
- Symbol map: Locations with size/color

Distribution:
- Histogram: Frequency distribution
- Box plot: Quartile summary
```

**Visualization Building Blocks:**
```
Shelves (Tableau interface):
- Columns: What goes on X-axis
- Rows: What goes on Y-axis
- Marks: Color, Size, Detail, Tooltip
- Filters: What to include/exclude

Example - Sales by Product by Region:
Columns: Product
Rows: Region
Marks Color: Sales amount
Filter: Only 2024 data

Result: Colored matrix showing sales breakdown
```

### 4. Dashboards & Stories
**What it is:** Combining multiple visualizations into interactive narratives.

**Dashboard Components:**
```
Layout:
- Sheets: Individual visualizations
- Containers: Organize and align objects
- Text & Images: Add context

Interactivity:
- Filters: User-controlled filtering
- Parameters: Allow users to adjust values
- Action Filters: Click one sheet to filter others
- Hover Actions: Show details on mouseover

Design Principles:
- One primary message per dashboard
- Clear visual hierarchy (important at top)
- Consistent color scheme
- White space for readability
- Mobile-responsive layout
```

**Stories (Guided Tours):**
```
Narrative sequence:
1. Opening scene: Context and question
2. Scene 2: Supporting evidence
3. Scene 3: More details
4. Final scene: Recommendation/Action

Example Story:
Scene 1: "Revenue declining in Q4"
Scene 2: "Product A saw biggest drop"
Scene 3: "Region West particularly affected"
Scene 4: "Recommend regional promotion"

Users click through narrative like slideshow
Maintains context but guides focus
```

### 5. Advanced Techniques
**What it is:** Beyond basic charting - advanced analysis and visualization.

**Table Calculations:**
```
Create metrics without modifying source data
- Running totals
- Percent of total
- Year-over-year growth
- Ranking

Example:
Sales by Month with % Change from Previous Month
Uses table calc to compute differences dynamically
```

**Parameters & Dynamic Analysis:**
```
Parameter: User-controlled input
- Allows what-if analysis
- Create parameter (numeric range)
- Use in calculated field
- Add parameter control to dashboard

Example:
"What if we increase price by X%?"
Parameter: Price Increase % (0-50)
Field: New Price = Price × (1 + Price Increase / 100)
Chart updates as user adjusts parameter
```

**Advanced Aggregations:**
```
LOD (Level of Detail) Expressions:
- Calculate metrics at specific dimension levels
- FIXED: Aggregate across entire dataset
- INCLUDE: Add additional dimension
- EXCLUDE: Remove dimension from calculation

Example:
{FIXED [Region] : SUM([Sales])}
Shows total sales per region on every row
Enables region comparison with detail rows
```

## Tools and Resources

**Tableau Products:**
- Tableau Public: Free web-based (share publicly)
- Tableau Desktop: Professional edition ($70/month)
- Tableau Server: Enterprise deployment
- Tableau Online: Cloud version

**Learning Resources:**
- Tableau Tutorial Videos: Official Tableau website
- DataCamp: Tableau courses
- Tableau Public Gallery: Inspiration and examples
- YouTube: Data storytelling with Tableau

**Datasets for Practice:**
- Tableau Sample Data: Built-in datasets
- Kaggle: Public datasets
- Tableau Public Gallery: Real dashboards to learn from

## Best Practices

1. **Start with Question:** What story do you want to tell?
2. **Appropriate Charts:** Choose visualization matching your data/message
3. **Color Intentionally:** Highlight key insights, use intuitive colors
4. **Label Clearly:** Titles, axes, legends need no outside knowledge
5. **Limit Dimensions:** Too many makes charts hard to read
6. **Test Filters:** Ensure interactivity works as expected
7. **Performance:** Optimize for fast loading (data source filters)
8. **Context Clues:** Add reference lines, benchmarks, targets
9. **Mobile First:** Ensure dashboards work on phones/tablets
10. **Iterate:** Get feedback and refine based on user needs

## Next Steps

1. **Week 1-2:** Master data sources and dimension/measure concepts
2. **Week 2-3:** Build variety of visualizations
3. **Week 3-4:** Create interactive dashboards with filters
4. **Week 4-5:** Build story-driven presentation
5. **Week 5-6:** Learn table calculations and parameters
6. **Week 6-7:** Publish and share dashboards publicly
7. **After:** Move to advanced Tableau Server or alternative tools
8. **Progression:** Tableau Desktop → Tableau Server → Advanced Analytics
