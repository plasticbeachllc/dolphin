"""Data flow analysis for tracking variable dependencies."""

from typing import Dict, List, Optional, Tuple

from tree_sitter import Node

from .models import EdgeType, GraphEdge, GraphNode, NodeType


class VariableReference:
    """Represents a variable reference in the code."""

    def __init__(
        self,
        var_name: str,
        line: int,
        func_id: Optional[str] = None,
        is_definition: bool = False,
        is_mutation: bool = False,
    ):
        self.var_name = var_name
        self.line = line
        self.func_id = func_id
        self.is_definition = is_definition
        self.is_mutation = is_mutation


class DataFlowAnalyzer:
    """Analyzes data flow and variable dependencies."""

    def __init__(self):
        pass

    def extract_data_flow_python(
        self, tree_root: Node, definitions: List[GraphNode], repo_id: int
    ) -> List[GraphEdge]:
        """Extract data flow edges for Python code."""
        edges = []

        # Track variable definitions and uses
        var_refs = self._find_python_variable_references(tree_root, definitions)

        # Create edges for variable usage
        for ref in var_refs:
            if not ref.is_definition and ref.func_id:
                # Find the definition of this variable
                for def_ref in var_refs:
                    if (
                        def_ref.var_name == ref.var_name
                        and def_ref.is_definition
                        and def_ref.func_id
                        and def_ref.line < ref.line
                    ):
                        # Create an edge from the using function to the defining function
                        edge_type = (
                            EdgeType.MODIFIES if ref.is_mutation else EdgeType.USES
                        )
                        edges.append(
                            GraphEdge(
                                source_id=ref.func_id,
                                target_id=def_ref.func_id,
                                edge_type=edge_type,
                                repo_id=repo_id,
                                attributes={
                                    "variable": ref.var_name,
                                    "use_line": ref.line,
                                    "def_line": def_ref.line,
                                },
                            )
                        )
                        break

        return edges

    def extract_data_flow_typescript(
        self, tree_root: Node, definitions: List[GraphNode], repo_id: int
    ) -> List[GraphEdge]:
        """Extract data flow edges for TypeScript code."""
        edges = []

        # Track variable declarations and uses
        var_refs = self._find_typescript_variable_references(tree_root, definitions)

        # Create edges for variable usage
        for ref in var_refs:
            if not ref.is_definition and ref.func_id:
                # Find the definition of this variable
                for def_ref in var_refs:
                    if (
                        def_ref.var_name == ref.var_name
                        and def_ref.is_definition
                        and def_ref.func_id
                        and def_ref.line < ref.line
                    ):
                        edge_type = (
                            EdgeType.MODIFIES if ref.is_mutation else EdgeType.USES
                        )
                        edges.append(
                            GraphEdge(
                                source_id=ref.func_id,
                                target_id=def_ref.func_id,
                                edge_type=edge_type,
                                repo_id=repo_id,
                                attributes={
                                    "variable": ref.var_name,
                                    "use_line": ref.line,
                                    "def_line": def_ref.line,
                                },
                            )
                        )
                        break

        return edges

    def _find_python_variable_references(
        self, tree_root: Node, definitions: List[GraphNode]
    ) -> List[VariableReference]:
        """Find all variable references in Python code."""
        refs: list[VariableReference] = []

        # Create a map of function nodes by line range
        def_map: Dict[Tuple[int, int], GraphNode] = {
            (node.start_line or 0, node.end_line or 0): node
            for node in definitions
            if node.node_type in (NodeType.FUNCTION, NodeType.METHOD)
            and node.start_line is not None
            and node.end_line is not None
        }

        # Walk the tree to find assignments and identifiers
        self._walk_python_tree(tree_root, refs, def_map)

        return refs

    def _walk_python_tree(
        self,
        node: Node,
        refs: List[VariableReference],
        def_map: Dict[Tuple[int, int], GraphNode],
    ) -> None:
        """Recursively walk the Python AST to find variable references."""
        # Check for assignments (variable definitions)
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                text = left.text
                if not text:
                    return
                var_name = text.decode("utf8")
                containing_func = self._find_containing_func(node, def_map)
                refs.append(
                    VariableReference(
                        var_name=var_name,
                        line=left.start_point[0],
                        func_id=containing_func.id if containing_func else None,
                        is_definition=True,
                    )
                )

        # Check for identifiers (variable uses)
        elif node.type == "identifier":
            text = node.text
            if not text:
                return
            var_name = text.decode("utf8")
            containing_func = self._find_containing_func(node, def_map)

            # Check if this is a mutation (left side of assignment)
            is_mutation = False
            if node.parent and node.parent.type == "assignment":
                left = node.parent.child_by_field_name("left")
                if left and left.id == node.id:
                    is_mutation = True

            if containing_func and not is_mutation:
                refs.append(
                    VariableReference(
                        var_name=var_name,
                        line=node.start_point[0],
                        func_id=containing_func.id,
                        is_definition=False,
                        is_mutation=is_mutation,
                    )
                )

        # Recurse on children
        for child in node.children:
            self._walk_python_tree(child, refs, def_map)

    def _find_typescript_variable_references(
        self, tree_root: Node, definitions: List[GraphNode]
    ) -> List[VariableReference]:
        """Find all variable references in TypeScript code."""
        refs: list[VariableReference] = []

        # Create a map of function nodes by line range
        def_map: Dict[Tuple[int, int], GraphNode] = {
            (node.start_line or 0, node.end_line or 0): node
            for node in definitions
            if node.node_type in (NodeType.FUNCTION, NodeType.METHOD)
            and node.start_line is not None
            and node.end_line is not None
        }

        # Walk the tree to find declarations and identifiers
        self._walk_typescript_tree(tree_root, refs, def_map)

        return refs

    def _walk_typescript_tree(
        self,
        node: Node,
        refs: List[VariableReference],
        def_map: Dict[Tuple[int, int], GraphNode],
    ) -> None:
        """Recursively walk the TypeScript AST to find variable references."""
        # Check for variable declarations
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node and name_node.type == "identifier":
                text = name_node.text
                if not text:
                    return
                var_name = text.decode("utf8")
                containing_func = self._find_containing_func(node, def_map)
                refs.append(
                    VariableReference(
                        var_name=var_name,
                        line=name_node.start_point[0],
                        func_id=containing_func.id if containing_func else None,
                        is_definition=True,
                    )
                )

        # Check for identifiers (variable uses)
        elif node.type == "identifier":
            text = node.text
            if not text:
                return
            var_name = text.decode("utf8")
            containing_func = self._find_containing_func(node, def_map)

            # Check if this is an assignment
            is_mutation = False
            if node.parent and node.parent.type == "assignment_expression":
                left = node.parent.child_by_field_name("left")
                if left and left.id == node.id:
                    is_mutation = True

            if containing_func:
                refs.append(
                    VariableReference(
                        var_name=var_name,
                        line=node.start_point[0],
                        func_id=containing_func.id,
                        is_definition=False,
                        is_mutation=is_mutation,
                    )
                )

        # Recurse on children
        for child in node.children:
            self._walk_typescript_tree(child, refs, def_map)

    def _find_containing_func(
        self, node: Node, def_map: Dict[Tuple[int, int], GraphNode]
    ) -> Optional[GraphNode]:
        """Find the function that contains this node."""
        current = node.parent
        while current:
            line_range = (current.start_point[0], current.end_point[0])
            if line_range in def_map:
                return def_map[line_range]
            current = current.parent
        return None
