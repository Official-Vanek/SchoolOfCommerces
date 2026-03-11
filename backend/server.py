from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import resend
import asyncio
import shutil
from twilio.rest import Client as TwilioClient
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Create uploads directory
UPLOAD_DIR = ROOT_DIR / 'uploads' / 'course_images'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get('JWT_SECRET_KEY')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

resend.api_key = os.environ.get('RESEND_API_KEY')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
ADMIN_NOTIFICATION_EMAIL = os.environ.get('ADMIN_NOTIFICATION_EMAIL', 'admin@school.com')

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

# Initialize Twilio client if credentials are provided
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
    try:
        twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("Twilio client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Twilio: {str(e)}")
else:
    logger.warning("Twilio credentials not configured - SMS will be sent via email (demo mode)")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== MODELS =====
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: str = "student"
    is_blocked: bool = False
    email_verified: bool = False
    phone_verified: bool = False
    verification_token: Optional[str] = None
    phone_otp: Optional[str] = None
    otp_expires: Optional[datetime] = None
    enrolled_courses: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "student"

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class VerifyEmailRequest(BaseModel):
    token: str

class SendPhoneOTPRequest(BaseModel):
    phone: str

class VerifyPhoneOTPRequest(BaseModel):
    phone: str
    otp: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Course(BaseModel):
    model_config = ConfigDict(extra="ignore")
    course_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    instructor: str
    duration: str
    fee: float
    thumbnail: Optional[str] = None
    lectures: List[dict] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CourseCreate(BaseModel):
    title: str
    description: str
    instructor: str
    duration: str
    fee: float
    thumbnail: Optional[str] = None

class Lecture(BaseModel):
    lecture_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    video_url: str
    description: Optional[str] = None
    duration: Optional[str] = None
    materials: List[dict] = []  # List of {name: str, url: str, type: str}

class Admission(BaseModel):
    model_config = ConfigDict(extra="ignore")
    admission_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    full_name: str
    email: EmailStr
    phone: str
    course_id: str
    message: Optional[str] = None
    status: str = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AdmissionCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    course_id: str
    message: Optional[str] = None

class Query(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    name: str
    email: EmailStr
    phone: str
    subject: str
    message: str
    status: str = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class QueryCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    subject: str
    message: str

class Result(BaseModel):
    model_config = ConfigDict(extra="ignore")
    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    course_id: str
    marks: float
    grade: str
    remarks: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ResultCreate(BaseModel):
    user_id: str
    course_id: str
    marks: float
    grade: str
    remarks: Optional[str] = None

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

class SocialGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")
    group_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: str  # whatsapp or telegram
    link: str
    is_active: bool = True

class SocialGroupCreate(BaseModel):
    name: str
    type: str
    link: str
    is_active: bool = True

class LiveClass(BaseModel):
    model_config = ConfigDict(extra="ignore")
    class_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    course_id: str
    title: str
    meeting_link: str
    scheduled_time: datetime
    duration_minutes: int
    is_live: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LiveClassCreate(BaseModel):
    course_id: str
    title: str
    meeting_link: str
    scheduled_time: str
    duration_minutes: int

# ===== UTILITIES =====
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        user = await db.users.find_one({"email": email}, {"_id": 0})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")

async def get_admin_user(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def send_email_async(recipient_email: str, subject: str, html_content: str):
    params = {
        "from": SENDER_EMAIL,
        "to": [recipient_email],
        "subject": subject,
        "html": html_content
    }
    try:
        email = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {recipient_email}")
        return email
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return None

def generate_verification_token():
    return str(uuid.uuid4())

def generate_otp():
    import random
    return str(random.randint(100000, 999999))

async def send_sms_async(phone_number: str, message: str):
    """Send SMS via Twilio or fallback to email"""
    if twilio_client:
        try:
            # Send actual SMS via Twilio
            sms = await asyncio.to_thread(
                twilio_client.messages.create,
                body=message,
                from_=TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            logger.info(f"SMS sent to {phone_number}: {sms.sid}")
            return {"success": True, "method": "sms", "sid": sms.sid}
        except Exception as e:
            logger.error(f"Failed to send SMS via Twilio: {str(e)}")
            return {"success": False, "error": str(e)}
    else:
        logger.warning(f"Twilio not configured - OTP for {phone_number} logged only")
        return {"success": False, "method": "demo", "message": "Twilio not configured"}

# ===== AUTH ROUTES =====
@api_router.post("/auth/register")
async def register(user_data: UserCreate):
    existing_user = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_data.password)
    verification_token = generate_verification_token()
    
    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        verification_token=verification_token
    )
    
    user_dict = user.model_dump()
    user_dict["hashed_password"] = hashed_password
    user_dict["created_at"] = user_dict["created_at"].isoformat()
    if user_dict.get("otp_expires"):
        user_dict["otp_expires"] = user_dict["otp_expires"].isoformat()
    
    await db.users.insert_one(user_dict)
    
    # Send email verification link
    verification_link = f"https://commerce-learn-2.preview.emergentagent.com/verify-email?token={verification_token}"
    email_html = f"""
    <h1>Welcome to School Of Commerce!</h1>
    <p>Dear {user.full_name},</p>
    <p>Thank you for registering. Please verify your email address to activate your account.</p>
    <p><a href="{verification_link}" style="background-color: #064e3b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0;">Verify Email Address</a></p>
    <p>Or copy this link: {verification_link}</p>
    <p>This link will expire in 24 hours.</p>
    <p>Best regards,<br>School Of Commerce Team</p>
    """
    await send_email_async(user.email, "Verify Your Email - School Of Commerce", email_html)
    
    token = create_access_token({"sub": user.email})
    user_dict_response = user.model_dump()
    user_dict_response.pop("verification_token", None)
    user_dict_response.pop("phone_otp", None)
    user_dict_response.pop("otp_expires", None)
    
    return {"token": token, "user": user_dict_response, "message": "Registration successful! Please check your email to verify your account."}

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if user.get("is_blocked"):
        raise HTTPException(status_code=403, detail="Your account has been blocked. Please contact administration.")
    
    token = create_access_token({"sub": user["email"]})
    user.pop("hashed_password", None)
    return {"token": token, "user": user}

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    current_user.pop("hashed_password", None)
    return current_user

@api_router.put("/auth/profile")
async def update_profile(update_data: UserUpdate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Check if email is being changed and if it's already taken
    if "email" in update_dict and update_dict["email"] != current_user["email"]:
        existing = await db.users.find_one({"email": update_dict["email"]}, {"_id": 0})
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
    
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get updated user
    updated_user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "hashed_password": 0})
    return updated_user

@api_router.put("/auth/change-password")
async def change_password(password_data: PasswordChange, current_user: dict = Depends(get_current_user)):
    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    
    if not verify_password(password_data.old_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    new_hashed_password = get_password_hash(password_data.new_password)
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"hashed_password": new_hashed_password}}
    )
    
    return {"message": "Password changed successfully"}

@api_router.post("/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    user = await db.users.find_one({"email": request.email}, {"_id": 0})
    if not user:
        # Don't reveal if email exists or not
        return {"message": "If the email exists, password reset instructions have been sent"}
    
    # Send email with username
    html_content = f"<h1>Account Recovery</h1><p>Your username/email is: <strong>{user['email']}</strong></p><p>Please contact admin to reset your password.</p>"
    await send_email_async(user['email'], "Account Recovery - School Of Commerce", html_content)
    
    return {"message": "If the email exists, password reset instructions have been sent"}

# ===== EMAIL VERIFICATION =====
@api_router.post("/auth/verify-email")
async def verify_email(request: VerifyEmailRequest):
    user = await db.users.find_one({"verification_token": request.token}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    
    if user.get("email_verified"):
        return {"message": "Email already verified"}
    
    await db.users.update_one(
        {"verification_token": request.token},
        {"$set": {"email_verified": True, "verification_token": None}}
    )
    
    return {"message": "Email verified successfully! You can now access all features."}

@api_router.post("/auth/resend-verification")
async def resend_verification(current_user: dict = Depends(get_current_user)):
    if current_user.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email already verified")
    
    verification_token = generate_verification_token()
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"verification_token": verification_token}}
    )
    
    verification_link = f"https://commerce-learn-2.preview.emergentagent.com/verify-email?token={verification_token}"
    email_html = f"""
    <h1>Verify Your Email</h1>
    <p>Dear {current_user['full_name']},</p>
    <p>Please verify your email address to activate your account.</p>
    <p><a href="{verification_link}" style="background-color: #064e3b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0;">Verify Email Address</a></p>
    <p>Or copy this link: {verification_link}</p>
    """
    await send_email_async(current_user['email'], "Verify Your Email - School Of Commerce", email_html)
    
    return {"message": "Verification email sent! Please check your inbox."}

# ===== PHONE VERIFICATION =====
@api_router.post("/auth/send-phone-otp")
async def send_phone_otp(request: SendPhoneOTPRequest, current_user: dict = Depends(get_current_user)):
    otp = generate_otp()
    otp_expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"phone": request.phone, "phone_otp": otp, "otp_expires": otp_expires.isoformat()}}
    )
    
    # Log OTP for debugging
    logger.info(f"OTP for {request.phone}: {otp}")
    
    # Try to send SMS via Twilio
    sms_message = f"Your School Of Commerce verification code is: {otp}\n\nThis code expires in 10 minutes.\n\nIf you didn't request this, please ignore."
    sms_result = await send_sms_async(request.phone, sms_message)
    
    if sms_result.get("success"):
        # SMS sent successfully
        return {
            "message": f"OTP sent to {request.phone} via SMS",
            "method": "sms",
            "expires_in": "10 minutes"
        }
    else:
        # Fallback: Send OTP via email (demo mode)
        email_html = f"""
        <h1>Phone Verification OTP</h1>
        <p>Dear {current_user['full_name']},</p>
        <p>Your OTP for phone verification is:</p>
        <div style="background-color: #f0f9ff; border: 2px solid #064e3b; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
            <h2 style="color: #064e3b; font-size: 32px; letter-spacing: 8px; margin: 0;">{otp}</h2>
        </div>
        <p>This OTP will expire in <strong>10 minutes</strong>.</p>
        <p style="color: #dc2626; margin-top: 20px;">
            <strong>⚠️ Demo Mode:</strong> Twilio SMS not configured. In production, this would be sent via SMS to {request.phone}
        </p>
        <hr style="margin: 30px 0;">
        <p style="font-size: 12px; color: #64748b;">
            To enable real SMS: Configure Twilio credentials in backend/.env<br>
            TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
        </p>
        """
        await send_email_async(current_user['email'], f"Phone Verification OTP: {otp}", email_html)
        
        return {
            "message": f"Twilio not configured. OTP sent to your email instead (Demo Mode)",
            "method": "email_fallback",
            "phone": request.phone,
            "expires_in": "10 minutes",
            "note": "To enable SMS: Add Twilio credentials to .env file"
        }

@api_router.post("/auth/verify-phone-otp")
async def verify_phone_otp(request: VerifyPhoneOTPRequest, current_user: dict = Depends(get_current_user)):
    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    
    if not user.get("phone_otp"):
        raise HTTPException(status_code=400, detail="No OTP found. Please request a new OTP.")
    
    if user.get("otp_expires"):
        otp_expires = datetime.fromisoformat(user["otp_expires"])
        if datetime.now(timezone.utc) > otp_expires:
            raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
    
    if user["phone_otp"] != request.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"phone_verified": True, "phone_otp": None, "otp_expires": None}}
    )
    
    return {"message": "Phone number verified successfully!"}

# ===== COURSE ROUTES =====
@api_router.get("/courses")
async def get_courses():
    courses = await db.courses.find({}, {"_id": 0}).to_list(100)
    for course in courses:
        if isinstance(course.get("created_at"), str):
            course["created_at"] = datetime.fromisoformat(course["created_at"])
    return courses

@api_router.get("/courses/{course_id}")
async def get_course(course_id: str):
    course = await db.courses.find_one({"course_id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if isinstance(course.get("created_at"), str):
        course["created_at"] = datetime.fromisoformat(course["created_at"])
    return course

@api_router.post("/courses")
async def create_course(course_data: CourseCreate, admin: dict = Depends(get_admin_user)):
    course = Course(**course_data.model_dump())
    course_dict = course.model_dump()
    course_dict["created_at"] = course_dict["created_at"].isoformat()
    await db.courses.insert_one(course_dict)
    return course

@api_router.post("/upload/course-image")
async def upload_course_image(file: UploadFile = File(...), admin: dict = Depends(get_admin_user)):
    # Validate file type
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Generate unique filename
    file_ext = file.filename.split('.')[-1]
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = UPLOAD_DIR / unique_filename
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Return URL path
    image_url = f"/uploads/course_images/{unique_filename}"
    return {"image_url": image_url}

@api_router.put("/courses/{course_id}")
async def update_course(course_id: str, course_data: CourseCreate, admin: dict = Depends(get_admin_user)):
    result = await db.courses.update_one(
        {"course_id": course_id},
        {"$set": course_data.model_dump()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"message": "Course updated successfully"}

@api_router.delete("/courses/{course_id}")
async def delete_course(course_id: str, admin: dict = Depends(get_admin_user)):
    result = await db.courses.delete_one({"course_id": course_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"message": "Course deleted successfully"}

@api_router.post("/courses/{course_id}/lectures")
async def add_lecture(course_id: str, lecture: Lecture, admin: dict = Depends(get_admin_user)):
    result = await db.courses.update_one(
        {"course_id": course_id},
        {"$push": {"lectures": lecture.model_dump()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return lecture

@api_router.post("/courses/{course_id}/enroll")
async def enroll_course(course_id: str, current_user: dict = Depends(get_current_user)):
    course = await db.courses.find_one({"course_id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    user_id = current_user["user_id"]
    if course_id in current_user.get("enrolled_courses", []):
        raise HTTPException(status_code=400, detail="Already enrolled in this course")
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$push": {"enrolled_courses": course_id}}
    )
    
    # Send confirmation to student
    student_html = f"""
    <h1>Course Enrollment Successful!</h1>
    <p>Dear {current_user['full_name']},</p>
    <p>You have successfully enrolled in <strong>{course['title']}</strong>.</p>
    <p><strong>Course Details:</strong></p>
    <ul>
      <li>Instructor: {course['instructor']}</li>
      <li>Duration: {course['duration']}</li>
      <li>Fee: ₹{course['fee']}</li>
    </ul>
    <p>You can now access all course materials and lectures from your dashboard.</p>
    <p>Best regards,<br>School Of Commerce Team</p>
    """
    await send_email_async(current_user['email'], f"Enrolled: {course['title']}", student_html)
    
    # Notify admin
    admin_html = f"""
    <h1>📚 New Course Enrollment</h1>
    <p><strong>A student has enrolled in a course!</strong></p>
    <p><strong>Student Details:</strong></p>
    <ul>
      <li><strong>Name:</strong> {current_user['full_name']}</li>
      <li><strong>Email:</strong> {current_user['email']}</li>
    </ul>
    <p><strong>Course Details:</strong></p>
    <ul>
      <li><strong>Course:</strong> {course['title']}</li>
      <li><strong>Instructor:</strong> {course['instructor']}</li>
      <li><strong>Fee:</strong> ₹{course['fee']}</li>
    </ul>
    <p><a href="https://commerce-learn-2.preview.emergentagent.com/admin" style="background-color: #064e3b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">View in Admin Panel</a></p>
    """
    await send_email_async(ADMIN_NOTIFICATION_EMAIL, f"New Enrollment: {course['title']}", admin_html)
    
    return {"message": "Enrolled successfully"}

# ===== ADMISSION ROUTES =====
@api_router.post("/admissions")
async def create_admission(admission_data: AdmissionCreate, current_user: dict = Depends(get_current_user)):
    admission = Admission(
        user_id=current_user["user_id"],
        **admission_data.model_dump()
    )
    admission_dict = admission.model_dump()
    admission_dict["created_at"] = admission_dict["created_at"].isoformat()
    await db.admissions.insert_one(admission_dict)
    
    # Send confirmation email to student
    student_html = f"""
    <h1>Admission Application Received</h1>
    <p>Dear {admission.full_name},</p>
    <p>Thank you for applying to School Of Commerce. We have received your admission application.</p>
    <p><strong>Application Details:</strong></p>
    <ul>
      <li>Course ID: {admission.course_id}</li>
      <li>Email: {admission.email}</li>
      <li>Phone: {admission.phone}</li>
    </ul>
    <p>We will review your application and get back to you shortly.</p>
    <p>Best regards,<br>School Of Commerce Team</p>
    """
    await send_email_async(admission.email, "Admission Application Received - School Of Commerce", student_html)
    
    # Send notification to admin
    admin_html = f"""
    <h1>🔔 New Admission Application</h1>
    <p><strong>A new student has applied for admission!</strong></p>
    <p><strong>Student Details:</strong></p>
    <ul>
      <li><strong>Name:</strong> {admission.full_name}</li>
      <li><strong>Email:</strong> {admission.email}</li>
      <li><strong>Phone:</strong> {admission.phone}</li>
      <li><strong>Course ID:</strong> {admission.course_id}</li>
      <li><strong>Message:</strong> {admission.message or 'No message provided'}</li>
      <li><strong>Applied on:</strong> {admission.created_at.strftime('%Y-%m-%d %H:%M:%S')}</li>
    </ul>
    <p>Login to admin dashboard to review and approve/reject this application.</p>
    <p><a href="https://commerce-learn-2.preview.emergentagent.com/admin" style="background-color: #064e3b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">View in Admin Panel</a></p>
    """
    await send_email_async(ADMIN_NOTIFICATION_EMAIL, f"New Admission: {admission.full_name}", admin_html)
    
    return admission

@api_router.get("/admissions")
async def get_admissions(admin: dict = Depends(get_admin_user)):
    admissions = await db.admissions.find({}, {"_id": 0}).to_list(100)
    for admission in admissions:
        if isinstance(admission.get("created_at"), str):
            admission["created_at"] = datetime.fromisoformat(admission["created_at"])
    return admissions

@api_router.put("/admissions/{admission_id}")
async def update_admission_status(admission_id: str, status: str, admin: dict = Depends(get_admin_user)):
    if status not in ["pending", "approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    admission = await db.admissions.find_one({"admission_id": admission_id}, {"_id": 0})
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    
    result = await db.admissions.update_one(
        {"admission_id": admission_id},
        {"$set": {"status": status}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Admission not found")
    
    # Send email notification
    if status == "approved":
        html_content = f"<h1>Admission Approved!</h1><p>Dear {admission['full_name']},</p><p>Congratulations! Your admission application has been approved. Welcome to School Of Commerce!</p>"
        await send_email_async(admission['email'], "Admission Approved - School Of Commerce", html_content)
    elif status == "rejected":
        html_content = f"<h1>Admission Status Update</h1><p>Dear {admission['full_name']},</p><p>Thank you for your interest. Unfortunately, we are unable to approve your admission at this time.</p>"
        await send_email_async(admission['email'], "Admission Status Update - School Of Commerce", html_content)
    
    return {"message": "Status updated successfully"}

# ===== QUERY ROUTES =====
@api_router.post("/queries")
async def create_query(query_data: QueryCreate):
    query = Query(**query_data.model_dump())
    query_dict = query.model_dump()
    query_dict["created_at"] = query_dict["created_at"].isoformat()
    await db.queries.insert_one(query_dict)
    
    # Send confirmation to user
    user_html = f"""
    <h1>Query Received</h1>
    <p>Dear {query.name},</p>
    <p>Thank you for contacting School Of Commerce. We have received your query.</p>
    <p><strong>Your Query:</strong></p>
    <ul>
      <li><strong>Subject:</strong> {query.subject}</li>
      <li><strong>Message:</strong> {query.message}</li>
    </ul>
    <p>Our team will respond to you within 24 hours.</p>
    <p>Best regards,<br>School Of Commerce Team</p>
    """
    await send_email_async(query.email, "Query Received - School Of Commerce", user_html)
    
    # Notify admin
    admin_html = f"""
    <h1>💬 New Student Query</h1>
    <p><strong>A new query has been submitted!</strong></p>
    <p><strong>Contact Details:</strong></p>
    <ul>
      <li><strong>Name:</strong> {query.name}</li>
      <li><strong>Email:</strong> {query.email}</li>
      <li><strong>Phone:</strong> {query.phone}</li>
    </ul>
    <p><strong>Query Details:</strong></p>
    <ul>
      <li><strong>Subject:</strong> {query.subject}</li>
      <li><strong>Message:</strong> {query.message}</li>
      <li><strong>Submitted on:</strong> {query.created_at.strftime('%Y-%m-%d %H:%M:%S')}</li>
    </ul>
    <p>Please respond to the student via email or phone.</p>
    <p><a href="https://commerce-learn-2.preview.emergentagent.com/admin" style="background-color: #064e3b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">View in Admin Panel</a></p>
    """
    await send_email_async(ADMIN_NOTIFICATION_EMAIL, f"New Query: {query.subject}", admin_html)
    
    return query

@api_router.get("/queries")
async def get_queries(admin: dict = Depends(get_admin_user)):
    queries = await db.queries.find({}, {"_id": 0}).to_list(100)
    for query in queries:
        if isinstance(query.get("created_at"), str):
            query["created_at"] = datetime.fromisoformat(query["created_at"])
    return queries

@api_router.put("/queries/{query_id}")
async def update_query_status(query_id: str, status: str, admin: dict = Depends(get_admin_user)):
    if status not in ["open", "resolved", "closed"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    result = await db.queries.update_one(
        {"query_id": query_id},
        {"$set": {"status": status}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Query not found")
    return {"message": "Query status updated successfully"}

# ===== STUDENT ROUTES =====
@api_router.get("/students")
async def get_students(admin: dict = Depends(get_admin_user)):
    # Return all users (both students and admins) for user management
    students = await db.users.find({}, {"_id": 0, "hashed_password": 0}).to_list(100)
    return students

@api_router.put("/students/{user_id}/block")
async def block_student(user_id: str, is_blocked: bool, admin: dict = Depends(get_admin_user)):
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"is_blocked": is_blocked}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"message": f"Student {'blocked' if is_blocked else 'unblocked'} successfully"}

# ===== RESULT ROUTES =====
@api_router.post("/results")
async def create_result(result_data: ResultCreate, admin: dict = Depends(get_admin_user)):
    result = Result(**result_data.model_dump())
    result_dict = result.model_dump()
    result_dict["created_at"] = result_dict["created_at"].isoformat()
    await db.results.insert_one(result_dict)
    return result

@api_router.get("/results")
async def get_my_results(current_user: dict = Depends(get_current_user)):
    results = await db.results.find({"user_id": current_user["user_id"]}, {"_id": 0}).to_list(100)
    return results

@api_router.get("/results/all")
async def get_all_results(admin: dict = Depends(get_admin_user)):
    results = await db.results.find({}, {"_id": 0}).to_list(100)
    return results

# ===== CHATBOT ROUTES =====
@api_router.post("/chatbot/message", response_model=ChatResponse)
async def chat_with_bot(message: ChatMessage, current_user: dict = Depends(get_current_user)):
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=current_user["user_id"],
            system_message="You are a helpful educational assistant for School Of Commerce. Help students with their queries about courses, admissions, and general academic questions. Be professional and friendly."
        )
        chat.with_model("gemini", "gemini-3-flash-preview")
        
        user_message = UserMessage(text=message.message)
        response = await chat.send_message(user_message)
        
        return ChatResponse(response=response)
    except Exception as e:
        logger.error(f"Chatbot error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chatbot error: {str(e)}")

# ===== SOCIAL GROUPS ROUTES =====
@api_router.get("/social-groups")
async def get_social_groups():
    groups = await db.social_groups.find({"is_active": True}, {"_id": 0}).to_list(100)
    return groups

@api_router.post("/social-groups")
async def create_social_group(group_data: SocialGroupCreate, admin: dict = Depends(get_admin_user)):
    group = SocialGroup(**group_data.model_dump())
    await db.social_groups.insert_one(group.model_dump())
    return group

@api_router.put("/social-groups/{group_id}")
async def update_social_group(group_id: str, group_data: SocialGroupCreate, admin: dict = Depends(get_admin_user)):
    result = await db.social_groups.update_one(
        {"group_id": group_id},
        {"$set": group_data.model_dump()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"message": "Group updated successfully"}

@api_router.delete("/social-groups/{group_id}")
async def delete_social_group(group_id: str, admin: dict = Depends(get_admin_user)):
    result = await db.social_groups.delete_one({"group_id": group_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"message": "Group deleted successfully"}

# ===== LIVE CLASSES ROUTES =====
@api_router.get("/live-classes")
async def get_live_classes(current_user: dict = Depends(get_current_user)):
    # Get user's enrolled courses
    enrolled_courses = current_user.get("enrolled_courses", [])
    
    # Get live classes for enrolled courses
    classes = await db.live_classes.find({
        "course_id": {"$in": enrolled_courses}
    }, {"_id": 0}).to_list(100)
    
    for cls in classes:
        if isinstance(cls.get("scheduled_time"), str):
            cls["scheduled_time"] = datetime.fromisoformat(cls["scheduled_time"])
        if isinstance(cls.get("created_at"), str):
            cls["created_at"] = datetime.fromisoformat(cls["created_at"])
    
    return classes

@api_router.get("/live-classes/all")
async def get_all_live_classes(admin: dict = Depends(get_admin_user)):
    classes = await db.live_classes.find({}, {"_id": 0}).to_list(100)
    for cls in classes:
        if isinstance(cls.get("scheduled_time"), str):
            cls["scheduled_time"] = datetime.fromisoformat(cls["scheduled_time"])
        if isinstance(cls.get("created_at"), str):
            cls["created_at"] = datetime.fromisoformat(cls["created_at"])
    return classes

@api_router.post("/live-classes")
async def create_live_class(class_data: LiveClassCreate, admin: dict = Depends(get_admin_user)):
    live_class = LiveClass(
        course_id=class_data.course_id,
        title=class_data.title,
        meeting_link=class_data.meeting_link,
        scheduled_time=datetime.fromisoformat(class_data.scheduled_time),
        duration_minutes=class_data.duration_minutes
    )
    
    class_dict = live_class.model_dump()
    class_dict["scheduled_time"] = class_dict["scheduled_time"].isoformat()
    class_dict["created_at"] = class_dict["created_at"].isoformat()
    
    await db.live_classes.insert_one(class_dict)
    return live_class

@api_router.put("/live-classes/{class_id}/toggle-live")
async def toggle_live_status(class_id: str, is_live: bool, admin: dict = Depends(get_admin_user)):
    result = await db.live_classes.update_one(
        {"class_id": class_id},
        {"$set": {"is_live": is_live}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"message": f"Class marked as {'live' if is_live else 'not live'}"}

@api_router.delete("/live-classes/{class_id}")
async def delete_live_class(class_id: str, admin: dict = Depends(get_admin_user)):
    result = await db.live_classes.delete_one({"class_id": class_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"message": "Class deleted successfully"}

app.include_router(api_router)

# Serve uploaded files
app.mount("/uploads", StaticFiles(directory=str(ROOT_DIR / "uploads")), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()