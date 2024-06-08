from pydantic import BaseModel, ConfigDict

from webapp.schema.enums import CartEnum


class MemCart(BaseModel):
    user_id: int
    mem_id: int
    cart_type: CartEnum


class MemCartCreate(MemCart):
    pass


class MemCart(MemCart):
    id: int

    model_config = ConfigDict(from_attributes=True)
