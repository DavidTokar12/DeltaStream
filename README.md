<p align="center">
  <img src="https://raw.githubusercontent.com/DavidTokar12/DeltaStream/main/logo.png" alt="Delta Stream Logo" height="200"/>
</p>

<h1 align="center">Delta Stream</h1>
<p align="center">Structured streaming made efficient – built for real-time structured LLM output with smart deltas and validation.</p>

<div align="center">

[![PyPI version](https://badge.fury.io/py/delta-stream.svg)](https://pypi.org/project/delta-stream/)
[![Python Versions](https://img.shields.io/pypi/pyversions/delta-stream.svg)](https://pypi.org/project/delta-stream/)
[![License](https://img.shields.io/github/license/DavidTokar12/DeltaStream)](https://github.com/DavidTokar12/DeltaStream/blob/main/LICENSE)
[![CI](https://github.com/DavidTokar12/DeltaStream/actions/workflows/ci.yml/badge.svg)](https://github.com/DavidTokar12/DeltaStream/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/DavidTokar12/DeltaStream/graph/badge.svg?token=L8WPX4BHLL)](https://codecov.io/gh/DavidTokar12/DeltaStream)

</div>

Delta Stream is a lightweight package for validating and parsing structured streams. It was created to handle real-time structured LLM outputs in one place – and do it efficiently.

---

## Installation

```bash
pip install delta_stream
```

---

## How it works

You define the expected structure of the stream using a `Pydantic` model:

```python
class Todo(BaseModel):
    task: str
    is_boring: bool | None
```

Then, pass the model to `JsonStreamParser`, which builds a copy of your model with default values:

```python
from delta_stream import JsonStreamParser

stream_parser = JsonStreamParser(data_model=Todo)
```

Now stream your incoming chunks through `parse_chunk`:

```python
task_str = '{"task":"study","is_boring": true}'
for chunk in task_str:
    result: Todo | None = stream_parser.parse_chunk(chunk)
```

Under the hood, `parse_chunk` uses a state machine to process only the incoming characters. If the chunk contains no meaningful data (e.g., just partial keys or syntax), it returns `None` – saving you resources, especially when forwarding to a frontend.

When meaningful data is detected, Delta Stream aggressively (more so than Pydantic’s `partial=True` parser) completes the partial string into valid JSON, then validates it using your model.

```
'{"ta'          -> None
'{"tas'         -> None
'{"task'        -> None
'{"task"'       -> None
'{"task":'      -> None  # Until now, no valuable data was streamed
'{"task":"s'    -> task='s' is_boring=None  # is_boring is None by default
...
'{"task":"study","is_boring": tru'  -> None
'{"task":"study","is_boring": true' -> task='study' is_boring=True
'{"task":"study","is_boring": true}' -> task='study' is_boring=True
```

---

## Example usage with `OpenAI`

```python
from delta_stream import JsonStreamParser
from openai import OpenAI
from pydantic import BaseModel

class ShortArticle(BaseModel):
    title: str
    description: str
    key_words: list[str]

stream_parser = JsonStreamParser(data_model=ShortArticle)

client = OpenAI()

with client.beta.chat.completions.stream(
    model="gpt-4o",
    messages=[],
    response_format=ShortArticle,
) as stream:
    for event in stream:
        if event.type == "content.delta" and event.parsed is not None:
            parsed: ShortArticle | None = stream_parser.parse_chunk(event.delta)

            if parsed is None:
                continue

            print(parsed)  # process valid ShortArticle object
```

### Delta Mode

In typical backend–frontend streaming, it's wasteful to send the full parsed object for every partial update. **Delta Mode** solves this by only including fields that changed in the last delta.

On the frontend, you can aggregate these partial updates by key to reconstruct and display the full object over time.

```python
stream_parser = JsonStreamParser(
    data_model=ShortArticle,
    delta_mode=True
)
```

**Sample output:**
```
title='The' description='' key_words=[]
title=' Power' description='' key_words=[]
title=' of' description='' key_words=[]
...
title='' description='' key_words=['', '', '', '', '', '', 'mot']
title='' description='' key_words=['', '', '', '', '', '', 'ivation']
```

> Only the fields that changed in the last update are populated. All others are set to their default, reducing payload size.

**Note:** Delta Mode only affects how **strings** are streamed. Booleans, numbers, and `None` values are included in every update.

**Warning:** Do **not** define non-empty defaults for strings when using Delta Mode. Doing so makes it impossible to reconstruct the full stream correctly on the frontend.

---

### Defaults

To ensure that each streamed delta can be parsed into a valid `Pydantic` model, Delta Stream must assign default values to all fields. For convenience, Delta Stream will automatically assign some fields with predefined defaults.

#### 🔧 Predefined defaults:

Delta Stream automatically applies the following defaults unless overridden:

- **str** → `""` (empty string)
- **list** → `[]` (empty list)
- **None / Optional[...]** → `None`
- **Nested Pydantic models** → Uses the nested model's default factory
- **Unions** → Chooses a default in this priority: `str` > `list` > `None` (if present)

If you provide an explicit default for a field, Delta Stream will use that instead of the predefined one.

> ⚠️ It's recommended **not** to set standard Pydantic defaults as this can degrade LLM output quality and conflict with OpenAI's strict mode. If the field is not a true default, use a `stream_default` value instead.

---

### Stream Defaults

To define safe, informative default values **without compromising generation accuracy**, use the `stream_default` field parameter:

```python
from pydantic import BaseModel, Field

class ShortArticle(BaseModel):
    article_number: int | None
    title: str = Field(json_schema_extra={"stream_default": "Title"})
    key_words: list[str]
```

**Sample output:**
```
key_words=[''] title='Title' article_number=None
key_words=['per'] title='Title' article_number=None
key_words=['perse'] title='Title' article_number=None
...
```

---

### Nested Models

Delta Stream supports default generation for nested models as well:

```python
class ArticleContent(BaseModel):
    description: str
    key_words: list[str]

class ShortArticle(BaseModel):
    title: str
    content: ArticleContent
```

**Sample output:**
```
title='' content=ArticleContent(description='', key_words=[])
title='The' content=ArticleContent(description='', key_words=[])
title='The Value' content=ArticleContent(description='', key_words=[])
...
```

> ⚠️ For numerical or boolean values you must define a default (or `stream_default`, preferably) because Delta Stream can't figure out a reasonable default for these values and will raise a `DeltaStreamModelBuildError` when you instantiate the `JsonStreamParser` class.

---

## ⚠️ Current Limitations

- ❌ **No custom `default_factory` support**  
  Custom default factories don't work with Delta Stream at the moment, so there's no reliable way to use nested classes inside `Union`s, for example. (Most models used for structured LLM output are supported.)

- ⚠️ **Delta Mode & non-empty string defaults**  
  Avoid setting non-empty string defaults when using Delta Mode, because you won't be able to reconstruct the object correctly on your frontend.

---

## Requirements

- Python 3.10+
- `pydantic >= 2.0`

---

## License

MIT License.

