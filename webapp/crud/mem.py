import uuid
import asyncio
from datetime import datetime
from typing import List, Optional

import orjson
from fastapi import HTTPException, UploadFile
from sqlalchemy import case, func, insert, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from starlette import status

from conf.config import settings
from webapp.db.minio import minio_client
from webapp.db.redis import get_redis
from webapp.models.sirius.mem import Mem as SQLAMem
from webapp.models.sirius.mem_cart import MemCart as SQLAMemCart
from webapp.models.sirius.mem_rating import LikeDislikeEnum, MemRating as SQLAMemRating
from webapp.schema.mem.mem import MemAfterCreate, MemCreate, MemDownload, MemRead

REDIS_PREFIX = settings.REDIS_SIRIUS_CACHE_PREFIX


async def upload_file_to_minio(file: UploadFile, user_id: int) -> str:
    bucket_name = settings.BUCKET_NAME

    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    current_date = datetime.now().strftime('%Y-%m-%d')
    unique_suffix = uuid.uuid4().hex
    file_name = f'{file.filename.rsplit(".", 1)[0]}_{unique_suffix}.{file.filename.rsplit(".", 1)[-1]}'
    file_path = f'{current_date}/{file_name}'

    file_data = file.file.read()
    file_size = len(file_data)
    file.file.seek(0)

    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            minio_client.put_object,
            bucket_name,
            file_path,
            file.file,
            file_size,
            file.content_type,
        )
        return file_path
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'ошибка в minio {str(e)}') from e


async def create_mem(
    session: AsyncSession,
    body: MemCreate,
    file: UploadFile,
    user_id: int,
) -> MemAfterCreate | None:
    minio_path = await upload_file_to_minio(file=file, user_id=user_id)
    new_file = SQLAMem(text=body.text, photo_url=minio_path, user_id=user_id)
    session.add(new_file)
    await session.commit()
    await session.refresh(new_file)
    add_to_cart = SQLAMemCart(user_id=user_id, cart_type='general', mem_id=new_file.id)
    session.add(add_to_cart)
    await session.commit()
    await session.refresh(add_to_cart)

    return MemAfterCreate.model_validate(new_file)


async def get_mem_by_id(session: AsyncSession, mem_id: int) -> MemRead | None:
    redis = await get_redis()
    cached_mem_data = await redis.get(f'{REDIS_PREFIX}:mem:{mem_id}')

    if cached_mem_data:
        cached_mem = orjson.loads(cached_mem_data)
        return MemRead.model_validate_json(cached_mem)

    mem_query = (
        select(
            SQLAMem.id,
            SQLAMem.text,
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .outerjoin(SQLAMemRating, SQLAMemRating.mem_id == SQLAMem.id)
        .where(SQLAMem.id == mem_id)
        .group_by(SQLAMem.id)
    )

    result = await session.execute(mem_query)
    mem = result.fetchone()
    if mem:
        mem_read = MemRead.model_validate(mem)
        await redis.set(f'{REDIS_PREFIX}:mem:{mem_id}', orjson.dumps(mem_read.model_dump_json()), 3600)
        return mem_read
    return None


async def get_memes_by_cart(session: AsyncSession, cart_type: str, user_id: int) -> Optional[List[MemRead]]:
    memes_query = (
        select(
            SQLAMem.id,
            SQLAMem.text,
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .join(SQLAMemCart, SQLAMem.id == SQLAMemCart.mem_id)
        .outerjoin(SQLAMemRating, SQLAMem.id == SQLAMemRating.mem_id)
        .where(SQLAMemCart.cart_type == cart_type)
        .group_by(SQLAMem.id)
    )

    if cart_type == 'personal':
        memes_query = memes_query.where(SQLAMemCart.user_id == user_id)

    result = await session.execute(memes_query)
    memes = result.all()
    mem_read_list = [MemRead.model_validate(mem) for mem in memes] if memes else None

    return mem_read_list


async def download_mem_by_id(session: AsyncSession, mem_id: int) -> MemDownload | None:
    redis = await get_redis()
    cache_key = f'{REDIS_PREFIX}:mem_download:{mem_id}'
    cached_mem_data = await redis.get(cache_key)

    if cached_mem_data:
        cached_mem = orjson.loads(cached_mem_data)
        return MemDownload.model_validate_json(cached_mem)

    result = await session.execute(select(SQLAMem).where(SQLAMem.id == mem_id))
    mem = result.scalars().first()
    if mem:
        mem_download = MemDownload.model_validate(mem)
        await redis.set(cache_key, orjson.dumps(mem_download.model_dump_json()), 3600)
        return mem_download
    return None


async def rating_mem(session: AsyncSession, mem_id: int, user_id: int, mark: LikeDislikeEnum) -> MemRead | None:
    redis = await get_redis()
    # начало транзакции
    async with session.begin():
        query = await session.execute(
            select(SQLAMemRating).where(SQLAMemRating.mem_id == mem_id, SQLAMemRating.user_id == user_id)
        )
        existing_rating = query.scalar_one_or_none()

        if existing_rating:
            # если оценка уже существует и совпадает, удаляем
            if existing_rating.rating == mark:
                await session.delete(existing_rating)
            # если оценка уже существует, но не совпадает
            else:
                stmt = (
                    update(SQLAMemRating)
                    .where(SQLAMemRating.mem_id == mem_id, SQLAMemRating.user_id == user_id)
                    .values(rating=mark)
                )
                await session.execute(stmt)
        # если оценки от юзера для этого мема еще нет
        else:
            stmt = insert(SQLAMemRating).values(user_id=user_id, mem_id=mem_id, rating=mark)
            await session.execute(stmt)

        # фиксация транзакции
        await session.commit()

    # удаляем из Redis после фиксации
    await redis.delete(f'{REDIS_PREFIX}:mem:{mem_id}')
    await redis.delete(f'{REDIS_PREFIX}:trendy_mem')

    # повторно запрашиваем информацию о меме
    async with session.begin():
        stmt = (
            select(
                SQLAMem.id,
                SQLAMem.text,
                func.count(case((SQLAMemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
                func.count(case((SQLAMemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
            )
            .outerjoin(SQLAMemRating, SQLAMem.id == SQLAMemRating.mem_id)
            .where(SQLAMem.id == mem_id)
            .group_by(SQLAMem.id)
        )
        result = await session.execute(stmt)
        mem = result.fetchone()

    if mem:
        mem_read = MemRead.model_validate(mem)
        await redis.set(f'{REDIS_PREFIX}:mem:{mem_id}', orjson.dumps(mem_read.model_dump_json()), ex=3600)
        return mem_read
    else:
        return None


async def random_mem(session: AsyncSession) -> MemRead | None:
    random_mem_query = (
        select(
            SQLAMem.id,
            SQLAMem.text,
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .join(SQLAMemCart, SQLAMem.id == SQLAMemCart.mem_id)
        .outerjoin(SQLAMemRating, SQLAMem.id == SQLAMemRating.mem_id)
        .where(SQLAMemCart.cart_type == 'general')
        .group_by(SQLAMem.id)
        .order_by(func.random())
        .limit(1)
    )
    random_mem = await session.execute(random_mem_query)
    mem = random_mem.fetchone() if random_mem else None
    return MemRead.model_validate(mem) if mem else None


async def trendy_mem(session: AsyncSession) -> MemRead | None:
    redis = await get_redis()
    cache_key = f'{REDIS_PREFIX}:trendy_mem'
    cached_mem_data = await redis.get(cache_key)

    if cached_mem_data:
        cached_mem = orjson.loads(cached_mem_data)
        return MemRead.model_validate_json(cached_mem)

    trendy_mem_query = (
        select(
            SQLAMem.id,
            SQLAMem.text,
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAMemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .join(SQLAMemCart, SQLAMem.id == SQLAMemCart.mem_id)
        .outerjoin(SQLAMemRating, SQLAMem.id == SQLAMemRating.mem_id)
        .where(SQLAMemCart.cart_type == 'general')
        .group_by(SQLAMem.id)
        .order_by(func.count(case((SQLAMemRating.rating == LikeDislikeEnum.like, 1))).desc())
        .limit(1)
    )
    trendy_mem = await session.execute(trendy_mem_query)
    mem = trendy_mem.fetchone() if trendy_mem else None

    if mem:
        mem_read = MemRead.model_validate(mem)
        await redis.set(cache_key, orjson.dumps(mem_read.model_dump_json()), 3600)
        return mem_read
    return None


async def personal_cart(session: AsyncSession, user_id: int, mem_id: int) -> bool:
    add_mem = SQLAMemCart(user_id=user_id, mem_id=mem_id, cart_type='personal')
    session.add(add_mem)
    try:
        await session.commit()
        return True
    except SQLAlchemyError:
        await session.rollback()
        return False
