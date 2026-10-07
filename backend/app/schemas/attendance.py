from pydantic import BaseModel


class StartIn(BaseModel):
    session_name: str = "Morning Session"


class OverrideIn(BaseModel):
    session_id: int
    student_id: str
    status: str


class FrameIn(BaseModel):
    image: str
