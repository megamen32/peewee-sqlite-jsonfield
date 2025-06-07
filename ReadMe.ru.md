# peewee-sqlite-jsonfield

Расширение для ORM [Peewee](http://docs.peewee-orm.com/) с поддержкой работы с `JSONField` в SQLite.

- ✅ Полностью совместим с SQLite и модулем `json1`
- ✅ Простой интерфейс: как `dict`, только с SQL-поддержкой
- ✅ Поддержка индексов по JSON-путям
- ✅ Расширенные методы: `.json_extract()`, `.contains_key()` и т.д.
- ✅ Поддержка `pydantic` и кастомных сериализаторов
- ✅ Поддержка кастомных названий колонок (`db_column`)
- ✅ Гарантия, что поле содержит **валидный JSON** при включённом `CHECK`

---

## Установка

```bash
pip install peewee-sqlite-jsonfield
````

---

## Минимальный пример

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

## Почему `SQLiteJSONField` лучше `TextField`?

Обычный `TextField` не умеет:

* Проверять, что внутри валидный JSON
* Выполнять SQL-запросы по вложенным полям (`WHERE json_extract(...)`)
* Создавать JSON-индексы
* Работать с Pydantic

А `SQLiteJSONField` умеет всё это. Он использует `json1`-расширение SQLite, которое доступно по умолчанию в Python 3.9+.

---

## Поддержка запросов по JSON

```python
# WHERE meta->'$.user.name' == 'Alice'
doc = (
    Doc
    .select()
    .where(Doc.meta.json_extract('$.user.name') == 'Alice')
    .first()
)
```

> Возвращает Python-значение: `'Alice'`, а не `"Alice"` или `'"Alice"'`.

---

## Проверка, что ключ существует

```python
# WHERE json_type(json_extract(meta, '$.user.name')) IS NOT NULL
docs = Doc.select().where(Doc.meta.contains_key('$.user.name'))
```

---

## Создание индекса по JSON-пути

```python
from peewee_sqlite_jsonfield import create_json_index

create_json_index(Doc, Doc.meta, '$.user.name')
```

### С кастомным именем и уникальностью:

```python
create_json_index(Doc, Doc.meta, '$.user.name', name='idx_name', unique=True)
```

---

## Автоматическая проверка валидности JSON

Поле можно использовать в `CHECK`:

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

## Кастомные сериализаторы

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

## Null-значения

* Если в БД `NULL`, а `default=dict` → будет возвращено `{}`.
* Если явно задано `meta=None` и `null_to_empty=False` → будет возвращено `None`.

---

## Поддержка Pydantic

```python
from pydantic import BaseModel, ValidationError

class MyModel(BaseModel):
    meta: dict

m = MyModel(meta={"x": 1})  # проходит
MyModel(meta="oops")        # вызывает ValidationError
```

---

## Работа с именем колонки

```python
class Doc(Model):
    data = SQLiteJSONField(db_column="meta_data")  # колонка будет называться meta_data
```

Методы `ddl_check_valid` и `create_json_index` учитывают `db_column` автоматически.

---

## Совместимость

* Python 3.7+
* Peewee 3.14+
* SQLite 3.9+ (должен быть собран с `json1` — это стандартно в Python 3.9+)

---

## Тесты

```bash
pytest
```

Полностью покрыто:

* Кастомные сериализаторы
* Обработка мусора
* Индексация
* Вложенные ключи
* Обход кавычек (`"yes"` → `yes`)
* Проверка JSON1

---

## TODO / Планы

* [ ] Поддержка `update(..., {field.set(...): ...})`
* [ ] Дополнительные выражения: `@>`, `->`, `#>` как в Postgres
* [ ] Интеграция с Alembic (миграции с DDL CHECK)
---

## License

MIT
