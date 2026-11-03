"""Column types that SQLAlchemy does not ship."""

from typing import Any

from sqlalchemy import Text, cast
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import UserDefinedType

# The size of one embedding. It is part of the table layout (the column is vector(768)), so
# changing it needs a migration; app.llm.embeddings asks the model for exactly this many numbers.
EMBEDDING_DIM = 768


class Vector(UserDefinedType[list[float]]):
    """A pgvector `vector(dim)` column, exchanged with Python as a list of floats.

    The driver is never asked to understand the vector type: the list travels as text and is
    cast to `vector` inside the SQL statement, so no codec has to be registered on every
    connection (the API, each worker task and the tests all open their own).

    The type compiles as `vector(dim)` on purpose. SQLAlchemy casts every value of a multi-row
    INSERT to its column type (`SELECT p4::<type> FROM (VALUES ...)`), and that cast must name
    the real type. The parameter itself carries no cast of its own (this type does not ask for
    one), and `bind_expression` pins it to text so the database never infers `vector` for it.
    """

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dim})"

    def bind_processor(self, dialect: Dialect) -> Any:
        def process(value: list[float] | None) -> str | None:
            return None if value is None else "[" + ",".join(repr(float(x)) for x in value) + "]"

        return process

    def result_processor(self, dialect: Dialect, coltype: Any) -> Any:
        def process(value: str | None) -> list[float] | None:
            return None if value is None else [float(x) for x in value.strip("[]").split(",")]

        return process

    def bind_expression(self, bindvalue: Any) -> ColumnElement[Any]:
        return cast(cast(bindvalue, Text), self)
