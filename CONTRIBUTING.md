# Contributing to Wenyoo

Thank you for your interest in contributing to the Wenyoo! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

## Code of Conduct

Please be respectful and constructive in all interactions. We are committed to providing a welcoming and inclusive experience for everyone.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a new branch for your changes
5. Make your changes
6. Submit a pull request

For architecture and documentation placement, also read:

- [`docs/contributing/developer-guide.md`](docs/contributing/developer-guide.md)
- [`docs/contributing/architect-design.md`](docs/contributing/architect-design.md)

## How to Contribute

### Types of Contributions

- **Bug fixes**: Fix issues in the existing codebase
- **New features**: Add new functionality to the engine
- **Documentation**: Improve or add documentation
- **Story content**: Create example stories or improve existing ones
- **Editor improvements**: Enhance the visual story editor
- **Tests**: Add or improve test coverage

### What We're Looking For

- Clear, readable code with appropriate comments
- Tests for new functionality
- Documentation updates for any changed behavior
- Backward compatibility when possible
- Engine changes that stay story-agnostic and reusable

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher (for story editor)
- Git

### Backend Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd TextAdventure

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Copy configuration files
cp config.example.yaml config.yaml
cp .env.example .env

# Add API keys only if you need a real provider
```

`config.yaml` supports named `config_groups`. If you do not pass `--config-group`, the server loads `config_groups.default`.

### Story Editor Setup

```bash
cd editor
npm install
npm run build
```

Editor-specific documentation lives under [`docs/editor/`](docs/editor/README.md).

### Running the Server

```bash
# With config_groups.default from config.yaml
python -m src.main

# Quick local test with mock mode
python -m src.main --config-group mock

# Example: use a named config group
python -m src.main --config-group claude
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_e2e_game.py
```

### Story Validation Workflow

When your change touches story data or story schema, also run:

```bash
# Validate one story
python scripts/validate_story_yaml.py stories/example.yaml

# Rebuild connections when structural relationships changed
python tools/compile_connections.py stories/example.yaml --write
```

## Code Style

### Python

- Follow [PEP 8](https://pep8.org/) style guide
- Use type hints for function parameters and return values
- Maximum line length: 100 characters
- Use descriptive variable and function names

```python
# Good
def calculate_damage(attacker: Character, defender: Character) -> int:
    """Calculate damage dealt by attacker to defender."""
    base_damage = attacker.stats.strength
    defense = defender.stats.defense
    return max(0, base_damage - defense)

# Avoid
def calc(a, d):
    return a.stats.strength - d.stats.defense
```

### JavaScript (Story Editor)

- Use ES6+ features
- Use meaningful component and variable names
- Keep components focused and small

### YAML (Stories)

- Use 2-space indentation
- Follow the format described in `prompts/story_format_description.md`
- Include comments for complex logic
- Run `python scripts/validate_story_yaml.py ...` before submitting larger story changes
- Rebuild `connections` with `python tools/compile_connections.py ... --write` when relevant
- Prefer canonical fields like `explicit_state`, `type`, and `target` in new content

### Documentation

- Keep `README.md` and `README_CN.md` as landing pages, not exhaustive manuals
- Put task-oriented user and contributor docs under `docs/`
- Treat `prompts/story_format_description.md` and `prompts/node_format_description.md` as canonical schema references
- If you update user-facing docs, sync the matching page under `docs/zh-CN/`

## Pull Request Process

### Before Submitting

1. **Test your changes**: Run the test suite and ensure all tests pass
2. **Update documentation**: If you changed behavior, update relevant docs
3. **Check code style**: Ensure your code follows the project's style guidelines
4. **Write clear commit messages**: Describe what changed and why

If you updated public-facing behavior, check whether matching changes are needed in:

- `README.md`
- `README_CN.md`
- `docs/`
- `docs/zh-CN/`
- `editor/README.md` if the visual editor behavior changed

### Commit Message Format

```
<type>: <short description>

<optional longer description>

<optional issue reference>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Example:
```
feat: add dice roll effect with success/failure branches

Implemented dice_roll effect type that allows story authors to create
skill checks with configurable difficulty and separate effect chains
for success and failure outcomes.

Closes #42
```

### Pull Request Description

Include in your PR description:
- **Summary**: What does this PR do?
- **Motivation**: Why is this change needed?
- **Testing**: How was this tested?
- **Screenshots**: If applicable (especially for UI changes)

### Review Process

1. A maintainer will review your PR
2. Address any feedback or requested changes
3. Once approved, a maintainer will merge your PR

## Reporting Bugs

### Before Reporting

- Check if the bug has already been reported in Issues
- Try to reproduce the bug with the latest version
- Gather relevant information (error messages, logs, etc.)

### Bug Report Template

```markdown
**Description**
A clear description of the bug.

**Steps to Reproduce**
1. Go to '...'
2. Click on '...'
3. See error

**Expected Behavior**
What you expected to happen.

**Actual Behavior**
What actually happened.

**Environment**
- OS: [e.g., Windows 10, macOS 14, Ubuntu 22.04]
- Python version: [e.g., 3.10.5]
- Browser: [e.g., Chrome 120] (if applicable)

**Additional Context**
Any other relevant information, logs, or screenshots.
```

## Suggesting Features

### Before Suggesting

- Check if the feature has already been suggested
- Consider if it aligns with the project's goals

### Feature Request Template

```markdown
**Problem**
What problem does this feature solve?

**Proposed Solution**
Describe your proposed solution.

**Alternatives Considered**
Any alternative solutions you've considered.

**Additional Context**
Any other relevant information or mockups.
```

## Questions?

If you have questions about contributing, feel free to:
- Open a Discussion on GitHub
- Check existing Issues for similar questions

Thank you for contributing!
