---
name: "Configuration Templates Setup"
situation: "When setting up configuration files for a new project"
tags: ["setup", "configuration", "templates"]
created: "2025-03-24"
last_updated: "2025-03-24"
author: "Iobox Team"
version: "1.0"
inputs_required:
  - "Project configuration requirements"
expected_outputs:
  - "Properly configured environment files"
  - "Template configuration files"
---

# Configuration Templates Setup

## Context

This prompt provides guidance on setting up configuration files for a new project, including environment variables, editor configurations, and other template files. The templates are stored in the `memory-bank/templates/` directory.

## Instructions

When setting up a new project with configuration templates:

1. **Identify Required Templates**
   - Review the available templates in `memory-bank/templates/`
   - Select the appropriate templates based on project requirements

2. **Copy Templates to Project Root**
   - Use the following pattern for copying templates:
     ```bash
     cp memory-bank/templates/.template_name project_location/.actual_name
     ```
   - For example:
     ```bash
     cp memory-bank/templates/.gitignore.template .gitignore
     cp memory-bank/templates/.env.example .env.example
     cp memory-bank/templates/.env.example .env
     cp memory-bank/templates/.cursorrules .cursorrules
     ```

3. **Customize Templates**
   - Review each copied template and update as needed for the specific project
   - Pay particular attention to environment variables in `.env`
   - Ensure the `.gitignore` includes project-specific patterns

## Examples

```bash
# Create a minimal set of configuration files
cp memory-bank/templates/.gitignore.template .gitignore
cp memory-bank/templates/.env.example .env
cp memory-bank/templates/.cursorrules .cursorrules

# For more comprehensive setup
cp memory-bank/templates/.pre-commit-config.yaml.template .pre-commit-config.yaml
cp memory-bank/templates/.github/workflows/ci.yml.template .github/workflows/ci.yml
```

## Notes

- Templates provide a starting point but should be customized for each project
- Ensure sensitive information is never committed to the repository
- Consider documenting any deviation from standard templates in the project README
