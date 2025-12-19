from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import os
import requests
from typing import List, Dict
from datetime import datetime

class QdrantService:
    def __init__(self):
        # Initialize Qdrant Cloud client
        self.qdrant_url = os.getenv("QDRANT_URL")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY")
        
        if not self.qdrant_url or not self.qdrant_api_key:
            raise ValueError("QDRANT_URL and QDRANT_API_KEY must be set in environment variables")
        
        self.client = QdrantClient(
            url=self.qdrant_url,
            api_key=self.qdrant_api_key,
        )
        
        # Use HuggingFace Inference API for embeddings
        self.hf_api_token = os.getenv("HF_API_TOKEN", "")
        self.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.vector_size = 384  # Dimension for all-MiniLM-L6-v2
        
        # Collection name
        self.collection_name = "meeting_minutes"
        
        # Ensure collection exists
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist"""
        try:
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                print(f"Created collection: {self.collection_name}")
        except Exception as e:
            print(f"Error ensuring collection: {e}")
            raise
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using HuggingFace Inference API"""
    
        api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.embedding_model}"
        
        headers = {}
        if self.hf_api_token:
            headers["Authorization"] = f"Bearer {self.hf_api_token}"
        
        try:
            response = requests.post(
                api_url,
                headers=headers,
                json={"inputs": text, "options": {"wait_for_model": True}}
            )
            response.raise_for_status()
            embedding = response.json()
            
            if isinstance(embedding, list) and len(embedding) > 0:
                if isinstance(embedding[0], list):
                    embedding = embedding[0]
            
            return embedding
        except Exception as e:
            print(f"Error generating embedding: {e}")
            # Fallback to zero vector if API fails
            return [0.0] * self.vector_size
    
    def store_meeting_chunks(
        self, 
        chunks: List[str], 
        meeting_date: datetime, 
        filename: str,
        meeting_db_id: int
    ) -> str:
        """Store meeting chunks in Qdrant with embeddings"""
        points = []
        
        for idx, chunk in enumerate(chunks):
            # Generate embedding
            embedding = self.generate_embedding(chunk)
            
            # Create point
            point = PointStruct(
                id=f"{meeting_db_id}_{idx}", 
                vector=embedding,
                payload={
                    "text": chunk,
                    "meeting_date": meeting_date.isoformat(),
                    "meeting_date_formatted": meeting_date.strftime("%A %d%s %B, %Y").replace(
                        meeting_date.strftime("%d"),
                        meeting_date.strftime("%d") + (
                            "th" if 11 <= meeting_date.day <= 13 
                            else {1: "st", 2: "nd", 3: "rd"}.get(meeting_date.day % 10, "th")
                        )
                    ),
                    "filename": filename,
                    "chunk_index": idx,
                    "meeting_db_id": meeting_db_id
                }
            )
            points.append(point)
        
        # Upload points to Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        
        return f"meeting_{meeting_db_id}"
    
    def search_relevant_chunks(
        self, 
        query: str, 
        meeting_date: datetime = None,
        top_k: int = 5
    ) -> List[Dict]:
        """Search for relevant chunks"""
        # Generate query embedding
        query_embedding = self.generate_embedding(query)
        
        # Build filter if date specified
        search_filter = None
        if meeting_date:
            search_filter = {
                "must": [
                    {
                        "key": "meeting_date",
                        "match": {"value": meeting_date.isoformat()}
                    }
                ]
            }
        
        # Search
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=search_filter
        )
        
        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "text": result.payload.get("text"),
                "meeting_date": result.payload.get("meeting_date"),
                "meeting_date_formatted": result.payload.get("meeting_date_formatted"),
                "score": result.score,
                "chunk_index": result.payload.get("chunk_index")
            })
        
        return formatted_results
    
    def delete_meeting(self, meeting_id: str):
        """Delete all chunks for a specific meeting"""
        # Extract meeting_db_id from meeting_id
        try:
            meeting_db_id = int(meeting_id.replace("meeting_", ""))
            
            # Delete all points with this meeting_db_id
            self.client.delete(
                collection_name=self.collection_name,
                points_selector={
                    "filter": {
                        "must": [
                            {
                                "key": "meeting_db_id",
                                "match": {"value": meeting_db_id}
                            }
                        ]
                    }
                }
            )
            print(f"Deleted meeting chunks for meeting_db_id: {meeting_db_id}")
        except Exception as e:
            print(f"Error deleting meeting: {e}")
            raise
    
    def get_most_recent_meeting_date(self) -> datetime:
        """Get the most recent meeting date from stored vectors"""
        # Search for any vector to get recent dates
        dummy_query = self.generate_embedding("meeting")
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=dummy_query,
            limit=1
        )
        
        if results:
            return datetime.fromisoformat(results[0].payload.get("meeting_date"))
        
        return None