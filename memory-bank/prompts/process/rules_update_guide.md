---
name: "Windsurf Rules Update Guide"
situation: "When changes to the project rules are required based on retrospectives or continuous improvement"
tags: ["process", "rules", "updates", "maintenance"]
created: "2025-03-24"
last_updated: "2025-03-24"
author: "Iobox Team"
version: "1.0"
inputs_required:
  - "Retrospective insights or continuous improvement inputs"
  - "Current .windsurfrules content"
expected_outputs:
  - ".windsurfrules.draft file for user review"
  - "Summary of proposed changes"
---

# Windsurf Rules Update Guide

## Context

The `.windsurfrules` file is a protected system file that contains core project rules. This prompt provides a structured process for proposing updates to these rules without directly modifying the protected file.

## Instructions

When updates to the `.windsurfrules` file are needed:

1. **Review Current Rules**
   - Review the existing `.windsurfrules` content
   - Identify sections that need updates based on retrospectives or continuous improvement insights
   - Note any outdated, redundant, or missing guidance

2. **Draft Updates**
   - Create a `.windsurfrules.draft` file that includes the proposed changes
   - Maintain the original structure and formatting of the file
   - Use comments or highlighting to indicate which sections are changed
   - Include rationale for each significant change

3. **Apply Prompt Integration Principles**
   - Move detailed, task-specific instructions to appropriate prompt files
   - Replace detailed instructions with `@prompt:` references
   - Keep high-level principles and values in the main rules file
   - Ensure all referenced prompts actually exist or create them

4. **Document Changes in Retrospectives**
   - Update `retrospectives.md` with an entry explaining the rule changes
   - Include the "Rule Impact" section detailing what was updated and why
   - Reference specific prompts that were created or modified

5. **Submit for Review**
   - Present the `.windsurfrules.draft` file to the user for review
   - Provide a clear summary of changes and their rationale
   - Note any prompt files that were created or modified as part of the update

## Format for .windsurfrules.draft File

```markdown
# Windsurf Assistant Rules
# DRAFT UPDATE: [YYYY-MM-DD]
# 
# Changes Overview:
# - [Brief description of change 1]
# - [Brief description of change 2]
# - [Brief description of change 3]
#
# The following is the proposed updated rules file.
# Added content is marked with [+]
# Removed content is marked with [-]
# Modified sections are indicated with [!]

[... content with appropriate markings ...]

# End of draft update
```

## Example Change

```markdown
## Working Process

### Quality Assurance

Review tasks upon completion to ensure they meet a good definition of done and check for potential breaking changes by searching the codebase for usages of modified functions, modules, or abstractions.

[+] **For detailed function implementation guidance:** @prompt:code/function_implementation_guide

[-] ### Function Analysis Before Implementation
[-] 
[-] Before modifying any function, thoroughly analyze its test cases to understand:
[-]    - Expected input parameters and their formats 
[-]    - Field name conventions and alternative names (e.g., both 'id' and 'message_id')
[-]    - Output format expectations, including exact spacing, indentation, and ordering
[-]    - Error handling behavior and edge cases
```

## Notes

- Create or update prompts before finalizing the `.windsurfrules.draft` file
- Only the user can actually update the `.windsurfrules` file
- Document the rule update process in the project retrospective
- Consider the impact on context window when deciding what to keep in the main rules file
