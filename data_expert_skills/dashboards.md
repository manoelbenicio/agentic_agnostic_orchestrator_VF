Dashboard 1 — Financial Performance (P&L)

You are an expert financial dashboard engineer and front-end developer.

Your task is to generate a fully functional interactive HTML dashboard based on the CSV dataset that I will upload with this prompt.

The output must be a single self-contained HTML file that I can download and open locally in a browser.

The dashboard should be designed for finance teams and executives to analyze profitability and margin drivers.

Dashboard Objective
Create a Financial Performance (P&L) Dashboard that answers the finance question:
Where is profit coming from and what is affecting margins?

The dashboard should visually explain:
- revenue performance
- profitability trends
- margin drivers
- expense structure
- product profitability

Data Source
The dashboard must load data from a CSV file.

When I first generate the dashboard, Claude will already receive the CSV.
However the HTML must also include a CSV upload button so the dashboard can be refreshed every month with new data.

Required CSV Schema
The CSV file will contain the following columns:

month
region
product
revenue
cogs
gross_profit
gross_margin
marketing
payroll
technology
logistics
admin
opex_total
ebitda
ebitda_margin

Dashboard Layout
Use:
- clean white background
- blue accent colors
- responsive layout
- card-based UI

Structure:
Header
Filters
KPI cards
Charts grid

Filters:
- Month / Quarter selector
- Region selector
- Product selector

KPI Cards:
- Revenue
- COGS
- Gross Profit
- Gross Margin %
- Operating Expenses
- EBITDA
- EBITDA Margin %

Charts:
1. Profitability Trend (Revenue, Gross Profit, EBITDA)
2. Profit Waterfall (Revenue → EBITDA)
3. Product Profitability (Gross Margin % by product)
4. Expense Structure (Donut chart)

Scenario Insight Panel:
If marketing costs decrease by 10%, recompute EBITDA impact.

Technical Requirements:
- HTML, CSS, Vanilla JS
- Chart.js
- Fully client-side
- Include CSV upload + validation

Output:
Return ONE complete HTML file only.
Do NOT explain anything.



Dashboard 2 — Revenue Performance

You are an expert dashboard engineer and front-end developer who builds finance-grade, interactive dashboards in a single self-contained HTML file.

Task:
Generate a single downloadable HTML file (with embedded CSS and JS) that implements a Revenue Performance Dashboard.

The dashboard must be fully client-side and include a CSV upload/refresh control.

Dashboard purpose:
Help finance leaders answer — what drives revenue growth?

Required CSV schema:
month
region
product
channel
units_2025
aov_2025
revenue_2025
units_2024
aov_2024
revenue_2024

KPI Cards:
- Total Revenue 2025
- Total Revenue 2024
- YoY Growth %
- Average Order Value
- Units Sold
- Top Region Revenue

Charts:
1. Revenue Trend (monthly)
2. Revenue by Region
3. Revenue by Product / Channel
4. YoY Growth Decomposition (Waterfall)
5. Channel & Product Mix

Scenario Panel:
- Volume change (%)
- Price change (%)
- Channel shift

Compute:
- YoY growth
- Volume effect
- Price effect
- Residual

Technical Requirements:
- Chart.js
- PapaParse
- HTML/CSS/JS only
- Fully client-side

Output:
Return ONE complete HTML file only.
Do NOT explain anything.



Dashboard 3 — Cost Center

You are an expert financial dashboard engineer and front-end developer.

Task:
Generate a single downloadable HTML file that implements a Cost Center Dashboard.

Dashboard purpose:
Which departments drive cost increases?

Required CSV schema:
month
department
category
gl_account
description
cost_2025
cost_2024
monthly_budget

KPI Cards:
- Total Operating Cost (2025)
- Total Operating Cost (2024)
- YoY Cost Change
- Cost vs Budget
- Cost per Employee
- Top Department

Charts:
1. Department Spending
2. Cost Trend
3. Category Breakdown
4. Variance Waterfall
5. Drilldown Table

Scenario Panel:
- Consulting cost reduction
- Software optimization

Technical Requirements:
- Chart.js
- PapaParse
- HTML/CSS/JS only
- Fully client-side

Output:
Return ONE complete HTML file only.
Do NOT explain anything.



Dashboard 4 — Sales Pipeline

You are an expert dashboard engineer and front-end developer.

Task:
Generate a single downloadable HTML file for a Sales Pipeline Dashboard.

Dashboard purpose:
How likely are we to hit sales targets?

Required CSV schema:
month
region
sales_rep
stage
deals_count
avg_deal_size
total_value

KPI Cards:
- Total Pipeline Value
- Forecast Revenue
- Deals in Pipeline
- Closed Deals
- Win Rate
- Average Deal Size

Charts:
1. Funnel (MQL → Closed Won)
2. Pipeline Trend
3. Conversion Rates
4. Pipeline by Sales Rep

Scenario Panel:
- Win rate adjustment
- Deal size change
- Volume change

Technical Requirements:
- Chart.js
- PapaParse
- HTML/CSS/JS only

Output:
Return ONE complete HTML file only.
Do NOT explain anything.



Dashboard 5 — Cash Flow

You are an expert financial dashboard engineer and front-end developer.

Task:
Generate a single downloadable HTML file for a Cash Flow Dashboard.

Dashboard purpose:
Do we have enough cash to operate and grow?

Required CSV schema:
month
operating_cash_flow
investing_cash_flow
financing_cash_flow
free_cash_flow
cash_balance_end
accounts_receivable
ar_0_30
ar_30_60
ar_60_90
ar_90_plus
accounts_payable
inventory

KPI Cards:
- Cash Balance
- Operating Cash Flow
- Free Cash Flow
- Accounts Receivable
- Accounts Payable
- Cash Runway

Charts:
1. Cash Flow Trend
2. Cash Flow Breakdown
3. Working Capital Breakdown
4. Receivables Aging
5. Cash Forecast

Scenario Panel:
- Revenue growth
- Payment delays
- Expense increase

Technical Requirements:
- Chart.js
- PapaParse
- HTML/CSS/JS only

Output:
Return ONE complete HTML file only.
Do NOT explain anything.