export default {
    darkMode: ['class'],
    content: ['./src/**/*.{html,js,svelte,ts}'],
    theme: {
        extend: {
            colors: {
                background: 'var(--vscode-background)',
                foreground: 'var(--vscode-foreground)',
                primary: {
                    DEFAULT: 'var(--vscode-primary)',
                    foreground: 'var(--vscode-foreground)'
                },
                secondary: 'var(--vscode-secondary)',
                border: 'var(--vscode-border)'
            }
        }
    },
    plugins: [require('tailwindcss-animate')]
};
