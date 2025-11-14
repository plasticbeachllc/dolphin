"""Extract call graph from Python code using tree-sitter."""

import uuid

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from ..models import EdgeType, GraphEdge, GraphNode, NodeType


class PythonCallGraphExtractor:
    """Extracts call graph from Python code."""

    def __init__(self):
        self.language = Language(tspython.language())
        self.parser = Parser(self.language)

    def extract(
        self,
        file_path: str,
        content: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Extract call graph from Python file.

        Args:
            file_path: Path to the file
            content: File content
            repo_id: Repository ID
            file_id: File ID in the database
            commit_sha: Current commit SHA
            branch: Current branch

        Returns:
            Tuple of (nodes, edges)
        """
        tree = self.parser.parse(bytes(content, "utf8"))
        nodes = []
        edges = []

        # Extract function/class definitions
        definitions = self._extract_definitions(
            tree.root_node, file_path, repo_id, file_id, commit_sha, branch
        )
        nodes.extend(definitions)

        # Extract call edges
        call_edges = self._extract_calls(
            tree.root_node, definitions, repo_id, commit_sha
        )
        edges.extend(call_edges)

        return nodes, edges

    def _extract_definitions(
        self,
        root: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
    ) -> list[GraphNode]:
        """Extract function and class definitions by walking the tree."""
        nodes = []
        class_stack = []  # Stack to track nested classes

        def visit(node: Node):
            if node.type == "class_definition":
                # Extract class
                class_node = self._extract_class_node(
                    node, file_path, repo_id, file_id, commit_sha, branch
                )
                nodes.append(class_node)
                class_stack.append(class_node)

                # Visit children
                for child in node.children:
                    visit(child)

                class_stack.pop()
                return

            elif node.type == "function_definition":
                # Extract function or method
                parent_class = class_stack[-1] if class_stack else None
                func_node = self._extract_function_node(
                    node, file_path, repo_id, file_id, commit_sha, branch, parent_class
                )
                nodes.append(func_node)

                # Visit children for nested functions
                for child in node.children:
                    visit(child)
                return

            # Recurse for other nodes
            for child in node.children:
                visit(child)

        visit(root)
        return nodes

    def _extract_class_node(
        self,
        node: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
    ) -> GraphNode:
        """Extract class definition node."""
        name_node = node.child_by_field_name("name")
        class_name = (
            name_node.text.decode("utf8")
            if (name_node and name_node.text)
            else "Unknown"
        )

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Build qualified name
        qualified_name = (
            f"{file_path.replace('/', '.').replace('.py', '')}.{class_name}"
        )

        return GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.CLASS,
            name=class_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="python",
            signature=node.text.decode("utf8")[:200],  # First 200 chars
            docstring=docstring,
            metadata={
                "ast_type": "class_definition",
                "file_id": file_id,
                "commit_sha": commit_sha,
                "branch": branch,
            },
        )

    def _extract_function_node(
        self,
        node: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
        parent_class: GraphNode | None = None,
    ) -> GraphNode:
        """Extract function/method definition node."""
        name_node = node.child_by_field_name("name")
        func_name = (
            name_node.text.decode("utf8")
            if (name_node and name_node.text)
            else "Unknown"
        )

        # Determine node type
        if parent_class:
            node_type = NodeType.METHOD
            qualified_name = f"{parent_class.qualified_name}.{func_name}"
        else:
            node_type = NodeType.FUNCTION
            qualified_name = (
                f"{file_path.replace('/', '.').replace('.py', '')}.{func_name}"
            )

        # Extract parameters for signature
        params_node = node.child_by_field_name("parameters")

        # Check if async by looking for 'async' keyword in children
        is_async = False
        for child in node.children:
            if child.type == "async":
                is_async = True
                break

        signature = f"{'async ' if is_async else ''}def {func_name}{params_node.text.decode('utf8') if (params_node and params_node.text) else '()'}"

        # Extract docstring
        docstring = self._extract_docstring(node)

        return GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=node_type,
            name=func_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="python",
            signature=signature,
            docstring=docstring,
            metadata={
                "ast_type": "function_definition",
                "parent_class": parent_class.id if parent_class else None,
                "is_async": is_async,
                "file_id": file_id,
                "commit_sha": commit_sha,
                "branch": branch,
            },
        )

    def _extract_calls(
        self, root: Node, definitions: list[GraphNode], repo_id: int, commit_sha: str
    ) -> list[GraphEdge]:
        """Extract call edges by walking the tree."""
        edges = []

        # Create a map of function nodes by their line ranges
        def_map: dict[tuple[int, int], GraphNode] = {
            (node.start_line or 0, node.end_line or 0): node
            for node in definitions
            if node.node_type in (NodeType.FUNCTION, NodeType.METHOD)
            and node.start_line is not None
            and node.end_line is not None
        }

        def visit(node: Node):
            if node.type == "call":
                # Find the containing function
                caller = self._find_containing_function(node, def_map)
                if caller:
                    # Extract callee name
                    function_node = node.child_by_field_name("function")
                    if function_node:
                        callee_name = self._extract_call_target(function_node)

                        # Try to resolve callee to a definition
                        callee = self._resolve_callee(callee_name, definitions)
                        if callee:
                            call_type = (
                                "method"
                                if function_node.type == "attribute"
                                else "direct"
                            )
                            edges.append(
                                GraphEdge(
                                    source_id=caller.id,
                                    target_id=callee.id,
                                    edge_type=EdgeType.CALLS,
                                    repo_id=repo_id,
                                    attributes={
                                        "call_line": node.start_point[0],
                                        "call_type": call_type,
                                        "commit_sha": commit_sha,
                                    },
                                )
                            )

            # Recurse
            for child in node.children:
                visit(child)

        visit(root)
        return edges

    def _find_containing_function(
        self, node: Node, def_map: dict[tuple[int, int], GraphNode]
    ) -> GraphNode | None:
        """Find the function/method that contains this node."""
        current = node.parent
        while current:
            line_range = (current.start_point[0], current.end_point[0])
            if line_range in def_map:
                return def_map[line_range]
            current = current.parent
        return None

    def _extract_call_target(self, node: Node) -> str:
        """Extract the name of the called function/method."""
        if node.type == "identifier":
            return node.text.decode("utf8") if node.text else "Unknown"
        elif node.type == "attribute":
            # For method calls like obj.method()
            attr_node = node.child_by_field_name("attribute")
            return (
                attr_node.text.decode("utf8")
                if (attr_node and attr_node.text)
                else "Unknown"
            )
        return "Unknown"

    def _resolve_callee(
        self, name: str, definitions: list[GraphNode]
    ) -> GraphNode | None:
        """Resolve a call target name to a definition node."""
        # Simple name matching - can be enhanced with scope analysis
        for node in definitions:
            if node.name == name:
                return node
        return None

    def _extract_docstring(self, func_node: Node) -> str | None:
        """Extract docstring from function or class definition."""
        body = func_node.child_by_field_name("body")
        if body and body.child_count > 0:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement" and first_stmt.child_count > 0:
                expr = first_stmt.children[0]
                if expr.type == "string":
                    docstring_text = expr.text.decode("utf8")
                    # Remove quotes and clean up
                    return docstring_text.strip("\"'").strip()
        return None
