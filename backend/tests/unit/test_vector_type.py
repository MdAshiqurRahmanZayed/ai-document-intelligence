"""The vector column type, checked without a database: the SQL it makes and how it converts."""

from typing import Any

from sqlalchemy import Float, insert, select, update
from sqlalchemy.dialects.postgresql import asyncpg

from app.db.models import Chunk
from app.db.types import EMBEDDING_DIM, Vector

DIALECT = asyncpg.dialect()  # type: ignore[no-untyped-call]
VECTOR = [0.1] * EMBEDDING_DIM


def sql(statement: Any, **kwargs: Any) -> str:
    return str(statement.compile(dialect=DIALECT, **kwargs)).replace("\n", " ")


def test_the_column_type_is_named_vector_with_its_size() -> None:
    # SQLAlchemy casts every value of a multi-row INSERT to this type name. It once compiled as
    # VARCHAR, and PostgreSQL refused to put that into a vector column.
    assert Chunk.__table__.c.embedding.type.compile(dialect=DIALECT) == "vector(768)"
    assert Vector(3).compile(dialect=DIALECT) == "vector(3)"


def test_a_value_reaches_the_database_as_text_cast_to_vector() -> None:
    insert_sql = sql(insert(Chunk).values(page_no=1, embedding=VECTOR))
    update_sql = sql(update(Chunk).where(Chunk.id == 1).values(embedding=VECTOR))

    for statement in (insert_sql, update_sql):
        # The inner cast makes the driver send text; the outer one gives the database a vector.
        assert "CAST(CAST($" in statement and "AS TEXT) AS vector(768))" in statement


def test_a_distance_query_casts_the_query_vector_the_same_way() -> None:
    distance = Chunk.embedding.op("<=>", return_type=Float)(VECTOR)

    statement = sql(select(Chunk.id).where(Chunk.embedding.is_not(None)).order_by(distance))

    assert "chunks.embedding <=> CAST(CAST($" in statement
    assert "AS TEXT) AS vector(768))" in statement


def test_a_list_becomes_the_text_pgvector_reads_and_back() -> None:
    column_type = Vector(3)
    to_db = column_type.bind_processor(DIALECT)
    from_db = column_type.result_processor(DIALECT, None)

    assert to_db([1.0, 0.5, -2.0]) == "[1.0,0.5,-2.0]"
    assert from_db("[1,0.5,-2]") == [1.0, 0.5, -2.0]
    assert to_db(None) is None and from_db(None) is None
