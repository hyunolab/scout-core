from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/articles",
    tags=["Articles"]
)


@router.get("")
def get_articles():

    return [
        {
            "title":"Sample Nuclear News",
            "country":"USA",
            "technology":"SMR"
        }
    ]