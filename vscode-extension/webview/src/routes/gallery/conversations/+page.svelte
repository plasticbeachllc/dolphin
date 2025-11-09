<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	
	import { 
		MessageSquare, 
		Pin, 
		Trash2, 
		Edit3, 
		Search, 
		Clock, 
		MessageCircle,
		MoreVertical,
		Grid3x3,
		List,
		Calendar,
		Plus,
		Filter,
		Archive,
		Download,
		Copy,
		GitBranch,
		Folder
	} from 'lucide-svelte';

	// Mock conversation data
	interface ConversationMetadata {
		id: string;
		title: string;
		preview: string;
		created_at: string;
		updated_at: string;
		workspace_root: string;
		message_count: number;
		pinned: boolean;
		tags?: string[];
		git_context?: {
			branch: string;
			commit: string;
		};
	}

	const mockConversations: ConversationMetadata[] = [
		{
			id: 'conv-001',
			title: 'Fix authentication bug in login flow',
			preview: 'Can you help me debug the OAuth redirect issue? Users are getting stuck after...',
			created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
			updated_at: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
			workspace_root: '/Users/dev/projects/webapp',
			message_count: 24,
			pinned: true,
			tags: ['bug-fix', 'authentication'],
			git_context: { branch: 'fix/oauth-redirect', commit: 'a3f2d1c' }
		},
		{
			id: 'conv-002',
			title: 'Refactor API client to use TypeScript generics',
			preview: 'I want to refactor the API client to be more type-safe. Can we add generic...',
			created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
			updated_at: new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString(),
			workspace_root: '/Users/dev/projects/webapp',
			message_count: 15,
			pinned: false,
			tags: ['refactor', 'typescript'],
			git_context: { branch: 'refactor/api-client', commit: 'b7e9f4a' }
		},
		{
			id: 'conv-003',
			title: 'Add unit tests for user service',
			preview: 'Let\'s add comprehensive tests for the user service methods...',
			created_at: new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString(),
			updated_at: new Date(Date.now() - 47 * 60 * 60 * 1000).toISOString(),
			workspace_root: '/Users/dev/projects/webapp',
			message_count: 8,
			pinned: false,
			tags: ['testing', 'feature'],
		},
		{
			id: 'conv-004',
			title: 'Design system migration planning',
			preview: 'Help me plan the migration from our old UI components to shadcn...',
			created_at: new Date(Date.now() - 72 * 60 * 60 * 1000).toISOString(),
			updated_at: new Date(Date.now() - 70 * 60 * 60 * 1000).toISOString(),
			workspace_root: '/Users/dev/projects/webapp',
			message_count: 42,
			pinned: true,
			tags: ['architecture', 'ui'],
			git_context: { branch: 'feature/design-system', commit: 'c1a8e3d' }
		},
		{
			id: 'conv-005',
			title: 'Database schema optimization',
			preview: 'The user table queries are slow. Can we optimize the indexes?',
			created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
			updated_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
			workspace_root: '/Users/dev/projects/backend',
			message_count: 12,
			pinned: false,
			tags: ['performance', 'database']
		}
	];

	// View state
	let viewMode = $state<'grid' | 'list' | 'timeline'>('grid');
	let searchQuery = $state('');
	let selectedConversation = $state<string | null>(null);
	let interactionModel = $state<'navigate' | 'split' | 'modal' | 'replace'>('navigate');

	// Filter conversations based on search
	$effect(() => {
		searchQuery; // Track dependency
	});

	function formatRelativeTime(isoDate: string): string {
		const now = Date.now();
		const then = new Date(isoDate).getTime();
		const diff = now - then;

		const minutes = Math.floor(diff / (60 * 1000));
		const hours = Math.floor(diff / (60 * 60 * 1000));
		const days = Math.floor(diff / (24 * 60 * 60 * 1000));

		if (minutes < 60) return `${minutes}m ago`;
		if (hours < 24) return `${hours}h ago`;
		if (days === 1) return 'Yesterday';
		if (days < 7) return `${days}d ago`;
		return new Date(isoDate).toLocaleDateString();
	}

	function groupByTime(conversations: ConversationMetadata[]) {
		const now = Date.now();
		const today: ConversationMetadata[] = [];
		const yesterday: ConversationMetadata[] = [];
		const lastWeek: ConversationMetadata[] = [];
		const older: ConversationMetadata[] = [];

		conversations.forEach(conv => {
			const diff = now - new Date(conv.updated_at).getTime();
			const hours = diff / (60 * 60 * 1000);
			const days = hours / 24;

			if (hours < 24) today.push(conv);
			else if (days < 2) yesterday.push(conv);
			else if (days < 7) lastWeek.push(conv);
			else older.push(conv);
		});

		return { today, yesterday, lastWeek, older };
	}

	const timeGroups = $derived(groupByTime(mockConversations));

	function handleConversationClick(convId: string) {
		selectedConversation = convId;
		console.log('Conversation clicked:', convId, 'Model:', interactionModel);
	}
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-7xl mx-auto">
		<!-- Header -->
		<div class="mb-8">
			<h1 class="text-4xl font-bold mb-2">Conversation Persistence Mockups</h1>
			<p class="text-muted-foreground">
				Interactive mockups demonstrating different UI patterns for Phase 5 conversation persistence
			</p>
		</div>

		<div class="space-y-12">
			<!-- Controls Section -->
			<section>
				<Card>
					<CardHeader>
						<CardTitle>View Controls</CardTitle>
						<CardDescription>Switch between different layout and interaction modes</CardDescription>
					</CardHeader>
					<CardContent class="space-y-4">
						<!-- View Mode Toggle -->
						<div class="flex items-center gap-4">
							<span class="text-sm font-medium">Layout:</span>
							<div class="flex gap-1">
								<Button 
									variant={viewMode === 'grid' ? 'default' : 'outline'} 
									size="sm"
									onclick={() => viewMode = 'grid'}
								>
									<Grid3x3 class="h-4 w-4 mr-2" />
									Card Grid
								</Button>
								<Button 
									variant={viewMode === 'list' ? 'default' : 'outline'} 
									size="sm"
									onclick={() => viewMode = 'list'}
								>
									<List class="h-4 w-4 mr-2" />
									Compact List
								</Button>
								<Button 
									variant={viewMode === 'timeline' ? 'default' : 'outline'} 
									size="sm"
									onclick={() => viewMode = 'timeline'}
								>
									<Calendar class="h-4 w-4 mr-2" />
									Timeline
								</Button>
							</div>
						</div>

						<!-- Interaction Model -->
						<div class="flex items-center gap-4">
							<span class="text-sm font-medium">Interaction:</span>
							<div class="flex gap-1">
								<Button 
									variant={interactionModel === 'navigate' ? 'default' : 'outline'} 
									size="sm"
									onclick={() => interactionModel = 'navigate'}
								>
									Navigate to Chat
								</Button>
								<Button 
									variant={interactionModel === 'split' ? 'default' : 'outline'} 
									size="sm"
									onclick={() => interactionModel = 'split'}
								>
									Split View
								</Button>
								<Button 
									variant={interactionModel === 'modal' ? 'default' : 'outline'} 
									size="sm"
									onclick={() => interactionModel = 'modal'}
								>
									Modal Overlay
								</Button>
								<Button 
									variant={interactionModel === 'replace' ? 'default' : 'outline'} 
									size="sm"
									onclick={() => interactionModel = 'replace'}
								>
									Detail Replace
								</Button>
							</div>
						</div>

						<p class="text-xs text-muted-foreground">
							Selected: <code>{selectedConversation || 'none'}</code>
						</p>
					</CardContent>
				</Card>
			</section>

			<Separator />

			<!-- Card Grid View -->
			{#if viewMode === 'grid'}
				<section>
					<div class="mb-6 space-y-4">
						<div class="flex items-center justify-between">
							<h2 class="text-2xl font-bold">Card Grid View</h2>
							<div class="flex items-center gap-2">
								<Button size="sm" variant="outline">
									<Filter class="h-4 w-4 mr-2" />
									Filter
								</Button>
								<Button size="sm">
									<Plus class="h-4 w-4 mr-2" />
									New Conversation
								</Button>
							</div>
						</div>

						<!-- Search Bar -->
						<div class="relative">
							<Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
							<Input 
								type="text" 
								placeholder="Search conversations..." 
								class="pl-9"
								bind:value={searchQuery}
							/>
						</div>
					</div>

					<!-- Pinned Section -->
					{#if mockConversations.some(c => c.pinned)}
						<div class="mb-6">
							<h3 class="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-2">
								<Pin class="h-3 w-3" />
								Pinned
							</h3>
							<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
								{#each mockConversations.filter(c => c.pinned) as conv (conv.id)}
									<button
										class="relative group text-left"
										onclick={() => handleConversationClick(conv.id)}
									>
										<Card class="hover:bg-accent transition-colors cursor-pointer h-full">
											<CardHeader class="pb-3">
												<div class="flex items-start justify-between gap-2">
													<div class="flex-1 min-w-0">
														<CardTitle class="text-base line-clamp-2 mb-1">
															{conv.title}
														</CardTitle>
														<div class="flex items-center gap-2 text-xs text-muted-foreground">
															<Clock class="h-3 w-3" />
															{formatRelativeTime(conv.updated_at)}
															<span>•</span>
															<MessageCircle class="h-3 w-3" />
															{conv.message_count} messages
														</div>
													</div>
													<Button
														variant="ghost"
														size="sm"
														class="h-8 w-8 p-0 opacity-0 group-hover:opacity-100"
														title="Actions (rename, pin, delete, export)"
													>
														<MoreVertical class="h-4 w-4" />
													</Button>
												</div>
											</CardHeader>
											<CardContent class="pt-0 space-y-3">
												<p class="text-sm text-muted-foreground line-clamp-2">
													{conv.preview}
												</p>
												
												{#if conv.tags && conv.tags.length > 0}
													<div class="flex flex-wrap gap-1">
														{#each conv.tags as tag}
															<Badge variant="secondary" class="text-xs">
																{tag}
															</Badge>
														{/each}
													</div>
												{/if}

												{#if conv.git_context}
													<div class="flex items-center gap-2 text-xs text-muted-foreground pt-2 border-t">
														<GitBranch class="h-3 w-3" />
														<code class="font-mono">{conv.git_context.branch}</code>
														<span class="opacity-50">@{conv.git_context.commit}</span>
													</div>
												{/if}
											</CardContent>
										</Card>
										{#if conv.pinned}
											<div class="absolute top-2 right-2 pointer-events-none">
												<Pin class="h-3 w-3 text-primary fill-current" />
											</div>
										{/if}
									</button>
								{/each}
							</div>
						</div>
					{/if}

					<!-- All Conversations -->
					<div>
						<h3 class="text-sm font-semibold text-muted-foreground mb-3">
							All Conversations
						</h3>
						<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
							{#each mockConversations.filter(c => !c.pinned) as conv (conv.id)}
								<button
									class="relative group text-left"
									onclick={() => handleConversationClick(conv.id)}
								>
									<Card class="hover:bg-accent transition-colors cursor-pointer h-full">
										<CardHeader class="pb-3">
											<div class="flex items-start justify-between gap-2">
												<div class="flex-1 min-w-0">
													<CardTitle class="text-base line-clamp-2 mb-1">
														{conv.title}
													</CardTitle>
													<div class="flex items-center gap-2 text-xs text-muted-foreground">
														<Clock class="h-3 w-3" />
														{formatRelativeTime(conv.updated_at)}
														<span>•</span>
														<MessageCircle class="h-3 w-3" />
														{conv.message_count} messages
													</div>
												</div>
												<Button
													variant="ghost"
													size="sm"
													class="h-8 w-8 p-0 opacity-0 group-hover:opacity-100"
													title="Actions (rename, pin, delete, export)"
												>
													<MoreVertical class="h-4 w-4" />
												</Button>
											</div>
										</CardHeader>
										<CardContent class="pt-0 space-y-3">
											<p class="text-sm text-muted-foreground line-clamp-2">
												{conv.preview}
											</p>
											
											{#if conv.tags && conv.tags.length > 0}
												<div class="flex flex-wrap gap-1">
													{#each conv.tags as tag}
														<Badge variant="secondary" class="text-xs">
															{tag}
														</Badge>
													{/each}
												</div>
											{/if}

											{#if conv.git_context}
												<div class="flex items-center gap-2 text-xs text-muted-foreground pt-2 border-t">
													<GitBranch class="h-3 w-3" />
													<code class="font-mono">{conv.git_context.branch}</code>
													<span class="opacity-50">@{conv.git_context.commit}</span>
												</div>
											{/if}
										</CardContent>
									</Card>
								</button>
							{/each}
						</div>
					</div>
				</section>
			{/if}

			<!-- Compact List View -->
			{#if viewMode === 'list'}
				<section>
					<div class="mb-6 space-y-4">
						<div class="flex items-center justify-between">
							<h2 class="text-2xl font-bold">Compact List View</h2>
							<div class="flex items-center gap-2">
								<Button size="sm" variant="outline">
									<Filter class="h-4 w-4 mr-2" />
									Filter
								</Button>
								<Button size="sm">
									<Plus class="h-4 w-4 mr-2" />
									New Conversation
								</Button>
							</div>
						</div>

						<!-- Search Bar -->
						<div class="relative">
							<Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
							<Input 
								type="text" 
								placeholder="Search conversations..." 
								class="pl-9"
								bind:value={searchQuery}
							/>
						</div>
					</div>

					<Card>
						<CardContent class="p-0">
							<div class="divide-y">
								{#each mockConversations as conv (conv.id)}
									<button
										class="w-full text-left hover:bg-accent transition-colors p-4 flex items-center gap-4 group"
										onclick={() => handleConversationClick(conv.id)}
									>
										<!-- Icon -->
										<div class="flex-shrink-0">
											<div class="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
												<MessageSquare class="h-5 w-5 text-primary" />
											</div>
										</div>

										<!-- Content -->
										<div class="flex-1 min-w-0">
											<div class="flex items-start justify-between gap-2 mb-1">
												<h3 class="font-semibold text-sm line-clamp-1 flex items-center gap-2">
													{#if conv.pinned}
														<Pin class="h-3 w-3 text-primary fill-current flex-shrink-0" />
													{/if}
													{conv.title}
												</h3>
												<span class="text-xs text-muted-foreground whitespace-nowrap">
													{formatRelativeTime(conv.updated_at)}
												</span>
											</div>
											<p class="text-xs text-muted-foreground line-clamp-1 mb-2">
												{conv.preview}
											</p>
											<div class="flex items-center gap-3 text-xs text-muted-foreground">
												<span class="flex items-center gap-1">
													<MessageCircle class="h-3 w-3" />
													{conv.message_count}
												</span>
												{#if conv.tags && conv.tags.length > 0}
													<div class="flex gap-1">
														{#each conv.tags.slice(0, 2) as tag}
															<Badge variant="secondary" class="text-xs px-1 h-4">
																{tag}
															</Badge>
														{/each}
													</div>
												{/if}
												{#if conv.git_context}
													<span class="flex items-center gap-1 font-mono">
														<GitBranch class="h-3 w-3" />
														{conv.git_context.branch}
													</span>
												{/if}
											</div>
										</div>

										<!-- Actions -->
										<Button
											variant="ghost"
											size="sm"
											class="h-8 w-8 p-0 opacity-0 group-hover:opacity-100"
											title="Actions (rename, pin, delete, export)"
										>
											<MoreVertical class="h-4 w-4" />
										</Button>
									</button>
								{/each}
							</div>
						</CardContent>
					</Card>
				</section>
			{/if}

			<!-- Timeline View -->
			{#if viewMode === 'timeline'}
				<section>
					<div class="mb-6 space-y-4">
						<div class="flex items-center justify-between">
							<h2 class="text-2xl font-bold">Timeline View</h2>
							<div class="flex items-center gap-2">
								<Button size="sm" variant="outline">
									<Filter class="h-4 w-4 mr-2" />
									Filter
								</Button>
								<Button size="sm">
									<Plus class="h-4 w-4 mr-2" />
									New Conversation
								</Button>
							</div>
						</div>

						<!-- Search Bar -->
						<div class="relative">
							<Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
							<Input 
								type="text" 
								placeholder="Search conversations..." 
								class="pl-9"
								bind:value={searchQuery}
							/>
						</div>
					</div>

					<div class="space-y-8">
						<!-- Today -->
						{#if timeGroups.today.length > 0}
							<div>
								<h3 class="text-sm font-semibold mb-4 flex items-center gap-2">
									<Calendar class="h-4 w-4" />
									Today
								</h3>
								<div class="space-y-3">
									{#each timeGroups.today as conv (conv.id)}
										<button
											class="w-full text-left"
											onclick={() => handleConversationClick(conv.id)}
										>
											<Card class="hover:bg-accent transition-colors cursor-pointer">
												<CardContent class="p-4">
													<div class="flex items-start gap-4">
														<div class="flex-shrink-0 pt-1">
															<div class="h-2 w-2 rounded-full bg-primary"></div>
														</div>
														<div class="flex-1 min-w-0">
															<div class="flex items-start justify-between gap-2 mb-2">
																<h4 class="font-semibold flex items-center gap-2">
																	{#if conv.pinned}
																		<Pin class="h-3 w-3 text-primary fill-current" />
																	{/if}
																	{conv.title}
																</h4>
																<span class="text-xs text-muted-foreground whitespace-nowrap">
																	{formatRelativeTime(conv.updated_at)}
																</span>
															</div>
															<p class="text-sm text-muted-foreground mb-2">
																{conv.preview}
															</p>
															<div class="flex items-center gap-3 text-xs text-muted-foreground">
																<span class="flex items-center gap-1">
																	<MessageCircle class="h-3 w-3" />
																	{conv.message_count} messages
																</span>
																{#if conv.tags}
																	{#each conv.tags as tag}
																		<Badge variant="secondary" class="text-xs">
																			{tag}
																		</Badge>
																	{/each}
																{/if}
															</div>
														</div>
													</div>
												</CardContent>
											</Card>
										</button>
									{/each}
								</div>
							</div>
						{/if}

						<!-- Yesterday -->
						{#if timeGroups.yesterday.length > 0}
							<div>
								<h3 class="text-sm font-semibold mb-4 flex items-center gap-2">
									<Calendar class="h-4 w-4" />
									Yesterday
								</h3>
								<div class="space-y-3">
									{#each timeGroups.yesterday as conv (conv.id)}
										<button
											class="w-full text-left"
											onclick={() => handleConversationClick(conv.id)}
										>
											<Card class="hover:bg-accent transition-colors cursor-pointer">
												<CardContent class="p-4">
													<div class="flex items-start gap-4">
														<div class="flex-shrink-0 pt-1">
															<div class="h-2 w-2 rounded-full bg-muted-foreground"></div>
														</div>
														<div class="flex-1 min-w-0">
															<div class="flex items-start justify-between gap-2 mb-2">
																<h4 class="font-semibold flex items-center gap-2">
																	{#if conv.pinned}
																		<Pin class="h-3 w-3 text-primary fill-current" />
																	{/if}
																	{conv.title}
																</h4>
																<span class="text-xs text-muted-foreground whitespace-nowrap">
																	{formatRelativeTime(conv.updated_at)}
																</span>
															</div>
															<p class="text-sm text-muted-foreground mb-2">
																{conv.preview}
															</p>
															<div class="flex items-center gap-3 text-xs text-muted-foreground">
																<span class="flex items-center gap-1">
																	<MessageCircle class="h-3 w-3" />
																	{conv.message_count} messages
																</span>
																{#if conv.tags}
																	{#each conv.tags as tag}
																		<Badge variant="secondary" class="text-xs">
																			{tag}
																		</Badge>
																	{/each}
																{/if}
															</div>
														</div>
													</div>
												</CardContent>
											</Card>
										</button>
									{/each}
								</div>
							</div>
						{/if}

						<!-- Last Week -->
						{#if timeGroups.lastWeek.length > 0}
							<div>
								<h3 class="text-sm font-semibold mb-4 flex items-center gap-2">
									<Calendar class="h-4 w-4" />
									Last 7 Days
								</h3>
								<div class="space-y-3">
									{#each timeGroups.lastWeek as conv (conv.id)}
										<button
											class="w-full text-left"
											onclick={() => handleConversationClick(conv.id)}
										>
											<Card class="hover:bg-accent transition-colors cursor-pointer">
												<CardContent class="p-4">
													<div class="flex items-start gap-4">
														<div class="flex-shrink-0 pt-1">
															<div class="h-2 w-2 rounded-full bg-muted-foreground/50"></div>
														</div>
														<div class="flex-1 min-w-0">
															<div class="flex items-start justify-between gap-2 mb-2">
																<h4 class="font-semibold flex items-center gap-2">
																	{#if conv.pinned}
																		<Pin class="h-3 w-3 text-primary fill-current" />
																	{/if}
																	{conv.title}
																</h4>
																<span class="text-xs text-muted-foreground whitespace-nowrap">
																	{formatRelativeTime(conv.updated_at)}
																</span>
															</div>
															<p class="text-sm text-muted-foreground mb-2">
																{conv.preview}
															</p>
															<div class="flex items-center gap-3 text-xs text-muted-foreground">
																<span class="flex items-center gap-1">
																	<MessageCircle class="h-3 w-3" />
																	{conv.message_count} messages
																</span>
																{#if conv.tags}
																	{#each conv.tags as tag}
																		<Badge variant="secondary" class="text-xs">
																			{tag}
																		</Badge>
																	{/each}
																{/if}
															</div>
														</div>
													</div>
												</CardContent>
											</Card>
										</button>
									{/each}
								</div>
							</div>
						{/if}

						<!-- Older -->
						{#if timeGroups.older.length > 0}
							<div>
								<h3 class="text-sm font-semibold mb-4 flex items-center gap-2">
									<Archive class="h-4 w-4" />
									Older
								</h3>
								<div class="space-y-3">
									{#each timeGroups.older as conv (conv.id)}
										<button
											class="w-full text-left"
											onclick={() => handleConversationClick(conv.id)}
										>
											<Card class="hover:bg-accent transition-colors cursor-pointer">
												<CardContent class="p-4">
													<div class="flex items-start gap-4">
														<div class="flex-shrink-0 pt-1">
															<div class="h-2 w-2 rounded-full bg-muted-foreground/30"></div>
														</div>
														<div class="flex-1 min-w-0">
															<div class="flex items-start justify-between gap-2 mb-2">
																<h4 class="font-semibold flex items-center gap-2">
																	{#if conv.pinned}
																		<Pin class="h-3 w-3 text-primary fill-current" />
																	{/if}
																	{conv.title}
																</h4>
																<span class="text-xs text-muted-foreground whitespace-nowrap">
																	{formatRelativeTime(conv.updated_at)}
																</span>
															</div>
															<p class="text-sm text-muted-foreground mb-2">
																{conv.preview}
															</p>
															<div class="flex items-center gap-3 text-xs text-muted-foreground">
																<span class="flex items-center gap-1">
																	<MessageCircle class="h-3 w-3" />
																	{conv.message_count} messages
																</span>
																{#if conv.tags}
																	{#each conv.tags as tag}
																		<Badge variant="secondary" class="text-xs">
																			{tag}
																		</Badge>
																	{/each}
																{/if}
															</div>
														</div>
													</div>
												</CardContent>
											</Card>
										</button>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				</section>
			{/if}

			<Separator />

			<!-- Implementation Notes -->
			<section>
				<Card>
					<CardHeader>
						<CardTitle>Implementation Notes</CardTitle>
					</CardHeader>
					<CardContent class="space-y-4 text-sm">
						<div>
							<h4 class="font-semibold mb-2">Current Selection</h4>
							<p class="text-muted-foreground">
								Layout: <code class="bg-muted px-1 py-0.5 rounded">{viewMode}</code>
								<br />
								Interaction Model: <code class="bg-muted px-1 py-0.5 rounded">{interactionModel}</code>
								<br />
								Selected Conversation: <code class="bg-muted px-1 py-0.5 rounded">{selectedConversation || 'none'}</code>
							</p>
						</div>

						<Separator />

						<div>
							<h4 class="font-semibold mb-2">Features Demonstrated</h4>
							<ul class="list-disc list-inside space-y-1 text-muted-foreground">
								<li>Three layout options: Card Grid, Compact List, Timeline</li>
								<li>Pinned conversations with visual indicators</li>
								<li>Tags and metadata (message count, git context)</li>
								<li>Search and filter UI</li>
								<li>Quick actions menu (rename, pin, delete, export)</li>
								<li>Relative timestamps with grouping</li>
								<li>Workspace and git branch context</li>
								<li>Hover states and transitions</li>
							</ul>
						</div>

						<Separator />

						<div>
							<h4 class="font-semibold mb-2">Next Steps</h4>
							<ul class="list-disc list-inside space-y-1 text-muted-foreground">
								<li>Add navigation button to AppNavigation.svelte</li>
								<li>Implement backend conversation CRUD APIs</li>
								<li>Wire up actual conversation data from ConversationStore</li>
								<li>Implement state restoration on mount</li>
								<li>Add workspace filtering logic</li>
								<li>Build export/import functionality</li>
							</ul>
						</div>
					</CardContent>
				</Card>
			</section>
		</div>
	</div>
</div>