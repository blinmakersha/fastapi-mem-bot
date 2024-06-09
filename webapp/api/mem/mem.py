import re
import mimetypes
from typing import List
from urllib.parse import quote

from fastapi import Depends, File, UploadFile
from fastapi.responses import ORJSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from conf.config import settings
from webapp.api.mem.router import mem_router
from webapp.crud.mem import (
    create_mem,
    download_mem_by_id,
    get_mem_by_id,
    get_memes_by_cart,
    personal_cart,
    random_mem,
    rating_mem,
    trendy_mem,
)
from webapp.db.minio import minio_client
from webapp.db.postgres import get_session
from webapp.models.sirius.mem_rating import LikeDislikeEnum
from webapp.schema.enums import CartEnum
from webapp.schema.mem.mem import MemAfterCreate, MemCreate, MemRead
from webapp.utils.auth.jwt import JwtTokenT, jwt_auth


@mem_router.get(
    '/', response_model=List[MemRead], response_class=ORJSONResponse, tags=['mem'], status_code=status.HTTP_200_OK
)
async def get_memes(
    cart_type: CartEnum,
    session: AsyncSession = Depends(get_session),
    current_user: JwtTokenT = Depends(jwt_auth.get_current_user),
):
    memes = await get_memes_by_cart(session=session, cart_type=cart_type, user_id=current_user['user_id'])
    if memes:
        return memes
    return ORJSONResponse({'message': 'Доступных мемов нет'}, status_code=status.HTTP_200_OK)


@mem_router.get(
    '/random', response_model=MemRead, response_class=ORJSONResponse, tags=['mem'], status_code=status.HTTP_200_OK
)
async def get_random_mem(
    session: AsyncSession = Depends(get_session), current_user: JwtTokenT = Depends(jwt_auth.get_current_user)
):
    return await random_mem(session=session) or ORJSONResponse(
        {'message': 'Доступных мемов нет'}, status_code=status.HTTP_200_OK
    )


@mem_router.post(
    '/upload',
    response_model=MemAfterCreate,
    status_code=status.HTTP_201_CREATED,
    response_class=ORJSONResponse,
    tags=['mem'],
)
async def upload_file(
    body: MemCreate = Depends(),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: JwtTokenT = Depends(jwt_auth.get_current_user),
):
    mem = await create_mem(session=session, body=body, file=file, user_id=current_user['user_id'])
    if mem:
        return mem
    return ORJSONResponse({'message': 'Невозможно выгрузить мем'}, status_code=status.HTTP_400_BAD_REQUEST)


@mem_router.get(
    '/trendy-mem',
    response_model=MemRead,
    response_class=ORJSONResponse,
    tags=['mem'],
    status_code=status.HTTP_200_OK,
)
async def get_trendy_mem(
    session: AsyncSession = Depends(get_session), current_user: JwtTokenT = Depends(jwt_auth.get_current_user)
):
    return await trendy_mem(session=session) or ORJSONResponse(
        {'message': 'Доступных мемов нет'}, status_code=status.HTTP_200_OK
    )


@mem_router.get(
    '/{mem_id}', response_model=MemRead, response_class=ORJSONResponse, tags=['mem'], status_code=status.HTTP_200_OK
)
async def get_mem(
    mem_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: JwtTokenT = Depends(jwt_auth.get_current_user),
):
    return await get_mem_by_id(session=session, mem_id=mem_id) or ORJSONResponse(
        {'message': 'Мема не существует'}, status_code=status.HTTP_200_OK
    )


@mem_router.get('/download/{mem_id}', response_class=ORJSONResponse, tags=['mem'], status_code=status.HTTP_200_OK)
async def download_mem(
    mem_id: int,
    session: AsyncSession = Depends(get_session),
):
    record = await download_mem_by_id(session=session, mem_id=mem_id)
    if not record:
        return ORJSONResponse({'message': 'Нет данных'}, status_code=status.HTTP_404_NOT_FOUND)

    response = minio_client.get_object(settings.BUCKET_NAME, record.photo_url)
    match = re.search(r'[^/]+$', record.photo_url)
    filename = match.group(0) if match else 'downloaded_file'
    media_type, _ = mimetypes.guess_type(filename)
    media_type = media_type or 'application/octet-stream'
    headers = {'Content-Disposition': f"attachment; filename*=utf-8''{quote(filename)}"}
    return StreamingResponse(response.stream(32 * 1024), media_type=media_type, headers=headers)


@mem_router.get(
    '/add-to-cart/{mem_id}', response_class=ORJSONResponse, tags=['mem'], status_code=status.HTTP_200_OK
)
async def add_to_cart(
    mem_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: JwtTokenT = Depends(jwt_auth.get_current_user),
):
    add = await personal_cart(session=session, mem_id=mem_id, user_id=current_user['user_id'])
    if add:
        return
    return ORJSONResponse({'message': 'Невозможно добавить в избранное'}, status_code=status.HTTP_200_OK)


@mem_router.get(
    '/mark/{mem_id}',
    response_model=MemRead,
    response_class=ORJSONResponse,
    tags=['mem'],
    status_code=status.HTTP_200_OK,
)
async def mark_mem(
    mem_id: int,
    mark: LikeDislikeEnum,
    session: AsyncSession = Depends(get_session),
    current_user: JwtTokenT = Depends(jwt_auth.get_current_user),
):
    return await rating_mem(
        session=session, mem_id=mem_id, user_id=current_user['user_id'], mark=mark
    ) or ORJSONResponse({'message': 'Нет данных'}, status_code=status.HTTP_200_OK)
