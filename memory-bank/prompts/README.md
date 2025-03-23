# Prompts Collection

This folder contains task-specific and situation-specific prompts that complement the general rules and processes defined in the memory bank system. Separating these prompts helps maintain a focused memory bank while providing specialised guidance when needed.

## Purpose

The prompts collection serves to:
1. Provide reusable, optimised instructions for common tasks
2. Capture expert workflows that might be too detailed for general rules
3. Allow for situation-specific guidance without diluting core processes
4. Maintain a library of proven effective prompts for consistent results

## Prompt Format

All prompts should follow this standardised format with YAML frontmatter:

```yaml
---
name: "Descriptive Name of Prompt"
situation: "When to use this prompt (specific task or scenario)"
tags: ["tag1", "tag2", "tag3"]
created: "YYYY-MM-DD"
last_updated: "YYYY-MM-DD"
author: "Original creator"
version: "1.0"
inputs_required:
  - "List specific inputs needed for this prompt to work effectively"
  - "For example: code file path, function name, etc."
expected_outputs:
  - "What outcomes this prompt should produce"
  - "For example: refactored code, test cases, documentation"
---

# [Prompt Title]

## Context
[Brief explanation of when to use this prompt and what problem it solves]

## Instructions
[Clear, step-by-step instructions for the specific task]

## Examples
[Optional: Example inputs and expected outputs]

## Notes
[Optional: Additional information, limitations, or considerations]
```

## Organisation

Prompts are organised in subdirectories by category:
- `code/` - Code-related prompts (refactoring, analysis, etc.)
- `testing/` - Test creation and debugging prompts
- `documentation/` - Documentation generation prompts
- `planning/` - Planning and design prompts
- `review/` - Code review and quality assessment prompts

## Usage Guidelines

1. **Reference prompts** in conversations using the format: `@prompt:[name]`
2. **Search for prompts** by tags or situations using the memory bank search functionality
3. **Create new prompts** when you find yourself repeating similar instructions
4. **Update existing prompts** when improvements are identified
5. **Document prompt effectiveness** in the retrospectives

## Relationship to Memory Bank

The prompts collection complements the memory bank by:
1. Keeping the core process documents focused on general principles and workflows
2. Providing specialised, detailed guidance for specific tasks
3. Enabling experimentation with new approaches without changing core processes

## Prompt Development Lifecycle

1. **Creation**: Identify a repeating task or situation requiring specific guidance
2. **Testing**: Use the prompt in actual work to validate effectiveness
3. **Refinement**: Improve based on outcomes and user feedback
4. **Integration**: Reference in relevant memory bank documents
5. **Maintenance**: Update periodically based on learnings from retrospectives

When creating new prompts, remember to apply the principles from our continuous improvement process to ensure they remain effective and relevant.
