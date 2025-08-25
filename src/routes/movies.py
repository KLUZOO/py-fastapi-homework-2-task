from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from math import ceil

from database import get_db, MovieModel
from database.models import CountryModel, GenreModel, ActorModel, LanguageModel

from schemas.movies import MovieListResponseSchema, MovieDetailSchema
from sqlalchemy.orm import selectinload

router = APIRouter()


@router.get("/movies/", response_model=MovieListResponseSchema)
async def get_movies(
        page: int = Query(1, ge=1),
        per_page: int = Query(10, ge=1, le=20),
        db: AsyncSession = Depends(get_db),
):
    total_items = await db.execute(select(func.count()).select_from(MovieModel))
    total_items = total_items.scalar_one()
    total_pages = ceil(total_items / per_page)

    result = await db.execute(
        select(MovieModel)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .order_by(MovieModel.id)
    )
    movies = result.scalars().all()

    if not movies:
        raise HTTPException(
            status_code=404, detail="No movies found."
        )

    return MovieListResponseSchema(
        movies=movies,
        prev_page=f"/theater/movies/?page={page - 1}"
                  f"&per_page={per_page}" if page > 1 else None,
        next_page=f"/theater/movies/?page={page + 1}"
                  f"&per_page={per_page}" if page < total_pages else None,
        total_pages=total_pages,
        total_items=total_items
    )


@router.get("/movies/{movie_id}/", response_model=MovieDetailSchema)
async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MovieModel).where(MovieModel.id == movie_id).options(
        selectinload(MovieModel.country)
    ))
    movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie
