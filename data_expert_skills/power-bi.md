---
name: "Power BI"
description: "Build interactive dashboards with Power BI desktop, data modeling, DAX calculations, and cloud publishing"
category: "Visualization"
level: "Intermediate"
duration: "5-7 weeks"
---

# Power BI

## Quick Start

Power BI is Microsoft's enterprise analytics platform. Within your first week, you'll load data, create charts, and build simple dashboards. By week four, you'll design professional reports with DAX calculations and publish to cloud for team access.

**First Task (30 minutes):**
1. Download Power BI Desktop (free from Microsoft)
2. Load a sample dataset (CSV or Excel)
3. Create a bar chart and line chart
4. Add filters and interact with data
5. Save and share basic report

## Key Concepts

### 1. Data Loading & Modeling
**What it is:** Connecting data sources and structuring relationships for analysis.

**Data Sources:**
```
Direct connections:
- Excel files
- CSV files
- Databases (SQL Server, PostgreSQL, MySQL)
- Cloud services (Salesforce, Google Analytics, Azure)
- Web APIs

Data Loading Process:
1. Get Data → Select source
2. Navigator → Choose tables
3. Transform → Clean and prepare (Power Query)
4. Load → Import into model

Power Query (ETL):
- Remove columns you don't need
- Filter rows
- Change data types
- Split/merge columns
- Remove duplicates
- Combine multiple tables
```

**Data Model (Star Schema):**
```
Fact Table (Transactions):
- Foreign keys to dimensions
- Measures (numeric data)
- Examples: Sales, Quantity, Date

Dimension Tables (Reference):
- Primary key
- Descriptive attributes
- Examples: Customers, Products, Dates

Relationships:
- Connect fact to dimensions
- Cardinality: one-to-many

Example Model:
Sales (Fact) ← Customer (Dim)
            ← Product (Dim)
            ← Date (Dim)
```

### 2. DAX (Data Analysis Expressions)
**What it is:** Formula language for creating calculated columns and measures.

**Measures (Dynamic Calculations):**
```
Simple Measures:
Total Sales = SUM(Sales[Amount])
Average Order = AVERAGE(Orders[Amount])

Conditional Measures:
High Value Orders =
  SUMIF(Orders[Amount], >1000)

YTD Sales (Year-to-Date):
YTD Sales =
  CALCULATE(
    SUM(Sales[Amount]),
    DATESBETWEEN(Date[Date], DATE(YEAR(TODAY()),1,1), TODAY())
  )

Previous Year Comparison:
Prior Year Sales =
  CALCULATE(
    SUM(Sales[Amount]),
    DATEADD(Date[Date], -12, MONTH)
  )

Market Share:
Market Share % =
  DIVIDE([Total Sales], CALCULATE([Total Sales], ALL(Product)))
```

**Calculated Columns (Row-by-Row):**
```
Full Name = Customer[FirstName] & " " & Customer[LastName]

Sales Category =
  IF(Sales[Amount] > 10000, "High",
    IF(Sales[Amount] > 5000, "Medium", "Low"))

Quarter = "Q" & ROUNDUP(MONTH([Date])/3, 0)
```

### 3. Building Dashboards & Visualizations
**What it is:** Combining multiple visualizations into interactive reports.

**Chart Types:**
```
Categorical Comparisons:
- Bar/Column charts: Sales by product
- Clustered bar: Compare across multiple categories

Trends Over Time:
- Line charts: Sales by month
- Area charts: Cumulative totals

Parts of Whole:
- Pie/Donut charts: Market share by region
- Treemap: Hierarchical breakdown

Relationships:
- Scatter plot: Correlation between variables
- Bubble chart: 3 dimensions

Key Metrics:
- Cards: Single KPI (total revenue, customer count)
- Gauge: Progress toward target

Geographic:
- Map visuals: Regional analysis
- Filled maps: Heat maps by region
```

**Dashboard Design:**
```
Layout Best Practices:
1. KPIs at top (summary metrics)
2. Filters at left (user controls)
3. Main visualizations center (largest charts)
4. Supporting details at bottom/right

Interactivity:
- Slicers: Filter across all visuals
- Cross-filtering: Click one chart to filter others
- Drill-down: Explore hierarchies (Year → Month → Day)
- Tooltips: Hover for detailed information

Color Scheme:
- Consistent palette (brand colors)
- Highlights for important metrics
- Accessible colors (colorblind-friendly)
```

### 4. Publishing & Sharing
**What it is:** Deploying reports to Power BI Service for team collaboration.

**Publishing Process:**
```
1. Publish to Power BI Service (cloud)
2. Specify workspace (teams can access)
3. Set refresh schedule (how often data updates)
4. Configure security (who can view/edit)

Access Levels:
- Viewer: Can interact but not edit
- Editor: Can modify reports
- Admin: Full control

Sharing Options:
- Power BI Service: Shared workspaces
- Email: Embed reports
- Web: Embed in websites
- Mobile: View on phone/tablet
```

**Refresh Options:**
```
Direct Query: Real-time connection (slower but most current)
Import: Data copied to model (faster, requires refresh schedule)
Scheduled refresh: Daily, hourly, or on-demand
Push API: Real-time updates for streaming data
```

### 5. Performance Optimization
**What it is:** Making dashboards fast and responsive.

**Optimization Techniques:**
```
Data Reduction:
- Aggregate at source (database) before loading
- Filter unnecessary data during import
- Use DirectQuery for huge datasets

Model Optimization:
- Remove unused columns
- Hide unnecessary fields
- Create efficient relationships
- Avoid circular relationships

DAX Optimization:
- Avoid nested CALCULATE functions
- Use SELECTEDVALUE instead of IF with VALUES
- Cache values in calculated columns when possible

Visual Optimization:
- Limit data shown per visual (top 10, not 1000)
- Use aggregations (SUM, AVG) not raw details
- Avoid too many visuals per page
```

## Tools and Resources

**Power BI Tools:**
- Power BI Desktop: Free download (windows only)
- Power BI Service: Cloud platform (subscription)
- Power BI Mobile: Mobile apps
- Power BI Report Builder: Paginated reports

**Learning Resources:**
- Microsoft Power BI Documentation (official)
- DataCamp: Power BI courses
- YouTube: Guy in a Cube (comprehensive tutorials)
- edX: Power BI fundamentals

**Sample Datasets:**
- Microsoft Sample Datasets: Built-in examples
- Kaggle: Public datasets for practice
- Adventure Works: Business scenario data

## Best Practices

1. **Plan Before Building:** Sketch dashboard layout, identify KPIs
2. **Single Responsibility:** Each visualization answers one question
3. **Clear Titles & Labels:** Assume users don't know your data
4. **Use Proper Data Types:** Numbers, dates formatted correctly
5. **Hide Unnecessary Fields:** Keep model clean and focused
6. **Test Filters:** Ensure cross-filtering works as expected
7. **Optimize Performance:** Monitor refresh times, simplify when slow
8. **Document Data:** Add descriptions to columns and measures
9. **Version Control:** Track changes to reports and models
10. **Regular Refreshes:** Ensure data always up-to-date

## Next Steps

1. **Week 1-2:** Load data and create basic visualizations
2. **Week 2-3:** Build star schema data model with relationships
3. **Week 3-4:** Learn DAX and create custom measures
4. **Week 4-5:** Design complete interactive dashboard
5. **Week 5-6:** Publish and configure refresh schedule
6. **Week 6-7:** Optimize performance and train users
7. **After:** Move to advanced analytics (R/Python in Power BI)
8. **Progression:** Power BI → Advanced Analytics → AI Features
