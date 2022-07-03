from http import HTTPStatus
from pydoc import doc
from typing import (
    Any,
    Callable,
    List,
    Optional,
    Type,
    cast,
    Coroutine,
    Union,
    Dict
)

from fastapi import HTTPException

from . import CRUDGenerator, NOT_FOUND, _utils
from ._types import DEPENDENCIES, PAGINATION

try:
    from odmantic import AIOEngine, Model
    from odmantic.bson import ObjectId
except ImportError:
    Model = None  # type: ignore
    odmantic_installed = False
else:
    odmantic_installed = True

CALLABLE = Callable[..., Coroutine[Any, Any, Model]]
CALLABLE_LIST = Callable[..., Coroutine[Any, Any, List[Optional[Model]]]]
DELETE_ALL_FAILED_MESSAGE: str = (
    "Could not delete {found} documents from database."
)


class ODManticCRUDRouter(CRUDGenerator[Model]):
    def __init__(
        self,
        engine: AIOEngine,
        schema: Type[Model],
        create_schema: Optional[Type[Model]] = None,
        update_schema: Optional[Type[Model]] = None,
        prefix: Optional[str] = None,
        tags: Optional[List[str]] = None,
        paginate: Optional[int] = None,
        get_all_route: Union[bool, DEPENDENCIES] = True,
        get_one_route: Union[bool, DEPENDENCIES] = True,
        create_route: Union[bool, DEPENDENCIES] = True,
        update_route: Union[bool, DEPENDENCIES] = True,
        delete_one_route: Union[bool, DEPENDENCIES] = True,
        delete_all_route: Union[bool, DEPENDENCIES] = True,
        **kwargs: Any
    ) -> None:
        assert odmantic_installed, (
            "Odmantic must be installed to use the OdmanticCRUDRouter."
        )
        self._pk: str = schema.__primary_field__
        self._pk_type: type = _utils.get_pk_type(schema, self._pk)
        self.engine: AIOEngine = engine

        super().__init__(
            schema=schema,
            create_schema=create_schema or schema,
            update_schema=update_schema or schema,
            prefix=prefix or schema.Config.collection,
            tags=tags,
            paginate=paginate,
            get_all_route=get_all_route,
            get_one_route=get_one_route,
            create_route=create_route,
            update_route=update_route,
            delete_one_route=delete_one_route,
            delete_all_route=delete_all_route,
            **kwargs
        )

        self._INTEGRITY_ERROR = self._get_integrity_error_type()

    def _get_all(self, *args: Any, **kwargs: Any) -> CALLABLE_LIST:
        async def route(
            pagination: PAGINATION = self.pagination,
        ) -> List[Optional[Model]]:
            skip, limit = pagination.get("skip"), pagination.get("limit")
            keyword_arguments: Dict[str, int] = {
                'skip': cast(int, skip)
            }
            if limit is not None:
                keyword_arguments['limit'] = cast(int, limit)
            return await self.engine.find(self.schema, **keyword_arguments)  # type: ignore

        return route

    def _get_one(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(item_id: self._pk_type) -> Model:  # type: ignore
            model: Optional[self.schema] = await self.engine.find_one(
                self.schema, self.__get_single_model_query(item_id)
            )
            if model is None:
                raise NOT_FOUND from None
            return model

        return route

    def _create(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(model: self.create_schema) -> Model:  # type: ignore
            model_dict = model.dict()
            if self.__is_default_primary_key():  # autoincrement
                model_dict.pop(self._pk, None)
            try:
                document: Model = self.schema(**model_dict)
                return await self.engine.save(document)
            except self._INTEGRITY_ERROR as error:
                raise HTTPException(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    f"Key already exists {error}"
                ) from None

        return route

    def _update(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(
            item_id: self._pk_type,  # type: ignore
            model: self.update_schema,  # type: ignore
        ) -> Model:
            document: Optional[self.schema] = await self._get_one()(item_id)
            document.update(model)
            await self.engine.save(document)
            return await self._get_one()(item_id)

        return route

    def _delete_all(self, *args: Any, **kwargs: Any) -> CALLABLE_LIST:
        async def route() -> List[Optional[Model]]:
            collection = self.engine.get_collection(self.schema)
            documents = await self._get_all()(
                pagination={"skip": 0, "limit": None}
            )
            result = await collection.delete_many({
                self.__get_primary_field(): getattr(instance, self._pk)
                for instance in documents
            })
            if (len(documents) - result.deleted_count) != 0:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=DELETE_ALL_FAILED_MESSAGE.format(
                        found=len(documents)
                    )
                )
            return await self._get_all()(pagination={"skip": 0, "limit": None})

        return route

    def _delete_one(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(item_id: self._pk_type) -> Model:  # type: ignore
            model = await self._get_one()(item_id)
            await self.engine.delete(model)
            return model

        return route

    def _get_integrity_error_type(self) -> Type[Exception]:
        """Imports the Integrity exception based on the used backend"""
        try:
            from pymongo.error import PyMongoError
            return PyMongoError
        except ImportError:
            return Exception

    def __is_default_primary_key(self) -> bool:
        return self._pk == "id" and self._pk_type == ObjectId

    def __get_primary_field(self):
        if self.__is_default_primary_key():
            return '_id'
        return self.schema.__primary_field__

    def __get_single_model_query(self, item_id: Any) -> Dict[str, Any]:
        filters: Dict[str, self._pk_type] = {
            id_field: item_id for id_field in self.schema.Config.fields
            if id_field == self.__get_primary_field()
        }
        return filters

