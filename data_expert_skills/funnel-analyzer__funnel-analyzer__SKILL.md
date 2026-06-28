# Funnel Analyzer

> Analyze conversion funnels to identify drop-off points and optimization opportunities.

## Workflow

```
Data Preparation → Funnel Analysis → Drop-off Detection → Visualization → Validation
```

**Progress:**
- [ ] Step 1: Prepare data schema
- [ ] Step 2: Analyze funnel stages
- [ ] Step 3: Detect drop-off points
- [ ] Step 4: Generate visualization
- [ ] Step 5: Validate results

## Step 1: Prepare Data Schema

Store user journey events in CSV format with timestamps and stages:

```csv
# data.csv
user_id,timestamp,stage
123,2024-03-01T08:00:00,visit
123,2024-03-01T08:05:00,signup
456,2024-03-01T08:10:00,visit
```

| Field | Type | Description |
|-------|------|-------------|
| user_id | string | Unique identifier |
| timestamp | datetime | ISO 8601 format |
| stage | string | Funnel stage name |

```python
# Load data with pandas
def load_data(path):
    import pandas as pd
    return pd.read_csv(path, parse_dates=['timestamp'])
```

## Step 2: Analyze Funnel Stages

```python
# Calculate conversion rates
def analyze_funnel(data, stages):
    from functools import reduce
    def stage_count(df, stage):
        return df[df['stage'] == stage].shape[0]
    
    counts = [stage_count(data, s) for s in stages]
    rates = [round(c/counts[i-1], 2) if i > 0 else 1.0 
            for i, c in enumerate(counts)]
    return dict(stages=stages, counts=counts, rates=rates)
```

## Step 3: Detect Drop-off Points

```python
# Identify significant drops (30%+ loss)
def find_dropoffs(analytics):
    return [i for i, rate in enumerate(analytics['rates'][1:], 1) 
           if rate < 0.7]  # Returns stage indices
```

Example output:
```json
{
  "stages": ["visit", "signup", "trial", "paid"],
  "counts": [1000, 800, 600, 200],
  "rates": [1.0, 0.8, 0.75, 0.33]
}
```

## Step 4: Generate Visualization

```python
# Create HTML funnel chart
import plotly.express as px
def visualize_funnel(analytics):
    fig = px.funnel(
        y=analytics['stages'],
        x=[f"{r*100:.0f}%" for r in analytics['rates']],
        title="Conversion Funnel"
    )
    fig.write_html("funnel-chart.html")
```

## Step 5: Validate Results

1. Verify data completeness: `python scripts/main.py validate data.csv`
2. Check for missing stages: `grep -v "visit\|signup\|trial\|paid" data.csv`
3. Compare expected vs actual conversion rates

## CLI Implementation

```python
# scripts/main.py
import click, pandas as pd

@click.group()
def cli(): pass

@cli.command()
@click.argument("path")
@click.option("--stages", required=True)
def analyze(path, stages):
    data = pd.read_csv(path, parse_dates=['timestamp'])
    stages = stages.split(',')
    result = analyze_funnel(data, stages)
    print(result)  # In production, output JSON

if __name__ == "__main__":
    cli()
```