# Shadcn Component Management

## Workflow

```
Prerequisites → Component Search → Implementation → Customization → Validation
```

**Progress:**
- [ ] Step 1: Verify project setup
- [ ] Step 2: Search components
- [ ] Step 3: Implement components
- [ ] Step 4: Customize design
- [ ] Step 5: Validate implementation

## Step 1: Verify Project Setup

Check if shadcn is initialized in the project:

```bash
npx shadcn@latest --help | grep "components.json"
```

If no configuration exists, initialize:

```bash
npx shadcn@latest init
```

| Config | Default Path | Description |
|--------|--------------|-----------|
| components.json | ./components.json | Component registry configuration |
| tailwind.config.js | ./tailwind.config.js | Theme configuration |

## Step 2: Search Components

Use MCP tools to find components:

```javascript
// Search registry for components
const results = shadcn___search_items_in_registries(
  registries, 
  "date-picker"
);
console.log(results.map(r => r.name));
```

Common component categories:

| Category | Components |
|---------|------------|
| Forms | input, select, checkbox, radio-group |
| Layout | card, dialog, sheet, drawer, tabs |
| Feedback | alert, toast, skeleton, progress |

## Step 3: Implement Components

For simple additions:

```javascript
// Get installation command
const cmd = shadcn___get_add_command_for_items([
  "@shadcn/ui/button",
  "@shadcn/ui/input"
]);
console.log(`Run: ${cmd}`);
```

Example implementation of a login form:

```tsx
// app/login/page.tsx
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export default function Login() {
  return (
    <div className="space-y-4">
      <Input placeholder="Email" type="email" />
      <Input placeholder="Password" type="password" />
      <Button className="w-full">Sign In</Button>
    </div>
  )
}
```

## Step 4: Customize Design

For custom styling:

```bash
# Modify tailwind config
npx shadcn@latest config tailwind.config.js
```

Example tailwind.config.js extension:

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          500: "#3B82F6",
          600: "#2563EB"
        }
      }
    }
  }
}
```

## Step 5: Validate Implementation

Run audit checklist:

```bash
npx shadcn@latest audit
```

Verify components work as expected:
1. Check UI rendering in browser
2. Validate form interactions
3. Confirm responsive design
4. Test accessibility features

## Complex UI Workflow

For multi-component features:

1. **Plan hierarchy**: Map component relationships
2. **Generate structure**: 
   ```javascript
   shadcn___generate_component_hierarchy([
     "card",
     "form",
     "button"
   ])
   ```
3. **Implement with dependencies**: 
   ```bash
   npx shadcn@latest add card form button
   ```
4. **Test integration**: 
   ```tsx
   // Example card with form
   import { Card } from "@/components/ui/card"
   import { LoginForm } from "@/components/login-form"
   
   <Card className="p-6">
     <LoginForm />
   </Card>
   ```