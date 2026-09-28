from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from pathlib import Path
from typing import Union
import uuid
import os

class QdrantCodeIntelAdapter:
    """
    Adapter for Qdrant (Hyper-Scale Codebase Indexing).
    Replaces brute-force grep_search for massive repositories by leveraging local vector search.
    """
    
    def __init__(self, storage_path: Union[Path, str]):
        self.storage_path = (Path(storage_path) / "qdrant_db").resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize local Qdrant instance
        self.client = QdrantClient(path=self.storage_path.as_posix())
        self.collection_name = "antigravity_code_intel"
        
        self._init_collection()

    def _init_collection(self):
        """Creates the code intel collection if it does not exist."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE) # Default size for MiniLM
            )
            print(f"[*] Qdrant Collection '{self.collection_name}' created at {self.storage_path}")

    def index_code_snippet(self, file_path: Union[str, Path], snippet: str, vector: list):
        """Indexes a parsed AST code snippet into Qdrant for semantic retrieval."""
        norm_path = Path(file_path).as_posix()
        point_id = str(uuid.uuid4())
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "file_path": norm_path,
                        "content": snippet
                    }
                )
            ]
        )

    def semantic_search(self, query_vector: list, limit: int = 5):
        """Searches the codebase structurally without naive string matching."""
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit
        )
        return [{"file": hit.payload["file_path"], "score": hit.score} for hit in results]

if __name__ == "__main__":
    adapter = QdrantCodeIntelAdapter(Path.cwd())
    print("[*] Qdrant Local Engine Ready.")
