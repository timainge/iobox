# Memory Bank Process and Guidelines

⚠️ **IMPORTANT: THIS DOCUMENT DEFINES HOW TO USE THE MEMORY BANK SYSTEM** ⚠️

This document defines how to use the memory bank system effectively for maintaining project context and collaboration between users and AI assistants.

## Memory Bank Purpose

The memory bank serves as a persistent, structured knowledge repository that:
1. Maintains consistent context across AI assistant sessions
2. Provides a single source of truth for project information
3. Enforces a methodical approach to planning and implementation
4. Documents important decisions and rationale
5. Supports effective collaboration between humans and AI tools

## Status Tracking and Authority

⚠️ **CRITICAL: STATUS TRACKING HIERARCHY AND AUTHORITY** ⚠️

The memory bank system uses the following hierarchy for tracking project status:

1. **`high-level-plan.md`** - **PRIMARY STATUS AUTHORITY**
   - Records status of overall project phases and major milestones
   - All phase status updates MUST be reflected here first
   - Serves as the authoritative shared representation of intent and consensus
   - Contains Success Metrics for each phase which are updated as they are achieved

2. **`detailed-plan.md`** - **IMPLEMENTATION STATUS AUTHORITY**
   - Maintains detailed implementation steps and their status
   - Contains the authoritative status for current feature implementation
   - All implementation steps should be tracked with clear status indicators
   - Progress updates should be dated and include specific achievements

3. **`todo.md`** - **SUPPORTING TASK TRACKER**
   - Used ONLY for working-level tasks that don't fit within the structure of high-level or detailed plans
   - Appropriate for tasks with different scope or feature affinity than current plan focus
   - NOT the authoritative source for project status or phase completion
   - Tasks that represent core milestones should be promoted to appropriate plan files

**Important**: When there are discrepancies between files, the hierarchy above determines which file takes precedence. Always resolve conflicts by updating lower-authority documents to match higher ones.

## Memory Bank Process Overview

The Memory Bank system operates in two distinct phases:
1. **Initialization Phase** (one-time setup) - Establish project foundations
2. **Development Cycle** (continuous process) - Iterative development using the OODA loop

### Initialization Phase (One-Time Setup)

⚠️ **FOLLOW THIS SEQUENCE EXACTLY - DO NOT SKIP STEPS** ⚠️

1. Complete `project-background.md` (FIRST, before anything else)
2. Update `high-level-plan.md` (SECOND)
3. Follow project setup instructions in `detailed-plan.md` (THIRD)
4. Have AI review ALL memory bank files (FOURTH)
5. Ask for more info or record questions, enhancements or opportunities in `todo.md` (FIFTH)
6. Begin implementation work (ONLY AFTER completing steps 1-5)

### Development Cycle (Continuous Process)

After initialization, development follows an OODA loop (Observe, Orient, Decide, Act):

1. **Observe** - Review current state of the project
   - Update `scratchpad.md` with observations
   - Review high-level-plan.md and detailed-plan.md for current status
   - Use todo.md only for supporting tasks not covered in plans

2. **Orient** - Analyze and prioritize
   - Update `detailed-plan.md` for the current feature
   - Revise `high-level-plan.md` if priorities shift
   - Document decisions and their rationale

3. **Decide** - Choose implementation approach
   - Determine specific implementation steps
   - Update primary plans with new status information
   - Add supporting tasks to `todo.md` only if they don't fit in the plans

4. **Act** - Implement and validate
   - Execute implementation according to plan
   - Document challenges and solutions
   - Update high-level-plan.md and detailed-plan.md with current status

Repeat this cycle for each feature or major component of the project.

## Process Guidelines

### Project Initialization

1. **Gather Initial Requirements**
   - Fill out the `project-background.md` completely
   - Replace ALL placeholder text with specific project details
   - Document initial technical choices and constraints
   - Define success criteria and evaluation metrics

2. **Create Initial Project Plan**
   - Complete the `high-level-plan.md` with project phases
   - Replace ALL placeholder text with specific dates and milestones
   - Set realistic timelines for each phase
   - Document dependencies and potential risks with specific details

3. **Setup Development Environment**
   - Follow the project setup instructions in `detailed-plan.md` EXACTLY
   - Initialize the development environment with required dependencies
   - DO NOT begin coding until memory bank is fully configured

### Feature Development Cycle

1. **Planning Phase**
   - Update `high-level-plan.md` to reflect current priorities
   - Create detailed plan in `detailed-plan.md` with status "Planning"
   - Include specific implementation steps with acceptance criteria
   - Use `scratchpad.md` for collaborative brainstorming

2. **Implementation Phase**
   - Update `detailed-plan.md` status to "Implementing"
   - Check off completed steps in the plan as you progress
   - Document challenges and solutions in the plan as they arise
   - Add items to `todo.md` ONLY for tasks that don't fit within plan structures

3. **Completion Phase**
   - Update `high-level-plan.md` and `detailed-plan.md` status to "Complete"
   - Document lessons learned and implementation notes
   - Move completed tasks in `todo.md` to the "Completed" section
   - Ensure all status indicators across files are consistent

## Memory Bank Maintenance Rules

1. **Regular Updates**
   - Update relevant memory bank files at the START of each development session
   - Keep the `high-level-plan.md` current as the PRIMARY status authority
   - Review and clean up the `scratchpad.md` at least weekly
   - Never delete memory bank files; only update them

2. **Decision Documentation**
   - Document ALL significant technical decisions with context and rationale
   - Include alternatives considered and specific reasons for rejection
   - Link decisions to requirements or constraints where applicable
   - Date each decision for future reference

3. **Status Consistency**
   - Always update status in high-level-plan.md FIRST, then detailed-plan.md
   - When updating status, include specific achievements and date
   - Use consistent status terminology across all files (e.g., "Planning", "Implementing", "Complete")
   - Resolve any status inconsistencies by following the status tracking hierarchy

4. **Context Preservation**
   - Ensure all memory bank files are consistent with each other
   - When changes are made to `project-background.md`, update all affected files
   - Maintain clear status indicators in all planning documents
   - Never contradict information between memory bank files

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

## Continuous Improvement Process

The memory bank system includes a structured approach to continuous improvement through regular retrospectives and rule refinement.

### Retrospective Triggers

Conduct retrospectives at these specific moments:

1. **After Debugging Sessions** - When solving challenging problems that reveal systemic issues
2. **Milestone Completion** - Upon finishing items in the high-level plan
3. **Test Failure Patterns** - When similar failures occur across multiple tests
4. **Quarterly Reviews** - Regular scheduled reviews regardless of project progress

### Capturing Learnings

Structure retrospective learnings in the following format:

1. **Context**: Brief description of the situation that triggered the retrospective
2. **Challenge**: The specific problem or obstacle encountered
3. **Solution**: How the challenge was overcome
4. **Insight**: The broader principle or pattern identified
5. **Rule Impact**: How existing rules should be updated or new rules created

All retrospective insights should be recorded in a dedicated file: `retrospectives.md`

### Rule Usage Logging

Track the effectiveness of project rules using a structured logging approach:

1. When applying a specific rule from `.windsurfrules`, record:
   ```
   [YYYY-MM-DD] [RULE_SECTION] [BRIEF_DESCRIPTION] [OUTCOME]
   ```

2. Example log entry:
   ```
   [2025-03-23] [Function Analysis] Applied to markdown.py - Fixed 4 failing tests
   ```

3. Store these entries in `rules_usage.log` for analysis during quarterly reviews


---
*Review this meta document at the beginning of each project phase to ensure everyone follows the memory bank process consistently.*
