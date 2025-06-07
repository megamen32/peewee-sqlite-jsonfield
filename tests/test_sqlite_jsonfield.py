# tests/test_sqlite_jsonfield.py
import json
import pytest
import peewee
from peewee import Model, SqliteDatabase

from peewee_sqlite_jsonfield import (
    SQLiteJSONField,
    create_json_index,
    JSON1_AVAILABLE, _check_json1,
)


def test_json1_flag():
    # Проверяем, что флаг доступности JSON1 — булево
    assert isinstance(JSON1_AVAILABLE, bool)


def test_default_returns_empty_dict():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        data = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    doc = Doc.create()  # без явного data
    assert isinstance(doc.data, dict)
    assert doc.data == {}


def test_store_and_retrieve_nested():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        meta = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    payload = {"foo": {"bar": 42, "baz": [1, 2, 3]}}
    doc = Doc.create(meta=payload)
    # reload из БД
    doc2 = Doc.get(Doc.id == doc.id)
    assert doc2.meta == payload


def test_null_to_empty_false_stores_null():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        m = SQLiteJSONField(null_to_empty=False, null=True)
        class Meta:
            database = db

    db.create_tables([Doc])
    doc = Doc.create(m=None)
    # Сырые данные в БД должны быть NULL
    row = db.execute_sql("SELECT m FROM doc WHERE id = ?", (doc.id,)).fetchone()
    assert row[0] is None
    # python_value всё равно даст {}
    doc2 = Doc.get(Doc.id == doc.id)
    assert doc2.m == {}


def test_invalid_json_returns_empty_dict():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        meta = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    d = Doc.create(meta={"a": 1})
    # вручную портим значение
    db.execute_sql("UPDATE doc SET meta = ? WHERE id = ?", ("not a json", d.id))
    d2 = Doc.get(Doc.id == d.id)
    assert d2.meta == {}


def test_json_extract_and_contains_path_eq():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        meta = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    d1 = Doc.create(meta={"x": {"y": "yes"}})
    d2 = Doc.create(meta={"x": {"y": "no"}})
    # json_extract
    row = (
        Doc
        .select(Doc.meta.json_extract('$.x.y').alias('val'))
        .where(Doc.id == d1.id)
        .get()
    )
    assert row.val == "yes"
    # contains_key
    qs = Doc.select().where(Doc.meta.contains_key('$.x.y'))
    assert set(d.id for d in qs) == {d1.id, d2.id}
    # path_eq
    qs2 = Doc.select().where(Doc.meta.path_eq('$.x.y', 'yes'))
    assert [d.id for d in qs2] == [d1.id]


def test_set_expr_update():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        meta = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    d = Doc.create(meta={})
    # обновляем in-place через JSON_SET
    Doc.update({Doc.meta: Doc.meta.set_expr('$.count', 5)}).where(Doc.id == d.id).execute()
    d2 = Doc.get(Doc.id == d.id)
    assert d2.meta.get("count") == 5


def test_update_using_set_shortcut():
    db = SqliteDatabase(":memory:")

    class Doc(Model):
        meta = SQLiteJSONField(default=dict)

        class Meta:
            database = db

    db.create_tables([Doc])
    d = Doc.create(meta={})

    Doc.update({Doc.meta.set('$.num'): 7}).where(Doc.id == d.id).execute()

    d2 = Doc.get(Doc.id == d.id)
    assert d2.meta.get("num") == 7


def test_create_json_index_and_pragmas():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        meta = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    # не должно падать
    idx = create_json_index(Doc, Doc.meta, '$.a.b', unique=False)
    # проверим, что индекс действительно создался через PRAGMA
    indexes = db.execute_sql("PRAGMA index_list('doc')").fetchall()
    names = {row[1] for row in indexes}  # row[1] — имя индекса
    assert idx.name in names


def test_pydantic_validator_accepts_and_rejects():
    # корректная строка
    v = SQLiteJSONField._validate('{"a": 1}')
    assert isinstance(v, dict) and v["a"] == 1
    # корректный dict
    v2 = SQLiteJSONField._validate({"b": 2})
    assert v2 == {"b": 2}
    # некорректная строка
    with pytest.raises(ValueError):
        SQLiteJSONField._validate("notjson")
    # неподдерживаемый тип
    with pytest.raises(TypeError):
        SQLiteJSONField._validate(123)


def test_custom_dumps_loads_are_used():
    # кастомный сериализатор/десериализатор
    def my_dumps(obj):
        return "<X>"
    def my_loads(s):
        return {"unpacked": True}

    db = SqliteDatabase(":memory:")
    class Doc(Model):
        meta = SQLiteJSONField(dumps=my_dumps, loads=my_loads, default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    d = Doc.create(meta={"anything": 123})
    # проверяем raw
    raw = db.execute_sql("SELECT meta FROM doc WHERE id = ?", (d.id,)).fetchone()[0]
    assert raw == "<X>"
    # проверяем python_value
    d2 = Doc.get(Doc.id == d.id)
    assert d2.meta == {"unpacked": True}

def test_integer_float_bool_and_list_roundtrip():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        data = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    payload = {
        "int": 123,
        "float": 3.14,
        "bool": True,
        "lst": [1, 2, {"x": "y"}],
    }
    d = Doc.create(data=payload)
    d2 = Doc.get(Doc.id == d.id)
    assert isinstance(d2.data["int"], int) and d2.data["int"] == 123
    assert isinstance(d2.data["float"], float) and abs(d2.data["float"] - 3.14) < 1e-6
    assert isinstance(d2.data["bool"], bool) and d2.data["bool"] is True
    assert isinstance(d2.data["lst"], list) and d2.data["lst"][2] == {"x": "y"}


def test_ensure_ascii_option_escapes_unicode():
    # Прямо проверим db_value
    field = SQLiteJSONField(
        ensure_ascii=True,
        dumps=None,  # используем стандартный json.dumps
        loads=None
    )
    raw = field.db_value({"ключ": "значение"})
    # "ключ" -> "\u043a\u043b\u044e\u0447"
    assert "\\u043a" in raw and "\\u043b" in raw


def test_default_factory_is_independent():
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        data = SQLiteJSONField(default=dict)
        class Meta:
            database = db

    db.create_tables([Doc])
    d1 = Doc.create()
    d2 = Doc.create()
    d1.data["foo"] = "bar"
    # второй инстанс не должен пострадать
    d2_reload = Doc.get(Doc.id == d2.id)
    assert d2_reload.data == {}


def test_ddl_check_valid_raises_without_json1(monkeypatch):
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        f = SQLiteJSONField()
        class Meta:
            database = db

    # Форсим отсутствие JSON1
    monkeypatch.setattr("peewee_sqlite_jsonfield._check_json1", lambda db_: False)
    with pytest.raises(RuntimeError):
        Doc.f.ddl_check_valid()


def test_ddl_check_valid_string(monkeypatch):
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        f = SQLiteJSONField(db_column="mycol")
        class Meta:
            database = db

    # Форсим наличие JSON1
    monkeypatch.setattr("peewee_sqlite_jsonfield._check_json1", lambda db_: True)
    chk = Doc.f.ddl_check_valid()
    # должно быть ровно json_valid(mycol)
    assert chk.strip().lower() == "json_valid(mycol)"


def test_create_json_index_unique_and_custom_name(monkeypatch):
    db = SqliteDatabase(":memory:")
    class Doc(Model):
        data = SQLiteJSONField()
        class Meta:
            database = db

    db.create_tables([Doc])
    # Форсим наличие JSON1
    monkeypatch.setattr("peewee_sqlite_jsonfield._check_json1", lambda db_: True)

    custom_name = "idx_custom"
    idx = create_json_index(Doc, Doc.data, "$.alpha.beta", unique=True, name=custom_name)
    # Список индексов
    rows = db.execute_sql("PRAGMA index_list('doc')").fetchall()
    # rows: [(seq, name, unique, origin, partial), ...]
    names = {row[1] for row in rows}
    assert custom_name in names

    # найдём собственную запись и проверим unique-флаг
    entry = [row for row in rows if row[1] == custom_name][0]
    assert entry[2] == 1  # unique == 1


def test_json1_available_flag_matches_check_on_memory_db():
    # Флаг импортирован как константа должен совпадать c реальной проверкой
    mem_db = SqliteDatabase(":memory:")
    actual = _check_json1(mem_db)
    assert JSON1_AVAILABLE == actual


def test_field_all_exports():
    # Убедимся, что все публичные имена доступны
    from peewee_sqlite_jsonfield import __all__ as public
    for name in ("SQLiteJSONField", "create_json_index", "JSON1_AVAILABLE"):
        assert name in public
