from typing import TYPE_CHECKING, List

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webapp.models.meta import DEFAULT_SCHEMA, Base

if TYPE_CHECKING:
    from webapp.models.sirius.mem_cart import MemCart
    from webapp.models.sirius.mem_rating import MemRating
    from webapp.models.sirius.user import User


class Mem(Base):
    __tablename__ = 'memes'
    __table_args__ = ({'schema': DEFAULT_SCHEMA},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{DEFAULT_SCHEMA}.users.id'), nullable=False)
    photo_url: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped['User'] = relationship('User', back_populates='memes')
    ratings: Mapped[List['MemRating']] = relationship('MemRating', back_populates='mem')
    carts: Mapped[List['MemCart']] = relationship('MemCart', back_populates='mem')
