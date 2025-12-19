import pdfplumber
import re
from datetime import datetime
from typing import List, Dict, Optional

class PDFProcessor:
    def __init__(self):
        self.date_patterns = [
            r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)\s+(\w+),?\s+(\d{4})',
            r'(\d{1,2})(?:st|nd|rd|th)\s+(\w+),?\s+(\d{4})',
            r'(\w+)\s+(\d{1,2})(?:st|nd|rd|th),?\s+(\d{4})'
        ]
        
        self.months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
    
    def extract_date(self, text: str) -> Optional[datetime]:
        """Extract meeting date from text using regex patterns"""
        for pattern in self.date_patterns:
            matches = re.search(pattern, text, re.IGNORECASE)
            if matches:
                groups = matches.groups()
                
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
                        try:
                            return datetime(year, month, day)
                        except ValueError:
                            continue
        
        return None
    
    def extract_tables_as_text(self, pdf_path: str) -> str:
        """Extract tables from PDF and convert to readable text"""
        table_text = ""
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                
                for table_num, table in enumerate(tables, 1):
                    if table:
                        table_text += f"\n\n[Table {table_num} from page {page_num}]\n"
                        
                        # Convert table to text format
                        for row_idx, row in enumerate(table):
                            if row_idx == 0:  # Header row
                                table_text += " | ".join([str(cell) if cell else "" for cell in row]) + "\n"
                                table_text += "-" * 80 + "\n"
                            else:
                                table_text += " | ".join([str(cell) if cell else "" for cell in row]) + "\n"
        
        return table_text
    
    def extract_text(self, pdf_path: str) -> str:
        """Extract all text from PDF including tables"""
        full_text = ""
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Extract regular text
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n\n"
        
        # Add table content
        table_content = self.extract_tables_as_text(pdf_path)
        full_text += table_content
        
        return full_text
    
    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks"""
        chunks = []
        words = text.split()
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        
        return chunks
    
    def process_pdf(self, pdf_path: str) -> Dict:
        """Main processing function"""
        # Extract text
        full_text = self.extract_text(pdf_path)
        
        if not full_text.strip():
            raise ValueError("No text could be extracted from PDF")
        
        # Extract meeting date
        meeting_date = self.extract_date(full_text[:2000])  # Check first 2000 chars
        
        if not meeting_date:
            raise ValueError("Could not extract meeting date from PDF. Please ensure date is in format: 'Sunday 26th October, 2025'")
        
        # Create chunks
        chunks = self.chunk_text(full_text)
        
        return {
            "meeting_date": meeting_date,
            "processed_text": full_text,
            "chunks": chunks,
            "total_chunks": len(chunks)
        }