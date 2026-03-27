from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.database import get_db
from core.security import verify_password, create_access_token, hash_password, require_role, get_current_user
from models.user import User, UserRole
from models.audit_log import AuditLog

router = APIRouter(prefix="/auth", tags=["auth"])


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str = ""
    role: UserRole = UserRole.paralegal


@router.post("/login")
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form.username).first()
    ip = request.client.host if request.client else ""

    if not user or not verify_password(form.password, user.hashed_password):
        db.add(
            AuditLog(
                action="LOGIN",
                user_email=form.username,
                success=False,
                detail="Invalid credentials",
                ip_address=ip,
            )
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role}
    )
    db.add(
        AuditLog(
            action="LOGIN",
            user_id=user.id,
            user_email=user.email,
            success=True,
            ip_address=ip,
        )
    )
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "email": user.email,
        "full_name": user.full_name,
    }


@router.post("/register")
async def register(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            action="REGISTER",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="user",
            resource_id=str(user.id),
            detail=f"Created {payload.email} ({payload.role})",
            ip_address=request.client.host if request.client else "",
        )
    )
    db.commit()
    return {"detail": f"User {payload.email} created successfully"}


@router.get("/users")
async def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    users = db.query(User).order_by(User.created_at).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    user.is_active = not user.is_active
    db.commit()
    return {"detail": f"User {'activated' if user.is_active else 'deactivated'}"}
