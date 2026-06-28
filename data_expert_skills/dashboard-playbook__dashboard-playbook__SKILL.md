# Dashboard Playbook Skill

## Summary
Implementation framework for creating effective business intelligence dashboards with proven layout patterns, data storytelling techniques, and adoption strategies. Includes code examples for common components.

## Workflow
```
Audience Analysis → Story Arc Design → Layout Implementation → Governance Setup → Adoption Planning → Validate
```

**Progress:**
- [ ] Step 1: Audience & Decisions
- [ ] Step 2: Story Arc Design
- [ ] Step 3: Layout Implementation
- [ ] Step 4: Governance Setup
- [ ] Step 5: Adoption Planning
- [ ] Step 6: Validate

## Step 1: Audience & Decisions
Document stakeholder requirements using structured format:

```json
{
  "persona": "Sales Director",
  "decision_frequency": "daily",
  "key_decisions": [
    "Resource allocation",
    "Pipeline prioritization",
    "Team performance review"
  ],
  "data_literacy": "intermediate"
}
```

## Step 2: Story Arc Design
Create narrative flow with visual hierarchy:

1. **Headline Metric**: Current month revenue vs target (KPI)
2. **Supporting Evidence**: Regional performance map + product mix chart
3. **Drill-Down**: Clickable time-series analysis + customer cohort breakdown
4. **Action Prompt**: "Investigate Midwest region performance" (with link to detailed report)

## Step 3: Layout Implementation
### Responsive Grid System (12-column)

```html
<div class="dashboard-grid">
  <div class="hero-tile span-4">Main KPI</div>
  <div class="supporting-chart span-8">Regional Map</div>
  <div class="context-panel span-3">Alerts</div>
  <div class="data-source span-9">Last updated: 2023-09-15</div>
</div>
```

```css
/* Color Semantics */
:root {
  --status-good: #4CAF50;
  --status-warning: #FFA726;
  --status-risk: #EF5350;
}

.kpi-card.good { color: var(--status-good); }
.status-indicator.risk { background-color: var(--status-risk); }
```

| Component | Size | Placement | Example |
|---------|------|-----------|---------|
| Hero Metric | 4 columns | Left/top | Revenue vs Target |
| Alerts Panel | 3 columns | Right/bottom | SLA Status |
| Drill-down | Full width | Below fold | Click-to-expand |

## Step 4: Governance Setup
Implement data quality indicators:

```javascript
// Data Freshness Checker
function checkFreshness(lastUpdate) {
  const daysOld = Math.floor((new Date() - new Date(lastUpdate)) / (1000 * 60 * 60 * 24));
  return daysOld < 1 ? 'fresh' : daysOld < 3 ? 'stale' : 'critical';
}
```

## Step 5: Adoption Planning
Create enablement assets:
- Training videos (Loom/Zoom recordings)
- Keyboard shortcut guide (PDF)
- Feedback form (Google Form/Typeform)
- Release notes template (Markdown)

## Step 6: Validate
Success criteria:
1. 80%+ stakeholder engagement in first month
2. Average session duration >3 minutes
3. <10% bounce rate on key pages
4. 3+ actionable decisions documented weekly

Implementation checklist:
- [ ] Color semantics applied consistently
- [ ] Drill-down paths defined for all KPIs
- [ ] Data freshness indicator visible
- [ ] Adoption assets distributed