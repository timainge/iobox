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
   - Review completed and pending tasks in `todo.md`

2. **Orient** - Analyze and prioritize
   - Update `detailed-plan.md` for the current feature
   - Revise `high-level-plan.md` if priorities shift
   - Document decisions and their rationale

3. **Decide** - Choose implementation approach
   - Determine specific implementation steps
   - Update `todo.md` with new tasks
   - Finalize feature implementation plan

4. **Act** - Implement and validate
   - Execute implementation according to plan
   - Document challenges and solutions
   - Update memory bank files to reflect progress

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
   - Add items to `todo.md` for minor tasks that emerge

3. **Completion Phase**
   - Update `detailed-plan.md` status to "Complete"
   - Document lessons learned and implementation notes
   - Move completed tasks in `todo.md` to the "Completed" section
   - Update `high-level-plan.md` to reflect progress

## Memory Bank Maintenance Rules

1. **Regular Updates**
   - Update relevant memory bank files at the START of each development session
   - Keep the `high-level-plan.md` current as priorities shift
   - Review and clean up the `scratchpad.md` at least weekly
   - Never delete memory bank files; only update them

2. **Decision Documentation**
   - Document ALL significant technical decisions with context and rationale
   - Include alternatives considered and specific reasons for rejection
   - Link decisions to requirements or constraints where applicable
   - Date each decision for future reference

3. **Context Preservation**
   - Ensure all memory bank files are consistent with each other
   - When changes are made to `project-background.md`, update all affected files
   - Maintain clear status indicators in all planning documents
   - Never contradict information between memory bank files


---
*Review this meta document at the beginning of each project phase to ensure everyone follows the memory bank process consistently.*
