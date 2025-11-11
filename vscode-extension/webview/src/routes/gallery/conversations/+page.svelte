<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Badge } from '$lib/components/ui/badge';
	import {
		MessageSquare,
		Pin,
		Trash2,
		Edit3,
		Search,
		Clock,
		MessageCircle,
		MoreVertical,
		Loader2,
		Plus
	} from 'lucide-svelte';
	import { listConversations, loadConversation, deleteConversation, renameConversation, onMessage, getVSCodeAPI } from '$lib/api/vscode';
	import type { ConversationListItem, AgentEvent } from '@shared/types/events';

	// Props from parent
	interface Props {
		onNavigate?: (path: string) => void;
	}

	let { onNavigate }: Props = $props();

	// State
	let conversations = $state<ConversationListItem[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');
	let deletingId = $state<string | null>(null);
	let renamingId = $state<string | null>(null);
	let renameText = $state('');

	// Filtered conversations based on search
	let filteredConversations = $derived(
		searchQuery.trim() === ''
			? conversations
			: conversations.filter(conv =>
					conv.metadata.title.toLowerCase().includes(searchQuery.toLowerCase())
			  )
	);

	// Group by pinned
	let pinnedConversations = $derived(
		filteredConversations.filter(c => c.metadata.pinned)
	);
	let unpinnedConversations = $derived(
		filteredConversations.filter(c => !c.metadata.pinned)
	);

	// Format relative time
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

	// Fetch conversations on mount
	onMount(() => {
		console.log('[ConversationsGallery] Mounting, fetching conversations...');
		
		// Set up listener for conversation events
		const unsubscribe = onMessage((event: AgentEvent) => {
			console.log('[ConversationsGallery] Received event:', event);
			
			switch (event.type) {
				case 'conversations_listed':
					console.log('[ConversationsGallery] Received conversations:', event.conversations);
					conversations = event.conversations;
					loading = false;
					error = null;
					break;
					
				case 'conversation_deleted':
					console.log('[ConversationsGallery] Conversation deleted:', event.conversationId);
					conversations = conversations.filter(c => c.id !== event.conversationId);
					deletingId = null;
					break;
					
				case 'conversation_renamed':
					console.log('[ConversationsGallery] Conversation renamed:', event.conversationId, event.newTitle);
					conversations = conversations.map(c =>
						c.id === event.conversationId
							? { ...c, metadata: { ...c.metadata, title: event.newTitle } }
							: c
					);
					renamingId = null;
					renameText = '';
					break;
					
				case 'error':
					console.error('[ConversationsGallery] Error:', event.error);
					error = event.error.message;
					loading = false;
					break;
			}
		});

		// Request conversation list
		listConversations();

		return () => {
			unsubscribe();
		};
	});

	// Handle conversation click
	function handleConversationClick(convId: string) {
		console.log('[ConversationsGallery] Loading conversation:', convId);
		loadConversation(convId);
		// Navigation to chat will happen in App.svelte when conversation_loaded event fires
	}

	// Handle delete
	function handleDelete(convId: string, title: string) {
		if (confirm(`Delete conversation "${title}"?\n\nThis action cannot be undone.`)) {
			deletingId = convId;
			deleteConversation(convId);
		}
	}

	// Start rename
	function startRename(convId: string, currentTitle: string) {
		renamingId = convId;
		renameText = currentTitle;
	}

	// Cancel rename
	function cancelRename() {
		renamingId = null;
		renameText = '';
	}

	// Save rename
	function saveRename(convId: string) {
		if (renameText.trim() === '') {
			alert('Title cannot be empty');
			return;
		}
		renameConversation(convId, renameText.trim());
	}
	
	// Handle new conversation
	function handleNewConversation() {
		console.log('[ConversationsGallery] Starting new conversation');
		// Clear the current conversation state
		const api = getVSCodeAPI();
		api.postMessage({
			type: 'clear_conversation'
		});
		// Navigate to chat view
		onNavigate?.('/');
	}
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-7xl mx-auto">
		<!-- Dev Mode Notice -->
		{#if typeof acquireVsCodeApi === 'undefined'}
			<div class="mb-6 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
				<div class="flex items-start gap-3">
					<div class="text-yellow-500 text-lg">ℹ️</div>
					<div class="flex-1">
						<h3 class="text-sm font-semibold text-yellow-500 mb-1">Development Mode</h3>
						<p class="text-sm text-muted-foreground">
							Conversations require the VS Code extension backend. To test this feature, run the webview inside VS Code.
						</p>
					</div>
				</div>
			</div>
		{/if}
		
		<!-- Header -->
		<div class="mb-8">
			<div class="flex items-center justify-between gap-4">
				<div>
					<h1 class="text-4xl font-bold mb-2">Conversations</h1>
					<p class="text-muted-foreground">
						Browse and restore your conversation history
					</p>
				</div>
				<Button onclick={handleNewConversation} size="sm" variant="outline" title="New Conversation" aria-label="New Conversation" class="gap-2">
					<Plus class="h-4 w-4" />
					<span>New</span>
				</Button>
			</div>
		</div>

		<!-- Search Bar -->
		<div class="mb-6 relative">
			<Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
			<Input 
				type="text" 
				placeholder="Search conversations..." 
				class="pl-9"
				bind:value={searchQuery}
			/>
		</div>

		<!-- Loading State -->
		{#if loading}
			<div class="flex items-center justify-center py-12">
				<div class="flex items-center gap-3 text-muted-foreground">
					<Loader2 class="h-5 w-5 animate-spin" />
					<span>Loading conversations...</span>
				</div>
			</div>
		{:else if error}
			<!-- Error State -->
			<Card class="border-destructive">
				<CardContent class="p-6">
					<p class="text-destructive font-semibold mb-2">Error loading conversations</p>
					<p class="text-sm text-muted-foreground">{error}</p>
					<Button 
						size="sm" 
						variant="outline" 
						class="mt-4"
						onclick={() => {
							loading = true;
							error = null;
							listConversations();
						}}
					>
						Retry
					</Button>
				</CardContent>
			</Card>
		{:else if conversations.length === 0}
			<!-- Empty State -->
			<Card>
				<CardContent class="p-12 text-center">
					<MessageSquare class="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
					<h3 class="text-lg font-semibold mb-2">No conversations yet</h3>
					<p class="text-sm text-muted-foreground mb-4">
						Start chatting to create your first conversation
					</p>
					<Button onclick={() => onNavigate?.('/')}>
						Go to Chat
					</Button>
				</CardContent>
			</Card>
		{:else}
			<!-- Conversations Grid -->
			<div class="space-y-6">
				<!-- Pinned Section -->
				{#if pinnedConversations.length > 0}
					<div>
						<h3 class="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-2">
							<Pin class="h-3 w-3" />
							Pinned
						</h3>
						<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
							{#each pinnedConversations as conv (conv.id)}
								<div class="relative group">
									<button
										class="w-full text-left"
										onclick={() => handleConversationClick(conv.id)}
										disabled={deletingId === conv.id}
									>
										<Card class="hover:bg-accent transition-colors cursor-pointer h-full">
											<CardHeader class="pb-3">
												<div class="flex items-start justify-between gap-2">
													<div class="flex-1 min-w-0">
														{#if renamingId === conv.id}
															<div
																class="space-y-2"
																role="form"
																onclick={(e) => e.stopPropagation()}
																onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') e.stopPropagation(); }}
															>
																<Input
																	type="text"
																	bind:value={renameText}
																	class="h-8 text-sm"
																	placeholder="Conversation title"
																	autofocus
																/>
																<div class="flex gap-1">
																	<Button size="sm" variant="default" onclick={() => saveRename(conv.id)}>
																		Save
																	</Button>
																	<Button size="sm" variant="outline" onclick={cancelRename}>
																		Cancel
																	</Button>
																</div>
															</div>
														{:else}
															<CardTitle class="text-base line-clamp-2 mb-1">
																{conv.metadata.title}
															</CardTitle>
															<div class="flex items-center gap-2 text-xs text-muted-foreground">
																<Clock class="h-3 w-3" />
																{formatRelativeTime(conv.updated_at)}
																<span>•</span>
																<MessageCircle class="h-3 w-3" />
																{conv.message_count} messages
															</div>
														{/if}
													</div>
													{#if renamingId !== conv.id}
														<div
															class="flex gap-1 opacity-0 group-hover:opacity-100"
															role="toolbar"
															aria-label="Conversation actions"
															onclick={(e) => e.stopPropagation()}
															onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') e.stopPropagation(); }}
														>
															<Button
																variant="ghost"
																size="sm"
																class="h-7 w-7 p-0"
																title="Rename"
																onclick={() => startRename(conv.id, conv.metadata.title)}
															>
																<Edit3 class="h-3 w-3" />
															</Button>
															<Button
																variant="ghost"
																size="sm"
																class="h-7 w-7 p-0"
																title="Delete"
																disabled={deletingId === conv.id}
																onclick={() => handleDelete(conv.id, conv.metadata.title)}
															>
																{#if deletingId === conv.id}
																	<Loader2 class="h-3 w-3 animate-spin" />
																{:else}
																	<Trash2 class="h-3 w-3 text-destructive" />
																{/if}
															</Button>
														</div>
													{/if}
												</div>
											</CardHeader>
											<CardContent class="pt-0">
												<div class="flex items-center gap-2 text-xs text-muted-foreground">
													{#if conv.metadata.files.length > 0}
														<span>{conv.metadata.files.length} files</span>
														<span>•</span>
													{/if}
													<span>{conv.metadata.token_count.toLocaleString()} tokens</span>
												</div>
											</CardContent>
										</Card>
									</button>
									<div class="absolute top-2 right-2 pointer-events-none">
										<Pin class="h-3 w-3 text-primary fill-current" />
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/if}

				<!-- All Conversations -->
				<div>
					<h3 class="text-sm font-semibold text-muted-foreground mb-3">
						{pinnedConversations.length > 0 ? 'All Conversations' : 'Recent'}
					</h3>
					<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
						{#each unpinnedConversations as conv (conv.id)}
							<div class="relative group">
								<button
									class="w-full text-left"
									onclick={() => handleConversationClick(conv.id)}
									disabled={deletingId === conv.id}
								>
									<Card class="hover:bg-accent transition-colors cursor-pointer h-full">
										<CardHeader class="pb-3">
											<div class="flex items-start justify-between gap-2">
												<div class="flex-1 min-w-0">
													{#if renamingId === conv.id}
														<div
															class="space-y-2"
															role="form"
															onclick={(e) => e.stopPropagation()}
															onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') e.stopPropagation(); }}
														>
															<Input
																type="text"
																bind:value={renameText}
																class="h-8 text-sm"
																placeholder="Conversation title"
																autofocus
															/>
															<div class="flex gap-1">
																<Button size="sm" variant="default" onclick={() => saveRename(conv.id)}>
																	Save
																</Button>
																<Button size="sm" variant="outline" onclick={cancelRename}>
																	Cancel
																</Button>
															</div>
														</div>
													{:else}
														<CardTitle class="text-base line-clamp-2 mb-1">
															{conv.metadata.title}
														</CardTitle>
														<div class="flex items-center gap-2 text-xs text-muted-foreground">
															<Clock class="h-3 w-3" />
															{formatRelativeTime(conv.updated_at)}
															<span>•</span>
															<MessageCircle class="h-3 w-3" />
															{conv.message_count} messages
														</div>
													{/if}
												</div>
												{#if renamingId !== conv.id}
													<div
														class="flex gap-1 opacity-0 group-hover:opacity-100"
														role="toolbar"
														aria-label="Conversation actions"
														onclick={(e) => e.stopPropagation()}
														onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') e.stopPropagation(); }}
													>
														<Button
															variant="ghost"
															size="sm"
															class="h-7 w-7 p-0"
															title="Rename"
															onclick={() => startRename(conv.id, conv.metadata.title)}
														>
															<Edit3 class="h-3 w-3" />
														</Button>
														<Button
															variant="ghost"
															size="sm"
															class="h-7 w-7 p-0"
															title="Delete"
															disabled={deletingId === conv.id}
															onclick={() => handleDelete(conv.id, conv.metadata.title)}
														>
															{#if deletingId === conv.id}
																<Loader2 class="h-3 w-3 animate-spin" />
															{:else}
																<Trash2 class="h-3 w-3 text-destructive" />
															{/if}
														</Button>
													</div>
												{/if}
											</div>
										</CardHeader>
										<CardContent class="pt-0">
											<div class="flex items-center gap-2 text-xs text-muted-foreground">
												{#if conv.metadata.files.length > 0}
													<span>{conv.metadata.files.length} files</span>
													<span>•</span>
												{/if}
												<span>{conv.metadata.token_count.toLocaleString()} tokens</span>
											</div>
										</CardContent>
									</Card>
								</button>
							</div>
						{/each}
					</div>
				</div>
			</div>
		{/if}
	</div>
</div>