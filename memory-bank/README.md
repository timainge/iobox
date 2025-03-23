# Memory Bank System

⚠️ **IMPORTANT: READ AND FOLLOW THESE INSTRUCTIONS CAREFULLY** ⚠️

This directory contains a structured memory bank system for maintaining project context, planning, and collaboration between users and AI assistants.

## Table of Contents
- [Core Concept](#core-concept)
- [Initialization Sequence](#initialization-sequence---do-not-skip-steps)
- [Critical Files](#critical-files-in-order-of-completion)
- [Working With AI Assistants](#working-with-ai-assistants)
- [Progression Checklist](#progression-checklist)

## Core Concept

The memory bank serves as a persistent repository of project knowledge that:
1. Maintains context across AI assistant sessions
2. Enforces methodical planning and implementation
3. Documents important decisions and their rationale
4. Provides a shared understanding for all project contributors

## Initialization Sequence - DO NOT SKIP STEPS

Follow these steps IN ORDER:
1. [x] move memory-bank.windsurfrules to .windsurfrules
2. [x] Read and understand the `meta.md` file for the complete process guidelines
3. [x] Complete `project-background.md` with detailed project information
4. [x] Update `high-level-plan.md` with specific phases and timelines
5. [x] Populate `todo.md` with actionable, prioritized tasks
6. [x] Follow the project setup steps in `detailed-plan.md` which has the initialization tasks prefilled
7. [x] Have AI review all memory bank files for context
8. [x] ONLY THEN begin implementation work

## Critical Files (In order of completion)

- `meta.md` - Process definitions and collaboration guidelines
- `project-background.md` - **COMPLETE FIRST** - Core project information 
- `high-level-plan.md` - **COMPLETE SECOND** - Project roadmap and phases
- `todo.md` - **COMPLETE THIRD** - Specific actionable tasks
- `detailed-plan.md` - Implementation plan starting with project setup
- `scratchpad.md` - Space for temporary notes and brainstorming
- `.env.example` - Template for environment variables
- `.cursorrules` - Template Instructions for AI assistants
- `.gitignore.template` - Template for gitignore

## Working With AI Assistants

To get the most effective help from AI assistants:

1. **ALWAYS** begin new sessions with: "Please review all files in the memory-bank directory to understand my project"
2. **NEVER** ask for implementation before memory bank files are complete

For detailed collaboration guidelines, see the `meta.md` file.

## Progression Checklist

- [x] meta.md reviewed and understood
- [x] project-background.md is complete
- [x] high-level-plan.md is reviewed and updated
- [x] todo.md is populated
- [x] Project setup complete following detailed-plan.md
- [x] All memory bank files have been reviewed by AI assistant

## Instructions for humans:

### Working with AI Assistants

1. **Initialization**
   - Begin new AI sessions with this EXACT request: "Please review all files in the memory-bank directory to understand my project"
   - Wait for the AI to confirm it has processed the memory bank before proceeding
   - NEVER assume the AI remembers context from previous sessions without reviewing memory bank

2. **Planning Assistance**
   - Ask AI to help draft detailed implementation plans using specific requirements
   - Request explicit critique of existing plans (e.g., "What risks or issues might I have missed?")
   - Have AI analyze dependencies and potential bottlenecks

3. **Implementation Support**
   - ALWAYS reference specific memory bank files when asking for implementation help
   - Example: "Based on the approach in detailed-plan.md, help me implement..."
   - Keep the `detailed-plan.md` updated for accurate AI assistance
   - Use `scratchpad.md` for temporary exploration without cluttering main files

4. **Documentation**
   - Ask AI to help update specific memory bank files as the project evolves
   - Request consistency checks across memory bank documents
   - Have AI create summaries of complex implementations for documentation
   - Never let memory bank files become outdated

### Customizing the Process

This process can be adapted to suit project needs:
- For smaller projects: Focus on project-background.md and high-level-plan.md
- For larger projects: Consider creating additional specialized memory bank files
- For team projects: Add a team-roles.md file defining responsibilities
- For complex projects: Create architecture-decisions.md to track major design choices

### When Things Go Wrong

If you find the AI assistance is not aligned with your project:
1. Check if all memory bank files are properly updated
2. Ask the AI to explicitly review the memory bank files again
3. Point out specific misalignments between AI suggestions and memory bank content
4. Update the memory bank files to address any gaps or ambiguities
5. Begin a new session with freshly updated memory bank content

---

*The success of your project depends on consistently following the memory bank system. Do not skip steps or take shortcuts. For ongoing process guidelines, refer to meta.md.*
