import datetime

from database.models import MovieStatusEnum, CountryModel
from pydantic import BaseModel, Field, validator
from typing import Literal

from typing import Optional, List


class CountrySchema(BaseModel):
    id: int
    code: str
    name: str | None

    class Config:
        from_attributes = True


class GenreSchema(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class ActorSchema(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class LanguageSchema(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class MovieDetailSchema(BaseModel):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str
    status: Literal["Released", "Post Production", "In Production"]
    budget: float
    revenue: float
    country: CountrySchema
    genres: list[GenreSchema]
    actors: list[ActorSchema]
    languages: list[LanguageSchema]

    class Config:
        from_attributes = True


class MovieListItemSchema(BaseModel):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str

    class Config:
        from_attributes = True


class MovieListResponseSchema(BaseModel):
    movies: list[MovieListItemSchema]
    prev_page: str | None
    next_page: str | None
    total_pages: int
    total_items: int

    class Config:
        from_attributes = True


class MovieCreateSchema(BaseModel):
    name: str = Field(..., max_length=255)
    date: datetime.date
    score: float = Field(..., ge=0, le=100)
    overview: str | None
    status: str
    budget: int = Field(..., ge=0)
    revenue: int = Field(..., ge=0)
    country: str
    genres: list[str]
    actors: list[str]
    languages: list[str]

    @validator("date")
    def date_not_too_far(cls, v: datetime.date):
        if v > datetime.date.today() + datetime.timedelta(days=365):
            raise ValueError("Date cannot be more than 1 year in the future")
        return v

    @validator("*", pre=True, always=True)
    def catch_invalid_input(cls, v, values, **kwargs):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("Invalid input data.")
        return v


class MoviePatchSchema(BaseModel):
    name: Optional[str] = None
    date: Optional[datetime.date] = None
    score: Optional[float] = None
    overview: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    revenue: Optional[float] = None

    @validator("date")
    def date_not_too_far(cls, v):
        if v and v > datetime.date.today() + datetime.timedelta(days=365):
            raise ValueError("Date cannot be more than 1 year in the future")
        return v

    @validator("score")
    def score_valid(cls, v):
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Score must be between 0 and 100")
        return v

    @validator("budget", "revenue")
    def non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Value cannot be negative")
        return v
