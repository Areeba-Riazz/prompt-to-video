import chromadb
from chromadb.config import Settings
import os

class MemoryManager:
    """
    Manages persistent memory using ChromaDB.
    Supports storing script history and character metadata for identity consistency.
    """
    def __init__(self, persist_directory: str = "memory/db"):
        if not os.path.exists(persist_directory):
            os.makedirs(persist_directory)
            
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # Initialize collections
        self.script_history = self.client.get_or_create_collection("script_history")
        self.character_db = self.client.get_or_create_collection("character_db")

    def store_script(self, script_id: str, content: str, metadata: dict = None):
        self.script_history.upsert(
            ids=[script_id],
            documents=[content],
            metadatas=[metadata] if metadata else [{}]
        )

    def store_character(self, character_name: str, description: str, traits: dict = None):
        self.character_db.upsert(
            ids=[character_name],
            documents=[description],
            metadatas=[traits] if traits else [{}]
        )

    def query_characters(self, query_text: str, n_results: int = 3):
        return self.character_db.query(
            query_texts=[query_text],
            n_results=n_results
        )

# Global manager instance
memory_manager = MemoryManager()
