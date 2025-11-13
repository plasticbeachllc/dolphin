// agent-core/src/kb/kb-context-enricher.ts

/**
 * EP-11: KB Context Enricher
 *
 * Enriches KB search results with graph-aware context.
 * Aggregates and structures graph data from multiple search results.
 */

import type { EnrichedChunk, GraphContext, GraphNode, GraphRelationship } from "../orchestration/types";

export class KBContextEnricher {
  /**
   * Enrich chunks with aggregated graph context
   *
   * Since the KB API already returns graph_context per chunk,
   * this method aggregates and deduplicates graph data across all chunks.
   */
  async enrichWithGraph(
    chunks: EnrichedChunk[],
    repoName: string
  ): Promise<GraphContext | null> {
    const allNodes: GraphNode[] = [];
    const allRelationships: GraphRelationship[] = [];

    // Extract graph context from all chunks
    for (const chunk of chunks) {
      if (chunk.graph_context) {
        // Collect nodes
        if (chunk.graph_context.nodes) {
          allNodes.push(...chunk.graph_context.nodes);
        }

        // Collect relationships
        if (chunk.graph_context.relationships) {
          allRelationships.push(...chunk.graph_context.relationships);
        }
      }
    }

    if (allNodes.length === 0 && allRelationships.length === 0) {
      return null;
    }

    // Deduplicate nodes by qualified name
    const uniqueNodes = this.deduplicateNodes(allNodes);

    // Deduplicate relationships by source/target/type combination
    const uniqueRelationships = this.deduplicateRelationships(allRelationships);

    return {
      nodes: uniqueNodes,
      relationships: uniqueRelationships
    };
  }

  /**
   * Deduplicate nodes by qualified name
   */
  private deduplicateNodes(nodes: GraphNode[]): GraphNode[] {
    const seen = new Map<string, GraphNode>();

    for (const node of nodes) {
      const key = node.qualified_name;

      if (!seen.has(key)) {
        seen.set(key, node);
      }
    }

    return Array.from(seen.values());
  }

  /**
   * Deduplicate relationships by source/target/type
   */
  private deduplicateRelationships(relationships: GraphRelationship[]): GraphRelationship[] {
    const seen = new Map<string, GraphRelationship>();

    for (const rel of relationships) {
      const key = `${rel.source.qualified_name}:${rel.type}:${rel.target.qualified_name}:${rel.direction}`;

      if (!seen.has(key)) {
        seen.set(key, rel);
      }
    }

    return Array.from(seen.values());
  }

  /**
   * Build a summary of graph context for display
   */
  formatGraphSummary(graph: GraphContext | null): string {
    if (!graph) {
      return "No graph context available";
    }

    const parts: string[] = [];

    // Node summary
    const nodeTypes = new Map<string, number>();
    for (const node of graph.nodes) {
      nodeTypes.set(node.type, (nodeTypes.get(node.type) || 0) + 1);
    }

    if (graph.nodes.length > 0) {
      parts.push(`**Entities**: ${graph.nodes.length} total`);

      const typeSummary = Array.from(nodeTypes.entries())
        .map(([type, count]) => `${count} ${type}${count > 1 ? 's' : ''}`)
        .join(", ");

      parts.push(`  - ${typeSummary}`);
    }

    // Relationship summary
    const relTypes = new Map<string, number>();
    for (const rel of graph.relationships) {
      relTypes.set(rel.type, (relTypes.get(rel.type) || 0) + 1);
    }

    if (graph.relationships.length > 0) {
      parts.push(`**Relationships**: ${graph.relationships.length} total`);

      const relSummary = Array.from(relTypes.entries())
        .map(([type, count]) => `${count} ${type}`)
        .join(", ");

      parts.push(`  - ${relSummary}`);
    }

    return parts.join("\n");
  }
}
