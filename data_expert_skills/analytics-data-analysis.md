# Analytics and Data Analysis

## Workflow

```
Data Preparation → Exploratory Analysis → Visualization → Error Handling → Validation
```

**Progress:**
- [ ] Step 1: Data Preparation
- [ ] Step 2: Exploratory Analysis
- [ ] Step 3: Visualization
- [ ] Step 4: Error Handling
- [ ] Step 5: Validation

## Step 1: Data Preparation

Load and validate data using pandas with proper error handling:

```python
import pandas as pd

try:
    df = pd.read_csv('data/sales_data.csv')
    # Validate required columns
    required_cols = ['date', 'product_id', 'quantity', 'revenue']
    if not all(col in df.columns for col in required_cols):
        raise ValueError("Missing required columns in data")
    # Handle missing values
    df['quantity'] = df['quantity'].fillna(0)
    df['revenue'] = df['revenue'].fillna(df['revenue'].median())
    # Convert date column
    df['date'] = pd.to_datetime(df['date'])
except FileNotFoundError:
    print("Error: Data file not found")
    raise
except Exception as e:
    print(f"Data validation error: {str(e)}")
    raise
```

| Validation Check | Description | Action |
|------------------|-------------|--------|
| File existence | Verify data source exists | Raise error if missing |
| Column presence | Ensure required fields exist | Raise error if missing |
| Data types | Convert to appropriate types | Auto-convert date fields |
| Missing values | Handle nulls appropriately | Fill quantity with 0, revenue with median |

## Step 2: Exploratory Analysis

Perform data transformation and aggregation:

```python
# Method chaining example
analysis_df = (
    df[df['quantity'] > 0]  # Remove invalid quantities
    .assign(unit_price=lambda x: x['revenue'] / x['quantity'])
    .groupby(['product_id', pd.Grouper(key='date', freq='M')])
    .agg(
        total_quantity=('quantity', 'sum'),
        total_revenue=('revenue', 'sum'),
        avg_price=('unit_price', 'mean')
    )
    .reset_index()
)

# Memory optimization
analysis_df['product_id'] = analysis_df['product_id'].astype('category')
```

## Step 3: Visualization

Create accessible visualizations with matplotlib and seaborn:

```python
import seaborn as sns
import matplotlib.pyplot as plt

plt.figure(figsize=(12, 6))
sns.set_theme(style="whitegrid", palette="colorblind")

# Time series visualization
monthly_trend = analysis_df.groupby('date')['total_revenue'].sum().reset_index()

sns.lineplot(data=monthly_trend, x='date', y='total_revenue')
plt.title('Monthly Revenue Trend')
plt.xlabel('Month')
plt.ylabel('Total Revenue ($)')
plt.tight_layout()
plt.savefig('monthly_trend.png', dpi=300, bbox_inches='tight')
```

| Library | Use Case | Strengths |
|---------|----------|----------|
| matplotlib | Custom visualizations | Fine-grained control |
| seaborn | Statistical plots | Built-in themes, accessibility |
| plotly | Interactive dashboards | Web-based interactivity |

## Step 4: Error Handling

Implement robust data pipeline checks:

```python
# Data quality check function
def validate_data(df):
    checks = {
        'no_missing_dates': df['date'].notnull().all(),
        'positive_revenue': (df['revenue'] >= 0).all(),
        'valid_product_ids': df['product_id'].nunique() > 1
    }
    
    failed_checks = [k for k, v in checks.items() if not v]
    if failed_checks:
        raise ValueError(f"Data validation failed: {failed_checks}")
    return True

# Usage in pipeline
try:
    validate_data(analysis_df)
    print("Data quality check passed")
except ValueError as e:
    print(f"Pipeline halted: {str(e)}")
    # Log to monitoring system
```

## Step 5: Validation

Verify analysis outputs and reproducibility:

1. Check output file existence and size:
```bash
ls -la monthly_trend.png
# Verify file size > 0
```

2. Validate notebook execution flow:
```bash
# Check for clear cell boundaries and execution order
jupyter nbconvert --to script sales_analysis.ipynb
grep -n "In\[" sales_analysis.py  # Verify sequential numbering
```

3. Reproduce environment:
```bash
# Create requirements.txt
pip freeze > requirements.txt

# Verify installation
python3 -m venv test_env
source test_env/bin/activate
pip install -r requirements.txt
```

Success criteria:
- All visualization files generated with non-zero size
- No errors in notebook execution flow
- Environment recreation successful
- Data validation checks passed