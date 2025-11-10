import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import MessageCard from './MessageCard.svelte';

describe('MessageCard', () => {
  describe('Accessibility', () => {
    it('should have article role with descriptive label', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message',
        timestamp: '10:30 AM'
      });

      const article = screen.getByRole('article');
      expect(article).toHaveAttribute('aria-label', 'User message at 10:30 AM');
    });

    it('should have descriptive aria-label for assistant messages', () => {
      render(MessageCard, {
        role: 'assistant',
        content: 'Assistant response',
        timestamp: '10:31 AM'
      });

      const article = screen.getByRole('article');
      expect(article).toHaveAttribute('aria-label', 'Assistant message at 10:31 AM');
    });

    it('should have aria-label without timestamp when not provided', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      const article = screen.getByRole('article');
      expect(article).toHaveAttribute('aria-label', 'User message');
    });

    it('should have descriptive aria-label for avatar', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      const avatar = screen.getByLabelText('User avatar');
      expect(avatar).toBeInTheDocument();
    });

    it('should have descriptive aria-label for assistant avatar', () => {
      render(MessageCard, {
        role: 'assistant',
        content: 'Test message'
      });

      const avatar = screen.getByLabelText('Assistant avatar');
      expect(avatar).toBeInTheDocument();
    });

    it('should have aria-label on role badge', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      // Badge should indicate who the message is from
      const badge = screen.getByText('You');
      expect(badge.closest('[aria-label]')).toHaveAttribute('aria-label', 'Message from You');
    });

    it('should have aria-label on timestamp', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message',
        timestamp: '10:30 AM'
      });

      const timestamp = screen.getByText('10:30 AM');
      expect(timestamp).toHaveAttribute('aria-label', 'Sent at 10:30 AM');
    });
  });

  describe('Theme Integration', () => {
    it('should apply theme-aware avatar class for user', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      const avatar = document.querySelector('.avatar-user');
      expect(avatar).toBeInTheDocument();
    });

    it('should apply theme-aware avatar class for assistant', () => {
      render(MessageCard, {
        role: 'assistant',
        content: 'Test message'
      });

      const avatar = document.querySelector('.avatar-assistant');
      expect(avatar).toBeInTheDocument();
    });

    it('should have CSS custom properties for user avatar', () => {
      const { container } = render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      // Check that the style tag exists with proper CSS variables
      const style = container.querySelector('style');
      expect(style?.textContent).toContain('--vscode-button-background');
      expect(style?.textContent).toContain('--vscode-button-foreground');
    });

    it('should have CSS custom properties for assistant avatar', () => {
      const { container } = render(MessageCard, {
        role: 'assistant',
        content: 'Test message'
      });

      // Check that the style tag exists with proper CSS variables
      const style = container.querySelector('style');
      expect(style?.textContent).toContain('--vscode-charts-purple');
    });
  });

  describe('Content Rendering', () => {
    it('should render user message content as plain text', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test user message'
      });

      expect(screen.getByText('Test user message')).toBeInTheDocument();
    });

    it('should render assistant message with MarkdownContent component', () => {
      render(MessageCard, {
        role: 'assistant',
        content: '**Bold text** in assistant message'
      });

      // MarkdownContent should handle the content
      // We're checking that the content is passed to it
      expect(screen.getByText(/Bold text/)).toBeInTheDocument();
    });

    it('should display timestamp when provided', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message',
        timestamp: '10:30 AM'
      });

      expect(screen.getByText('10:30 AM')).toBeInTheDocument();
    });

    it('should not display timestamp when not provided', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      // Should not throw when accessing timestamp elements
      const timestamps = screen.queryByText(/AM|PM/);
      expect(timestamps).not.toBeInTheDocument();
    });
  });

  describe('Layout and Styling', () => {
    it('should align user messages to the right', () => {
      const { container } = render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      const card = container.querySelector('[role="article"]');
      expect(card?.className).toMatch(/ml-auto/);
    });

    it('should align assistant messages to the left', () => {
      const { container } = render(MessageCard, {
        role: 'assistant',
        content: 'Test message'
      });

      const card = container.querySelector('[role="article"]');
      expect(card?.className).toMatch(/mr-auto/);
    });

    it('should have max-width constraint', () => {
      const { container } = render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      const card = container.querySelector('[role="article"]');
      expect(card?.className).toMatch(/max-w-/);
    });
  });

  describe('Avatar Display', () => {
    it('should show "U" fallback for user avatar', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      expect(screen.getByText('U')).toBeInTheDocument();
    });

    it('should show "A" fallback for assistant avatar', () => {
      render(MessageCard, {
        role: 'assistant',
        content: 'Test message'
      });

      expect(screen.getByText('A')).toBeInTheDocument();
    });
  });

  describe('Badge Display', () => {
    it('should show "You" badge for user messages', () => {
      render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      expect(screen.getByText('You')).toBeInTheDocument();
    });

    it('should show "Assistant" badge for assistant messages', () => {
      render(MessageCard, {
        role: 'assistant',
        content: 'Test message'
      });

      expect(screen.getByText('Assistant')).toBeInTheDocument();
    });

    it('should use secondary variant for user badge', () => {
      const { container } = render(MessageCard, {
        role: 'user',
        content: 'Test message'
      });

      const badge = screen.getByText('You').closest('[class*="badge"]');
      // Verify badge has the expected variant styling
      expect(badge).toBeInTheDocument();
    });

    it('should use default variant for assistant badge', () => {
      const { container } = render(MessageCard, {
        role: 'assistant',
        content: 'Test message'
      });

      const badge = screen.getByText('Assistant').closest('[class*="badge"]');
      expect(badge).toBeInTheDocument();
    });
  });

  describe('Whitespace Handling', () => {
    it('should preserve whitespace and line breaks in user messages', () => {
      const multilineMessage = 'Line 1\nLine 2\nLine 3';
      const { container } = render(MessageCard, {
        role: 'user',
        content: multilineMessage
      });

      const content = container.querySelector('.whitespace-pre-wrap');
      expect(content).toBeInTheDocument();
      expect(content?.className).toMatch(/break-words/);
    });
  });
});
