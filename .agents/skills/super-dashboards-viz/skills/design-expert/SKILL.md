# UI/UX Design Reference

UI/UX design expertise covering component architecture, design systems, responsive layouts, and Figma file analysis. Includes implementation examples for modern design frameworks.

## Workflow

```
Figma Analysis → Component Design → Design System Setup → Responsive Layout Implementation → Validation
```

**Progress:**
- [ ] Step 1: Analyze Figma Files
- [ ] Step 2: Design Component Architecture
- [ ] Step 3: Implement Design System
- [ ] Step 4: Create Responsive Layouts
- [ ] Step 5: Validate Design

## Step 1: Analyze Figma Files

Extract design requirements and assets from Figma files using official API or plugin integrations.

```javascript
// Example Figma API request to get file components
const figmaApi = new Figma.Api({
  personalAccessToken: process.env.FIGMA_TOKEN
});

async function getComponents(fileKey) {
  const file = await figmaApi.getFile(fileKey);
  return Object.values(file.components).map(component => ({
    id: component.key,
    name: component.name,
    description: component.description
  }));
}
```

| Tool | Use Case | Example |
|------|----------|---------|
| Figma API | Programmatic access | `GET /v1/files/:key/components` |
| Figmagic | Sync design tokens | `figmagic sync tokens` |
| Anima | Export production code | `anima export react` |

## Step 2: Design Component Architecture

Implement atomic design principles with React component examples:

```jsx
// Atoms: Button component
const Button = ({ variant = 'primary', children }) => (
  <button className={`btn ${variant}`}>{children}</button>
);

// Molecules: Search Form
const SearchForm = () => (
  <form className="search-form">
    <Input placeholder="Search" />
    <Button type="submit">Search</Button>
  </form>
);
```

**Atomic Design Layers:**
1. Atoms: Basic UI elements (buttons, inputs)
2. Molecules: Functional combinations
3. Organisms: Complex layouts
4. Templates: Page structure
5. Pages: Specific instances

## Step 3: Implement Design System

Create consistent design tokens in CSS and Tailwind:

```css
/* CSS Design Tokens */
:root {
  --color-primary: #3B82F6;
  --spacing-md: 1rem;
  --radius-sm: 0.25rem;
}

/* Tailwind config example */
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: '#3B82F6',
      },
      spacing: {
        'md': '1rem',
      }
    }
  }
```

| Token Type | Example Values |
|-----------|----------------|
| Colors | Primary, secondary, error |
| Spacing | 0.5rem - 8rem |
| Typography | Font sizes, weights |
| Shadows | Elevation levels |

## Step 4: Create Responsive Layouts

Mobile-first CSS with media queries:

```css
/* Mobile-first approach */
.container {
  width: 100%;
  padding: 1rem;
}

/* Tablet */
@media (min-width: 768px) {
  .container {
    max-width: 720px;
    margin: 0 auto;
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .container {
    max-width: 1140px;
  }
}
```

| Device | Breakpoint | Use Case |
|--------|------------|----------|
| Mobile | < 768px | Single column |
| Tablet | 768-1024px | Two column |
| Desktop | > 1024px | Full layout |

## Step 5: Validate Design

**Success Criteria:**
- All components pass accessibility checks (WCAG AA+)
- Responsive layouts work across all breakpoints
- Design tokens maintain consistency
- Figma implementation matches spec within 2px

```bash
# Validate with automated tools
npm run test:accessibility
npm run lint:design-tokens
npx responsive-screenshot-test
```

**Common Validation Tools:**
- Storybook (component testing)
- Chromatic (visual regression)
- Lighthouse (accessibility)
- Stylelint (CSS validation)