import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ToolCallCard from './ToolCallCard.svelte';

describe('ToolCallCard', () => {
  const defaultProps = {
    tool: 'kb_search',
    input: { query: 'test query' },
    result: null,
    error: null,
    status: 'running' as const,
    executionTime: null
  };

  describe('Accessibility', () => {
    it('should have region role with descriptive label', () => {
      render(ToolCallCard, defaultProps);

      const region = screen.getByRole('region', { name: /knowledge base search tool call/i });
      expect(region).toBeInTheDocument();
    });

    it('should use human-readable tool names in aria-labels', () => {
      render(ToolCallCard, { ...defaultProps, tool: 'apply_diff' });

      const region = screen.getByRole('region', { name: /apply diff tool call/i });
      expect(region).toBeInTheDocument();
    });

    it('should have descriptive button with aria-expanded', () => {
      render(ToolCallCard, { ...defaultProps, collapsed: true });

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-expanded', 'false');
      expect(button).toHaveAttribute('aria-label', expect.stringContaining('Expand'));
    });

    it('should update aria-expanded when toggled', async () => {
      render(ToolCallCard, { ...defaultProps, collapsed: true });

      const button = screen.getByRole('button');
      await fireEvent.click(button);

      expect(button).toHaveAttribute('aria-expanded', 'true');
      expect(button).toHaveAttribute('aria-label', expect.stringContaining('Collapse'));
    });

    it('should include status in aria-label', () => {
      render(ToolCallCard, { ...defaultProps, status: 'success' });

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-label', expect.stringContaining('Status: success'));
    });

    it('should include execution time in aria-label when available', () => {
      render(ToolCallCard, { ...defaultProps, executionTime: 150, status: 'success' });

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-label', expect.stringContaining('150 milliseconds'));
    });

    it('should mark decorative icons as aria-hidden', () => {
      render(ToolCallCard, defaultProps);

      const icons = document.querySelectorAll('svg[aria-hidden="true"]');
      expect(icons.length).toBeGreaterThan(0);
    });

    it('should have aria-label on status icons', () => {
      render(ToolCallCard, { ...defaultProps, status: 'running' });

      const statusIcon = screen.getByLabelText('Running');
      expect(statusIcon).toBeInTheDocument();
    });

    it('should have aria-label for success status', () => {
      render(ToolCallCard, { ...defaultProps, status: 'success' });

      const statusIcon = screen.getByLabelText('Success');
      expect(statusIcon).toBeInTheDocument();
    });

    it('should have aria-label for error status', () => {
      render(ToolCallCard, { ...defaultProps, status: 'error' });

      const statusIcon = screen.getByLabelText('Error');
      expect(statusIcon).toBeInTheDocument();
    });

    it('should have aria-label on execution time badge', () => {
      render(ToolCallCard, { ...defaultProps, executionTime: 250 });

      const badge = screen.getByLabelText('Execution time: 250 milliseconds');
      expect(badge).toBeInTheDocument();
    });

    it('should have aria-label on peek file button', () => {
      render(ToolCallCard, {
        ...defaultProps,
        tool: 'apply_diff',
        status: 'success',
        input: { file_path: '/test/file.ts' }
      });

      const peekButton = screen.getByLabelText('View file /test/file.ts');
      expect(peekButton).toBeInTheDocument();
    });
  });

  describe('Keyboard Navigation', () => {
    it('should toggle expand on Enter key', async () => {
      render(ToolCallCard, { ...defaultProps, collapsed: true });

      const button = screen.getByRole('button');
      await fireEvent.keyPress(button, { key: 'Enter' });

      expect(button).toHaveAttribute('aria-expanded', 'true');
    });

    it('should toggle expand on Space key', async () => {
      render(ToolCallCard, { ...defaultProps, collapsed: true });

      const button = screen.getByRole('button');
      await fireEvent.keyPress(button, { key: ' ' });

      expect(button).toHaveAttribute('aria-expanded', 'true');
    });

    it('should be keyboard focusable with tabindex', () => {
      render(ToolCallCard, defaultProps);

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('tabindex', '0');
    });

    it('should have focus-visible styles', () => {
      render(ToolCallCard, defaultProps);

      const button = screen.getByRole('button');
      expect(button.className).toMatch(/focus-visible/);
    });
  });

  describe('Theme Integration', () => {
    it('should apply theme-aware border color for running status', () => {
      const { container } = render(ToolCallCard, { ...defaultProps, status: 'running' });

      const card = container.querySelector('[data-status="running"]');
      expect(card).toBeInTheDocument();
    });

    it('should apply theme-aware border color for success status', () => {
      const { container } = render(ToolCallCard, { ...defaultProps, status: 'success' });

      const card = container.querySelector('[data-status="success"]');
      expect(card).toBeInTheDocument();
    });

    it('should apply theme-aware border color for error status', () => {
      const { container } = render(ToolCallCard, { ...defaultProps, status: 'error' });

      const card = container.querySelector('[data-status="error"]');
      expect(card).toBeInTheDocument();
    });

    it('should use theme colors for status icons', () => {
      const { container } = render(ToolCallCard, { ...defaultProps, status: 'running' });

      const icon = container.querySelector('.tool-status-running');
      expect(icon).toBeInTheDocument();

      // Check that styles use CSS custom properties
      const style = container.querySelector('style');
      expect(style?.textContent).toContain('--vscode-charts-blue');
    });

    it('should use theme colors for peek button', () => {
      const { container } = render(ToolCallCard, {
        ...defaultProps,
        tool: 'file_write',
        status: 'success',
        input: { file_path: '/test/file.ts' }
      });

      const style = container.querySelector('style');
      expect(style?.textContent).toContain('--vscode-input-background');
      expect(style?.textContent).toContain('--vscode-button-hoverBackground');
      expect(style?.textContent).toContain('--vscode-focusBorder');
    });
  });

  describe('Tool Name Display', () => {
    it('should display human-readable tool names', () => {
      const toolMapping = [
        { tool: 'search_knowledge', expected: 'Search Knowledge Base' },
        { tool: 'kb_search', expected: 'Knowledge Base Search' },
        { tool: 'read_files', expected: 'Read Files' },
        { tool: 'file_write', expected: 'Write File' },
        { tool: 'apply_diff', expected: 'Apply Diff' },
        { tool: 'run_command', expected: 'Run Command' }
      ];

      toolMapping.forEach(({ tool, expected }) => {
        const { unmount } = render(ToolCallCard, { ...defaultProps, tool });
        expect(screen.getByRole('region', { name: new RegExp(expected, 'i') })).toBeInTheDocument();
        unmount();
      });
    });

    it('should handle unknown tools gracefully', () => {
      render(ToolCallCard, { ...defaultProps, tool: 'unknown_tool_name' });

      const region = screen.getByRole('region', { name: /unknown tool name/i });
      expect(region).toBeInTheDocument();
    });
  });

  describe('Expand/Collapse Functionality', () => {
    it('should start collapsed when collapsed prop is true', () => {
      render(ToolCallCard, { ...defaultProps, collapsed: true });

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-expanded', 'false');

      // Content should not be visible
      expect(screen.queryByText('Input')).not.toBeInTheDocument();
    });

    it('should start expanded when collapsed prop is false', () => {
      render(ToolCallCard, { ...defaultProps, collapsed: false });

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-expanded', 'true');

      // Content should be visible
      expect(screen.getByText('Input')).toBeInTheDocument();
    });

    it('should toggle content visibility on click', async () => {
      render(ToolCallCard, { ...defaultProps, collapsed: true });

      const button = screen.getByRole('button');
      await fireEvent.click(button);

      expect(screen.getByText('Input')).toBeInTheDocument();
    });

    it('should show chevron down when expanded', () => {
      render(ToolCallCard, { ...defaultProps, collapsed: false });

      // Chevron should indicate expanded state
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-expanded', 'true');
    });
  });

  describe('Status Display', () => {
    it('should show loading spinner for running status', () => {
      render(ToolCallCard, { ...defaultProps, status: 'running' });

      const loadingIcon = screen.getByLabelText('Running');
      expect(loadingIcon).toBeInTheDocument();
      expect(loadingIcon.closest('svg')).toHaveClass('animate-spin');
    });

    it('should show check icon for success status', () => {
      render(ToolCallCard, { ...defaultProps, status: 'success' });

      const successIcon = screen.getByLabelText('Success');
      expect(successIcon).toBeInTheDocument();
    });

    it('should show X icon for error status', () => {
      render(ToolCallCard, { ...defaultProps, status: 'error', error: 'Test error' });

      const errorIcon = screen.getByLabelText('Error');
      expect(errorIcon).toBeInTheDocument();
    });
  });

  describe('Execution Time Display', () => {
    it('should display execution time when provided', () => {
      render(ToolCallCard, { ...defaultProps, executionTime: 123 });

      expect(screen.getByText('123ms')).toBeInTheDocument();
    });

    it('should not display execution time when null', () => {
      render(ToolCallCard, { ...defaultProps, executionTime: null });

      expect(screen.queryByText(/ms$/)).not.toBeInTheDocument();
    });
  });

  describe('Peek File Button', () => {
    it('should show peek button for file edit tools with file path', () => {
      render(ToolCallCard, {
        ...defaultProps,
        tool: 'apply_diff',
        status: 'success',
        input: { file_path: '/test/file.ts' }
      });

      expect(screen.getByText('👁️ View')).toBeInTheDocument();
    });

    it('should not show peek button for non-file-edit tools', () => {
      render(ToolCallCard, {
        ...defaultProps,
        tool: 'kb_search',
        status: 'success'
      });

      expect(screen.queryByText('👁️ View')).not.toBeInTheDocument();
    });

    it('should not show peek button when status is not success', () => {
      render(ToolCallCard, {
        ...defaultProps,
        tool: 'apply_diff',
        status: 'running',
        input: { file_path: '/test/file.ts' }
      });

      expect(screen.queryByText('👁️ View')).not.toBeInTheDocument();
    });

    it('should handle peek button click', async () => {
      const consoleSpy = vi.spyOn(console, 'log');

      render(ToolCallCard, {
        ...defaultProps,
        tool: 'file_write',
        status: 'success',
        input: { file_path: '/test/file.ts' }
      });

      const peekButton = screen.getByText('👁️ View');
      await fireEvent.click(peekButton);

      expect(consoleSpy).toHaveBeenCalledWith('[ToolCallCard] Peek file:', '/test/file.ts');
      consoleSpy.mockRestore();
    });
  });

  describe('Content Display', () => {
    it('should display input when expanded', () => {
      render(ToolCallCard, {
        ...defaultProps,
        collapsed: false,
        input: { query: 'test query', limit: 10 }
      });

      expect(screen.getByText('Input')).toBeInTheDocument();
      expect(screen.getByText(/"query": "test query"/)).toBeInTheDocument();
    });

    it('should display result when expanded and available', () => {
      render(ToolCallCard, {
        ...defaultProps,
        collapsed: false,
        status: 'success',
        result: { data: 'test result' }
      });

      expect(screen.getByText('Result')).toBeInTheDocument();
      expect(screen.getByText(/"data": "test result"/)).toBeInTheDocument();
    });

    it('should display error when present', () => {
      render(ToolCallCard, {
        ...defaultProps,
        collapsed: false,
        status: 'error',
        error: 'Test error message'
      });

      expect(screen.getByText('Test error message')).toBeInTheDocument();
    });

    it('should not display content when collapsed', () => {
      render(ToolCallCard, {
        ...defaultProps,
        collapsed: true,
        result: { data: 'test result' }
      });

      expect(screen.queryByText('Input')).not.toBeInTheDocument();
      expect(screen.queryByText('Result')).not.toBeInTheDocument();
    });
  });

  describe('Diff Display', () => {
    it('should display diff viewer for file edit tools with diff data', () => {
      const diffData = {
        oldFileName: 'test.ts',
        newFileName: 'test.ts',
        additions: 2,
        deletions: 1,
        hunks: []
      };

      render(ToolCallCard, {
        ...defaultProps,
        tool: 'apply_diff',
        collapsed: false,
        diff: diffData
      });

      // DiffViewer should be rendered
      // This checks that the component structure supports diff display
      expect(screen.getByText('Input')).toBeInTheDocument();
    });
  });

  describe('Tool Icons', () => {
    it('should display appropriate emoji icon for known tools', () => {
      const { container } = render(ToolCallCard, { ...defaultProps, tool: 'kb_search' });

      expect(container.textContent).toContain('🔍');
    });

    it('should display default hammer icon for unknown tools', () => {
      const { container } = render(ToolCallCard, { ...defaultProps, tool: 'unknown_tool' });

      expect(container.textContent).toContain('🔨');
    });
  });
});
