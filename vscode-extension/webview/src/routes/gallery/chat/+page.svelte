<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Separator } from '$lib/components/ui/separator';
	import MessageCard from '$lib/components/chat/MessageCard.svelte';
	import ToolCallCard from '$lib/components/tools/ToolCallCard.svelte';
import { MessageSquare, Code, Wrench, FileCode } from 'lucide-svelte';

	type GalleryMessage = {
		role: 'user' | 'assistant';
		content: string;
		timestamp?: string;
	};

	// Comprehensive mock conversation data showcasing all formatting scenarios
	const mockConversation: GalleryMessage[] = [
		{
			role: 'user',
			content: 'Can you help me understand how to implement authentication in a React app?',
			timestamp: '2:30 PM'
		},
		{
			role: 'assistant',
			content: `I'll help you implement authentication in React. Let me break this down into key concepts:

## Authentication Overview

Authentication typically involves:
1. **User Login** - Collecting credentials
2. **Token Management** - Storing and refreshing tokens
3. **Protected Routes** - Restricting access to authenticated users
4. **Session Handling** - Managing user sessions

### Basic Implementation

Here's a simple authentication flow using JWT tokens:

\`\`\`typescript
import { useState, useEffect } from 'react';
import axios from 'axios';

interface User {
  id: string;
  email: string;
  name: string;
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in
    const token = localStorage.getItem('authToken');
    if (token) {
      validateToken(token);
    } else {
      setLoading(false);
    }
  }, []);

  const validateToken = async (token: string) => {
    try {
      const response = await axios.get('/api/auth/validate', {
        headers: { Authorization: \`Bearer \${token}\` }
      });
      setUser(response.data.user);
    } catch (error) {
      localStorage.removeItem('authToken');
    } finally {
      setLoading(false);
    }
  };

  const login = async (email: string, password: string) => {
    const response = await axios.post('/api/auth/login', { email, password });
    localStorage.setItem('authToken', response.data.token);
    setUser(response.data.user);
  };

  const logout = () => {
    localStorage.removeItem('authToken');
    setUser(null);
  };

  return { user, loading, login, logout };
}
\`\`\`

Let me also show you a protected route component.`,
			timestamp: '2:31 PM'
		},
		{
			role: 'user',
			content: 'This looks great! Can you show me the ProtectedRoute component and explain inline code like `localStorage.getItem()` vs `sessionStorage`?',
			timestamp: '2:32 PM'
		},
		{
			role: 'assistant',
			content: `Great question! Let me explain both concepts.

## Storage Options

When choosing between \`localStorage\` and \`sessionStorage\`, consider:

- **localStorage**: Persists data across browser sessions (survives page reloads and browser restarts)
- **sessionStorage**: Data is cleared when the page session ends (tab/window closes)
- **Cookies**: Can be set with expiration, accessible server-side, smaller storage limit

For authentication tokens, \`localStorage\` is common for "remember me" functionality, while \`sessionStorage\` is better for enhanced security.

### Protected Route Component

Here's the implementation:

\`\`\`tsx
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from './useAuth';

export function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
      </div>
    );
  }

  return user ? <Outlet /> : <Navigate to="/login" replace />;
}
\`\`\`

### Usage in Router

\`\`\`tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/profile" element={<Profile />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
\`\`\`

> **Security Note**: Never store sensitive tokens in \`localStorage\` if you're concerned about XSS attacks. Consider using httpOnly cookies for production applications.

Would you like me to search the codebase for any existing authentication patterns?`,
			timestamp: '2:33 PM'
		}
	];

	// Tool call examples with different states
	const toolCallExamples = [
		{
			tool: 'search',
			input: { 
				query: 'authentication implementation react',
				repos: ['dolphin'],
				top_k: 5,
				embed_model: 'large'
			},
			result: {
				snippets: [
					{
						repo: 'dolphin',
						path: 'vscode-extension/src/auth/provider.ts',
						score: 0.89,
						content: 'Authentication provider implementation...'
					}
				],
				total_results: 5,
				search_time_ms: 234
			},
			status: 'success' as const,
			executionTime: 234,
			collapsed: false
		},
		{
			tool: 'read_files',
			input: {
				paths: [
					'vscode-extension/src/auth/provider.ts',
					'vscode-extension/src/auth/token-manager.ts',
					'vscode-extension/src/views/provider.ts'
				],
				max_size_bytes: 1048576
			},
			result: {
				files: [
					{ path: 'vscode-extension/src/auth/provider.ts', size_bytes: 2048, success: true },
					{ path: 'vscode-extension/src/auth/token-manager.ts', size_bytes: 1536, success: true },
					{ path: 'vscode-extension/src/views/provider.ts', size_bytes: 8192, success: true }
				],
				summary: { successful: 3, failed: 0, total_bytes: 11776 }
			},
			status: 'success' as const,
			executionTime: 89,
			collapsed: false
		},
		{
			tool: 'apply_diff',
			input: {
				path: 'src/hooks/useAuth.ts',
				diff: `<<<<<<< SEARCH
:start_line:15
-------
  const login = async (email: string, password: string) => {
    const response = await axios.post('/api/auth/login', { email, password });
    localStorage.setItem('authToken', response.data.token);
    setUser(response.data.user);
  };
=======
  const login = async (email: string, password: string) => {
    try {
      const response = await axios.post('/api/auth/login', { email, password });
      localStorage.setItem('authToken', response.data.token);
      setUser(response.data.user);
      return { success: true };
    } catch (error) {
      console.error('Login failed:', error);
      return { success: false, error };
    }
  };
>>>>>>> REPLACE`
			},
			result: {
				applied: true,
				file_path: 'src/hooks/useAuth.ts',
				changes: {
					additions: 8,
					deletions: 5,
					modifications: 1
				}
			},
			status: 'success' as const,
			executionTime: 45,
			collapsed: false,
			diff: {
				oldFileName: 'src/hooks/useAuth.ts',
				newFileName: 'src/hooks/useAuth.ts',
				additions: 8,
				deletions: 5,
				hunks: [{
					oldStart: 15,
					oldLines: 5,
					newStart: 15,
					newLines: 13,
					lines: [
						' const login = async (email: string, password: string) => {',
						'-  const response = await axios.post(\'/api/auth/login\', { email, password });',
						'-  localStorage.setItem(\'authToken\', response.data.token);',
						'-  setUser(response.data.user);',
						'+ try {',
						'+   const response = await axios.post(\'/api/auth/login\', { email, password });',
						'+   localStorage.setItem(\'authToken\', response.data.token);',
						'+   setUser(response.data.user);',
						'+   return { success: true };',
						'+ } catch (error) {',
						'+   console.error(\'Login failed:\', error);',
						'+   return { success: false, error };',
						'+ }',
						' };'
					]
				}]
			}
		},
		{
			tool: 'execute_command',
			input: {
				command: 'npm test src/hooks/useAuth.test.ts',
				cwd: '/Users/user/project'
			},
			status: 'running' as const,
			collapsed: false
		},
		{
			tool: 'file_write',
			input: {
				path: 'src/config/auth.config.ts',
				content: `export const authConfig = {
  tokenKey: 'authToken',
  apiEndpoint: '/api/auth',
  refreshInterval: 3600000, // 1 hour
};`
			},
			error: 'Permission denied: Cannot write to protected directory',
			status: 'error' as const,
			executionTime: 12,
			collapsed: false
		}
	];

	// Additional complex formatting examples
	const complexFormatting: GalleryMessage = {
		role: 'assistant',
		content: `Here are some advanced patterns and edge cases:

## Code with Multiple Languages

### TypeScript Interface
\`\`\`typescript
interface AuthConfig {
  tokenKey: string;
  apiEndpoint: string;
  refreshInterval: number;
  onAuthError?: (error: Error) => void;
}
\`\`\`

### Python Backend
\`\`\`python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta

SECRET_KEY = "your-secret-key-here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")
\`\`\`

### SQL Schema
\`\`\`sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created_at ON users(created_at);
\`\`\`

### JSON Configuration
\`\`\`json
{
  "auth": {
    "providers": ["local", "google", "github"],
    "tokenExpiry": "1h",
    "refreshTokenExpiry": "7d",
    "passwordPolicy": {
      "minLength": 8,
      "requireUppercase": true,
      "requireNumbers": true,
      "requireSpecialChars": true
    }
  }
}
\`\`\`

## Inline Code Variations

Here are different inline code patterns:
- Simple variable: \`user\`
- Function call: \`localStorage.getItem('token')\`
- With special chars: \`response?.data?.user ?? null\`
- Long path: \`/Users/username/projects/my-app/src/components/auth/LoginForm.tsx\`
- Generic type: \`Array<{ id: string; name: string }>\`
- Template literal: \`\\\`Bearer \${token}\\\`\`

## Lists and Nesting

### Ordered List with Code
1. Install dependencies:
   \`\`\`bash
   npm install react-router-dom axios
   \`\`\`
2. Create the auth hook with proper error handling
3. Set up protected routes using \`<ProtectedRoute>\` wrapper
4. Test authentication flow:
   - Login with valid credentials
   - Verify token storage in \`localStorage\`
   - Test protected route access
   - Verify logout clears session

### Unordered List
- **JWT Tokens**: Stateless authentication
  - Access tokens (short-lived)
  - Refresh tokens (long-lived)
- **Session-based**: Server-side session storage
  - Redis for session store
  - Database-backed sessions
- **OAuth2**: Third-party authentication
  - Google OAuth
  - GitHub OAuth

## Tables

| Method | Storage | Expiration | Security | Use Case |
|--------|---------|------------|----------|----------|
| localStorage | Browser | Never | Medium | Remember me |
| sessionStorage | Browser | On close | Medium | Single session |
| Cookies | Browser | Custom | High* | Production apps |
| Memory | Runtime | On reload | High | Temporary state |

*When using httpOnly and secure flags

## Blockquotes

> **Important Security Considerations**
>
> Always hash passwords using bcrypt or argon2 before storing them. Never store plain-text passwords in your database.
>
> Consider these additional security measures:
> - Rate limiting on login endpoints
> - CSRF protection for state-changing operations
> - XSS protection through proper content sanitization
> - Regular security audits and dependency updates

## Links and References

For more information, see:
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [JWT.io](https://jwt.io) - JWT debugger and information
- MDN Web Docs on [Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API)

## Horizontal Rules and Separation

---

## Very Long Code Block (Testing Wrap)

\`\`\`typescript
// This is an intentionally long line to test horizontal scrolling: const reallyLongVariableName = calculateSomethingWithManyParametersAndAVeryLongFunctionName(param1, param2, param3, param4, param5);

export class AuthenticationService {
  private tokenManager: TokenManager;
  private apiClient: ApiClient;
  private refreshTimer: NodeJS.Timeout | null = null;

  constructor(config: AuthConfig) {
    this.tokenManager = new TokenManager(config.tokenKey);
    this.apiClient = new ApiClient(config.apiEndpoint);
    this.setupAutoRefresh(config.refreshInterval);
  }

  async login(credentials: LoginCredentials): Promise<AuthResult> {
    try {
      const response = await this.apiClient.post<AuthResponse>('/login', credentials);
      
      if (!response.data.token || !response.data.user) {
        throw new Error('Invalid response from authentication server');
      }

      this.tokenManager.setToken(response.data.token);
      this.tokenManager.setRefreshToken(response.data.refreshToken);
      
      return {
        success: true,
        user: response.data.user,
        token: response.data.token
      };
    } catch (error) {
      if (error instanceof NetworkError) {
        return { success: false, error: 'Network error. Please check your connection.' };
      } else if (error instanceof ValidationError) {
        return { success: false, error: 'Invalid credentials provided.' };
      }
      return { success: false, error: 'An unexpected error occurred.' };
    }
  }

  private setupAutoRefresh(interval: number): void {
    this.refreshTimer = setInterval(async () => {
      const token = this.tokenManager.getRefreshToken();
      if (token) {
        await this.refreshAccessToken(token);
      }
    }, interval);
  }

  async refreshAccessToken(refreshToken: string): Promise<void> {
    try {
      const response = await this.apiClient.post<TokenResponse>('/refresh', { refreshToken });
      this.tokenManager.setToken(response.data.token);
    } catch (error) {
      console.error('Failed to refresh token:', error);
      this.logout();
    }
  }

  logout(): void {
    this.tokenManager.clearTokens();
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }
}
\`\`\`

## Mixed Content

Sometimes you need to mix explanations with code snippets. For example, when working with \`useEffect\`, you need to understand the dependency array \`[]\` versus \`[dependency]\`. Here's how:

\`\`\`javascript
// No dependencies - runs once on mount
useEffect(() => {
  console.log('Component mounted');
}, []);

// With dependencies - runs when dependencies change
useEffect(() => {
  console.log('User changed:', user);
}, [user]);
\`\`\`

The key difference is the dependency array!

## Edge Cases

### Empty code block
\`\`\`

\`\`\`

### Very short inline code
\`a\`

### Code with emojis
\`\`\`javascript
const status = '✅ Success';
const loading = '⏳ Loading...';
const error = '❌ Error occurred';
\`\`\`

### Special characters
\`\`\`text
Special chars: <>&"'
Brackets: []{}()
Math: += -= *= /= %= **=
Arrows: => -> <-
\`\`\``,
		timestamp: '2:35 PM'
	};

	const edgeCaseMessage: GalleryMessage = {
		role: 'assistant',
		content: `## Edge Case Testing

### Single backtick: \`code\`

### Triple backticks with language:
\`\`\`typescript
const test = 'value';
\`\`\`

### Triple backticks without language:
\`\`\`
plain text block
no syntax highlighting
\`\`\`

### Nested formatting
**Bold with \`code\`** and *italic with \`code\`* and ***bold italic with \`code\`***

### URLs in text
Check out https://example.com and [link text](https://example.com)

### Escaped characters
This is how you write backticks: \\\` and backslashes: \\\\

### Line breaks and spacing


Multiple empty lines above.

Single line break above.`,
		timestamp: '2:36 PM'
	};
</script>

<div class="h-full overflow-auto">
	<div class="max-w-5xl mx-auto p-6">
		<!-- Header -->
		<div class="mb-8">
			<div class="flex items-center gap-3 mb-3">
				<MessageSquare class="h-8 w-8 text-primary" />
				<h1 class="text-4xl font-bold">Chat View Gallery</h1>
			</div>
			<p class="text-muted-foreground mb-4">
				Comprehensive reference for all chat formatting scenarios including messages, code blocks, tool calls, 
				inline code, tables, lists, and edge cases. Use this gallery to evaluate and debug formatting issues.
			</p>
			<div class="flex gap-2">
				<Badge variant="outline" class="gap-1">
					<Code class="size-3" />
					Markdown Rendering
				</Badge>
				<Badge variant="outline" class="gap-1">
					<FileCode class="size-3" />
					Code Syntax Highlighting
				</Badge>
				<Badge variant="outline" class="gap-1">
					<Wrench class="size-3" />
					Tool Call Display
				</Badge>
			</div>
		</div>

		<Separator class="mb-8" />

		<!-- Section 1: Basic Chat Messages -->
		<section class="mb-12">
			<div class="mb-6">
				<h2 class="text-2xl font-bold mb-2 flex items-center gap-2">
					<Badge variant="secondary">1</Badge>
					Basic Chat Messages
				</h2>
				<p class="text-sm text-muted-foreground">
					User and assistant messages with timestamps, showing proper text wrapping and spacing
				</p>
			</div>

			<Card>
				<CardContent class="p-6 space-y-4">
					{#each mockConversation as message}
						<MessageCard {...message} />
					{/each}
				</CardContent>
			</Card>
		</section>

		<Separator class="mb-12" />

		<!-- Section 2: Tool Calls -->
		<section class="mb-12">
			<div class="mb-6">
				<h2 class="text-2xl font-bold mb-2 flex items-center gap-2">
					<Badge variant="secondary">2</Badge>
					Tool Call Examples
				</h2>
				<p class="text-sm text-muted-foreground">
					All tool call states: running, success, error. Includes search, file operations, and command execution
				</p>
			</div>

			<Card>
				<CardContent class="p-6 space-y-4">
					{#each toolCallExamples as toolCall}
						<ToolCallCard {...toolCall} />
					{/each}
				</CardContent>
			</Card>
		</section>

		<Separator class="mb-12" />

		<!-- Section 3: Complex Formatting -->
		<section class="mb-12">
			<div class="mb-6">
				<h2 class="text-2xl font-bold mb-2 flex items-center gap-2">
					<Badge variant="secondary">3</Badge>
					Complex Formatting Scenarios
				</h2>
				<p class="text-sm text-muted-foreground">
					Multiple languages, tables, lists, blockquotes, links, horizontal rules, and long code blocks
				</p>
			</div>

			<Card>
				<CardContent class="p-6">
					<MessageCard {...complexFormatting} />
				</CardContent>
			</Card>
		</section>

		<Separator class="mb-12" />

		<!-- Section 4: Edge Cases -->
		<section class="mb-12">
			<div class="mb-6">
				<h2 class="text-2xl font-bold mb-2 flex items-center gap-2">
					<Badge variant="secondary">4</Badge>
					Edge Cases & Special Scenarios
				</h2>
				<p class="text-sm text-muted-foreground">
					Testing boundary conditions: empty blocks, special characters, nested formatting, escaped content
				</p>
			</div>

			<Card>
				<CardContent class="p-6">
					<MessageCard {...edgeCaseMessage} />
				</CardContent>
			</Card>
		</section>

		<Separator class="mb-12" />

		<!-- Section 5: Interleaved Messages and Tools -->
		<section class="mb-12">
			<div class="mb-6">
				<h2 class="text-2xl font-bold mb-2 flex items-center gap-2">
					<Badge variant="secondary">5</Badge>
					Interleaved Conversation Flow
				</h2>
				<p class="text-sm text-muted-foreground">
					Realistic conversation showing alternating messages and tool calls as they appear in actual usage
				</p>
			</div>

			<Card>
				<CardContent class="p-6 space-y-4">
					<MessageCard
						role="user"
						content="Can you analyze the authentication code and suggest improvements?"
						timestamp="3:00 PM"
					/>
					
					<MessageCard
						role="assistant"
						content="I'll analyze the authentication implementation. Let me search the codebase first."
						timestamp="3:00 PM"
					/>
					
					<ToolCallCard
						tool="search"
						input={{ query: "authentication security patterns", top_k: 10 }}
						result={{ total_results: 10, search_time_ms: 156 }}
						status="success"
						executionTime={156}
						collapsed={false}
					/>
					
					<ToolCallCard
						tool="read_files"
						input={{ paths: ["src/auth/provider.ts", "src/auth/middleware.ts"] }}
						result={{ files: [{ path: "src/auth/provider.ts", size_bytes: 3200 }], summary: { successful: 2, failed: 0 } }}
						status="success"
						executionTime={67}
						collapsed={false}
					/>
					
					<MessageCard
						role="assistant"
						content={`I've analyzed the code. Here are my recommendations:

## Security Improvements

1. **Add rate limiting** to prevent brute force attacks:
\`\`\`typescript
import rateLimit from 'express-rate-limit';

const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 5, // 5 requests per window
  message: 'Too many login attempts, please try again later'
});

app.post('/login', loginLimiter, handleLogin);
\`\`\`

2. **Implement token rotation** for refresh tokens
3. **Add CSRF protection** using tokens
4. **Enable secure and httpOnly** flags on cookies

Would you like me to implement these changes?`}
						timestamp="3:01 PM"
					/>
					
					<MessageCard
						role="user"
						content="Yes, please implement the rate limiting and token rotation."
						timestamp="3:02 PM"
					/>
					
					<ToolCallCard
						tool="apply_diff"
						input={{ path: "src/auth/middleware.ts", diff: "..." }}
						result={{ applied: true, changes: { additions: 15, deletions: 3 } }}
						status="success"
						executionTime={89}
						collapsed={false}
					/>
					
					<MessageCard
						role="assistant"
						content="I've implemented the rate limiting middleware. The changes include:\n\n- Rate limiter with 5 attempts per 15-minute window\n- Custom error messages for exceeded limits\n- IP-based tracking with Redis backend\n\nThe authentication flow is now more secure against brute force attacks."
						timestamp="3:03 PM"
					/>
				</CardContent>
			</Card>
		</section>

		<!-- Testing Notes -->
		<section class="mb-12">
			<Card class="bg-muted/30">
				<CardHeader>
					<CardTitle>Testing & Debugging Notes</CardTitle>
					<CardDescription>Key areas to verify in this gallery</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div>
						<h3 class="font-semibold mb-2">✅ Code Block Rendering</h3>
						<ul class="list-disc list-inside text-sm text-muted-foreground space-y-1">
							<li>Syntax highlighting for multiple languages (TypeScript, Python, SQL, JSON, Bash)</li>
							<li>Horizontal scrolling for long lines (no text wrapping in code)</li>
							<li>Copy button functionality</li>
							<li>Line numbers and proper spacing</li>
							<li>Background colors and borders</li>
						</ul>
					</div>
					
					<Separator />
					
					<div>
						<h3 class="font-semibold mb-2">✅ Inline Code</h3>
						<ul class="list-disc list-inside text-sm text-muted-foreground space-y-1">
							<li>Proper background color and padding</li>
							<li>Text wrapping behavior (should wrap gracefully)</li>
							<li>Special characters display correctly</li>
							<li>Works within bold, italic, and other formatting</li>
						</ul>
					</div>
					
					<Separator />
					
					<div>
						<h3 class="font-semibold mb-2">✅ Tool Calls</h3>
						<ul class="list-disc list-inside text-sm text-muted-foreground space-y-1">
							<li>Expand/collapse animations smooth</li>
							<li>Status indicators (running/success/error) visible</li>
							<li>Input/output JSON formatting readable</li>
							<li>Diff viewer displays properly in file edit tools</li>
							<li>Execution time badges display correctly</li>
						</ul>
					</div>
					
					<Separator />
					
					<div>
						<h3 class="font-semibold mb-2">✅ Markdown Elements</h3>
						<ul class="list-disc list-inside text-sm text-muted-foreground space-y-1">
							<li>Headers (h1-h6) with proper sizing and spacing</li>
							<li>Lists (ordered, unordered, nested) aligned correctly</li>
							<li>Tables with borders and alternating row colors</li>
							<li>Blockquotes with left border and background</li>
							<li>Links underlined on hover</li>
							<li>Horizontal rules visible</li>
						</ul>
					</div>
					
					<Separator />
					
					<div>
						<h3 class="font-semibold mb-2">✅ Edge Cases</h3>
						<ul class="list-disc list-inside text-sm text-muted-foreground space-y-1">
							<li>Empty code blocks don't break layout</li>
							<li>Very long words/paths wrap appropriately</li>
							<li>Special characters render correctly</li>
							<li>Multiple consecutive line breaks handled properly</li>
							<li>Mixed formatting (bold + code, etc.) works</li>
						</ul>
					</div>
				</CardContent>
			</Card>
		</section>
	</div>
</div>
