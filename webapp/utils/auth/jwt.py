import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from starlette import status
from typing_extensions import TypedDict

from conf.config import settings
from webapp.models.sirius.user import User

auth_scheme = HTTPBearer()


class JwtTokenT(TypedDict):
    uid: str
    exp: datetime
    user_id: int


@dataclass
class JwtAuth:
    secret: str

    def create_token(self, user: User) -> str:
        access_token = {
            'uid': uuid.uuid4().hex,
            'exp': datetime.utcnow() + timedelta(days=6),
            'user_id': user.id,
        }
        return jwt.encode(access_token, self.secret)

    def validate_token(self, credentials: HTTPAuthorizationCredentials = Security(auth_scheme)) -> JwtTokenT:
        token = credentials.credentials

        try:
            return cast(JwtTokenT, jwt.decode(token, self.secret))
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    def get_current_user(self, credentials: HTTPAuthorizationCredentials = Security(auth_scheme)) -> JwtTokenT:
        return self.validate_token(credentials)


jwt_auth = JwtAuth(settings.JWT_SECRET_SALT)
