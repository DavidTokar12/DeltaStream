<p align="center">
  <img src="https://github.com/DavidTokar12/DeltaStream/blob/main/logo.png" alt="Delta Stream Logo" height="200"/>
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

---

## ✨ Features

- **Efficiency** – Only triggers updates when *new* information is added.
- **Delta Mode** – Dramatically reduces bandwidth by sending only the changed values.
- **Validation** – Powered by Pydantic for safe and structured data integrity.
- **Convenience** – Define stream defaults without compromising LLM accuracy.

---

## 📦 Installation

```bash
pip install delta_stream
```

Or with Poetry:

```bash
poetry add delta_stream
```

---

## 🚀 Usage

### Basic Parsing

```python
from delta_stream import JsonStreamParser
from openai import OpenAI
from pydantic import BaseModel

class ShortArticle(BaseModel):
    title: str
    description: str
    key_words: list[str]

# Initialize the stream parser with your Pydantic model
# Delta stream will try to initialize reasonable defaults for your model, see defaults section
stream_parser = JsonStreamParser(data_model=ShortArticle)

client = OpenAI()

with client.beta.chat.completions.stream(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Write short articles with a 1-sentence description."},
        {"role": "user", "content": "Write an article about why it's worth keeping moving forward."},
    ],
    response_format=ShortArticle,
) as stream:
    for event in stream:
        if event.type == "content.delta" and event.parsed is not None:
            parsed: ShortArticle | None = stream_parser.parse_chunk(event.delta)

            # If no valuable information was added by the delta(e.g the LLM is writing a key within a json) parsed will be None
            if parsed is None:
                continue

            # Valid ShortArticle object, with stream defaults
            print(parsed)
```

**Sample output:**
```
title='The' description='' key_words=[]
title='The Importance' description='' key_words=[]
title='The Importance of' description='' key_words=[]
...
title='The Importance of Perseverance in Personal Growth' description='Moving forward, despite challenges, is crucial for personal growth as it fosters resilience, opens new opportunities, and leads to self-discovery.' key_words=['perseverance', 'resilience', 'personal growth', 'challenges', 'opportunities', 'self-discovery']
```

---

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

📝 **Note:** Delta Mode only affects how **strings** are streamed. Booleans, numbers, and `None` values are included in every update.

⚠️ **Warning:** Do **not** define non-empty defaults for strings when using Delta Mode. Doing so makes it impossible to reconstruct the full stream correctly on the frontend. 

---


### Defaults

To ensure that each streamed delta can be parsed into a valid Pydantic model, Delta Stream tries to assign default values to all fields.

#### 🔧 Predefined defaults:

Delta Stream automatically applies the following defaults unless overridden:

- **str** → `""` (empty string)
- **list** → `[]` (empty list)
- **None / Optional[...]** → `None`
- **Nested Pydantic models** → Uses the nested model's default factory
- **Unions** → Chooses a default in this priority: `str` > `list` > `None` (if present)

If you provide an explicit default for a field, Delta Stream will use that instead of the predefined one.

> ⚠️ It's recommended **not** to set standard Pydantic defaults for strings or lists in streamed models. This can degrade LLM output quality and conflict with OpenAI's strict mode.

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
    article_number: int | None
    content: ArticleContent
```

**Sample output:**
```
title='' article_number=None content=ArticleContent(description='', key_words=[])
title='The' article_number=None content=ArticleContent(description='', key_words=[])
title='The Value' article_number=None content=ArticleContent(description='', key_words=[])
...
```

> ⚠️ For numerical or boolean values you must define a default(or stream_default preferably) because Delta Stream can't figure out a reasonable default for these values and has to throw a DeltaStreamModelBuildError when you instantiate the JsonStreamParser class.

---

## ⚠️ Current Limitations

- ❌ **No custom `default_factory` support**  
  Custom default factories don't work with delta stream at the moment, so there is no reasonable way to use nested classes in unions.

- ⚠️ **Delta Mode & non-empty string defaults**  
  Avoid setting non-empty string defaults when using delta mode, as they can cause false-positive deltas.

---

## 📋 Requirements

- Python 3.10+
- `pydantic >= 2.0`

---

## 📄 License

MIT License.


