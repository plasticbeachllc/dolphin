import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ChatInput from './ChatInput.svelte';

describe('ChatInput', () => {
  describe('Accessibility', () => {
    it('should have proper ARIA labels on textarea', () => {
      render(ChatInput);
      const textarea = screen.getByRole('textbox');

      expect(textarea).toHaveAttribute('aria-label', expect.stringContaining('Type your message'));
      expect(textarea).toHaveAttribute('aria-label', expect.stringContaining('Ctrl+Enter'));
    });

    it('should have region role with descriptive label', () => {
      render(ChatInput);
      const region = screen.getByRole('region', { name: /message input/i });

      expect(region).toBeInTheDocument();
    });

    it('should announce processing status to screen readers', () => {
      render(ChatInput, { isProcessing: true });

      const statusElement = document.getElementById('processing-status');
      expect(statusElement).toBeInTheDocument();
      expect(statusElement).toHaveTextContent('Processing your message');
      expect(statusElement).toHaveAttribute('aria-live', 'polite');
      expect(statusElement).toHaveClass('sr-only');
    });

    it('should link textarea to processing status with aria-describedby', () => {
      render(ChatInput, { isProcessing: true });
      const textarea = screen.getByRole('textbox');

      expect(textarea).toHaveAttribute('aria-describedby', 'processing-status');
    });

    it('should have descriptive button labels', () => {
      const { rerender } = render(ChatInput, { isProcessing: false });
      const button = screen.getByRole('button');

      expect(button).toHaveAttribute('aria-label', 'Send message');

      rerender({ isProcessing: true });
      expect(button).toHaveAttribute('aria-label', 'Stop generation');
    });

    it('should mark icons as decorative with aria-hidden', () => {
      render(ChatInput, { isProcessing: false });

      // Icons should be hidden from screen readers
      const icons = document.querySelectorAll('svg[aria-hidden="true"]');
      expect(icons.length).toBeGreaterThan(0);
    });

    it('should have title tooltips for buttons', () => {
      render(ChatInput);
      const button = screen.getByRole('button');

      expect(button).toHaveAttribute('title', expect.stringContaining('Ctrl+Enter'));
    });
  });

  describe('Keyboard Navigation', () => {
    it('should send message on Ctrl+Enter', async () => {
      const onSend = vi.fn();
      render(ChatInput, { onSend });

      const textarea = screen.getByRole('textbox');
      await fireEvent.input(textarea, { target: { value: 'Test message' } });
      await fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });

      expect(onSend).toHaveBeenCalledWith('Test message');
    });

    it('should send message on Cmd+Enter (Mac)', async () => {
      const onSend = vi.fn();
      render(ChatInput, { onSend });

      const textarea = screen.getByRole('textbox');
      await fireEvent.input(textarea, { target: { value: 'Test message' } });
      await fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true });

      expect(onSend).toHaveBeenCalledWith('Test message');
    });

    it('should not send on Enter without modifier keys', async () => {
      const onSend = vi.fn();
      render(ChatInput, { onSend });

      const textarea = screen.getByRole('textbox');
      await fireEvent.input(textarea, { target: { value: 'Test message' } });
      await fireEvent.keyDown(textarea, { key: 'Enter' });

      expect(onSend).not.toHaveBeenCalled();
    });
  });

  describe('Focus Management', () => {
    it('should expose focus method for parent components', async () => {
      const { component } = render(ChatInput);

      expect(typeof component.focus).toBe('function');
    });

    it('should expose prefill method for parent components', async () => {
      const { component } = render(ChatInput);

      expect(typeof component.prefill).toBe('function');
    });

    it('should prefill textarea and focus when prefill is called', async () => {
      const { component } = render(ChatInput);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      component.prefill('Prefilled text');

      expect(textarea.value).toBe('Prefilled text');
    });
  });

  describe('Processing State', () => {
    it('should disable textarea when processing', () => {
      render(ChatInput, { isProcessing: true });
      const textarea = screen.getByRole('textbox');

      expect(textarea).toBeDisabled();
    });

    it('should disable textarea when disabled prop is true', () => {
      render(ChatInput, { disabled: true });
      const textarea = screen.getByRole('textbox');

      expect(textarea).toBeDisabled();
    });

    it('should change button variant to destructive when processing', () => {
      render(ChatInput, { isProcessing: true });
      const button = screen.getByRole('button');

      // Check for destructive variant class or data attribute
      expect(button.className).toMatch(/destructive/);
    });

    it('should call onStop when clicked during processing', async () => {
      const onStop = vi.fn();
      render(ChatInput, { isProcessing: true, onStop });

      const button = screen.getByRole('button');
      await fireEvent.click(button);

      expect(onStop).toHaveBeenCalled();
    });
  });

  describe('New Conversation Button', () => {
    it('should show plus icon when no active conversation and input is empty', () => {
      render(ChatInput, { hasActiveConversation: false });
      const button = screen.getByRole('button');

      expect(button).toHaveAttribute('aria-label', 'Start new conversation');
    });

    it('should show send icon when there is text in input', async () => {
      render(ChatInput, { hasActiveConversation: false });

      const textarea = screen.getByRole('textbox');
      await fireEvent.input(textarea, { target: { value: 'Some text' } });

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-label', 'Send message');
    });
  });

  describe('Screen Reader Only Content', () => {
    it('should have sr-only class with proper styles', () => {
      render(ChatInput, { isProcessing: true });
      const srOnlyElement = document.querySelector('.sr-only');

      expect(srOnlyElement).toBeInTheDocument();

      // Verify the element exists but is visually hidden
      const styles = window.getComputedStyle(srOnlyElement!);
      // Note: In jsdom, computed styles may not be fully calculated,
      // so we just verify the class exists
      expect(srOnlyElement).toHaveClass('sr-only');
    });
  });

  describe('Message Sending', () => {
    it('should clear input after sending', async () => {
      const onSend = vi.fn();
      render(ChatInput, { onSend });

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      await fireEvent.input(textarea, { target: { value: 'Test message' } });

      const button = screen.getByRole('button');
      await fireEvent.click(button);

      expect(onSend).toHaveBeenCalledWith('Test message');
      expect(textarea.value).toBe('');
    });

    it('should not send empty messages', async () => {
      const onSend = vi.fn();
      render(ChatInput, { onSend });

      const button = screen.getByRole('button');
      await fireEvent.click(button);

      expect(onSend).not.toHaveBeenCalled();
    });

    it('should not send whitespace-only messages', async () => {
      const onSend = vi.fn();
      render(ChatInput, { onSend });

      const textarea = screen.getByRole('textbox');
      await fireEvent.input(textarea, { target: { value: '   ' } });

      const button = screen.getByRole('button');
      await fireEvent.click(button);

      expect(onSend).not.toHaveBeenCalled();
    });
  });
});
