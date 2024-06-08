from enum import Enum


class LikeDislikeEnum(str, Enum):
    like = 'like'
    dislike = 'dislike'


class CartEnum(str, Enum):
    personal = 'personal'
    general = 'general'
