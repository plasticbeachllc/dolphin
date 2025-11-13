"""Extract call graph from TypeScript code using tree-sitter."""

import uuid
from typing import Dict, List, Optional, Tuple

import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

from ..models import EdgeType, GraphEdge, GraphNode, NodeType


class TypeScriptCallGraphExtractor:
    """Extracts call graph from TypeScript code."""

    def __init__(self):
        self.language = Language(tsts.language_typescript())
        self.parser = Parser(self.language)

    def extract(
        self,
        file_path: str,
        content: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """Extract call graph from TypeScript file.

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

        # Extract relationship edges (implements, extends)
        relationship_edges = self._extract_relationships(
            tree.root_node, definitions, repo_id, commit_sha
        )
        edges.extend(relationship_edges)

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
    ) -> List[GraphNode]:
        """Extract function, method, and class definitions by walking the tree."""
        nodes = []
        class_stack = []  # Stack to track nested classes

        def visit(node: Node):
            if node.type == "class_declaration":
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

            elif node.type == "function_declaration":
                # Extract function
                func_node = self._extract_function_node(
                    node, file_path, repo_id, file_id, commit_sha, branch
                )
                nodes.append(func_node)

                # Visit children
                for child in node.children:
                    visit(child)
                return

            elif node.type == "method_definition":
                # Extract method
                parent_class = class_stack[-1] if class_stack else None
                method_node = self._extract_method_node(
                    node, file_path, repo_id, file_id, commit_sha, branch, parent_class
                )
                nodes.append(method_node)

                # Visit children
                for child in node.children:
                    visit(child)
                return

            elif node.type == "interface_declaration":
                # Extract interface (TypeScript only)
                interface_node = self._extract_interface_node(
                    node, file_path, repo_id, file_id, commit_sha, branch
                )
                nodes.append(interface_node)

                # Visit children
                for child in node.children:
                    visit(child)
                return

            elif node.type == "variable_declarator":
                # Check if it's an arrow function
                value_node = node.child_by_field_name("value")
                if value_node and value_node.type == "arrow_function":
                    arrow_node = self._extract_arrow_function_node(
                        node, file_path, repo_id, file_id, commit_sha, branch
                    )
                    if arrow_node:
                        nodes.append(arrow_node)

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
        class_name = name_node.text.decode("utf8") if name_node else "Unknown"

        # Extract docstring/comment
        docstring = self._extract_comment(node)

        # Build qualified name
        qualified_name = f"{file_path.replace('/', '.').replace('.ts', '').replace('.tsx', '')}.{class_name}"

        return GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.CLASS,
            name=class_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="typescript",
            signature=node.text.decode("utf8")[:200],
            docstring=docstring,
            metadata={
                "ast_type": "class_declaration",
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
    ) -> GraphNode:
        """Extract function declaration node."""
        name_node = node.child_by_field_name("name")
        func_name = name_node.text.decode("utf8") if name_node else "Unknown"

        # Build qualified name
        qualified_name = f"{file_path.replace('/', '.').replace('.ts', '').replace('.tsx', '')}.{func_name}"

        # Extract parameters for signature
        params_node = node.child_by_field_name("parameters")
        params_text = params_node.text.decode("utf8") if params_node else "()"

        # Check if async
        is_async = self._is_async(node)
        signature = f"{'async ' if is_async else ''}function {func_name}{params_text}"

        # Extract docstring/comment
        docstring = self._extract_comment(node)

        return GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.FUNCTION,
            name=func_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="typescript",
            signature=signature,
            docstring=docstring,
            metadata={
                "ast_type": "function_declaration",
                "is_async": is_async,
                "file_id": file_id,
                "commit_sha": commit_sha,
                "branch": branch,
            },
        )

    def _extract_method_node(
        self,
        node: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
        parent_class: Optional[GraphNode] = None,
    ) -> GraphNode:
        """Extract method definition node."""
        name_node = node.child_by_field_name("name")
        method_name = name_node.text.decode("utf8") if name_node else "Unknown"

        # Build qualified name
        if parent_class:
            qualified_name = f"{parent_class.qualified_name}.{method_name}"
        else:
            qualified_name = f"{file_path.replace('/', '.').replace('.ts', '').replace('.tsx', '')}.{method_name}"

        # Extract parameters for signature
        params_node = node.child_by_field_name("parameters")
        params_text = params_node.text.decode("utf8") if params_node else "()"

        # Check if async
        is_async = self._is_async(node)
        signature = f"{'async ' if is_async else ''}{method_name}{params_text}"

        # Extract docstring/comment
        docstring = self._extract_comment(node)

        return GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.METHOD,
            name=method_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="typescript",
            signature=signature,
            docstring=docstring,
            metadata={
                "ast_type": "method_definition",
                "parent_class": parent_class.id if parent_class else None,
                "is_async": is_async,
                "file_id": file_id,
                "commit_sha": commit_sha,
                "branch": branch,
            },
        )

    def _extract_arrow_function_node(
        self,
        node: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
    ) -> Optional[GraphNode]:
        """Extract arrow function assigned to a variable."""
        # Get the variable declarator
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        func_name = name_node.text.decode("utf8")

        # Build qualified name
        qualified_name = f"{file_path.replace('/', '.').replace('.ts', '').replace('.tsx', '')}.{func_name}"

        # Get the arrow function node
        arrow_func_node = node.child_by_field_name("value")
        if not arrow_func_node:
            return None

        # Extract parameters
        params_node = arrow_func_node.child_by_field_name("parameters")
        params_text = params_node.text.decode("utf8") if params_node else "()"

        # Check if async
        is_async = self._is_async(arrow_func_node)
        signature = (
            f"const {func_name} = {'async ' if is_async else ''}{params_text} => ..."
        )

        # Extract docstring/comment
        docstring = self._extract_comment(node.parent) if node.parent else None

        return GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.FUNCTION,
            name=func_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="typescript",
            signature=signature,
            docstring=docstring,
            metadata={
                "ast_type": "arrow_function",
                "is_async": is_async,
                "file_id": file_id,
                "commit_sha": commit_sha,
                "branch": branch,
            },
        )

    def _extract_interface_node(
        self,
        node: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        branch: str,
    ) -> GraphNode:
        """Extract interface declaration node (TypeScript)."""
        name_node = node.child_by_field_name("name")
        interface_name = name_node.text.decode("utf8") if name_node else "Unknown"

        # Build qualified name
        qualified_name = f"{file_path.replace('/', '.').replace('.ts', '').replace('.tsx', '')}.{interface_name}"

        # Extract docstring/comment
        docstring = self._extract_comment(node)

        return GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.INTERFACE,
            name=interface_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="typescript",
            signature=node.text.decode("utf8")[:200],
            docstring=docstring,
            metadata={
                "ast_type": "interface_declaration",
                "file_id": file_id,
                "commit_sha": commit_sha,
                "branch": branch,
            },
        )

    def _extract_relationships(
        self, root: Node, definitions: List[GraphNode], repo_id: int, commit_sha: str
    ) -> List[GraphEdge]:
        """Extract relationship edges (implements, extends) by walking the tree."""
        edges = []

        def visit(node: Node):
            if node.type == "class_declaration":
                # Find the class node
                name_node = node.child_by_field_name("name")
                if not name_node:
                    for child in node.children:
                        visit(child)
                    return

                class_name = name_node.text.decode("utf8")
                class_node = next(
                    (
                        n
                        for n in definitions
                        if n.name == class_name and n.node_type == NodeType.CLASS
                    ),
                    None,
                )

                if not class_node:
                    for child in node.children:
                        visit(child)
                    return

                # Look for implements/extends clauses
                for child in node.children:
                    if child.type == "class_heritage":
                        for heritage_child in child.children:
                            if heritage_child.type == "implements_clause":
                                # Extract implemented interfaces
                                for impl_child in heritage_child.children:
                                    if impl_child.type in (
                                        "type_identifier",
                                        "identifier",
                                    ):
                                        interface_name = impl_child.text.decode("utf8")
                                        # Find the interface node
                                        interface_node = next(
                                            (
                                                n
                                                for n in definitions
                                                if n.name == interface_name
                                                and n.node_type == NodeType.INTERFACE
                                            ),
                                            None,
                                        )
                                        if interface_node:
                                            edges.append(
                                                GraphEdge(
                                                    source_id=class_node.id,
                                                    target_id=interface_node.id,
                                                    edge_type=EdgeType.IMPLEMENTS,
                                                    repo_id=repo_id,
                                                    attributes={
                                                        "line_number": heritage_child.start_point[
                                                            0
                                                        ],
                                                        "commit_sha": commit_sha,
                                                    },
                                                )
                                            )
                            elif heritage_child.type == "extends_clause":
                                # Extract extended class
                                for ext_child in heritage_child.children:
                                    if ext_child.type in (
                                        "identifier",
                                        "member_expression",
                                    ):
                                        base_class_name = ext_child.text.decode("utf8")
                                        # Find the base class node
                                        base_node = next(
                                            (
                                                n
                                                for n in definitions
                                                if n.name == base_class_name
                                                and n.node_type == NodeType.CLASS
                                            ),
                                            None,
                                        )
                                        if base_node:
                                            edges.append(
                                                GraphEdge(
                                                    source_id=class_node.id,
                                                    target_id=base_node.id,
                                                    edge_type=EdgeType.INHERITS,
                                                    repo_id=repo_id,
                                                    attributes={
                                                        "line_number": heritage_child.start_point[
                                                            0
                                                        ],
                                                        "commit_sha": commit_sha,
                                                    },
                                                )
                                            )

            # Recurse for other nodes
            for child in node.children:
                visit(child)

        visit(root)
        return edges

    def _extract_calls(
        self, root: Node, definitions: List[GraphNode], repo_id: int, commit_sha: str
    ) -> List[GraphEdge]:
        """Extract call edges by walking the tree."""
        edges = []

        # Create a map of function nodes by their line ranges
        def_map: Dict[Tuple[int, int], GraphNode] = {
            (node.start_line, node.end_line): node
            for node in definitions
            if node.node_type in (NodeType.FUNCTION, NodeType.METHOD)
        }

        def visit(node: Node):
            if node.type == "call_expression":
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
                                if function_node.type == "member_expression"
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
        self, node: Node, def_map: Dict[Tuple[int, int], GraphNode]
    ) -> Optional[GraphNode]:
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
            return node.text.decode("utf8")
        elif node.type == "member_expression":
            # For method calls like obj.method()
            prop_node = node.child_by_field_name("property")
            return prop_node.text.decode("utf8") if prop_node else "Unknown"
        return "Unknown"

    def _resolve_callee(
        self, name: str, definitions: List[GraphNode]
    ) -> Optional[GraphNode]:
        """Resolve a call target name to a definition node."""
        # Simple name matching - can be enhanced with scope analysis
        for node in definitions:
            if node.name == name:
                return node
        return None

    def _is_async(self, node: Node) -> bool:
        """Check if a function/method is async."""
        # Check for 'async' keyword in the node
        for child in node.children:
            if child.type == "async":
                return True
        return False

    def _extract_comment(self, node: Node) -> Optional[str]:
        """Extract JSDoc or line comment before the node."""
        # Look for comment in previous siblings
        if not node.parent:
            return None

        # Find the node in parent's children
        siblings = node.parent.children
        node_index = -1
        for i, sibling in enumerate(siblings):
            if sibling.id == node.id:
                node_index = i
                break

        if node_index <= 0:
            return None

        # Check previous sibling for comment
        prev_sibling = siblings[node_index - 1]
        if prev_sibling.type == "comment":
            comment_text = prev_sibling.text.decode("utf8")
            # Clean up JSDoc or line comments
            return comment_text.strip("/*").strip("*/").strip("//").strip()

        return None
