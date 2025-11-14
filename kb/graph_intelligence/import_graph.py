"""Import and dependency graph extraction."""

from typing import List, Optional
from tree_sitter import Node, Language
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from .models import GraphNode, GraphEdge, EdgeType, NodeType
import uuid


class ImportGraphExtractor:
    """Extracts import dependencies between modules."""

    def __init__(self):
        self.python_language = Language(tspython.language())
        self.typescript_language = Language(tsts.language_typescript())

    def extract_imports_python(
        self,
        tree_root: Node,
        source_file: str,
        file_id: int,
        repo_id: int,
        commit_sha: str,
        all_files: List[str],
    ) -> tuple[List[GraphNode], List[GraphEdge]]:
        """Extract Python import statements and create import edges."""
        nodes = []
        edges = []

        # Query for imports
        import_query = self.python_language.query("""
            (import_statement
                name: (dotted_name) @import_path)

            (import_from_statement
                module_name: (dotted_name) @from_module)
        """)

        captures = import_query.captures(tree_root)

        # Create a module node for this file if not exists
        module_name = source_file.replace("/", ".").replace(".py", "")
        source_module_node = GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.MODULE,
            name=module_name.split(".")[-1],
            qualified_name=module_name,
            file_path=source_file,
            start_line=0,
            end_line=0,
            language="python",
            metadata={
                "file_id": file_id,
                "commit_sha": commit_sha,
            },
        )

        for node, capture_name in captures:
            if capture_name in ("import_path", "from_module"):
                imported_module = node.text.decode("utf8")

                # Try to resolve to a file in the repo
                target_file = self._resolve_python_import(imported_module, all_files)

                if target_file:
                    # Create target module node
                    target_module_name = target_file.replace("/", ".").replace(
                        ".py", ""
                    )
                    target_module_node = GraphNode(
                        id=str(uuid.uuid4()),
                        repo_id=repo_id,
                        node_type=NodeType.MODULE,
                        name=target_module_name.split(".")[-1],
                        qualified_name=target_module_name,
                        file_path=target_file,
                        start_line=0,
                        end_line=0,
                        language="python",
                        metadata={
                            "commit_sha": commit_sha,
                        },
                    )
                    nodes.append(target_module_node)

                    # Create import edge
                    edges.append(
                        GraphEdge(
                            source_id=source_module_node.id,
                            target_id=target_module_node.id,
                            edge_type=EdgeType.IMPORTS,
                            repo_id=repo_id,
                            attributes={
                                "import_line": node.start_point[0],
                                "import_type": "from"
                                if capture_name == "from_module"
                                else "import",
                                "commit_sha": commit_sha,
                            },
                        )
                    )

        if nodes:  # Only add source module if there are imports
            nodes.insert(0, source_module_node)

        return nodes, edges

    def extract_imports_typescript(
        self,
        tree_root: Node,
        source_file: str,
        file_id: int,
        repo_id: int,
        commit_sha: str,
        all_files: List[str],
    ) -> tuple[List[GraphNode], List[GraphEdge]]:
        """Extract TypeScript/JavaScript import statements."""
        nodes = []
        edges = []

        # Query for imports
        import_query = self.typescript_language.query("""
            (import_statement
                source: (string) @import_source)
        """)

        captures = import_query.captures(tree_root)

        # Create a module node for this file
        module_name = (
            source_file.replace("/", ".")
            .replace(".ts", "")
            .replace(".tsx", "")
            .replace(".js", "")
        )
        source_module_node = GraphNode(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            node_type=NodeType.MODULE,
            name=module_name.split(".")[-1],
            qualified_name=module_name,
            file_path=source_file,
            start_line=0,
            end_line=0,
            language="typescript",
            metadata={
                "file_id": file_id,
                "commit_sha": commit_sha,
            },
        )

        for node, capture_name in captures:
            if capture_name == "import_source":
                # Remove quotes from import path
                import_path = node.text.decode("utf8").strip("\"'")

                # Try to resolve to a file in the repo
                target_file = self._resolve_typescript_import(
                    import_path, source_file, all_files
                )

                if target_file:
                    # Create target module node
                    target_module_name = (
                        target_file.replace("/", ".")
                        .replace(".ts", "")
                        .replace(".tsx", "")
                        .replace(".js", "")
                    )
                    target_module_node = GraphNode(
                        id=str(uuid.uuid4()),
                        repo_id=repo_id,
                        node_type=NodeType.MODULE,
                        name=target_module_name.split(".")[-1],
                        qualified_name=target_module_name,
                        file_path=target_file,
                        start_line=0,
                        end_line=0,
                        language="typescript",
                        metadata={
                            "commit_sha": commit_sha,
                        },
                    )
                    nodes.append(target_module_node)

                    # Create import edge
                    edges.append(
                        GraphEdge(
                            source_id=source_module_node.id,
                            target_id=target_module_node.id,
                            edge_type=EdgeType.IMPORTS,
                            repo_id=repo_id,
                            attributes={
                                "import_line": node.start_point[0],
                                "import_path": import_path,
                                "commit_sha": commit_sha,
                            },
                        )
                    )

        if nodes:  # Only add source module if there are imports
            nodes.insert(0, source_module_node)

        return nodes, edges

    def _resolve_python_import(
        self, import_path: str, all_files: List[str]
    ) -> Optional[str]:
        """Resolve a Python import path to an actual file in the repo."""
        # Convert dotted import to file path
        possible_paths = [
            import_path.replace(".", "/") + ".py",
            import_path.replace(".", "/") + "/__init__.py",
        ]

        for path in possible_paths:
            if path in all_files:
                return path

        return None

    def _resolve_typescript_import(
        self, import_path: str, source_file: str, all_files: List[str]
    ) -> Optional[str]:
        """Resolve a TypeScript import path to an actual file."""
        # Handle relative imports
        if import_path.startswith("."):
            # Get the directory of the source file
            source_dir = "/".join(source_file.split("/")[:-1])

            # Resolve relative path
            if import_path.startswith("./"):
                base_path = source_dir + "/" + import_path[2:]
            elif import_path.startswith("../"):
                # Handle going up directories
                parts = source_dir.split("/")
                up_count = import_path.count("../")
                remaining_path = import_path.replace("../", "", up_count)
                base_path = "/".join(parts[:-up_count]) + "/" + remaining_path
            else:
                base_path = import_path

            # Try various extensions
            possible_paths = [
                base_path + ".ts",
                base_path + ".tsx",
                base_path + ".js",
                base_path + "/index.ts",
                base_path + "/index.tsx",
                base_path + "/index.js",
            ]

            for path in possible_paths:
                if path in all_files:
                    return path

        return None
