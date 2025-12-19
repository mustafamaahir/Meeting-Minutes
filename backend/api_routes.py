from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import tempfile
import os

from database import get_db
from model import User, UserRole, MeetingMinute, QueryLog
from auth import get_current_user, require_role

# Import services
from pdf_processor import PDFProcessor
from qdrant_service import QdrantService
from rag_service import RAGService

# Create router
router = APIRouter()

# Initialize services (singleton pattern)
pdf_processor = PDFProcessor()
qdrant_service = QdrantService()
rag_service = RAGService(qdrant_service)

@router.post("/upload")
async def upload_meeting_minutes(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.secretary])),
    db: Session = Depends(get_db)
):
    """Upload meeting minutes PDF (admin/secretary only)"""
    
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    tmp_path = None
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        # Process PDF using PDFProcessor
        result = pdf_processor.process_pdf(tmp_path)
        
        # Check if meeting already exists
        existing = db.query(MeetingMinute).filter(
            MeetingMinute.meeting_date == result['meeting_date']
        ).first()
        
        if existing:
            # Update existing meeting
            meeting_record = existing
            # Delete old vectors from Qdrant
            try:
                qdrant_service.delete_meeting(meeting_record.qdrant_collection)
            except Exception as e:
                print(f"Warning: Failed to delete old vectors: {e}")
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
        
        # Store chunks in Qdrant using QdrantService
        meeting_id = qdrant_service.store_meeting_chunks(
            chunks=result['chunks'],
            meeting_date=result['meeting_date'],
            filename=file.filename,
            meeting_db_id=meeting_record.id
        )
        
        # Generate summary using RAGService
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
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        
        # Format date with ordinal suffix
        day = result['meeting_date'].day
        if 11 <= day <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        
        formatted_date = result['meeting_date'].strftime(f"%A %d{suffix} %B, %Y")
        
        return {
            "message": "Meeting minutes uploaded successfully",
            "meeting_id": meeting_record.id,
            "meeting_date": formatted_date,
            "total_chunks": result['total_chunks'],
            "summary": summary
        }
        
    except ValueError as e:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/query")
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
        # Get response from RAGService
        result = rag_service.query(
            user_query=query,
            max_words=max_words
        )
        
        # Log query to database
        meeting_date_queried = None
        if result['meeting_date']:
            try:
                meeting_date_queried = datetime.fromisoformat(result['meeting_date'])
            except (ValueError, TypeError):
                pass
        
        query_log = QueryLog(
            user_id=current_user.id,
            query=query,
            meeting_date_queried=meeting_date_queried
        )
        db.add(query_log)
        db.commit()
        
        return {
            "answer": result['answer'],
            "meeting_date": result.get('meeting_date_formatted'),
            "sources_count": len(result['sources']),
            "sources": result['sources']
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@router.get("/meetings")
async def list_meetings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all available meetings"""
    
    meetings = db.query(MeetingMinute).order_by(MeetingMinute.meeting_date.desc()).all()
    
    meeting_list = []
    for m in meetings:
        # Format date with ordinal suffix
        day = m.meeting_date.day
        if 11 <= day <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        
        formatted_date = m.meeting_date.strftime(f"%A %d{suffix} %B, %Y")
        
        meeting_list.append({
            "id": m.id,
            "date": formatted_date,
            "filename": m.filename,
            "uploaded_at": m.uploaded_at.isoformat()
        })
    
    return {"meetings": meeting_list}

@router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: int,
    current_user: User = Depends(require_role([UserRole.admin])),
    db: Session = Depends(get_db)
):
    """Delete a meeting (admin only)"""
    
    meeting = db.query(MeetingMinute).filter(MeetingMinute.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    # Delete from Qdrant using QdrantService
    try:
        qdrant_service.delete_meeting(meeting.qdrant_collection)
    except Exception as e:
        print(f"Warning: Failed to delete from Qdrant: {e}")
        # Continue with DB deletion even if Qdrant deletion fails
    
    # Delete from DB
    db.delete(meeting)
    db.commit()
    
    return {"message": "Meeting deleted successfully"}

@router.get("/admin/query-logs")
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