"""Unit tests for language classification."""

from pathlib import Path


from kb.ingest.lang import classify_language


class TestClassifyLanguage:
    """Test language classification from file paths."""

    def test_python_extensions(self):
        """Test Python file extensions are correctly classified."""
        assert classify_language(Path("test.py")) == (".py", "python")
        assert classify_language(Path("script.pyw")) == (".pyw", "python")
        assert classify_language(Path("stubs.pyi")) == (".pyi", "python")

    def test_typescript_extensions(self):
        """Test TypeScript file extensions."""
        assert classify_language(Path("component.ts")) == (".ts", "typescript")
        assert classify_language(Path("app.tsx")) == (".tsx", "typescriptreact")
        assert classify_language(Path("module.mts")) == (".mts", "typescript")
        assert classify_language(Path("config.cts")) == (".cts", "typescript")

    def test_javascript_extensions(self):
        """Test JavaScript file extensions."""
        assert classify_language(Path("app.js")) == (".js", "javascript")
        assert classify_language(Path("component.jsx")) == (".jsx", "javascriptreact")
        assert classify_language(Path("common.cjs")) == (".cjs", "javascript")
        assert classify_language(Path("module.mjs")) == (".mjs", "javascript")

    def test_markdown_extensions(self):
        """Test Markdown file extensions."""
        assert classify_language(Path("README.md")) == (".md", "markdown")
        assert classify_language(Path("doc.markdown")) == (".markdown", "markdown")
        assert classify_language(Path("react.mdx")) == (".mdx", "markdown")

    def test_config_file_extensions(self):
        """Test configuration file extensions."""
        assert classify_language(Path("config.json")) == (".json", "json")
        assert classify_language(Path("data.yml")) == (".yml", "yaml")
        assert classify_language(Path("config.yaml")) == (".yaml", "yaml")
        assert classify_language(Path("pyproject.toml")) == (".toml", "toml")

    def test_shell_script_extensions(self):
        """Test shell script extensions."""
        assert classify_language(Path("run.sh")) == (".sh", "shell")
        assert classify_language(Path("setup.bash")) == (".bash", "shell")
        assert classify_language(Path("profile.zsh")) == (".zsh", "shell")

    def test_special_filenames_without_extension(self):
        """Test special filenames without extensions."""
        assert classify_language(Path("Justfile")) == (None, "just")
        assert classify_language(Path("README")) == (None, "text")
        assert classify_language(Path("LICENSE")) == (None, "text")
        assert classify_language(Path("Makefile")) == (None, "text")
        assert classify_language(Path("Dockerfile")) == (None, "text")

    def test_just_extension(self):
        """Test that .just extension works."""
        assert classify_language(Path("build.just")) == (".just", "just")

    def test_svelte_extension(self):
        """Test Svelte component extension."""
        assert classify_language(Path("App.svelte")) == (".svelte", "svelte")

    def test_text_extension(self):
        """Test plain text extension."""
        assert classify_language(Path("notes.txt")) == (".txt", "text")

    def test_unknown_extension_defaults_to_text(self):
        """Test that unknown extensions default to 'text'."""
        ext, lang = classify_language(Path("file.xyz"))
        assert ext == ".xyz"
        assert lang == "text"

    def test_no_extension_defaults_to_text(self):
        """Test files without extension (not special) default to text."""
        ext, lang = classify_language(Path("randomfile"))
        assert ext is None
        assert lang == "text"

    def test_case_insensitive_extensions(self):
        """Test that extensions are case-insensitive."""
        assert classify_language(Path("Test.PY")) == (".py", "python")
        assert classify_language(Path("App.TS")) == (".ts", "typescript")
        assert classify_language(Path("Config.JSON")) == (".json", "json")
        assert classify_language(Path("README.MD")) == (".md", "markdown")

    def test_special_filename_is_case_sensitive(self):
        """Test that special filenames are case-sensitive."""
        # Justfile is special, justfile is not
        assert classify_language(Path("Justfile")) == (None, "just")
        ext, lang = classify_language(Path("justfile"))
        assert ext is None
        assert lang == "text"

    def test_path_with_directories(self):
        """Test that directory paths don't affect classification."""
        assert classify_language(Path("/path/to/file.py")) == (".py", "python")
        assert classify_language(Path("./src/components/App.tsx")) == (
            ".tsx",
            "typescriptreact",
        )
        assert classify_language(Path("../utils/helper.js")) == (".js", "javascript")

    def test_multiple_dots_in_filename(self):
        """Test files with multiple dots use only the last extension."""
        assert classify_language(Path("test.spec.ts")) == (".ts", "typescript")
        assert classify_language(Path("config.local.json")) == (".json", "json")
        assert classify_language(Path("archive.tar.gz")) == (".gz", "text")

    def test_hidden_files_with_extension(self):
        """Test hidden files (starting with dot) are classified by extension."""
        assert classify_language(Path(".gitignore")) == (None, "text")
        assert classify_language(Path(".env")) == (None, "text")
        # Hidden file with recognized extension
        ext, lang = classify_language(Path(".test.py"))
        assert ext == ".py"
        assert lang == "python"

    def test_all_python_variations(self):
        """Test all Python file variations."""
        python_files = ["script.py", "test.pyw", "types.pyi"]
        for f in python_files:
            ext, lang = classify_language(Path(f))
            assert lang == "python", f"Failed for {f}"

    def test_all_typescript_variations(self):
        """Test all TypeScript file variations."""
        ts_files = [
            ("app.ts", "typescript"),
            ("component.tsx", "typescriptreact"),
            ("module.mts", "typescript"),
            ("config.cts", "typescript"),
        ]
        for filename, expected_lang in ts_files:
            ext, lang = classify_language(Path(filename))
            assert lang == expected_lang, f"Failed for {filename}"

    def test_all_javascript_variations(self):
        """Test all JavaScript file variations."""
        js_files = [
            ("app.js", "javascript"),
            ("component.jsx", "javascriptreact"),
            ("common.cjs", "javascript"),
            ("module.mjs", "javascript"),
        ]
        for filename, expected_lang in js_files:
            ext, lang = classify_language(Path(filename))
            assert lang == expected_lang, f"Failed for {filename}"

    def test_all_yaml_variations(self):
        """Test all YAML file variations."""
        assert classify_language(Path("config.yml")) == (".yml", "yaml")
        assert classify_language(Path("docker-compose.yaml")) == (".yaml", "yaml")

    def test_all_markdown_variations(self):
        """Test all Markdown file variations."""
        md_files = ["README.md", "doc.markdown", "blog.mdx"]
        for f in md_files:
            ext, lang = classify_language(Path(f))
            assert lang == "markdown", f"Failed for {f}"

    def test_all_shell_variations(self):
        """Test all shell script variations."""
        shell_files = ["run.sh", "setup.bash", "profile.zsh"]
        for f in shell_files:
            ext, lang = classify_language(Path(f))
            assert lang == "shell", f"Failed for {f}"

    def test_special_filenames_comprehensive(self):
        """Test all special filenames."""
        special_files = {
            "Justfile": "just",
            "README": "text",
            "LICENSE": "text",
            "Makefile": "text",
            "Dockerfile": "text",
        }
        for filename, expected_lang in special_files.items():
            ext, lang = classify_language(Path(filename))
            assert ext is None, f"Expected no extension for {filename}"
            assert lang == expected_lang, f"Failed for {filename}"

    def test_edge_case_empty_filename(self):
        """Test edge case with empty string (should not crash)."""
        # Path("") creates a Path('.'), which has no suffix
        ext, lang = classify_language(Path(""))
        assert ext is None
        assert lang == "text"

    def test_edge_case_only_extension(self):
        """Test file that is only an extension like '.py'."""
        # This is technically a hidden file with no extension
        ext, lang = classify_language(Path(".py"))
        assert ext is None
        assert lang == "text"

    def test_consistency_with_and_without_path(self):
        """Test that classification is consistent regardless of path depth."""
        filenames = ["test.py", "./test.py", "/absolute/path/test.py", "../../test.py"]
        results = [classify_language(Path(f)) for f in filenames]

        # All should give same result
        assert all(r == (".py", "python") for r in results)

    def test_return_type_tuple(self):
        """Test that return value is always a tuple of (ext, lang)."""
        result = classify_language(Path("test.py"))
        assert isinstance(result, tuple)
        assert len(result) == 2
        ext, lang = result
        assert isinstance(ext, str) or ext is None
        assert isinstance(lang, str)
