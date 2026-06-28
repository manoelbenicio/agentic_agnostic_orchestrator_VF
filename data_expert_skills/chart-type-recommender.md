# Chart Type Recommender

## Workflow

```
Analyze Data → Define Requirements → Generate Recommendations → Implement Visualization → Validate Output
```

**Progress:**
- [ ] Step 1: Analyze Data Characteristics
- [ ] Step 2: Define Visualization Requirements
- [ ] Step 3: Generate Recommendations
- [ ] Step 4: Implement Visualization
- [ ] Step 5: Validate Output

## Step 1: Analyze Data Characteristics

Identify data types, cardinality, and distribution patterns using statistical analysis.

```python
import pandas as pd
def analyze_data(df):
    return pd.DataFrame({
        'dtype': df.dtypes,
        'unique_count': df.nunique(),
        'missing_ratio': df.isnull().mean(),
        'sample_values': df.apply(lambda x: x.dropna().unique()[:3])
    })
```

| Feature | Requirement | Notes |
|---------|-------------|-------|
| Data Types | Support numerical, categorical, time-series | |
| Cardinality | Detect high/low uniqueness | >50% unique = high |
| Missing Values | Flag patterns for special handling | |

## Step 2: Define Visualization Requirements

Determine use case constraints and audience needs.

```python
# Example requirement schema
class VizRequirements:
    def __init__(self, purpose, audience, constraints):
        self.purpose = purpose  # 'comparison', 'distribution', 'relationship'
        self.audience = audience  # 'technical', 'business', 'general'
        self.constraints = constraints  # {'max_time': 30, 'interactive': True}
```

| Data Type | Best For | Common Constraints |
|----------|----------|-------------------|
| Categorical | Comparisons, distributions | Limited categories |
| Numerical | Trends, relationships | Outlier handling |
| Time-series | Temporal patterns | Date range limits |

## Step 3: Generate Recommendations

Apply decision matrix to produce prioritized chart suggestions.

```python
def recommend_charts(data_stats, requirements):
    recommendations = []
    # Core recommendation logic
    if data_stats['dtype'] == 'object':
        recommendations.append('bar')
        if data_stats['unique_count'] > 10: recommendations.append('treemap')
    # Add more conditions based on data_stats and requirements
    return sorted(recommendations, key=lambda x: CHART_RANKING.get(x, 10))
```

## Step 4: Implement Visualization

Generate production-ready visualization code with best practices.

```python
# Bar chart implementation example
import matplotlib.pyplot as plt
def create_bar_chart(df, x_col, y_col):
    plt.figure(figsize=(12, 6))
    df.groupby(x_col)[y_col].mean().plot(kind='bar')
    plt.title(f'{y_col} by {x_col}')
    plt.xticks(rotation=45)
    plt.tight_layout()
    return plt.gcf()
```

## Step 5: Validate Output

Verify visualization meets quality standards and requirements.

```python
def validate_chart(chart, requirements):
    # Check title presence
    if not chart.gca().get_title(): return False, 'Missing title'
    # Validate time constraints
    if requirements.constraints.get('max_time'):
        if chart.get_window_extent().width > 1000: return False, 'Too large'
    return True, 'Valid'
```

**Validation Checklist:**
- [ ] Title and axis labels present
- [ ] Color contrast meets accessibility standards
- [ ] Data-ink ratio optimized
- [ ] Interactive elements functional (if required)
- [ ] File size within constraints