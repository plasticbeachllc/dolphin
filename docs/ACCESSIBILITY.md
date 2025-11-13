# Accessibility Guide for Dolphin

## Table of Contents

1. [Introduction](#introduction)
2. [Core Principles](#core-principles)
3. [Keyboard Navigation](#keyboard-navigation)
4. [Screen Reader Support](#screen-reader-support)
5. [Visual Accessibility](#visual-accessibility)
6. [Webview Accessibility](#webview-accessibility)
7. [Extension-Specific Considerations](#extension-specific-considerations)
8. [Testing Strategy](#testing-strategy)
9. [Common Patterns](#common-patterns)
10. [Resources](#resources)

---

## Introduction

Accessibility is a fundamental requirement, not an optional feature. This guide outlines the standards and practices for ensuring Dolphin is usable by developers with diverse abilities, including those who:

- Use screen readers (NVDA, JAWS, VoiceOver, Narrator)
- Navigate exclusively via keyboard
- Have visual impairments (low vision, color blindness)
- Use alternative input devices
- Have motor control limitations
- Experience cognitive differences

**Accessibility is not compliance—it's about building a product that works for everyone.**

---

## Core Principles

### WCAG 2.1 AA Compliance

We target [WCAG 2.1 Level AA](https://www.w3.org/WAI/WCAG21/quickref/) compliance as our baseline:

- **Perceivable**: Information must be presentable in ways users can perceive
- **Operable**: UI components must be operable by all users
- **Understandable**: Information and operation must be understandable
- **Robust**: Content must work with current and future assistive technologies

### VSCode Accessibility Standards

VSCode has excellent built-in accessibility support. We must:

1. **Leverage VSCode's accessibility features** rather than reimplementing them
2. **Follow VSCode's accessibility patterns** for consistency
3. **Test with VSCode's screen reader mode** (`kb(editor.action.toggleScreenReaderAccessibilityMode)`)
4. **Use VSCode's high contrast theme support**

### Inclusive Design

- **Design for keyboard-first workflows** (many developers prefer this anyway)
- **Provide multiple ways to accomplish tasks**
- **Avoid time-based interactions** that pressure users
- **Make error recovery easy and forgiving**

---

## Keyboard Navigation

### Fundamental Requirements

#### Tab Order

```typescript
// ✅ GOOD: Logical, predictable tab order
<div role="dialog">
  <h2 id="dialog-title">Confirm Action</h2>
  <p>Are you sure you want to proceed?</p>
  <button>Cancel</button>
  <button>Confirm</button>
</div>

// ❌ BAD: Non-logical tab order using tabindex
<div role="dialog">
  <button tabindex="3">Confirm</button>
  <p tabindex="2">Are you sure?</p>
  <button tabindex="1">Cancel</button>
</div>
```

**Rules:**

- Natural DOM order should define tab order
- Use `tabindex="0"` to add items to tab order
- Use `tabindex="-1"` to remove from tab order (but keep programmatically focusable)
- **Never use positive tabindex values** (they break natural order)

#### Focus Indicators

```css
/* ✅ GOOD: Visible focus indicators */
button:focus-visible {
  outline: 2px solid var(--vscode-focusBorder);
  outline-offset: 2px;
}

/* ❌ BAD: Removing focus indicators */
button:focus {
  outline: none;
}
```

**Requirements:**

- Minimum 2px outline width
- Contrast ratio of at least 3:1 against background
- Use VSCode's `--vscode-focusBorder` color token
- Consider `:focus-visible` to avoid showing focus on mouse clicks

#### Keyboard Shortcuts

All major actions must have keyboard shortcuts:

```typescript
// Register keyboard shortcuts in package.json
{
  "contributes": {
    "keybindings": [
      {
        "command": "dolphin.openChat",
        "key": "ctrl+alt+d",
        "mac": "cmd+alt+d",
        "when": "editorTextFocus"
      }
    ]
  }
}
```

**Best Practices:**

- Provide sensible defaults that don't conflict with VSCode/OS shortcuts
- Make all shortcuts configurable
- Document shortcuts in the README and UI
- Support standard shortcuts: `Escape` to close, `Enter` to submit, `Ctrl+Z` to undo

#### Focus Management

```typescript
// ✅ GOOD: Proper focus management in dialogs
class ConfirmDialog {
  private previousFocus: HTMLElement | null = null;

  show() {
    this.previousFocus = document.activeElement as HTMLElement;
    this.dialog.showModal();
    this.firstFocusableElement.focus();
  }

  close() {
    this.dialog.close();
    this.previousFocus?.focus();
  }
}

// ❌ BAD: Not managing focus
function showDialog() {
  document.querySelector(".dialog").style.display = "block";
  // Focus is lost, user is stuck
}
```

**Rules:**

- Save focus before opening dialogs/modals
- Restore focus when closing
- Trap focus within modal dialogs
- Move focus to appropriate element after actions (e.g., after deletion, focus next item)

### VSCode-Specific Keyboard Support

#### Command Palette Integration

```typescript
// Register commands that appear in Command Palette
vscode.commands.registerCommand("dolphin.action", async () => {
  // Ensure all major features are accessible via Command Palette
});
```

#### Quick Pick Menus

```typescript
// Use VSCode's QuickPick for accessible selection
const items = ["Option 1", "Option 2", "Option 3"];
const selected = await vscode.window.showQuickPick(items, {
  placeHolder: "Select an option",
  canPickMany: false,
});
```

#### Status Bar Integration

```typescript
// Status bar items should be keyboard accessible
const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
statusBarItem.command = "dolphin.showStatus";
statusBarItem.text = "$(robot) Dolphin";
statusBarItem.tooltip = "Click to open Dolphin (Ctrl+Alt+D)";
```

---

## Screen Reader Support

### ARIA Labels and Roles

#### Semantic HTML First

```svelte
<!-- ✅ GOOD: Semantic HTML provides context -->
<button type="button" on:click={handleSubmit}>
  Submit Request
</button>

<nav aria-label="Main navigation">
  <ul>
    <li><a href="#chat">Chat</a></li>
    <li><a href="#history">History</a></li>
  </ul>
</nav>

<!-- ❌ BAD: Div soup with no semantics -->
<div class="button" on:click={handleSubmit}>
  Submit Request
</div>
```

#### ARIA When Needed

```svelte
<!-- Button with icon needs aria-label -->
<button
  type="button"
  aria-label="Close dialog"
  on:click={close}
>
  <CloseIcon />
</button>

<!-- Dynamic content needs live regions -->
<div
  role="status"
  aria-live="polite"
  aria-atomic="true"
>
  {statusMessage}
</div>

<!-- Loading states -->
<button
  type="button"
  aria-busy={isLoading}
  disabled={isLoading}
>
  {#if isLoading}
    <Spinner aria-hidden="true" />
    Loading...
  {:else}
    Submit
  {/if}
</button>
```

#### Common ARIA Patterns

**Status Messages:**

```svelte
<!-- Polite: Non-urgent updates -->
<div role="status" aria-live="polite">
  Code generated successfully
</div>

<!-- Assertive: Important updates -->
<div role="alert" aria-live="assertive">
  Error: Unable to connect to API
</div>
```

**Progress Indicators:**

```svelte
<div
  role="progressbar"
  aria-valuenow={progress}
  aria-valuemin={0}
  aria-valuemax={100}
  aria-label="Indexing workspace"
>
  <div class="progress-bar" style="width: {progress}%" />
</div>
```

**Expandable Sections:**

```svelte
<button
  type="button"
  aria-expanded={isExpanded}
  aria-controls="section-content"
  on:click={toggle}
>
  {isExpanded ? 'Collapse' : 'Expand'} Section
</button>

<div id="section-content" hidden={!isExpanded}>
  Content here
</div>
```

### Announcing Dynamic Content

#### Streaming Messages

```typescript
// Announce streaming AI responses appropriately
class MessageStream {
  private announceDebounce: NodeJS.Timeout | null = null;

  updateStreamingMessage(content: string) {
    // Visual update
    this.updateDisplay(content);

    // Debounced screen reader announcement
    if (this.announceDebounce) {
      clearTimeout(this.announceDebounce);
    }

    this.announceDebounce = setTimeout(() => {
      this.announceToScreenReader(content);
    }, 1000); // Announce after 1s of no updates
  }

  private announceToScreenReader(content: string) {
    // Use aria-live region
    const liveRegion = document.getElementById("live-region");
    if (liveRegion) {
      liveRegion.textContent = `AI response updated: ${content.slice(0, 100)}...`;
    }
  }
}
```

**Best Practices:**

- Don't announce every character in streaming responses
- Debounce announcements to avoid overwhelming users
- Provide a summary rather than full content
- Allow users to navigate to full content at their pace

#### Status Updates

```svelte
<script>
  let status = '';

  async function performAction() {
    status = 'Starting analysis...';
    await analyze();
    status = 'Analysis complete. Found 3 issues.';
  }
</script>

<div role="status" aria-live="polite" aria-atomic="true">
  {status}
</div>
```

### Screen Reader Testing

#### Recommended Screen Readers

- **Windows**: NVDA (free), JAWS (paid)
- **macOS**: VoiceOver (built-in)
- **Linux**: Orca (free)

#### Testing Checklist

- [ ] All interactive elements are reachable and announced
- [ ] Button purposes are clear from their labels
- [ ] Form inputs have associated labels
- [ ] Error messages are announced
- [ ] Status changes are announced appropriately
- [ ] Modal dialogs trap focus and announce their purpose
- [ ] Navigation landmarks are properly labeled
- [ ] Images have alt text (or aria-hidden if decorative)
- [ ] Tables have proper headers
- [ ] Lists are marked up as lists

---

## Visual Accessibility

### Color Contrast

#### Minimum Requirements (WCAG AA)

- **Normal text**: 4.5:1 contrast ratio
- **Large text** (18pt+/14pt+ bold): 3:1 contrast ratio
- **UI components**: 3:1 contrast ratio
- **Focus indicators**: 3:1 contrast ratio

#### Using VSCode Color Tokens

```css
/* ✅ GOOD: Use VSCode theme colors */
.message-user {
  background-color: var(--vscode-editor-background);
  color: var(--vscode-editor-foreground);
  border: 1px solid var(--vscode-panel-border);
}

.message-assistant {
  background-color: var(--vscode-editor-inactiveSelectionBackground);
  color: var(--vscode-editor-foreground);
}

/* Error states */
.error {
  color: var(--vscode-errorForeground);
  border-color: var(--vscode-inputValidation-errorBorder);
}

/* ❌ BAD: Hard-coded colors */
.message {
  background: #ffffff;
  color: #000000;
}
```

**Available Color Tokens:**

- `--vscode-foreground`
- `--vscode-editor-background`
- `--vscode-editor-foreground`
- `--vscode-button-background`
- `--vscode-button-foreground`
- `--vscode-input-background`
- `--vscode-focusBorder`
- Many more in [VSCode Theme Color Reference](https://code.visualstudio.com/api/references/theme-color)

### Color Independence

**Never rely on color alone to convey information:**

```svelte
<!-- ✅ GOOD: Color + icon + text -->
<div class="status-success">
  <CheckIcon aria-hidden="true" />
  <span>Success: Code generated</span>
</div>

<div class="status-error">
  <ErrorIcon aria-hidden="true" />
  <span>Error: API connection failed</span>
</div>

<!-- ❌ BAD: Color only -->
<div class="green">Code generated</div>
<div class="red">Connection failed</div>
```

### Typography

```css
/* Minimum font sizes and line heights */
.code-block {
  font-family: var(--vscode-editor-font-family);
  font-size: max(12px, var(--vscode-editor-font-size));
  line-height: 1.5;
}

.prose {
  font-family: var(--vscode-font-family);
  font-size: 13px;
  line-height: 1.6;

  /* Reasonable line length for readability */
  max-width: 65ch;
}
```

**Guidelines:**

- Minimum font size: 12px (respect user's VSCode settings)
- Line height: 1.5 for body text, 1.3 for headings
- Line length: 45-75 characters for optimal readability
- Use relative units (em, rem) where possible

### High Contrast Mode

VSCode's high contrast themes must be supported:

```typescript
// Detect high contrast mode
const isHighContrast =
  vscode.window.activeColorTheme.kind === vscode.ColorThemeKind.HighContrast ||
  vscode.window.activeColorTheme.kind === vscode.ColorThemeKind.HighContrastLight;

// Apply appropriate styles
if (isHighContrast) {
  panel.webview.html = getWebviewContent({ highContrast: true });
}
```

```css
/* High contrast specific styles */
@media (prefers-contrast: more) {
  .button {
    border: 2px solid currentColor;
  }

  .message {
    border: 1px solid var(--vscode-foreground);
  }
}
```

### Motion and Animation

```css
/* Respect reduced motion preferences */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* Default animations should be subtle */
.message-enter {
  animation: slide-in 200ms ease-out;
}

@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

---

## Webview Accessibility

### HTML Structure

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Dolphin Chat</title>
  </head>
  <body>
    <!-- Main landmark -->
    <main id="app">
      <!-- Navigation landmark -->
      <nav aria-label="Chat options">
        <button type="button">New Chat</button>
        <button type="button">History</button>
      </nav>

      <!-- Main content region -->
      <section aria-label="Chat messages">
        <div role="log" aria-live="polite" aria-relevant="additions">
          <!-- Messages appear here -->
        </div>
      </section>

      <!-- Form landmark -->
      <form aria-label="Message input">
        <label for="message-input" class="sr-only"> Enter your message </label>
        <textarea
          id="message-input"
          aria-describedby="input-help"
          placeholder="Ask Dolphin anything..."
        ></textarea>
        <div id="input-help" class="sr-only">
          Press Ctrl+Enter to send. Use Shift+Enter for new line.
        </div>
        <button type="submit">Send</button>
      </form>
    </main>

    <!-- Live region for announcements -->
    <div id="live-region" role="status" aria-live="polite" aria-atomic="true" class="sr-only"></div>
  </body>
</html>
```

### Screen Reader Only Content

```css
/* Screen reader only text */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

```svelte
<!-- Provide context for icon buttons -->
<button type="button" on:click={copy}>
  <CopyIcon aria-hidden="true" />
  <span class="sr-only">Copy code to clipboard</span>
</button>
```

### Interactive Code Blocks

```svelte
<script>
  let copied = false;

  async function copyCode() {
    await navigator.clipboard.writeText(code);
    copied = true;
    announceToScreenReader('Code copied to clipboard');
    setTimeout(() => copied = false, 2000);
  }
</script>

<div class="code-block" role="region" aria-label="Code snippet">
  <div class="code-header">
    <span class="language">{language}</span>
    <button
      type="button"
      on:click={copyCode}
      aria-label="Copy code to clipboard"
    >
      {#if copied}
        <CheckIcon aria-hidden="true" />
        <span class="sr-only">Copied</span>
      {:else}
        <CopyIcon aria-hidden="true" />
        <span class="sr-only">Copy</span>
      {/if}
    </button>
  </div>
  <pre><code>{code}</code></pre>
</div>
```

### Webview-Extension Communication

```typescript
// Announce actions taken in extension to webview users
class WebviewManager {
  announceAction(message: string) {
    this.panel.webview.postMessage({
      type: "announce",
      message: message,
    });
  }
}

// In webview
window.addEventListener("message", (event) => {
  const message = event.data;

  if (message.type === "announce") {
    const liveRegion = document.getElementById("live-region");
    if (liveRegion) {
      liveRegion.textContent = message.message;
    }
  }
});
```

---

## Extension-Specific Considerations

### Context Menus

```typescript
// Make context menu items keyboard accessible
vscode.commands.registerCommand("dolphin.contextAction", async () => {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  // Provide feedback
  vscode.window.showInformationMessage("Analyzing code...");

  // Perform action
  const result = await analyzeCode(editor.document);

  // Show results accessibly
  await vscode.window.showQuickPick(result.suggestions, {
    placeHolder: "Select a suggestion to apply",
  });
});
```

### Notifications

```typescript
// Use appropriate notification levels
// Information - non-critical updates
vscode.window.showInformationMessage("Code generated successfully");

// Warning - things users should know about
vscode.window.showWarningMessage("API rate limit approaching");

// Error - problems that need attention
vscode.window
  .showErrorMessage("Failed to connect to API", "Retry", "Settings")
  .then((selection) => {
    if (selection === "Retry") {
      // Retry logic
    }
  });
```

### Progress Indicators

```typescript
// Long-running operations should show progress
vscode.window.withProgress(
  {
    location: vscode.ProgressLocation.Notification,
    title: "Dolphin: Indexing workspace",
    cancellable: true,
  },
  async (progress, token) => {
    token.onCancellationRequested(() => {
      vscode.window.showInformationMessage("Indexing cancelled");
    });

    for (let i = 0; i < 100; i++) {
      if (token.isCancellationRequested) break;

      progress.report({
        increment: 1,
        message: `${i}% complete`,
      });

      await processFile(files[i]);
    }
  }
);
```

### Settings UI

```json
// Make settings accessible with clear descriptions
{
  "contributes": {
    "configuration": {
      "title": "Dolphin",
      "properties": {
        "dolphin.autoIndex": {
          "type": "boolean",
          "default": true,
          "description": "Automatically index workspace files for better context awareness",
          "order": 1
        },
        "dolphin.keyboardShortcuts": {
          "type": "object",
          "description": "Customize keyboard shortcuts for Dolphin actions",
          "properties": {
            "openChat": {
              "type": "string",
              "default": "ctrl+alt+d",
              "description": "Keyboard shortcut to open chat panel"
            }
          }
        }
      }
    }
  }
}
```

---

## Testing Strategy

### Automated Testing

#### axe-core Integration

```typescript
// Install: npm install --save-dev @axe-core/playwright
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Webview accessibility", () => {
  test("should not have automatically detectable accessibility issues", async ({ page }) => {
    await page.goto("http://localhost:3000");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test("keyboard navigation works", async ({ page }) => {
    await page.goto("http://localhost:3000");

    // Tab through interactive elements
    await page.keyboard.press("Tab");
    await expect(page.locator("button:first-of-type")).toBeFocused();

    await page.keyboard.press("Tab");
    await expect(page.locator("textarea")).toBeFocused();

    // Escape closes modal
    await page.click('button:has-text("Open Settings")');
    await page.keyboard.press("Escape");
    await expect(page.locator('[role="dialog"]')).not.toBeVisible();
  });
});
```

#### ARIA Validation

```typescript
test("ARIA attributes are valid", async ({ page }) => {
  await page.goto("http://localhost:3000");

  // Check for invalid ARIA
  const invalidAria = await page.evaluate(() => {
    const elements = document.querySelectorAll("[role]");
    const invalid = [];

    elements.forEach((el) => {
      const role = el.getAttribute("role");
      const validRoles = [
        "button",
        "dialog",
        "navigation",
        "main",
        "region",
        "status",
        "alert",
        "log",
        "progressbar",
        "menu",
      ];

      if (!validRoles.includes(role!)) {
        invalid.push({ role, tag: el.tagName });
      }
    });

    return invalid;
  });

  expect(invalidAria).toEqual([]);
});
```

### Manual Testing Checklist

#### Keyboard Testing

- [ ] Tab through all interactive elements in logical order
- [ ] Shift+Tab moves backwards
- [ ] Enter/Space activates buttons and links
- [ ] Escape closes modals and menus
- [ ] Arrow keys navigate lists and menus
- [ ] All features accessible without mouse
- [ ] Focus indicator always visible
- [ ] No keyboard traps

#### Screen Reader Testing

Using NVDA (Windows), VoiceOver (macOS), or Orca (Linux):

- [ ] Navigate through headings (H key)
- [ ] Navigate through landmarks (D key)
- [ ] Navigate through buttons (B key)
- [ ] Navigate through forms (F key)
- [ ] All interactive elements announced with purpose
- [ ] State changes announced (loading, error, success)
- [ ] Dynamic content announced appropriately
- [ ] Images have alt text or are hidden
- [ ] Tables navigable and understandable

#### Visual Testing

- [ ] 4.5:1 contrast for normal text
- [ ] 3:1 contrast for large text and UI components
- [ ] Works in high contrast mode
- [ ] Works in light and dark themes
- [ ] Color not sole means of conveying information
- [ ] Text remains readable at 200% zoom
- [ ] Animations respect prefers-reduced-motion

#### Browser Testing

Test in Chromium-based webview (VSCode's default):

- [ ] Chrome DevTools Lighthouse audit
- [ ] Chrome DevTools accessibility tree
- [ ] Keyboard navigation
- [ ] Screen reader compatibility

---

## Common Patterns

### Accessible Button Groups

```svelte
<div role="group" aria-label="Message actions">
  <button
    type="button"
    aria-label="Copy message"
    on:click={copy}
  >
    <CopyIcon aria-hidden="true" />
  </button>

  <button
    type="button"
    aria-label="Edit message"
    on:click={edit}
  >
    <EditIcon aria-hidden="true" />
  </button>

  <button
    type="button"
    aria-label="Delete message"
    on:click={remove}
  >
    <DeleteIcon aria-hidden="true" />
  </button>
</div>
```

### Accessible Forms

```svelte
<form on:submit|preventDefault={handleSubmit}>
  <div class="form-group">
    <label for="api-key">
      API Key
      <span aria-label="required">*</span>
    </label>
    <input
      id="api-key"
      type="password"
      bind:value={apiKey}
      required
      aria-required="true"
      aria-invalid={error ? 'true' : 'false'}
      aria-describedby={error ? 'api-key-error' : 'api-key-help'}
    />
    <div id="api-key-help" class="help-text">
      Get your API key from Anthropic Console
    </div>
    {#if error}
      <div id="api-key-error" role="alert" class="error-text">
        {error}
      </div>
    {/if}
  </div>

  <button type="submit" disabled={!apiKey}>
    Save Settings
  </button>
</form>
```

### Accessible Modals

```svelte
<script>
  import { onMount } from 'svelte';

  let dialogElement: HTMLDialogElement;
  let firstFocusable: HTMLElement;
  let lastFocusable: HTMLElement;

  export function show() {
    dialogElement.showModal();
    firstFocusable?.focus();
  }

  function close() {
    dialogElement.close();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      close();
    }

    // Trap focus
    if (e.key === 'Tab') {
      const focusables = dialogElement.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      const first = focusables[0] as HTMLElement;
      const last = focusables[focusables.length - 1] as HTMLElement;

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }
</script>

<dialog
  bind:this={dialogElement}
  aria-labelledby="dialog-title"
  aria-describedby="dialog-description"
  on:keydown={handleKeydown}
>
  <header>
    <h2 id="dialog-title">Confirm Action</h2>
    <button
      type="button"
      aria-label="Close dialog"
      on:click={close}
      bind:this={firstFocusable}
    >
      <CloseIcon aria-hidden="true" />
    </button>
  </header>

  <div id="dialog-description">
    <p>Are you sure you want to proceed with this action?</p>
  </div>

  <footer>
    <button type="button" on:click={close}>
      Cancel
    </button>
    <button
      type="button"
      on:click={confirm}
      bind:this={lastFocusable}
    >
      Confirm
    </button>
  </footer>
</dialog>
```

### Accessible Tabs

```svelte
<script>
  let selectedTab = 0;
  const tabs = ['Chat', 'History', 'Settings'];

  function handleKeydown(e: KeyboardEvent, index: number) {
    if (e.key === 'ArrowRight') {
      selectedTab = (index + 1) % tabs.length;
      focusTab(selectedTab);
    } else if (e.key === 'ArrowLeft') {
      selectedTab = (index - 1 + tabs.length) % tabs.length;
      focusTab(selectedTab);
    } else if (e.key === 'Home') {
      selectedTab = 0;
      focusTab(0);
    } else if (e.key === 'End') {
      selectedTab = tabs.length - 1;
      focusTab(tabs.length - 1);
    }
  }

  function focusTab(index: number) {
    const tabButton = document.querySelector(
      `button[role="tab"]:nth-child(${index + 1})`
    ) as HTMLElement;
    tabButton?.focus();
  }
</script>

<div class="tabs">
  <div role="tablist" aria-label="Main sections">
    {#each tabs as tab, i}
      <button
        role="tab"
        aria-selected={selectedTab === i}
        aria-controls="panel-{i}"
        tabindex={selectedTab === i ? 0 : -1}
        on:click={() => selectedTab = i}
        on:keydown={(e) => handleKeydown(e, i)}
      >
        {tab}
      </button>
    {/each}
  </div>

  {#each tabs as tab, i}
    <div
      role="tabpanel"
      id="panel-{i}"
      aria-labelledby="tab-{i}"
      hidden={selectedTab !== i}
      tabindex="0"
    >
      <slot name="panel-{i}" />
    </div>
  {/each}
</div>
```

---

## Resources

### Documentation

- [VSCode Accessibility Guide](https://code.visualstudio.com/docs/editor/accessibility)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [MDN ARIA Guide](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA)
- [A11y Project](https://www.a11yproject.com/)
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)

### Testing Tools

- [axe DevTools](https://www.deque.com/axe/devtools/)
- [WAVE Browser Extension](https://wave.webaim.org/extension/)
- [Lighthouse](https://developers.google.com/web/tools/lighthouse)
- [NVDA Screen Reader](https://www.nvaccess.org/) (Windows, free)
- [VoiceOver](https://www.apple.com/accessibility/voiceover/) (macOS, built-in)

### VSCode APIs

- [Theme Colors](https://code.visualstudio.com/api/references/theme-color)
- [Extension Guidelines](https://code.visualstudio.com/api/references/extension-guidelines)
- [Webview API](https://code.visualstudio.com/api/extension-guides/webview)

### Screen Reader Commands

**NVDA (Windows):**

- `Insert + Down`: Enter focus mode
- `H`: Next heading
- `D`: Next landmark
- `B`: Next button
- `F`: Next form field

**VoiceOver (macOS):**

- `VO + Space`: Activate element
- `VO + →/←`: Navigate elements
- `VO + U`: Open rotor
- `VO + H H`: Next heading

**Orca (Linux):**

- `H`: Next heading
- `D`: Next landmark
- `B`: Next button
- `Insert + Space`: Toggle focus/browse mode

---

## Conclusion

Accessibility is not a checklist—it's an ongoing commitment to building inclusive software. This guide provides the foundation, but accessibility testing should be integrated into every sprint:

1. **Design with accessibility in mind** from the start
2. **Test with real users** who rely on assistive technologies
3. **Automate what you can** with axe-core and Playwright
4. **Manually test regularly** with keyboard and screen readers
5. **Stay current** with WCAG updates and best practices

Remember: **An accessible product is a better product for everyone.**

---

_Last updated: 2025_
_Maintained by: Dolphin Team_
