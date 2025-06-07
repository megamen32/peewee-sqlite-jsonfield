# peewee-sqlite-jsonfield

Extension for the [Peewee](http://docs.peewee-orm.com/) ORM with `JSONField` support in SQLite.

- ✅ Fully compatible with SQLite and the `json1` module
- ✅ Simple interface: behaves like a `dict` but with SQL support
- ✅ Support for indexes on JSON paths
- ✅ Extended methods: `.json_extract()`, `.contains_key()`, etc.
- ✅ Integration with `pydantic` and custom serializers
- ✅ Custom column names (`db_column`) supported
- ✅ Guarantees field contains **valid JSON** when `CHECK` is enabled

---

## Installation

```bash
pip install peewee-sqlite-jsonfield
```

---

## Minimal example

```python
from peewee import Model, SqliteDatabase
from peewee_sqlite_jsonfield import SQLiteJSONField

db = SqliteDatabase('my.db')

class Doc(Model):
    meta = SQLiteJSONField(default=dict)

    class Meta:
        database = db

db.connect()
db.create_tables([Doc])

doc = Doc.create(meta={"user": {"name": "Alice"}})
print(doc.meta)                         # => {'user': {'name': 'Alice'}}
print(doc.meta["user"]["name"])        # => 'Alice'
```

---

## Why is `SQLiteJSONField` better than `TextField`?

A regular `TextField` cannot:

* Validate that the value is proper JSON
* Perform SQL queries on nested fields (`WHERE json_extract(...)`)
* Create JSON indexes
* Work with Pydantic

`SQLiteJSONField` can do all of this. It uses SQLite's `json1` extension which is available by default in Python 3.9+.

---

## Querying JSON

```python
# WHERE meta->'$.user.name' == 'Alice'
doc = (
    Doc
    .select()
    .where(Doc.meta.json_extract('$.user.name') == 'Alice')
    .first()
)
```

> Returns the Python value `'Alice'`, not "Alice" or `'"Alice"'`.

---

## Checking if a key exists

```python
# WHERE json_type(json_extract(meta, '$.user.name')) IS NOT NULL
docs = Doc.select().where(Doc.meta.contains_key('$.user.name'))
```

---

## Creating an index on a JSON path

```python
from peewee_sqlite_jsonfield import create_json_index

create_json_index(Doc, Doc.meta, '$.user.name')
```

### With a custom name and uniqueness:

```python
create_json_index(Doc, Doc.meta, '$.user.name', name='idx_name', unique=True)
```

---

## Automatic JSON validity check

The field can be used in a `CHECK` constraint:

```python
class Doc(Model):
    meta = SQLiteJSONField()

    class Meta:
        database = db
        table_settings = [
            SQLiteJSONField().ddl_check_valid()  # 'json_valid(meta)'
        ]
```

---

## Custom serializers

```python
import json

def my_dumps(obj):
    return json.dumps(obj, indent=2)

def my_loads(s):
    return json.loads(s)

class Doc(Model):
    meta = SQLiteJSONField(dumps=my_dumps, loads=my_loads)
```

---

## Null handling

* If the DB value is `NULL` and `default=dict` → `{}` is returned.
* If explicitly set to `meta=None` and `null_to_empty=False` → `None` is returned.

---

## Pydantic support

```python
from pydantic import BaseModel, ValidationError

class MyModel(BaseModel):
    meta: dict

m = MyModel(meta={"x": 1})  # passes
MyModel(meta="oops")        # raises ValidationError
```

---

## Working with column name

```python
class Doc(Model):
    data = SQLiteJSONField(db_column="meta_data")  # column name will be meta_data
```

Methods `ddl_check_valid` and `create_json_index` automatically take `db_column` into account.

---

## Compatibility

* Python 3.7+
* Peewee 3.14+
* SQLite 3.9+ (should be built with `json1` — standard in Python 3.9+)

---

## Tests

```bash
pytest
```

Test coverage includes:

* Custom serializers
* Garbage collection
* Indexing
* Nested keys
* Quote unwrapping (`"yes"` → `yes`)
* JSON1 check

---

## TODO / Plans

* [ ] Support `update(..., {field.set(...): ...})`
* [ ] Additional expressions: `@>`, `->`, `#>` like in Postgres
* [ ] Integration with Alembic (migrations with DDL CHECK)

---

## License

MIT
