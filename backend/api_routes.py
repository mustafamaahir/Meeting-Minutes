# api_routes.py

from fastapi import UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import tempfile
import os
from pdf_processor import PDFProcessor
from qdrant_service import QdrantService
from rag_service import RAGService
from fastapi_main import app, get_current_user, require_role
from database import get_db
from model import (
    User,
    UserRole,
    MeetingMinute,
    QueryLog
)

# Initialize services
pdf_processor = PDFProcessor()
qdrant_service = QdrantService()
rag_service = RAGService(qdrant_service)

@app.post("/upload")
async def upload_meeting_minutes(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.secretary])),
    db: Session = Depends(get_db)
):
    """Upload meeting minutes PDF (admin/secretary only)"""
    
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        # Process PDF
        result = pdf_processor.process_pdf(tmp_path)
        
        # Check if meeting already exists
        existing = db.query(MeetingMinute).filter(
            MeetingMinute.meeting_date == result['meeting_date']
        ).first()
        
        if existing:
            # Update existing meeting
            meeting_record = existing
            # Delete old vectors
            qdrant_service.delete_meeting(meeting_record.qdrant_collection)
        else:
            # Create new meeting record
            meeting_record = MeetingMinute(
                meeting_date=result['meeting_date'],
                filename=file.filename,
                uploaded_by=current_user.id,
                qdrant_collection=""  # Will be updated below
            )
            db.add(meeting_record)
            db.commit()
            db.refresh(meeting_record)
        
        # Store in Qdrant
        meeting_id = qdrant_service.store_meeting_chunks(
            chunks=result['chunks'],
            meeting_date=result['meeting_date'],
            filename=file.filename,
            meeting_db_id=meeting_record.id
        )
        
        # Generate summary
        summary = rag_service.generate_summary(
            meeting_text=result['processed_text'],
            meeting_date=result['meeting_date']
        )
        
        # Update meeting record
        meeting_record.qdrant_collection = meeting_id
        meeting_record.summary = summary
        meeting_record.filename = file.filename
        meeting_record.uploaded_at = datetime.utcnow()
        db.commit()
        
        # Cleanup temp file
        os.unlink(tmp_path)
        
        return {
            "message": "Meeting minutes uploaded successfully",
            "meeting_id": meeting_record.id,
            "meeting_date": result['meeting_date'].strftime("%A %d %B, %Y"),
            "total_chunks": result['total_chunks'],
            "summary": summary
        }
        
    except ValueError as e:
        if 'tmp_path' in locals():
            os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if 'tmp_path' in locals():
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/query")
async def query_minutes(
    query: str = Form(...),
    max_words: int = Form(300),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Query meeting minutes (authenticated users only)"""
    
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Validate max_words
    if max_words < 50 or max_words > 1000:
        raise HTTPException(status_code=400, detail="max_words must be between 50 and 1000")
    
    try:
        # Get response from RAG
        result = rag_service.query(
            user_query=query,
            max_words=max_words
        )
        
        # Log query
        query_log = QueryLog(
            user_id=current_user.id,
            query=query,
            meeting_date_queried=datetime.fromisoformat(result['meeting_date']) if result['meeting_date'] else None
        )
        db.add(query_log)
        db.commit()
        
        return {
            "answer": result['answer'],
            "meeting_date": result.get('meeting_date_formatted'),
            "sources_count": len(result['sources']),
            "sources": result['sources']  # Include for debugging/transparency
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/meetings")
async def list_meetings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all available meetings"""
    
    meetings = db.query(MeetingMinute).order_by(MeetingMinute.meeting_date.desc()).all()
    
    return {
        "meetings": [
            {
                "id": m.id,
                "date": m.meeting_date.strftime("%A %d %B, %Y"),
                "filename": m.filename,
                "uploaded_at": m.uploaded_at.isoformat()
            }
            for m in meetings
        ]
    }

@app.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: int,
    current_user: User = Depends(require_role([UserRole.admin])),
    db: Session = Depends(get_db)
):
    """Delete a meeting (admin only)"""
    
    meeting = db.query(MeetingMinute).filter(MeetingMinute.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    # Delete from Qdrant
    qdrant_service.delete_meeting(meeting.qdrant_collection)
    
    # Delete from DB
    db.delete(meeting)
    db.commit()
    
    return {"message": "Meeting deleted successfully"}

@app.get("/admin/query-logs")
async def get_query_logs(
    limit: int = 50,
    current_user: User = Depends(require_role([UserRole.admin])),
    db: Session = Depends(get_db)
):
    """Get recent query logs (admin only)"""
    
    logs = db.query(QueryLog).order_by(QueryLog.timestamp.desc()).limit(limit).all()
    
    return {
        "logs": [
            {
                "user_id": log.user_id,
                "query": log.query,
                "timestamp": log.timestamp.isoformat(),
                "meeting_date_queried": log.meeting_date_queried.strftime("%Y-%m-%d") if log.meeting_date_queried else None
            }
            for log in logs
        ]
    }