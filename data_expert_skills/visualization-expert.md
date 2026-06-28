# Visualization Expert

Transforms raw data into impactful visual narratives through expert chart selection, design principles, and interactive dashboard implementation.

## Workflow

```
Define Purpose → Select Chart Type → Implement Visualization → Apply Design Principles → Validate Accessibility
```

**Progress:**
- [x] Step 1: Define Purpose and Data Characteristics
- [x] Step 2: Select Chart Type Based on Data Type
- [x] Step 3: Implement Visualization with Tooling
- [x] Step 4: Apply Design Principles
- [x] Step 5: Validate Accessibility and Edge Cases

## Step 1: Define Purpose and Data Characteristics

Understand the data context and communication goals through exploratory analysis.

```python
# Example data inspection
import pandas as pd
df = pd.read_csv('sales_data.csv')
print(f"Data shape: {df.shape}")
print(f"Key metrics: {df.describe()}")
```

## Step 2: Select Chart Type Based on Data Type

| Data Type          | Recommended Charts              | Anti-Patterns           |
|--------------------|----------------------------------|-------------------------|
| Comparison         | Bar/column charts                | 3D charts               |
| Distribution       | Histograms, box plots            | Pie charts for >5 slices|
| Relationship       | Scatter plots, line charts       | Radar charts            |
| Composition        | Stacked bars, area charts        | Exploded pie charts     |
| Trend Over Time    | Line charts, small multiples     | Bar charts for time     |
| Geospatial         | Choropleth maps, heatmaps        | 3D terrain maps         |

```python
# Bar chart for comparison
import matplotlib.pyplot as plt

categories = ['Q1', 'Q2', 'Q3', 'Q4']
sales = [23, 45, 12, 67]
plt.bar(categories, sales)
plt.title('Quarterly Sales Comparison')
plt.ylabel('Revenue (M$)')
plt.show()
```

## Step 3: Implement Visualization with Tooling

```python
# Scatter plot with Plotly
import plotly.express as px
df = px.data.iris()
fig = px.scatter(df, x='sepal_width', y='sepal_length', color='species',
                 title='Iris Measurements (Colorblind-friendly)')
fig.show()
```

```python
# Dash interactive dashboard
import dash
from dash import dcc, html
import plotly.express as px

app = dash.Dash(__name__)
df = px.data.iris()
fig = px.scatter(df, x='sepal_width', y='sepal_length', color='species')

app.layout = html.Div([
    html.H1('Interactive Iris Dataset Visualization'),
    dcc.Graph(
        id='scatter-plot',
        figure=fig
    )
])

if __name__ == '__main__':
    app.run_server(debug=True)
```

## Step 4: Apply Design Principles

Key implementation considerations:
- Use `sns.color_palette("colorblind")` for accessible colors
- Avoid chartjunk (minimal gridlines, no 3D effects)
- Ensure proper aspect ratios (e.g., `figsize=(10,6)` in matplotlib)
- Prioritize white space and clear labeling

```python
# Colorblind-friendly palette
import seaborn as sns
sns.set_palette("colorblind")
plt.style.use('seaborn-whitegrid')
```

## Step 5: Validate Accessibility and Edge Cases

Handle common visualization challenges:
- Overplotting: Use transparency (`alpha=0.5`) or hexbin plots
- Scale distortion: Apply log scales for skewed data
- Color misuse: Avoid red/green contrasts

```python
# Log scale for skewed data
plt.xscale('log')
plt.hist(df['transaction_amount'], bins=50)
plt.title('Transaction Amount Distribution (Log Scale)')
plt.xlabel('Transaction Amount (USD)')
plt.ylabel('Frequency')
plt.show()
```