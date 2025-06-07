"""
sqlite_jsonfield.py
Supercharged JSON field for Peewee + SQLite JSON1 — финальная версия.
"""

from __future__ import annotations
import json
from functools import partial
from typing import Any, Callable, Optional, Union, NamedTuple

import peewee
from peewee import TextField, fn, Value

__all__ = ["SQLiteJSONField", "create_json_index", "JSON1_AVAILABLE"]


# -----------------------------------------------------------------------------
# 0. Быстрый сериализатор: orjson → ujson → stdlib json
# -----------------------------------------------------------------------------
def _pick_serializer() -> tuple[Callable[[Any, bool], str], Callable[[str], Any]]:
    try:
        import orjson  # type: ignore

        def _dumps(obj: Any, ensure_ascii: bool = False) -> str:
            opts = 0
            if ensure_ascii:
                opts |= orjson.OPT_NON_STR_KEYS
            return orjson.dumps(obj, option=opts).decode()

        return _dumps, orjson.loads  # type: ignore
    except ImportError:
        pass

    try:
        import ujson  # type: ignore

        def _dumps(obj: Any, ensure_ascii: bool = False) -> str:
            return ujson.dumps(obj, ensure_ascii=ensure_ascii)

        return _dumps, ujson.loads  # type: ignore
    except ImportError:
        pass

    def _dumps(obj: Any, ensure_ascii: bool = False) -> str:
        return json.dumps(obj, ensure_ascii=ensure_ascii)

    return _dumps, json.loads


_FAST_DUMPS, _FAST_LOADS = _pick_serializer()


# -----------------------------------------------------------------------------
# 1. Проверка JSON1
# -----------------------------------------------------------------------------
_JSON1_CACHE: dict[peewee.Database, bool] = {}


def _check_json1(db: Optional[peewee.Database] = None) -> bool:
    target = db or peewee.SqliteDatabase(":memory:")
    if target in _JSON1_CACHE:
        return _JSON1_CACHE[target]
    try:
        target.execute_sql("SELECT json('{\"x\":1}')")
        _JSON1_CACHE[target] = True
    except Exception:
        _JSON1_CACHE[target] = False
    return _JSON1_CACHE[target]


JSON1_AVAILABLE = _check_json1(None)


# -----------------------------------------------------------------------------
# 2. Поле SQLiteJSONField
# -----------------------------------------------------------------------------
class SQLiteJSONField(TextField):
    """
    JSON-поле для Peewee + SQLite JSON1.
    """

    def __init__(
        self,
        null_to_empty: bool = True,
        *,
        ensure_ascii: bool = False,
        dumps: Optional[Callable[[Any], str]] = None,
        loads: Optional[Callable[[Union[str, bytes], Any]]] = None,
        **kwargs,
    ):
        self.null_to_empty = null_to_empty
        self.dumps = dumps or partial(_FAST_DUMPS, ensure_ascii=ensure_ascii)
        self.loads = loads or _FAST_LOADS

        # default=dict → новая копия при каждом создании
        if kwargs.get("default") is dict:
            kwargs["default"] = dict  # type: ignore

        super().__init__(**kwargs)

    def db_value(self, value: Optional[Any]) -> Optional[str]:
        if value is None:
            return "{}" if self.null_to_empty else None
        if isinstance(value, str):
            return value
        return self.dumps(value)

    def python_value(self, value: Optional[Any]) -> Any:
        if value is None:
            return {}
        if isinstance(value, (dict, list, int, float, bool)):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                return self.loads(value.decode("utf-8"))
            except Exception:
                return {}
        if isinstance(value, str):
            try:
                # всегда пытаем загрузить JSON
                return self.loads(value)
            except Exception:
                return {}
        return {}

    # ——— Query-helpers ———

    def json_extract(self, path: str) -> peewee.Expression:
        """
        Возвращает JSON_QUOTE(JSON_EXTRACT(...)) AS TEXT,
        чтобы SELECT возвращал валидный JSON-подобный текст.
        """
        # JSON_QUOTE оборачивает строку/число в валидную JSON-строку, e.g. '"yes"'
        return fn.JSON_QUOTE(fn.JSON_EXTRACT(self, path)).cast("TEXT")

    def contains_key(self, path: str) -> peewee.Expression:
        """
        WHERE json_valid(col)=1 AND json_type(json_extract(col, path)) IS NOT NULL
        """
        return (fn.json_valid(self) == 1) & (
            fn.json_type(fn.json_extract(self, path)) >> None
        )

    def path_eq(self, path: str, value: Any) -> peewee.Expression:
        """WHERE json_extract(col, path) = value"""
        return fn.json_extract(self, path) == value

    def set_expr(self, path: str, value: Any) -> peewee.Expression:
        """Для UPDATE: json_set(col, path, value)"""
        return fn.json_set(self, path, Value(value))

    # ——— Pydantic ———

    @classmethod
    def __get_validators__(cls):
        yield cls._validate

    @classmethod
    def _validate(cls, v):
        if isinstance(v, dict):
            return v
        if isinstance(v, (str, bytes, bytearray)):
            try:
                return json.loads(v)
            except Exception as e:
                raise ValueError("Invalid JSON") from e
        raise TypeError("Expected dict or JSON string")

    # ——— DDL helper ———

    def ddl_check_valid(self) -> str:
        """
        Возвращает выражение для CHECK: "json_valid(<column>)"
        """
        if not _check_json1(None):
            raise RuntimeError("SQLite без JSON1; json_valid недоступен")
        col = self.db_column or self.name
        return f"json_valid({col})"


# -----------------------------------------------------------------------------
# 3. Utility: JSON-путь → индекс
# -----------------------------------------------------------------------------
class _Idx(NamedTuple):
    name: str


def create_json_index(
    model: type[peewee.Model],
    field: SQLiteJSONField,
    path: str,
    *,
    unique: bool = False,
    name: Optional[str] = None,
) -> _Idx:
    """
    Делает CREATE [UNIQUE] INDEX IF NOT EXISTS ... ON table(json_extract(...));
    """
    if not _check_json1(None):
        raise RuntimeError("SQLite без JSON1; json_extract недоступен")

    db = model._meta.database
    table = model._meta.table_name
    col = field.db_column or field.name
    safe = path.lstrip("$").replace(".", "_").replace("[", "_").replace("]", "")
    idx = name or f"{table}_{field.name}_{safe}_idx"
    uniq_sql = "UNIQUE " if unique else ""
    sql = (
        f'CREATE {uniq_sql}INDEX IF NOT EXISTS "{idx}" '
        f'ON "{table}" (json_extract("{col}", "{path}"));'
    )
    db.execute_sql(sql)
    return _Idx(idx)
