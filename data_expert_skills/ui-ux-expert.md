# UI/UX Design Expert

## Workflow

```
User Research → Design System Setup → Component TDD → Performance Optimization → Validation
```

**Progress:**
- [ ] Step 1: Conduct User Research
- [ ] Step 2: Implement Design System
- [ ] Step 3: Develop Accessible Components
- [ ] Step 4: Optimize Performance
- [ ] Step 5: Validate & Test

## Step 1: Conduct User Research

### Key Methodologies

1. **Contextual Inquiry**: Observe users in their natural environment
2. **Usability Testing**: Remote/in-person testing with prototypes
3. **Surveys & Interviews**: Quantitative/qualitative data collection
4. **Analytics Review**: Heatmaps, click tracking, conversion funnels

| Method | Deliverable | Tools |
|-------|-------------|-------|
| User Interviews | Personas, Pain Points | Figma, Miro | 
| A/B Testing | Conversion Metrics | Optimizely, Google Optimize |
| Card Sorting | Information Architecture | UXPressia, Mural |

### Research Template
```markdown
# User Research Plan

## Objectives
- Understand user needs for [feature/product]
- Identify accessibility requirements

## Participants
- 5 users with diverse abilities
- Mix of tech-savvy and novice users

## Tasks
1. Complete primary workflow
2. Locate key feature X
3. Test screen reader navigation
```

## Step 2: Implement Design System

### Core Components

1. **Design Tokens**: Centralized CSS variables for colors, spacing, typography
2. **Component Library**: Reusable Vue/React components with accessibility baked in
3. **Documentation**: Storybook with usage guidelines and examples

| Tool | Purpose | Integration |
|------|---------|-------------|
| Figma | Source of truth | Dev Mode, Variables |
| Style Dictionary | Token management | JSON config, CLI |
| Storybook | Component docs | CSF files, Canvas |

### Figma Automation Example
```javascript
// figma.tokens.js - Sync tokens from Figma API
const { Client } = require('figma-js');

const client = Client({ personalAccessToken: process.env.FIGMA_TOKEN });

async function getDesignTokens() {
  const styles = await client.files.listVariableCollectionsAsync('FIGMA_FILE_KEY');
  const tokens = styles.variables.map(var => ({
    name: var.name,
    value: var.valuesCollection[0].value,
    type: var.resolvedType
  }));
  
  // Generate CSS variables
  const css = tokens.map(t => `--${t.name}: ${t.value};`).join('\n');
  fs.writeFileSync('tokens.css', css);
}
```

## Step 3: Develop Accessible Components

### Complete Button Component Test
```typescript
// tests/components/Button.test.ts (completed)
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Button from '@/components/ui/Button.vue'

describe('Button', () => {
  // Accessibility tests
  it('has accessible role and label', () => {
    const wrapper = mount(Button, {
      props: { label: 'Submit' }
    })
    expect(wrapper.attributes('role')).toBe('button')
    expect(wrapper.text()).toContain('Submit')
  })

  it('supports keyboard activation', async () => {
    const wrapper = mount(Button, {
      props: { label: 'Click me' }
    })
    await wrapper.trigger('keydown.enter')
    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('has visible focus indicator', () => {
    const wrapper = mount(Button, {
      props: { label: 'Focus me' }
    })
    expect(wrapper.classes()).not.toContain('no-outline')
  })

  it('meets minimum touch target size', () => {
    const wrapper = mount(Button, {
      props: { label: 'Tap me' }
    })
    expect(wrapper.attributes('style')).toContain('min-width: 44px')
  })

  // Responsive behavior tests
  it('adapts to container width', () => {
    const wrapper = mount(Button, {
      props: { label: 'Responsive', fullWidth: true }
    })
    expect(wrapper.classes()).toContain('w-full')
  })

  // Loading state tests
  it('shows loading state correctly', async () => {
    const wrapper = mount(Button, {
      props: { label: 'Submit', loading: true }
    })
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    expect(wrapper.attributes('disabled')).toBeDefined()
  })

  // Color contrast (visual regression)
  it('maintains sufficient color contrast', () => {
    const wrapper = mount(Button, {
      props: { label: 'Contrast', variant: 'primary' }
    })
    expect(wrapper.classes()).toContain('high-contrast')
  })
})
```

## Step 4: Optimize Performance

### Critical CSS Extraction
```bash
# Using PurgeCSS to extract critical CSS
npx purgecss 
  --content ./src/**/*.vue 
  --css ./src/assets/main.css 
  --output ./dist/critical.css
```

| Optimization | Metric Impact | Implementation |
|-------------|---------------|----------------|
| Lazy Images | LCP +15% | Intersection Observer |
| Code Splitting | FCP -2s | Webpack dynamic imports |
| WebP AVIF | File size -40% | <picture> element |

## Step 5: Validate & Test

### Accessibility Audit
```bash
# Run axe-core accessibility audit
npx axe-cli 
  --url https://your-site.com 
  --output results.json
```

### Lighthouse CI
```javascript
// lighthouse.config.js
module.exports = {
  extends: 'lighthouse:default',
  settings: {
    preset: 'performance',
    throttlingMethod: 'simulate',
    emulatedFormFactor: 'desktop'
  }
};
```

**Success Criteria:**
- WCAG 2.2 AA compliance
- Lighthouse performance score >90
- Core Web Vitals in green
- All unit tests passing
- Design system coverage >90%