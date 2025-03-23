# Prompt Integration Proposal

## Overview

This document outlines how to integrate the newly created task-specific prompts with the global `.windsurfrules` and memory bank files. The goal is to achieve a denser focus in the global context while ensuring task-specific details remain discoverable when needed.

## Proposed Changes to `.windsurfrules`

The `.windsurfrules` file should be streamlined to focus on core principles and values, with contextual references to specific prompts. Below is a proposed structure:

```markdown
# Windsurf Assistant Rules

## Memory Bank System

[Keep the core Memory Bank System introduction and high-level process]

### Memory Bank Files

[Keep this section as is]

### Memory Bank Process

[Keep the high-level process, but add prompt references]

1. **Initial Review**: At the start of each session, I will review all memory bank files
2. **Context Checking**: I will confirm my understanding of the current project status
3. **Process Adherence**: I will follow the process defined in `meta.md`
4. **Documentation Updates**: I will assist in keeping the memory bank updated

**For detailed implementation of the development cycle:** @prompt:process/development_cycle_guide

### Memory Bank Behaviors

[Keep this section as is]

## Language and Style

[Keep this section as is]

## Working Process

[Keep the high-level principles, but add prompt references for details]

### Autonomous Work

Work autonomously when there are detailed instructions and clear steps, evaluating new functionality and confirming changes haven't caused regression. If confidence in the specified plan is low, ask for clarification or undertake more detailed planning to enable longer autonomy.

### Critical Evaluation

[Keep this section as is]

### Focused Implementation

[Keep this section as is]

### Quality Assurance

[Keep this section as is]

**For detailed function implementation guidance:** @prompt:code/function_implementation_guide

## Technical Stack Defaults

[Keep high-level defaults but reference the detailed setup guide]

1. Python is the primary implementation language
2. Virtual environments (venv) are used for dependency management
3. Typer is used for CLI applications
4. FastAPI is used for API development
5. OpenAI APIs or Ollama are preferred for LLM and embeddings
6. SQLite is used for simpler projects, PostgreSQL for more complex ones

**For detailed setup instructions:** @prompt:setup/project_setup_guide

## Repository Standards

[Keep this section as is]
```

## Integration in Memory Bank Files

The memory bank files should be updated to reference prompts in relevant contexts:

### 1. Update to `meta.md`

Add a new section about prompts:

```markdown
## Prompts System

The memory bank includes a collection of task-specific prompts in the `prompts/` directory. These prompts provide detailed guidance for specific situations while keeping the core process documents focused.

### Using Prompts

1. **Reference Syntax**: Use `@prompt:[path/to/prompt]` to reference a specific prompt
2. **When to Reference**: Include prompt references when:
   - Defining implementation steps that require specific guidance
   - Documenting processes that have detailed sub-processes
   - Referencing technical patterns that should be consistently applied

### Prompt Categories

1. **Code**: Detailed guidance for code implementation (`@prompt:code/...`)
2. **Process**: Specific process implementation details (`@prompt:process/...`)
3. **Setup**: Repository and environment setup guides (`@prompt:setup/...`)
4. **Testing**: Test creation and debugging guidance (`@prompt:testing/...`)

For a complete list of available prompts, see the `prompts/README.md` file.
```

### 2. Update to `detailed-plan.md`

Add prompt references in implementation sections:

```markdown
## Implementation Steps

1. [ ] **Initialize Repository**
   - Details: Set up git in the current directory (which already contains memory-bank/)
   - Reference: @prompt:setup/project_setup_guide
   
2. [ ] **Implement Core Functionality**
   - Details: Create the main module structure and implement core features
   - Reference: @prompt:code/function_implementation_guide
```

## Contextual Triggers

To ensure discoverability, add contextual triggers that will prompt the code assistant to reference specific prompts in relevant situations:

1. **Code Editing Triggers**:
   - When modifying functions with test dependencies: @prompt:code/function_implementation_guide
   - When analyzing test failures: @prompt:testing/comprehensive_test_analysis

2. **Process Triggers**:
   - When starting a new feature implementation: @prompt:process/development_cycle_guide
   - When updating project status: @prompt:process/development_cycle_guide

3. **Setup Triggers**:
   - When initializing a new project component: @prompt:setup/project_setup_guide
   - When configuring development environments: @prompt:setup/project_setup_guide

## Implementation Steps

1. **Update `.windsurfrules`** with the streamlined structure and prompt references
2. **Add the Prompts Section to `meta.md`** to document how prompts should be used
3. **Update `detailed-plan.md`** with prompt references in implementation steps
4. **Create a Mechanism to Detect Contextual Triggers** in conversations or code edits
5. **Train Team Members** to use the @prompt reference syntax in documentation

## Benefits

This approach provides several benefits:

1. **Focused Global Context**: Core rules remain concise and principle-focused
2. **Detailed Guidance When Needed**: Task-specific details are available on demand
3. **Contextual Discovery**: Prompts are suggested based on the current task context
4. **Evolutionary Design**: New prompts can be added without modifying core rules
5. **Reduced Cognitive Load**: Users and assistants can focus on relevant guidance
