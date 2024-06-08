from pydantic import BaseModel, ConfigDict

from webapp.schema.enums import CartEnum, LikeDislikeEnum


class MemRead(BaseModel):
    id: int
    text: str
    likes: int
    dislikes: int

    model_config = ConfigDict(from_attributes=True)


class MemCreate(BaseModel):
    text: str


class MemAfterCreate(BaseModel):
    id: int

    model_config = ConfigDict(from_attributes=True)


class MemDownload(BaseModel):
    photo_url: str

    model_config = ConfigDict(from_attributes=True)
