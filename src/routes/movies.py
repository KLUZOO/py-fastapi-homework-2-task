from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from math import ceil

from database import get_db, MovieModel
from database.models import CountryModel, GenreModel, ActorModel, LanguageModel

from schemas.movies import MovieListResponseSchema, MovieDetailSchema, MovieCreateSchema, MoviePatchSchema
from sqlalchemy.orm import selectinload
from starlette import status

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
        .order_by(MovieModel.id.desc())
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
        selectinload(MovieModel.genres),
        selectinload(MovieModel.actors),
        selectinload(MovieModel.languages),
        selectinload(MovieModel.country),
    ))
    movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")
    return movie


@router.delete("/movies/{movie_id}/", status_code=204)
async def remove_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MovieModel).where(MovieModel.id == movie_id))
    db_film = result.scalar_one_or_none()

    if not db_film:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    await db.delete(db_film)
    await db.commit()

    return None


@router.post("/movies/", status_code=status.HTTP_201_CREATED, response_model=MovieDetailSchema)
async def create_movie(movie: MovieCreateSchema, db: AsyncSession = Depends(get_db)):
    # --- Перевірка дубліката ---
    result = await db.execute(
        select(MovieModel).options(
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
            selectinload(MovieModel.country),
        ).where(MovieModel.name == movie.name, MovieModel.date == movie.date)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A movie with the name '{movie.name}' and release date '{movie.date}' already exists."
        )

    # --- Country ---
    country = (await db.execute(select(CountryModel).where(CountryModel.code == movie.country))).scalar_one_or_none()
    if not country:
        country = CountryModel(code=movie.country)
        db.add(country)

    # --- Genres, Actors, Languages ---
    async def get_or_create(model, name):
        obj = (await db.execute(select(model).where(model.name == name))).scalar_one_or_none()
        if not obj:
            obj = model(name=name)
            db.add(obj)
        return obj

    genres = [await get_or_create(GenreModel, g) for g in movie.genres]
    actors = [await get_or_create(ActorModel, a) for a in movie.actors]
    languages = [await get_or_create(LanguageModel, lng) for lng in movie.languages]

    # --- Movie ---
    db_movie = MovieModel(
        name=movie.name,
        date=movie.date,
        score=movie.score,
        overview=movie.overview,
        status=movie.status,
        budget=movie.budget,
        revenue=movie.revenue,
        country=country,
        genres=genres,
        actors=actors,
        languages=languages
    )

    db.add(db_movie)
    await db.flush()  # один раз перед commit
    await db.commit()
    await db.refresh(db_movie)

    db_movie = (await db.execute(
        select(MovieModel)
        .options(
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
            selectinload(MovieModel.country)
        )
        .where(MovieModel.id == db_movie.id)
    )).scalar_one()

    return {
        "id": db_movie.id,
        "name": db_movie.name,
        "date": db_movie.date,
        "score": db_movie.score,
        "overview": db_movie.overview,
        "status": db_movie.status,
        "budget": db_movie.budget,
        "revenue": db_movie.revenue,
        "country": {
            "id": db_movie.country.id,
            "code": db_movie.country.code,
            "name": db_movie.country.name
        } if db_movie.country else None,
        "genres": [{"id": gnr.id, "name": gnr.name} for gnr in db_movie.genres],
        "actors": [{"id": act.id, "name": act.name} for act in db_movie.actors],
        "languages": [{"id": lng.id, "name": lng.name} for lng in db_movie.languages],
    }


@router.patch("/movies/{movie_id}/")
async def update_movie(
        movie_id: int,
        movie_update: MoviePatchSchema,
        db: AsyncSession = Depends(get_db)
):
    # --- Знаходимо фільм ---
    result = await db.execute(select(MovieModel).options(
        selectinload(MovieModel.genres),
        selectinload(MovieModel.actors),
        selectinload(MovieModel.languages),
        selectinload(MovieModel.country),
    ).where(MovieModel.id == movie_id))
    db_movie = result.scalar_one_or_none()

    if not db_movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    # --- Оновлення простих полів ---
    for field, value in movie_update.dict(exclude_unset=True).items():
        if field in ["name", "date", "score", "overview", "status", "budget", "revenue"]:
            # --- Валідація ---
            if field == "score" and not (0 <= value <= 100):
                raise HTTPException(status_code=400, detail={"detail": "Invalid input data."})
            if field in ["budget", "revenue"] and value < 0:
                raise HTTPException(status_code=400, detail={"detail": "Invalid input data."})
            if field == "date" and value > date.today() + timedelta(days=365):
                raise HTTPException(status_code=400, detail={"detail": "Invalid input data."})

            setattr(db_movie, field, value)

    # --- Оновлення простих полів ---
    for field, value in movie_update.dict(exclude_unset=True).items():
        if field in ["name", "date", "score", "overview", "status", "budget", "revenue"]:
            # --- Валідація ---
            if field == "score" and not (0 <= value <= 100):
                raise HTTPException(status_code=400, detail={"detail": "Invalid input data."})
            if field in ["budget", "revenue"] and value < 0:
                raise HTTPException(status_code=400, detail={"detail": "Invalid input data."})
            if field == "date" and value > date.today() + timedelta(days=365):
                raise HTTPException(status_code=400, detail={"detail": "Invalid input data."})

            setattr(db_movie, field, value)

    await db.commit()
    await db.refresh(db_movie)

    return {
        "detail": "Movie updated successfully.",
        "movie": {
            "id": db_movie.id,
            "name": db_movie.name,
            "date": db_movie.date,
            "score": db_movie.score,
            "overview": db_movie.overview,
            "status": db_movie.status,
            "budget": db_movie.budget,
            "revenue": db_movie.revenue
        }
    }
