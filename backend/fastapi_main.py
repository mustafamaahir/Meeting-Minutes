import api_routes
from database import get_db
from model import Base, MeetingMinute, User, UserRole 
from database import engine
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from passlib.context import CryptContext
import jwt
import os
from dotenv import load_dotenv

load_dotenv()


# Create tables
Base.metadata.create_all(bind=engine)


SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours



# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# FastAPI app
app = FastAPI(title="Meeting Minutes RAG System")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth utilities
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(token_data: dict = Depends(verify_token), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == token_data.get("user_id")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_role(allowed_roles: list):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

# Routes
@app.get("/")
async def root():
    return {"message": "Meeting Minutes RAG API", "status": "active"}

@app.post("/auth/register")
async def register(username: str, email: str, password: str, role: str = "user", db: Session = Depends(get_db)):
    # Check if user exists
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Validate role
    try:
        user_role = UserRole[role]
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    # Create user
    hashed_password = pwd_context.hash(password)
    new_user = User(username=username, email=email, hashed_password=hashed_password, role=user_role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully", "user_id": new_user.id}

@app.post("/auth/login")
async def login(username: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"user_id": user.id, "role": user.role.value})
    return {"access_token": token, "token_type": "bearer", "role": user.role.value}

@app.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role.value
    }

@app.get("/summary/latest")
async def get_latest_summary(db: Session = Depends(get_db)):
    """Public endpoint - no auth required"""
    latest = db.query(MeetingMinute).order_by(MeetingMinute.meeting_date.desc()).first()
    if not latest:
        return {"summary": "No meeting minutes available yet."}
    
    return {
        "meeting_date": latest.meeting_date.strftime("%A %d%s %B, %Y").replace(
            latest.meeting_date.strftime("%d"),
            latest.meeting_date.strftime("%d") + (
                "th" if 11 <= latest.meeting_date.day <= 13 
                else {1: "st", 2: "nd", 3: "rd"}.get(latest.meeting_date.day % 10, "th")
            )
        ),
        "summary": latest.summary
    }
    

app.include_router(api_routes.router)