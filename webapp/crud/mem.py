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
from webapp.models.sirius.mem import mem as SQLAmem
from webapp.models.sirius.mem_cart import memcart as SQLAmemcart
from webapp.models.sirius.mem_rating import LikeDislikeEnum, memRating as SQLAmemRating
from webapp.schema.mem.mem import memAfterCreate, memCreate, memDownload, memRead

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
    body: memCreate,
    file: UploadFile,
    user_id: int,
) -> memAfterCreate | None:
    minio_path = await upload_file_to_minio(file=file, user_id=user_id)
    new_file = SQLAmem(text=body.text, photo_url=minio_path, user_id=user_id)
    session.add(new_file)
    await session.commit()
    await session.refresh(new_file)
    add_to_cart = SQLAmemcart(user_id=user_id, cart_type='general', mem_id=new_file.id)
    session.add(add_to_cart)
    await session.commit()
    await session.refresh(add_to_cart)

    return memAfterCreate.model_validate(new_file)


async def get_mem_by_id(session: AsyncSession, mem_id: int) -> memRead | None:
    redis = await get_redis()
    cached_mem_data = await redis.get(f'{REDIS_PREFIX}:mem:{mem_id}')

    if cached_mem_data:
        cached_mem = orjson.loads(cached_mem_data)
        return memRead.model_validate_json(cached_mem)

    mem_query = (
        select(
            SQLAmem.id,
            SQLAmem.text,
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .outerjoin(SQLAmemRating, SQLAmemRating.mem_id == SQLAmem.id)
        .where(SQLAmem.id == mem_id)
        .group_by(SQLAmem.id)
    )

    result = await session.execute(mem_query)
    mem = result.fetchone()
    if mem:
        mem_read = memRead.model_validate(mem)
        await redis.set(f'{REDIS_PREFIX}:mem:{mem_id}', orjson.dumps(mem_read.model_dump_json()), 3600)
        return mem_read
    return None


async def get_memes_by_cart(session: AsyncSession, cart_type: str, user_id: int) -> Optional[List[memRead]]:
    memes_query = (
        select(
            SQLAmem.id,
            SQLAmem.text,
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .join(SQLAmemcart, SQLAmem.id == SQLAmemcart.mem_id)
        .outerjoin(SQLAmemRating, SQLAmem.id == SQLAmemRating.mem_id)
        .where(SQLAmemcart.cart_type == cart_type)
        .group_by(SQLAmem.id)
    )

    if cart_type == 'personal':
        memes_query = memes_query.where(SQLAmemcart.user_id == user_id)

    result = await session.execute(memes_query)
    memes = result.all()
    mem_read_list = [memRead.model_validate(mem) for mem in memes] if memes else None

    return mem_read_list


async def download_mem_by_id(session: AsyncSession, mem_id: int) -> memDownload | None:
    redis = await get_redis()
    cache_key = f'{REDIS_PREFIX}:mem_download:{mem_id}'
    cached_mem_data = await redis.get(cache_key)

    if cached_mem_data:
        cached_mem = orjson.loads(cached_mem_data)
        return memDownload.model_validate_json(cached_mem)

    result = await session.execute(select(SQLAmem).where(SQLAmem.id == mem_id))
    mem = result.scalars().first()
    if mem:
        mem_download = memDownload.model_validate(mem)
        await redis.set(cache_key, orjson.dumps(mem_download.model_dump_json()), 3600)
        return mem_download
    return None


async def rating_mem(session: AsyncSession, mem_id: int, user_id: int, mark: LikeDislikeEnum) -> memRead | None:
    redis = await get_redis()
    # начало транзакции
    async with session.begin():
        query = await session.execute(
            select(SQLAmemRating).where(SQLAmemRating.mem_id == mem_id, SQLAmemRating.user_id == user_id)
        )
        existing_rating = query.scalar_one_or_none()

        if existing_rating:
            # если оценка уже существует и совпадает, удаляем
            if existing_rating.rating == mark:
                await session.delete(existing_rating)
            # если оценка уже существует, но не совпадает
            else:
                stmt = (
                    update(SQLAmemRating)
                    .where(SQLAmemRating.mem_id == mem_id, SQLAmemRating.user_id == user_id)
                    .values(rating=mark)
                )
                await session.execute(stmt)
        # если оценки от юзера для этого мема еще нет
        else:
            stmt = insert(SQLAmemRating).values(user_id=user_id, mem_id=mem_id, rating=mark)
            await session.execute(stmt)

        # фиксация транзакции
        await session.commit()

    # удаляем из Redis после фиксации
    await redis.delete(f'{REDIS_PREFIX}:mem:{mem_id}')
    await redis.delete(f'{REDIS_PREFIX}:trend_mem')

    # повторно запрашиваем информацию о меме
    async with session.begin():
        stmt = (
            select(
                SQLAmem.id,
                SQLAmem.text,
                func.count(case((SQLAmemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
                func.count(case((SQLAmemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
            )
            .outerjoin(SQLAmemRating, SQLAmem.id == SQLAmemRating.mem_id)
            .where(SQLAmem.id == mem_id)
            .group_by(SQLAmem.id)
        )
        result = await session.execute(stmt)
        mem = result.fetchone()

    if mem:
        mem_read = memRead.model_validate(mem)
        await redis.set(f'{REDIS_PREFIX}:mem:{mem_id}', orjson.dumps(mem_read.model_dump_json()), ex=3600)
        return mem_read
    else:
        return None


async def random_mem(session: AsyncSession) -> memRead | None:
    random_mem_query = (
        select(
            SQLAmem.id,
            SQLAmem.text,
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .join(SQLAmemcart, SQLAmem.id == SQLAmemcart.mem_id)
        .outerjoin(SQLAmemRating, SQLAmem.id == SQLAmemRating.mem_id)
        .where(SQLAmemcart.cart_type == 'general')
        .group_by(SQLAmem.id)
        .order_by(func.random())
        .limit(1)
    )
    random_mem = await session.execute(random_mem_query)
    mem = random_mem.fetchone() if random_mem else None
    return memRead.model_validate(mem) if mem else None


async def trend_mem(session: AsyncSession) -> memRead | None:
    redis = await get_redis()
    cache_key = f'{REDIS_PREFIX}:trend_mem'
    cached_mem_data = await redis.get(cache_key)

    if cached_mem_data:
        cached_mem = orjson.loads(cached_mem_data)
        return memRead.model_validate_json(cached_mem)

    trend_mem_query = (
        select(
            SQLAmem.id,
            SQLAmem.text,
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.like, 1))).label('likes'),
            func.count(case((SQLAmemRating.rating == LikeDislikeEnum.dislike, 1))).label('dislikes'),
        )
        .join(SQLAmemcart, SQLAmem.id == SQLAmemcart.mem_id)
        .outerjoin(SQLAmemRating, SQLAmem.id == SQLAmemRating.mem_id)
        .where(SQLAmemcart.cart_type == 'general')
        .group_by(SQLAmem.id)
        .order_by(func.count(case((SQLAmemRating.rating == LikeDislikeEnum.like, 1))).desc())
        .limit(1)
    )
    trend_mem = await session.execute(trend_mem_query)
    mem = trend_mem.fetchone() if trend_mem else None

    if mem:
        mem_read = memRead.model_validate(mem)
        await redis.set(cache_key, orjson.dumps(mem_read.model_dump_json()), 3600)
        return mem_read
    return None


async def personal_cart(session: AsyncSession, user_id: int, mem_id: int) -> bool:
    add_mem = SQLAmemcart(user_id=user_id, mem_id=mem_id, cart_type='personal')
    session.add(add_mem)
    try:
        await session.commit()
        return True
    except SQLAlchemyError:
        await session.rollback()
        return False
