from typing import List
from sqlalchemy.exc import IntegrityError


from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from sqlmodel import Session, select

from dundie.db import ActiveSession
from dundie.tasks.user import try_to_send_pwd_reset_email
from dundie.models.user import User, UserRequest, UserResponse, UserProfilePatchRequest, UserPasswordPatchRequest

from dundie.auth import AuthenticatedUser, CanChangeUserPassword, SuperUser

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def list_users(*, session: Session = ActiveSession):
    """List all users."""
    users = session.exec(select(User)).all()
    return users


@router.get("/{username}/", response_model=UserResponse)
async def get_user_by_username(
    *, session: Session = ActiveSession, username: str
):
    """Get user by username"""
    query = select(User).where(User.username == username)
    user = session.exec(query).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post(
    "/", response_model=UserResponse, status_code=201, dependencies=[SuperUser]
)
async def create_user(*, session: Session = ActiveSession, user: UserRequest):
    """Creates new user"""
    if session.exec(select(User).where(User.username == user.username)).first():
        raise HTTPException(status_code=409, detail="Username already taken")

    db_user = User.from_orm(user)  # transform UserRequest in User
    session.add(db_user)
    try:
        session.commit()
    except IntegrityError:
        raise HTTPException(status_code=500, detail="Database IntegrityError")

    session.refresh(db_user)
    return db_user

@router.patch("/{username}/", response_model=UserResponse)
async def update_user(
    *,
    session: Session = ActiveSession,
    patch_data: UserProfilePatchRequest,
    current_user: User = AuthenticatedUser,
    username: str
):
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != current_user.id and not current_user.superuser:
        raise HTTPException(status_code=403, detail="You can only update your own profile")

    # Update
    user.avatar = patch_data.avatar
    user.bio = patch_data.bio

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/{username}/password/", response_model=UserResponse)
async def change_password(
    *,
    session: Session = ActiveSession,
    patch_data: UserPasswordPatchRequest,
    user: User = CanChangeUserPassword
):
    user.password = patch_data.hashed_password  # pyright: ignore
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/pwd_reset_token/")
async def send_password_reset_token(*, email: str = Body(embed=True)):
    """Sends an email with the token to reset password."""
    try_to_send_pwd_reset_email(email)
    return {
        "message": "If we found a user with that email, we sent a password reset token to it."
    }

