# Contributing to hr-project-map

Thank you for your interest in contributing. This project is maintained by
Josiah Wilson and is MIT-licensed — contributions are welcome under the
same license.

## How to contribute

1. **File an issue first** for anything beyond a trivial fix: describe the
   problem or proposal on GitHub Issues
   (https://github.com/josiahwilson-bit/hr-project-map/issues). This avoids
   duplicated or unwanted work.
2. **Fork, branch, and submit a pull request** against `main`. Keep changes
   focused; one concern per pull request.
3. **Tests are required.** New functionality must include tests following
   the existing style in `tests/`. Run the full suite before submitting:
   `python3 -m unittest discover -s tests -v`
   All 49 existing tests must keep passing.
4. **Documentation.** Update README.md and/or docs/ when behavior changes.

## Reporting bugs

File an issue at https://github.com/josiahwilson-bit/hr-project-map/issues
with: what you did, what you expected, what happened instead, and your
Python version. For security issues, see SECURITY.md instead — do not
file them as public issues.

## What we're looking for

- Bug fixes with regression tests
- Documentation improvements and worked examples
- Interoperability (import/export formats)
- Test coverage for untested paths

## License

By contributing, you agree your contributions are licensed under the
MIT License. No contributor license agreement is required.
