from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from math import ceil

from database import get_db, MovieModel
from database.models import CountryModel, GenreModel, ActorModel, LanguageModel

from schemas.movies import MovieListResponseSchema, MovieDetailSchema, MovieCreateSchema
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
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@router.delete("/movies/}", status_code=204)
async def remove_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MovieModel).where(MovieModel.id == movie_id))
    db_film = result.scalar_one_or_none()

    if not db_film:
        raise HTTPException(status_code=404, detail="Film not found")

    await db.delete(db_film)
    await db.commit()

    return None


@router.post("/movies/")
async def create_movie(movie: MovieCreateSchema, db: AsyncSession = Depends(get_db)):
    # --- Перевірка дубліката ---
    result = await db.execute(
        select(MovieModel).where(
            MovieModel.name == movie.name,
            MovieModel.date == movie.date
        )
    )
    existing_movie = result.scalar_one_or_none()
    if existing_movie:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A movie with the same {movie.name} and {movie.date} already exists."
        )

    # --- Country (ISO 3166-1 alpha-3) ---
    result = await db.execute(select(CountryModel).where(CountryModel.code == movie.country))
    country = result.scalar_one_or_none()
    if not country:
        country = CountryModel(code=movie.country, name=movie.country)
        db.add(country)
        await db.flush()

    # --- Genres ---
    genres = []
    for g in movie.genres:
        result = await db.execute(select(GenreModel).where(GenreModel.name == g))
        genre = result.scalar_one_or_none()
        if not genre:
            genre = GenreModel(name=g)
            db.add(genre)
            await db.flush()
        genres.append(genre)

    # --- Actors ---
    actors = []
    for a in movie.actors:
        result = await db.execute(select(ActorModel).where(ActorModel.name == a))
        actor = result.scalar_one_or_none()
        if not actor:
            actor = ActorModel(name=a)
            db.add(actor)
            await db.flush()
        actors.append(actor)

    # --- Languages ---
    languages = []
    for l in movie.languages:
        result = await db.execute(select(LanguageModel).where(LanguageModel.name == l))
        language = result.scalar_one_or_none()
        if not language:
            language = LanguageModel(name=l)
            db.add(language)
            await db.flush()
        languages.append(language)


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
        languages=languages,
    )

    db.add(db_movie)
    await db.commit()
    await db.refresh(db_movie)

    return {
        "id": db_movie.id,
        "name": db_movie.name,
        "country": country.code,  # повертаємо ISO-код
        "genres": [g.name for g in genres],
        "actors": [a.name for a in actors],
        "languages": [l.name for l in languages],
    }
