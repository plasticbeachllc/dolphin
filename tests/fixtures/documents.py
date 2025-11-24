"""Test document fixtures for ingestion and search tests."""

DOCUMENT_FIXTURES = [
    {
        "path": "src/main.py",
        "content": 'def hello_world():\n    print("Hello, Python!")',
    },
    {
        "path": "src/utils.py",
        "content": 'def goodbye():\n    print("Goodbye, Python!")',
    },
    {
        "path": "src/script.js",
        "content": 'function hello() {\n    console.log("Hello, JavaScript!");\n}',
    },
]
