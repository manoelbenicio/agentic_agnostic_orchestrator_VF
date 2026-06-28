# Customer Churn Analysis Helper

## Purpose

Automated assistant for identifying customer attrition patterns through statistical analysis, cohort tracking, and predictive modeling.

## Workflow

```
Data Preparation → Exploratory Analysis → Statistical Modeling → Visualization → Validation
```

**Progress:**
- [ ] Step 1: Data Preparation
- [ ] Step 2: Exploratory Analysis
- [ ] Step 3: Statistical Modeling
- [ ] Step 4: Visualization Creation
- [ ] Step 5: Validate Results

## Step 1: Data Preparation

Extract and clean relevant data points for churn analysis:

```sql
-- Calculate customer lifetime duration
WITH churn_data AS (
  SELECT 
    customer_id,
    MIN(event_date) AS start_date,
    MAX(CASE WHEN event_type = 'cancel' THEN event_date END) AS churn_date
  FROM subscription_events
  GROUP BY customer_id
)
SELECT 
  customer_id,
  start_date,
  churn_date,
  COALESCE(DATE_PART('day', churn_date - start_date), 365) AS tenure_days,
  (churn_date IS NOT NULL) AS is_churned
FROM churn_data;
```

| Parameter | Value | Description |
|----------|-------|-------------|
| Timeframe | 12 months | Standard period for churn analysis |
| Event Types | 'signup', 'cancel' | Required event tracking schema |
| Tenure Cap | 365 days | Maximum observation period |

## Step 2: Exploratory Analysis

Identify patterns in customer behavior:

```python
import pandas as pd
# Calculate churn rate by cohort
cohorts = df.groupby('signup_month').agg(
    total_customers=('customer_id', 'count'),
    churned=('is_churned', 'sum')
)
cohorts['churn_rate'] = cohorts['churned'] / cohorts['total_customers']
```

## Step 3: Statistical Modeling

Perform survival analysis:

```python
from lifelines import KaplanMeierFitter
# Fit survival curve
kmf = KaplanMeierFitter()
kmf.fit(durations=df['tenure_days'], event_observed=df['is_churned'])
kmf.plot_survival_function()
```

## Step 4: Visualization Creation

Create churn heatmap:

```python
import seaborn as sns
import matplotlib.pyplot as plt

# Create cohort retention matrix
cohort_matrix = df.pivot_table(
    index='signup_cohort',
    columns='tenure_month',
    values='is_churned',
    aggfunc='mean'
)

sns.heatmap(cohort_matrix, annot=True, fmt='.1%', cmap='YlOrRd')
plt.title('Customer Churn by Cohort and Tenure')
plt.show()
```

## Step 5: Validate Results

Verify analysis meets quality standards:
- [ ] Churn rate trends match business intuition
- [ ] Statistical significance (p < 0.05) in survival analysis
- [ ] Cohort sizes > 50 customers for reliable patterns
- [ ] Missing data < 5% of total dataset
- [ ] Tenure calculations match billing system records