from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import get_db, engine, Base
from model import User, UserRole, MeetingMinute
from auth import create_access_token, hash_password, verify_password, get_current_user

load_dotenv()

# Create tables
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Meeting Minutes RAG System")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
@app.get("/")
async def root():
    return {"message": "Meeting Minutes RAG API", "status": "active"}

@app.post("/auth/register")
async def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    db: Session = Depends(get_db)
):
    """Register a new user"""
    # Check if user exists
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Validate role
    try:
        user_role = UserRole[role]
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid role. Must be: admin, secretary, or user")
    
    # Create user
    hashed_password = hash_password(password)
    new_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=user_role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully", "user_id": new_user.id}

@app.post("/auth/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Login and get access token"""
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"user_id": user.id, "role": user.role.value})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value
    }

@app.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role.value
    }

@app.get("/summary/latest")
async def get_latest_summary(db: Session = Depends(get_db)):
    """Public endpoint - Get latest meeting summary (no auth required)"""
    latest = db.query(MeetingMinute).order_by(MeetingMinute.meeting_date.desc()).first()
    if not latest:
        return {"summary": "No meeting minutes available yet."}
    
    # Format date with ordinal suffix
    day = latest.meeting_date.day
    if 11 <= day <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    
    formatted_date = latest.meeting_date.strftime(f"%A %d{suffix} %B, %Y")
    
    return {
        "meeting_date": formatted_date,
        "summary": latest.summary
    }

# Import and include API routes
from api_routes import router as api_router
app.include_router(api_router)