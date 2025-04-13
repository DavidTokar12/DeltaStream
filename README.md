<p align="center">
  <img src="logo.png" alt="Delta Stream Logo" height="200"/>
</p>

<h1 align="center">Delta Stream</h1>
<p align="center">Structured streaming made efficient – built for real-time structured LLM output with smart deltas and validation.</p>

<div align="center">

<!-- [![PyPI version](https://badge.fury.io/py/delta-stream.svg)](https://pypi.org/project/delta-stream/) -->
<!-- [![Python Versions](https://img.shields.io/pypi/pyversions/delta-stream.svg)](https://pypi.org/project/delta-stream/)
[![License](https://img.shields.io/github/license/your-org/delta-stream)](https://github.com/your-org/delta-stream/blob/main/LICENSE) -->
<!-- [![CI](https://github.com/your-org/delta-stream/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/delta-stream/actions/workflows/ci.yml) -->
[![Coverage](https://codecov.io/gh/DavidTokar12/DeltaStream/graph/badge.svg?token=L8WPX4BHLL)](https://codecov.io/gh/DavidTokar12/DeltaStream)

</div>

<!-- <p align="center">
  <a href="https://your-project-url.com">
    <img src="https://your-image-url.com/demo.gif" alt="Delta Stream Demo" height="400"/>
  </a>
</p> -->

---

## ✨ Features

- **Efficiency** – Only triggers an update when *new* information is added.
- **Delta Mode** – Dramatically reduces bandwidth by sending only diffs.
- **Validation** – Powered by Pydantic for safe and structured data integrity.
- **Convenience** – Define stream-defaults without impacting LLM accuracy.

<!-- ---

## 📦 Installation

We recommend using [uv](https://docs.astral.sh/uv/) for fast installs:

```bash
uv add delta-stream
```

Or with pip:

```bash
pip install delta-stream
```

---

## 🚀 Usage

> TBD – usage examples and code snippets coming soon. -->

---

## ⚠️ Current Limitations

- ❌ **No custom `default_factory` support**  
  Nested Union models cannot currently define custom default factories.

- ⚠️ **Delta mode & non-empty string defaults**  
  Avoid setting non-empty string defaults when using delta mode, as this may lead to false "deltas."


## 📋 Requirements

- Python 3.10+
- pydantic >= 2.0


## 📄 License

MIT License.
