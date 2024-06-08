from typing import List

from pydantic import BaseModel, ConfigDict


class File(BaseModel):
    url: str
    mem_id: str

    model_config = ConfigDict(from_attributes=True)


class User(BaseModel):
    files: List[File]
    username: str

    model_config = ConfigDict(from_attributes=True)
