from pydantic import BaseModel


class UserLogin(BaseModel):
    username: int
    tg: str
    code: str


class UserLoginResponse(BaseModel):
    access_token: str
