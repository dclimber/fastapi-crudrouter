from beanie import Document, init_beanie
from fastapi import FastAPI

from fastapi_crudrouter import BeanieCRUDRouter
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from tests import (
    Carrot,
    CarrotCreate,
    CarrotUpdate,
    PAGINATION_SIZE,
    Potato,
    CUSTOM_TAGS,
    config
)

DATABASE_URL: str = config.MONGO_URI


class PotatoModel(Document):
    thickness: float
    mass: float
    color: str
    type: str

    class Config:
        fields = {'id': '_id'}


class CarrotModel(Document):
    length: float
    color: str

    class Config:
        fields = {'id': '_id'}


async def on_startup():
    database_client: AsyncIOMotorClient = AsyncIOMotorClient(DATABASE_URL)
    database = database_client.get_default_database()

    # database_client.drop_database(database)
    await init_beanie(
        database=database,
        document_models=[
            PotatoModel,
            CarrotModel,
        ],
    )


def beanie_implementation(**kwargs):

    print('\n\n\nstart!\n\n')
    print(DATABASE_URL)
    app = FastAPI(on_startup=[on_startup])

    router_settings = [
        dict(
            schema=PotatoModel,
            prefix="potato",
            paginate=PAGINATION_SIZE,
        ),
        dict(
            schema=CarrotModel,
            create_schema=CarrotCreate,
            update_schema=CarrotUpdate,
            prefix="carrot",
            tags=CUSTOM_TAGS,
        ),
    ]

    return app, BeanieCRUDRouter, router_settings
