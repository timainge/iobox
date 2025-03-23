---
name: "Project Setup Guide"
situation: "When initializing a project repository or setting up new components"
tags: ["setup", "repository", "environment", "configuration"]
created: "2025-03-24"
last_updated: "2025-03-24"
author: "Iobox Team"
version: "1.0"
inputs_required:
  - "Project requirements from project-background.md"
  - "Technical stack decisions"
expected_outputs:
  - "Repository structure"
  - "Environment configuration"
  - "Initial project files"
---

# Project Setup Guide

## Context

This guide provides detailed instructions for initializing a project repository and setting up the development environment according to project standards. It includes specific guidance on repository structure, configuration files, and environment setup to ensure consistency across projects.

## Instructions

### Repository Structure Setup

Create a standardized project structure with these components:

```
project-root/
├── memory-bank/    (Project management and context)
├── src/            (Application source code)
│   └── [project_name]/
│       ├── __init__.py
│       ├── main.py
│       └── [module_directories]/
├── tests/          (Test files)
│   ├── unit/       (Unit tests)
│   └── integration/ (Integration tests)
├── docs/           (Documentation)
├── README.md       (Project README)
├── .gitignore      (Git ignore rules)
├── .env.example    (Template for environment variables)
└── requirements.txt (Python dependencies)
```

### Technical Stack Implementation

#### Python Environment

1. **Virtual Environment Setup**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   ```

2. **Core Dependencies**
   ```bash
   pip install typer pydantic fastapi pytest
   pip freeze > requirements.txt
   ```

#### CLI Application with Typer

Create a basic CLI structure:

```python
# src/[project_name]/cli.py
import typer

app = typer.Typer()

@app.command()
def hello(name: str = "World"):
    """Say hello to someone."""
    print(f"Hello {name}!")

if __name__ == "__main__":
    app.run()
```

#### API Development with FastAPI

Set up a basic API structure:

```python
# src/[project_name]/api.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}
```

### Repository Configuration Files

#### .gitignore Setup

Create a comprehensive .gitignore:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environments
venv/
ENV/

# Environment variables
.env

# IDE specific files
.idea/
.vscode/
*.swp
*.swo

# OS specific files
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db
```

#### Environment Variables

Create a .env.example template:

```
# API Keys
API_KEY=your_api_key_here

# Database Configuration
DB_USER=username
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=database_name

# Application Settings
DEBUG=False
LOG_LEVEL=INFO
```

### README.md Template

Create a comprehensive README:

```markdown
# Project Name

Brief description of the project and its purpose.

## Features

- Feature 1: Description
- Feature 2: Description
- Feature 3: Description

## Installation

```bash
# Clone the repository
git clone https://github.com/username/project.git
cd project

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your values
```

## Usage

```bash
# Basic usage example
python -m project_name command

# More examples...
```

## Development

```bash
# Run tests
pytest

# More development instructions...
```

## License

Specify the license.
```

## Examples

### Example Project Structure for a CLI Tool

```
my-cli-tool/
├── memory-bank/
├── src/
│   └── mycli/
│       ├── __init__.py
│       ├── cli.py
│       ├── commands/
│       └── utils/
├── tests/
│   └── test_cli.py
├── README.md
├── .gitignore
├── .env.example
└── requirements.txt
```

### Example Project Structure for an API

```
my-api-service/
├── memory-bank/
├── src/
│   └── myapi/
│       ├── __init__.py
│       ├── main.py
│       ├── api.py
│       ├── models/
│       ├── routers/
│       └── services/
├── tests/
│   ├── unit/
│   └── integration/
├── README.md
├── .gitignore
├── .env.example
└── requirements.txt
```

## Notes

- Adjust the structure based on specific project requirements
- Document any deviations from standard structure in project-background.md
- For simpler projects, some directories may be omitted
- Always create a comprehensive README.md with setup and usage instructions
