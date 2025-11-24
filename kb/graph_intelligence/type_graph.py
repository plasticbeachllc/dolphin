"""Type relationship extraction for inheritance and interfaces."""

import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node

from .models import EdgeType, GraphEdge, GraphNode, NodeType


class TypeGraphExtractor:
    """Extracts type relationships like inheritance and interface implementation."""

    def __init__(self):
        self.python_language = Language(tspython.language())
        self.typescript_language = Language(tsts.language_typescript())

    def extract_type_relationships_python(
        self,
        tree_root: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        existing_classes: list[GraphNode],
    ) -> list[GraphEdge]:
        """Extract Python inheritance relationships."""
        edges = []

        # Query for class definitions with inheritance
        inheritance_query = self.python_language.query(
            """
            (class_definition
                name: (identifier) @class_name
                superclasses: (argument_list) @bases)
        """
        )

        captures = inheritance_query.captures(tree_root)  # type: ignore[attr-defined]

        # Process captures in pairs (class_name, bases)
        for i in range(0, len(captures), 2):
            if i + 1 >= len(captures):
                break

            class_node_ast, class_capture = captures[i]
            bases_node_ast, bases_capture = captures[i + 1]

            if class_capture == "class_name" and bases_capture == "bases":
                class_name = class_node_ast.text.decode("utf8")

                # Find the GraphNode for this class
                source_class = next(
                    (cls for cls in existing_classes if cls.name == class_name and cls.file_path == file_path),
                    None,
                )

                if not source_class:
                    continue

                # Extract base class names
                base_classes = self._extract_python_bases(bases_node_ast)

                for base_class_name in base_classes:
                    # Try to find the base class in existing classes
                    target_class = next(
                        (cls for cls in existing_classes if cls.name == base_class_name),
                        None,
                    )

                    if target_class:
                        edges.append(
                            GraphEdge(
                                source_id=source_class.id,
                                target_id=target_class.id,
                                edge_type=EdgeType.INHERITS,
                                repo_id=repo_id,
                                attributes={
                                    "base_class": base_class_name,
                                    "commit_sha": commit_sha,
                                },
                            )
                        )

        return edges

    def extract_type_relationships_typescript(
        self,
        tree_root: Node,
        file_path: str,
        repo_id: int,
        file_id: int,
        commit_sha: str,
        existing_classes: list[GraphNode],
    ) -> list[GraphEdge]:
        """Extract TypeScript inheritance and interface implementation."""
        edges = []

        # Query for class inheritance
        class_query = self.typescript_language.query(
            """
            (class_declaration
                name: (type_identifier) @class_name
                (class_heritage
                    (extends_clause
                        value: (identifier) @extends_class)))

            (class_declaration
                name: (type_identifier) @class_name2
                (class_heritage
                    (implements_clause
                        (type_identifier) @implements_interface)))
        """
        )

        captures = class_query.captures(tree_root)  # type: ignore[attr-defined]

        # Track which class we're currently processing
        current_class_name = None
        current_class_node = None

        for node, capture_name in captures:
            if capture_name in ("class_name", "class_name2"):
                current_class_name = node.text.decode("utf8")
                # Find the GraphNode for this class
                current_class_node = next(
                    (cls for cls in existing_classes if cls.name == current_class_name and cls.file_path == file_path),
                    None,
                )

            elif capture_name == "extends_class" and current_class_node:
                parent_class_name = node.text.decode("utf8")

                # Try to find the parent class
                parent_class = next(
                    (cls for cls in existing_classes if cls.name == parent_class_name),
                    None,
                )

                if parent_class:
                    edges.append(
                        GraphEdge(
                            source_id=current_class_node.id,
                            target_id=parent_class.id,
                            edge_type=EdgeType.INHERITS,
                            repo_id=repo_id,
                            attributes={
                                "parent_class": parent_class_name,
                                "commit_sha": commit_sha,
                            },
                        )
                    )

            elif capture_name == "implements_interface" and current_class_node:
                interface_name = node.text.decode("utf8")

                # Try to find the interface
                interface_node = next(
                    (cls for cls in existing_classes if cls.name == interface_name and cls.node_type == NodeType.CLASS),
                    None,
                )

                if interface_node:
                    edges.append(
                        GraphEdge(
                            source_id=current_class_node.id,
                            target_id=interface_node.id,
                            edge_type=EdgeType.IMPLEMENTS,
                            repo_id=repo_id,
                            attributes={
                                "interface": interface_name,
                                "commit_sha": commit_sha,
                            },
                        )
                    )

        return edges

    def _extract_python_bases(self, bases_node: Node) -> list[str]:
        """Extract base class names from Python argument list."""
        base_classes = []

        for child in bases_node.children:
            if child.type == "identifier":
                text = child.text
                if text:
                    base_classes.append(text.decode("utf8"))
            elif child.type == "attribute":
                # Handle qualified names like module.ClassName
                text = child.text
                if text:
                    base_classes.append(text.decode("utf8"))

        return base_classes
