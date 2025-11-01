"""pb_kb package - re-exporting from src directory for backward compatibility."""

# Re-export all submodules from src
from pb_kb.src import *

# Make submodules accessible directly
from pb_kb import src

# Alias src submodules to package root for backward compatibility
import sys
from pb_kb.src import (
    api,
    chunkers,
    embeddings,
    ingest,
    retrieval,
    store,
    config,
    hashing,
    ignores,
)

# Make these available at package level
sys.modules['pb_kb.api'] = api
sys.modules['pb_kb.chunkers'] = chunkers
sys.modules['pb_kb.embeddings'] = embeddings
sys.modules['pb_kb.ingest'] = ingest
sys.modules['pb_kb.retrieval'] = retrieval
sys.modules['pb_kb.store'] = store
sys.modules['pb_kb.config'] = config
sys.modules['pb_kb.hashing'] = hashing
sys.modules['pb_kb.ignores'] = ignores