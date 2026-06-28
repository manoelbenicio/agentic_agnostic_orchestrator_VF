# Visualization Best Practices

## Workflow

```
Define Goals → Select Chart Type → Apply Color Theory → Implement Accessibility → Validate Ethics → Generate Output
```

**Progress:**
- [ ] Step 1: Define Visualization Goals
- [ ] Step 2: Select Appropriate Chart Type
- [ ] Step 3: Apply Color Theory Principles
- [ ] Step 4: Implement Accessibility Standards
- [ ] Step 5: Validate Data Ethics
- [ ] Step 6: Generate Visualization

## Sample Data Setup

```python
import pandas as pd
import numpy as np

# Generate sample datasets
sales_data = pd.DataFrame({
    'date': pd.date_range(start='2023-01-01', periods=12, freq='M'),
    'revenue': np.random.randint(100, 500, size=12) * 1e6
})

product_data = pd.DataFrame({
    'category': ['Electronics', 'Clothing', 'Home', 'Books', 'Beauty'],
    'sales': [250, 150, 300, 80, 200]
})
```

## Step 1: Define Visualization Goals

Establish purpose and audience requirements before implementation. Key considerations:
- Primary message to convey
- Audience technical proficiency
- Required decision-making impact
- Data complexity level

| Goal Type | Example | Implementation Priority |
|----------|---------|-----------------------|
| Trend Analysis | Time-series sales data | High | 
| Comparative Analysis | Product category performance | Medium |
| Distribution Analysis | Customer demographic data | High |

## Step 2: Select Appropriate Chart Type

Match visualization type to data characteristics using this decision matrix:

```python
# Time-series example
plt.figure(figsize=(12, 6))
sns.lineplot(data=sales_data, x='date', y='revenue')
plt.title('Monthly Revenue Trends')
plt.xlabel('Month')
plt.ylabel('Revenue ($M)')
plt.show()
```

| Data Relationship | Recommended Chart | Limitations |
|------------------|------------------|------------|
| Temporal Trends | Line Chart | Avoid >5 lines |
| Category Comparison | Bar Chart | Limit to 10 categories |
| Distribution Patterns | Histogram | Requires large datasets |
| Correlation Analysis | Scatter Plot | Needs numerical axes |

## Step 3: Apply Color Theory Principles

Implement effective color schemes for clarity and accessibility:

```python
# Seaborn color palette example
sns.set_palette("viridis")
sns.barplot(data=product_data, x='category', y='sales')
plt.title('Product Category Performance')
plt.xlabel('Category')
plt.ylabel('Units Sold')
plt.xticks(rotation=45)
plt.show()
```

Color Application Guidelines:
- Use sequential palettes for ordered data
- Avoid red/green combinations (use pattern overlays instead)
- Ensure 4.5:1 contrast ratio for text/background
- Use luminance gradients for print-friendly visuals

## Step 4: Implement Accessibility Standards

Meet WCAG 2.1 AA compliance requirements:

```python
# Accessible visualization template
plt.style.use('seaborn')
plt.rcParams.update({
    'font.size': 14,
    'axes.titlesize': 16,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12
})
sns.set(context='talk', style='whitegrid')

# Pattern-based differentiation
bars = plt.bar(product_data['category'], product_data['sales'])
for bar in bars:
    bar.set_hatch('///')  # Add texture for colorblind accessibility
plt.show()
```

Accessibility Checklist:
- [ ] Text size ≥ 12pt
- [ ] Alt-text descriptions
- [ ] Keyboard navigation support
- [ ] Pattern-based differentiation

## Step 5: Validate Data Ethics

Check for potential ethical issues with this implementation:

```python
def validate_data_ethics(data):
    """Basic ethical validation checklist"""
    issues = []
    
    # Data source transparency
    if not hasattr(data, 'source'):
        issues.append("Missing data source documentation")
    
    # Bias detection
    if 'demographics' in data.columns:
        missing_groups = ['age', 'gender', 'ethnicity'] 
        if not all(group in data.columns for group in missing_groups):
            issues.append(f"Missing demographic fields: {missing_groups}")
    
    # Scale integrity check
    y_min, y_max = data.min(), data.max()
    if y_max / y_min > 10 if y_min > 0 else False:
        issues.append("Potential misleading scale: Ratio exceeds 10:1")
    
    return issues

# Example usage
ethics_issues = validate_data_ethics(sales_data['revenue'])
for issue in ethics_issues:
    print(f"⚠️ {issue}")
```

## Step 6: Generate Visualization

Final implementation with best practices integrated:

```python
# Complete visualization example
plt.figure(figsize=(14, 8))
sns.set_style("whitegrid")
sns.lineplot(data=sales_data, x='date', y='revenue', linewidth=2.5)
plt.title('Quarterly Revenue Growth (FY2023)', fontsize=20)
plt.xlabel('Month', fontsize=16)
plt.ylabel('Revenue ($M)', fontsize=16)
plt.legend(['Revenue Trend'])
plt.tight_layout()
plt.savefig('revenue_report.png', dpi=300, bbox_inches='tight')
print("✅ Visualization saved with best practices implemented")
```

## Conclusion

Effective visualizations require systematic implementation of design principles:
1. Start with clear goals and audience analysis
2. Match chart types to data characteristics
3. Apply color theory with accessibility in mind
4. Implement WCAG compliance standards
5. Validate ethical data usage
6. Follow production-ready implementation practices