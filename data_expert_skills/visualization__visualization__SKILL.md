# Data Visualization Fundamentals

## Workflow
```
Data Preparation → Chart Selection → Implementation → Enhancement → Validation
```

**Progress:**
- [ ] Step 1: Data Preparation
- [ ] Step 2: Chart Selection
- [ ] Step 3: Implementation
- [ ] Step 4: Enhancement
- [ ] Step 5: Validation

## Step 1: Data Preparation
Clean and structure data for visualization using Pandas or dplyr. Handle missing values and format datetime fields.

```python
# Python data preparation example
import pandas as pd

# Load and clean data
df = pd.read_csv('sales_data.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.dropna()
```

| Task | Tool | Command |
|------|------|---------|
| Data cleaning | Pandas | `df.dropna()` |
| Date formatting | Pandas | `pd.to_datetime()` |
| Data filtering | dplyr | `filter(date > '2023-01-01')` |

## Step 2: Chart Selection
Choose appropriate visualization based on data type and audience needs:

| Data Type | Recommended Charts | Audience |
|----------|--------------------|----------|
| Categorical | Bar, Pie, Treemap | Business |
| Time Series | Line, Area, Candlestick | Technical |
| Distribution | Histogram, Boxplot | Executive |
| Relationships | Scatter, Heatmap | Public |

## Step 3: Implementation
Create base visualizations using Python or R:

```python
# Python Plotly example
import plotly.express as px

fig = px.line(df, x='date', y='sales', title='Monthly Sales Trend')
fig.update_layout(template='plotly_white')
fig.show()
```

```r
# R ggplot2 example
library(ggplot2)

ggplot(df, aes(x=date, y=sales)) + 
  geom_line(color='#1f77b4') +
  labs(title='Monthly Sales Trend')
```

## Step 4: Enhancement
Add accessibility features and responsive design:

```python
# Colorblind-safe palette example
import seaborn as sns

palette = sns.color_palette('colorblind')
sns.set_palette(palette)
plt = sns.barplot(x='category', y='sales', data=df)
```

| Enhancement | Technique | Tool |
|-----------|-----------|------|
| Accessibility | Colorblind palette | Seaborn |
| Responsiveness | Auto-scaling | Plotly |
| Annotation | Callout boxes | Power BI |

## Step 5: Validation
Verify visualization effectiveness through:
1. Clarity check: Can insights be understood in 5 seconds?
2. Accessibility test: Passes WCAG 2.1 AA contrast standards
3. Performance: Loads in <3 seconds for web dashboards
4. Accuracy: Axis scales and labels correctly represent data