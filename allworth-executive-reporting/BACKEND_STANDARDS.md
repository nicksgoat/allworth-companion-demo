# Agent Guidelines for Python Code Quality

**Version 1.0.0 (Allworth — Flask + Python 3.11)**

> Guidance for the Flask backend. This codebase uses **Flask blueprints**,
> **pandas**, **SQLAlchemy**, **pyodbc**, **requirements.txt**, and **Ruff +
> mypy** (already configured at `backend/ruff.toml` and `backend/mypy.ini`).

---

## Core Principles

All code you write MUST be fully optimized:

- Maximize algorithmic efficiency for memory and runtime.
- Follow proper style conventions (DRY, single responsibility).
- No extra code beyond what is needed to solve the problem.
- If a library can significantly reduce code at optimal performance, use it.

---

## Preferred Tools

- Use `pip` with `backend/requirements.txt` for package management.
- Use `orjson` for JSON loading/dumping in performance-sensitive paths.
- Use `logger.error` (not `print`) for error reporting.
- Use `tqdm` to track long-running loops in Jupyter notebooks.
- Use `pandas` for DataFrames (the codebase is already on pandas).
- Use `pytest` for all testing.
- Use `Ruff` for linting and formatting (`backend/ruff.toml` is configured).
- Use `mypy` for type checking (`backend/mypy.ini` is configured).

---

## Code Style and Formatting

- Use meaningful, descriptive variable and function names.
- Follow PEP 8 style guidelines.
- Use 4 spaces for indentation (never tabs).
- **NEVER** use emoji in Python source code.
- Use snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants.
- Limit line length to 88 characters (Ruff standard).
- Avoid tautological comments — don't comment what the code already says.

---

## Documentation

Include docstrings for all public functions, classes, and methods.

```python
def calculate_total(items: list[dict], tax_rate: float = 0.0) -> float:
    """Calculate the total cost of items including tax.

    Args:
        items: List of item dictionaries with 'price' keys.
        tax_rate: Tax rate as decimal (e.g. 0.08 for 8%).

    Returns:
        Total cost including tax.

    Raises:
        ValueError: If items is empty or tax_rate is negative.
    """
```

---

## Type Hints

- Use type hints for all function signatures.
- Avoid `Any` unless absolutely necessary.
- Run mypy and resolve all type errors (new packages: `investments/`, `email_batch/`).
- Use `T | None` for nullable types (Python 3.10+ style).

---

## Error Handling

- **NEVER** silently swallow exceptions without logging.
- **NEVER** use bare `except:`.
- Catch specific exceptions rather than broad `Exception` where practical.
- Use context managers (`with`) for resource cleanup.
- Use `contextlib.suppress(SpecificError)` instead of `try/except: pass`.
- Provide meaningful error messages.

```python
# ❌
except:
    pass

# ✅
except (ValueError, KeyError) as exc:
    logger.warning("Failed to parse response: %s", exc)
```

---

## Function Design

- Keep functions focused on a single responsibility.
- **NEVER** use mutable objects as default argument values.
- Limit function parameters to 5 or fewer.
- Return early to reduce nesting.

```python
# ❌
def validate(users):
    for user in users:
        if user.email:
            if user.name:
                process(user)

# ✅
def validate(users):
    for user in users:
        if not user.email: return False
        if not user.name:  return False
        process(user)
    return True
```

---

## Flask Blueprint Conventions

This codebase registers tools as Flask blueprint packages. Each tool lives under
`backend/<tool>/` with a `routes.py` that defines `bp`.

- Register blueprints in `backend/app.py` using the defensive `try/except` pattern:

```python
try:
    from my_tool.routes import bp as my_tool_bp
    app.register_blueprint(my_tool_bp, url_prefix="/api/my-tool")
    print("My Tool blueprint registered")
except Exception as _e:  # pragma: no cover - defensive
    print(f"My Tool blueprint unavailable: {type(_e).__name__}: {_e}")
```

- Keep route handlers thin: validate input → call service → return response.
- Business logic lives in a separate `service.py` or `services/` module, not in routes.
- Use `pydantic` `BaseModel` for request/response schemas in new blueprints.
- Return consistent JSON error shapes: `{"detail": "message"}` with appropriate HTTP status.

---

## Database / DataWarehouse

- Use **parameterised queries** — never construct SQL with string interpolation.
- Use `with db_session() as session:` (or equivalent context manager) so sessions are always closed.
- Use `contextlib.suppress(Exception)` when closing sessions that may emit rollback noise.
- Authenticate via `AUTH_METHOD` env var (`SqlPassword`, `ServicePrincipal`, `ActiveDirectoryInteractive`).
- Read credentials from environment variables only — never hardcode.

---

## Security

- **NEVER** store secrets, API keys, or passwords in code. Use `backend/.env`.
- Ensure `backend/.env` is in `.gitignore` (it is).
- **NEVER** log passwords, tokens, or PII.
- **NEVER** log URLs containing API keys.
- Use environment variables for all sensitive configuration.

---

## Testing

- Write unit tests for all new functions and classes.
- Mock external dependencies (APIs, databases, file systems).
- Use pytest as the testing framework.
- Save tests as discrete files before running them.
- Never delete test files.
- Follow the Arrange-Act-Assert pattern.
- Do not commit commented-out tests.

```python
def test_parse_workbook_returns_groups():
    # Arrange
    content = build_test_workbook(...)
    # Act
    result = parse_workbook(content, "test.xlsx")
    # Assert
    assert len(result.groups) > 0
```

---

## Imports and Dependencies

- **NEVER** use wildcard imports (`from module import *`).
- Add new dependencies to `backend/requirements.txt`.
- Organise imports: standard library → third-party → local.
- Ruff handles import sorting automatically (`I001`).

---

## Python Best Practices

- **NEVER** use mutable default arguments.
- Use context managers for file/resource management.
- Use `is` for comparing with `None`, `True`, `False`.
- Use f-strings for string formatting.
- Use list comprehensions and generator expressions.
- Use `enumerate()` instead of manual counter variables.
- Use `toSorted()` / `toReversed()` instead of `sort()` / `reverse()` when immutability matters.

---

## Before Committing

- [ ] All tests pass (`python -m pytest tests/ -q`)
- [ ] Type checking passes (`mypy investments/ email_batch/`)
- [ ] Ruff passes (`ruff check .`)
- [ ] All new public functions have docstrings and type hints
- [ ] No commented-out code or debug statements
- [ ] No hardcoded credentials

---

**Remember:** Prioritize clarity and maintainability over cleverness.
