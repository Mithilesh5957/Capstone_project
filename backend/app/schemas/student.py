from pydantic import BaseModel, Field


class EnrollIn(BaseModel):
    student_id: str
    name: str
    branch: str = "CSE"
    images: list = Field(default_factory=list)


class StudentOut(BaseModel):
    student_id: str
    name: str
    branch: str
    created_at: str | None = None
