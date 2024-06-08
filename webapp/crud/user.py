from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webapp.models.sirius.user import User
from webapp.schema.login.user import UserLogin
from webapp.utils.auth.password import hash_password


async def get_user_by_username(session: AsyncSession, user_info: UserLogin) -> User | None:
    return (await session.scalars(select(User).where(User.username == user_info.username))).one_or_none()


async def get_user(session: AsyncSession, user_info: UserLogin) -> User | None:
    return (
        await session.scalars(
            select(User).where(
                User.username == user_info.username,
                User.code == hash_password(user_info.code),
            )
        )
    ).one_or_none()


async def register_user(session: AsyncSession, user_info: UserLogin) -> User:
    new_user = User(username=user_info.username, tg=user_info.tg, code=hash_password(user_info.code))
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user
