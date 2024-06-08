from typing import List

from pydantic import BaseModel, ConfigDict

from webapp.schema.mem.mem import Mem
from webapp.schema.mem.mem_cart import MemCart


class UserModel(BaseModel):
    tg: str
    memes: List[Mem] = []
    carts: List[MemCart] = []

    model_config = ConfigDict(from_attributes=True)
