from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webapp.models.meta import DEFAULT_SCHEMA, Base

if TYPE_CHECKING:
    from webapp.models.sirius.mem import Mem
    from webapp.models.sirius.user import User


class LikeDislikeEnum(Enum):
    like = 'like'
    dislike = 'dislike'


class MemRating(Base):
    __tablename__ = 'mem_ratings'
    __table_args__ = (
        UniqueConstraint('user_id', 'mem_id', name='user_mem_unique_rating'),
        {'schema': DEFAULT_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{DEFAULT_SCHEMA}.users.id'), nullable=False)
    mem_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{DEFAULT_SCHEMA}.memes.id'), nullable=False)
    rating: Mapped[LikeDislikeEnum] = mapped_column(
        ENUM(LikeDislikeEnum, name='like_dislike_enum', schema=DEFAULT_SCHEMA), nullable=False
    )

    user: Mapped['User'] = relationship('User', back_populates='ratings')
    mem: Mapped['Mem'] = relationship('Mem', back_populates='ratings')
