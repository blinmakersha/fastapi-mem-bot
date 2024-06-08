from typing import TYPE_CHECKING, List

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webapp.models.meta import DEFAULT_SCHEMA, Base

if TYPE_CHECKING:
    from webapp.models.sirius.mem import Mem
    from webapp.models.sirius.mem_cart import MemCart
    from webapp.models.sirius.mem_rating import MemRating


class User(Base):
    __tablename__ = 'users'
    __table_args__ = ({'schema': DEFAULT_SCHEMA},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[int] = mapped_column(BigInteger, unique=True)
    tg: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String)

    memes: Mapped[List['Mem']] = relationship('Mem', back_populates='user')
    ratings: Mapped[List['MemRating']] = relationship('MemRating', back_populates='user')
    carts: Mapped[List['MemCart']] = relationship('MemCart', back_populates='user')
