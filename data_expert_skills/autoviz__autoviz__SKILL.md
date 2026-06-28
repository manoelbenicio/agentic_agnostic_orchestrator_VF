# AutoViz Automatic EDA Skill

Master AutoViz for instant exploratory data analysis with a single line of code. Generate comprehensive visualizations, detect patterns, identify outliers, and export publication-ready charts automatically.

## Workflow

```
Load Data → Initialize AutoViz → Generate Visualizations → Customize Output → Interpret Results
```

**Progress:**
- [ ] Step 1: Load Data
- [ ] Step 2: Initialize AutoViz
- [ ] Step 3: Generate Visualizations
- [ ] Step 4: Customize Output
- [ ] Step 5: Interpret Results

## Step 1: Load Data

Supports multiple data sources with automatic format detection:

```python
import pandas as pd

# Load from CSV
filename = "data.csv"
df = pd.read_csv(filename)

# Load from Parquet
# df = pd.read_parquet("data.parquet")

# Create sample data
sample_df = pd.DataFrame({
    "numeric_col": [1.2, 2.3, 3.4, 4.5],
    "category_col": ["A", "B", "A", "C"],
    "target_col": [0, 1, 0, 1]
})
```

| Format | Command | Notes |
|--------|---------|-------|
| CSV | `pd.read_csv()` | Default delimiter is comma |
| Parquet | `pd.read_parquet()` | Requires pyarrow |
| JSON | `pd.read_json()` | Supports nested structures |
| Excel | `pd.read_excel()` | Needs openpyxl installed |

## Step 2: Initialize AutoViz

Configure core parameters for analysis:

```python
from autoviz import AutoViz_Class

AV = AutoViz_Class()

# Configuration parameters
config = {
    "sep": ",",  # Delimiter
    "depVar": "target_col",  # Target variable
    "header": 0,  # Header row index
    "verbose": 2,  # Output level
    "lowess": True,  # Enable trend lines
    "chart_format": "html",  # Output format
    "max_rows_analyzed": 100000,  # Sampling limit
    "max_cols_analyzed": 30  # Column limit
}
```

## Step 3: Generate Visualizations

Create comprehensive EDA with one command:

```python
# Run AutoViz with configuration
result_df = AV.AutoViz(
    filename=filename,  # Empty if using dfte
    dfte=df,  # DataFrame input
    **config
)

print(f"Generated {len(result_df.columns)} visualizations")
```

**Output includes:**
- Distribution plots for numerical features
- Bar charts for categorical variables
- Correlation matrices
- Pair plots for feature relationships
- Outlier detection visualizations

## Step 4: Customize Output

Adjust visualization settings and output formats:

```python
# HTML output with interactive plots
config["chart_format"] = "html"
result_html = AV.AutoViz(
    dfte=sample_df,
    **config
)

# Save to directory
import os
output_dir = "eda_results"
os.makedirs(output_dir, exist_ok=True)

config.update({
    "chart_format": "png",
    "save_plot_dir": output_dir
})

result_files = AV.AutoViz(
    dfte=sample_df,
    **config
)
```

| Format | Use Case | Interactivity |
|--------|----------|-------------|
| html | Reports | High |
| svg | Vector graphics | Medium |
| png | Presentations | Low |
| bokeh | Dashboards | High |

## Step 5: Interpret Results

Key elements to analyze in output:

1. **Feature Distributions**
   - Skewness detection in numerical features
   - Category imbalance in categorical variables

2. **Correlation Analysis**
   - Heatmap showing feature relationships
   - Scatter plots with LOWESS trends

3. **Outlier Detection**
   - Box plots highlighting extreme values
   - Isolation Forest-based anomaly detection

4. **Target Relationships**
   - Feature importance rankings
   - Conditional distributions vs target

## Troubleshooting Common Issues

**Problem:** Charts not displaying in Jupyter
```bash
# Solution: Install required widgets
pip install ipywidgets
jupyter nbextension enable --py widgetsnbextension
```

**Problem:** Memory issues with large datasets
```python
# Adjust sampling parameters
config.update({
    "max_rows_analyzed": 50000,
    "max_cols_analyzed": 15
})
```

**Problem:** Missing visualization backends
```bash
# Install all supported backends
pip install matplotlib seaborn plotly bokeh
```

## Comparison with Alternatives

| Feature | AutoViz | ydata-profiling |
|--------|---------|----------------|
| One-line EDA | ✅ | ✅ |
| Interactive plots | ✅ (Plotly/Bokeh) | ❌ (Static HTML) |
| Correlation analysis | ✅ | ✅ |
| Outlier visualization | ✅ | Limited |
| Time-series support | ✅ | Limited |
| Custom styling | ❌ | ✅ (via templates) |

## Validation

Verify successful execution by:
1. Checking output directory for generated files
2. Inspecting returned DataFrame shape
3. Reviewing HTML report in browser
4. Confirming no errors in verbose output