"""conftest.py — test setup: JSONB/ARRAY compat for the sqlite test DB."""
import json as _json

from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "JSON"


# ARRAY has no sqlite (de)serializer -> lists/nulls would hit sqlite raw.
_ARRAY_bind_processor = ARRAY.bind_processor
_ARRAY_result_processor = ARRAY.result_processor


def _sqlite_aware_bind(self, dialect):
    if dialect.name == "sqlite":
        # None must stay NULL: serializing it as "[]" would make
        # `tender.required_msme_tier is null` read false in tests.
        return lambda value: None if value is None else _json.dumps(value)
    return _ARRAY_bind_processor(self, dialect)


def _sqlite_aware_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def loads(value):
            return _json.loads(value) if isinstance(value, str) else value
        return loads
    return _ARRAY_result_processor(self, dialect, coltype)


ARRAY.bind_processor = _sqlite_aware_bind
ARRAY.result_processor = _sqlite_aware_result
