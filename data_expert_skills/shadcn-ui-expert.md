# shadcn/ui Expert - Component & Chart Reference

A static, self-contained reference for all shadcn/ui base components and Recharts-based chart types with full code examples.

## When to Use This Skill

- User asks for a **shadcn/ui component** by name (e.g., "add a button", "use a dialog")
- User needs a **code example** for any base component or chart
- User asks about **component variants** (e.g., "outline button", "stacked bar chart")
- User needs **install commands** for shadcn components
- User asks about **Recharts charts** with shadcn/ui theming

## How to Use

1. **Read the index** to find the component:
   - Components: `references/index.md`
   - Charts: `references/charts-index.md`

2. **Read the specific component/chart file** for code:
   - Components: `references/components/{slug}.md`
   - Charts: `references/charts/{type}.md`

3. **Follow the variant selection rule** (see below)

## CRITICAL: Variant Selection Rule

When a component or chart has **multiple variants**:

1. **List the available variants** to the user
2. **Ask which variant they need** before outputting code
3. **Output only the selected variant's code**

Do NOT dump all variants at once. Components with 1 variant can be output directly.

## Common Patterns

### Install a component
```bash
npx shadcn@latest add {component-slug}
```

### Import pattern
```tsx
import { ComponentName } from "@/components/ui/{component-slug}"
```

### Chart architecture
All charts use `<ChartContainer>` with a `ChartConfig` for theming:
```tsx
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
```
Install: `npx shadcn@latest add chart`

## Component Categories

| Category | Components |
|----------|-----------|
| **Layout** | Aspect Ratio, Card, Collapsible, Resizable, Scroll Area, Separator, Sidebar |
| **Forms** | Button, Button Group, Calendar, Checkbox, Combobox, Field, Form, Input, Input Group, Input OTP, Label, Native Select, Radio Group, Select, Slider, Switch, Textarea, Toggle, Toggle Group |
| **Navigation** | Breadcrumb, Command, Context Menu, Dropdown Menu, Menubar, Navigation Menu, Pagination, Tabs |
| **Data Display** | Accordion, Avatar, Badge, Carousel, Hover Card, Item, Kbd, Table, Tooltip |
| **Feedback** | Alert, Empty, Progress, Skeleton, Sonner, Spinner |
| **Overlay** | Alert Dialog, Dialog, Drawer, Popover, Sheet |

## Chart Types

| Type | Variants | File |
|------|----------|------|
| Area | 10 | `references/charts/area.md` |
| Bar | 10 | `references/charts/bar.md` |
| Line | 10 | `references/charts/line.md` |
| Pie | 11 | `references/charts/pie.md` |
| Radar | 14 | `references/charts/radar.md` |
| Radial | 6 | `references/charts/radial.md` |
| Tooltip | 9 | `references/charts/tooltip.md` |

## Reference Files

- `references/index.md` - Full component catalog with descriptions
- `references/charts-index.md` - Chart type catalog with variant lists
- `references/components/{slug}.md` - One file per component with all variant code
- `references/charts/{type}.md` - One file per chart type with all variant code