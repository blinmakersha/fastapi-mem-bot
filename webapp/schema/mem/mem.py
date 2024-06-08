from pydantic import BaseModel, ConfigDict

from webapp.schema.enums import BasketEnum, LikeDislikeEnum


class MemeRead(BaseModel):
    id: int
    text: str
    likes: int
    dislikes: int

    model_config = ConfigDict(from_attributes=True)


class MemeCreate(BaseModel):
    text: str


class MemeAfterCreate(BaseModel):
    id: int

    model_config = ConfigDict(from_attributes=True)


class MemeDownload(BaseModel):
    photo_url: str

    model_config = ConfigDict(from_attributes=True)
