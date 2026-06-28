# Data Visualization Guide

## Chart Selection
| Purpose | Chart Type |
|---------|------------|
| Compare values | Bar chart |
| Show trend | Line chart |
| Distribution | Histogram |
| Relationship | Scatter plot |
| Composition | Pie/Donut |

## Python Example
```python
import matplotlib.pyplot as plt
plt.figure(figsize=(10,6))
plt.plot(data['date'], data['value'])
plt.title('Trend Analysis')
plt.show()
```
