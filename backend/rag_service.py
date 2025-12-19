from groq import Groq
import os
import re
from datetime import datetime
from typing import Dict, Optional

class RAGService:
    def __init__(self, qdrant_service):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY must be set in environment variables")
        
        self.client = Groq(api_key=self.groq_api_key)
        self.qdrant_service = qdrant_service
        
        # Date extraction patterns
        self.date_patterns = [
            r'(?:on\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*(\d{1,2})(?:st|nd|rd|th)?\s+(\w+),?\s+(\d{4})',
            r'(\d{1,2})(?:st|nd|rd|th)\s+(\w+),?\s+(\d{4})',
            r'(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})'
        ]
        
        self.months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
    
    def extract_date_from_query(self, query: str) -> Optional[datetime]:
        """Extract date from user query using regex"""
        for pattern in self.date_patterns:
            matches = re.search(pattern, query, re.IGNORECASE)
            if matches:
                groups = matches.groups()
                
                try:
                    # Handle different pattern formats
                    if len(groups) == 3:
                        if groups[1].isalpha():  # Day, Month, Year
                            day = int(groups[0])
                            month_name = groups[1].lower()
                            year = int(groups[2])
                        else:  # Month, Day, Year
                            month_name = groups[0].lower()
                            day = int(groups[1])
                            year = int(groups[2])
                        
                        month = self.months.get(month_name)
                        if month:
                            return datetime(year, month, day)
                except (ValueError, KeyError):
                    continue
        
        return None
    
    def generate_summary(self, meeting_text: str, meeting_date: datetime) -> str:
        """Generate meeting summary using Groq"""
        # Use first 2000 words for summary
        words = meeting_text.split()[:2000]
        truncated_text = " ".join(words)
        
        prompt = f"""You are summarizing a meeting that took place on {meeting_date.strftime('%A %d%s %B, %Y').replace(meeting_date.strftime('%d'), meeting_date.strftime('%d') + ('th' if 11 <= meeting_date.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(meeting_date.day % 10, 'th')))}.

Please provide a concise summary (150-200 words) covering:
1. Main topics discussed
2. Key decisions made
3. Important action items
4. Notable attendees (if mentioned)

Meeting content:
{truncated_text}

Provide only the summary without any preamble."""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a professional meeting summarizer. Provide clear, concise summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating summary: {e}")
            return "Summary generation failed. Please try re-uploading the document."
    
    def query(self, user_query: str, max_words: int = 300) -> Dict:
        """Process user query and generate response"""
        # Extract date from query
        query_date = self.extract_date_from_query(user_query)
        
        # If no date specified, get most recent meeting
        if not query_date:
            query_date = self.qdrant_service.get_most_recent_meeting_date()
        
        if not query_date:
            return {
                "answer": "No meeting minutes are available in the system yet. Please contact an administrator to upload meeting minutes.",
                "meeting_date": None,
                "meeting_date_formatted": None,
                "sources": []
            }
        
        # Search for relevant chunks
        relevant_chunks = self.qdrant_service.search_relevant_chunks(
            query=user_query,
            meeting_date=query_date,
            top_k=5
        )
        
        if not relevant_chunks:
            return {
                "answer": f"No information found for the meeting on {query_date.strftime('%A %d%s %B, %Y').replace(query_date.strftime('%d'), query_date.strftime('%d') + ('th' if 11 <= query_date.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(query_date.day % 10, 'th')))}. Please verify the date or try a different query.",
                "meeting_date": query_date.isoformat(),
                "meeting_date_formatted": relevant_chunks[0]["meeting_date_formatted"] if relevant_chunks else None,
                "sources": []
            }
        
        # Combine context from relevant chunks
        context = "\n\n".join([f"[Excerpt {i+1}]: {chunk['text']}" for i, chunk in enumerate(relevant_chunks)])
        
        # Build prompt for Groq
        prompt = f"""You are an AI assistant helping users understand meeting minutes.

Meeting Date: {relevant_chunks[0]['meeting_date_formatted']}

User Question: {user_query}

Relevant excerpts from the meeting minutes:
{context}

Instructions:
1. Answer the question based ONLY on the provided excerpts
2. Be specific and include relevant details (names, numbers, decisions)
3. Keep your answer to approximately {max_words} words
4. If the excerpts don't contain enough information to answer fully, say so
5. Do not make up information not present in the excerpts

Provide a clear, direct answer:"""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions about meeting minutes accurately and concisely."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=max_words * 2  # Rough token estimate
            )
            
            answer = response.choices[0].message.content.strip()
            
            return {
                "answer": answer,
                "meeting_date": query_date.isoformat(),
                "meeting_date_formatted": relevant_chunks[0]["meeting_date_formatted"],
                "sources": relevant_chunks
            }
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return {
                "answer": f"An error occurred while processing your query: {str(e)}",
                "meeting_date": query_date.isoformat(),
                "meeting_date_formatted": relevant_chunks[0]["meeting_date_formatted"] if relevant_chunks else None,
                "sources": relevant_chunks
            }