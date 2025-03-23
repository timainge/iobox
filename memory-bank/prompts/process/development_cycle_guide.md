---
name: "Development Cycle Guide"
situation: "When implementing features or beginning a new development cycle"
tags: ["process", "development", "OODA", "planning"]
created: "2025-03-24"
last_updated: "2025-03-24"
author: "Iobox Team"
version: "1.0"
inputs_required:
  - "Current project phase from high-level-plan.md"
  - "Feature focus from detailed-plan.md"
expected_outputs:
  - "Step-by-step guidance for the current development phase"
  - "Status update templates for documentation"
---

# Development Cycle Guide

## Context

This guide provides detailed instructions for implementing the OODA loop (Observe, Orient, Decide, Act) development process. It offers specific guidance for each phase of feature development, with special attention to maintaining consistent status tracking across memory bank files.

## Instructions

### Development Cycle Implementation (OODA Loop)

#### 1. Observe Phase

- **Review Current Project State**
  - Check `high-level-plan.md` for overall project status
  - Review `detailed-plan.md` for current feature status
  - Examine `todo.md` for any related supporting tasks
  - Note any discrepancies between status indicators
  
- **Document Current State**
  - Record observations in `scratchpad.md`
  - Note any challenges, blockers, or dependencies
  - Identify any status inconsistencies that need resolution

#### 2. Orient Phase

- **Analyze and Prioritize**
  - Determine how current task fits into overall project goals
  - Identify dependencies and potential bottlenecks
  - Consider alternative implementation approaches
  - Evaluate technical debt implications

- **Update Planning Documents**
  - Ensure `high-level-plan.md` accurately reflects current priorities
  - Update `detailed-plan.md` with any new insights or dependencies
  - Make sure status indicators are consistent across documents

#### 3. Decide Phase

- **Choose Implementation Approach**
  - Select specific technical approaches for implementation
  - Document decisions with clear rationale
  - Consider alternatives that were rejected and why

- **Create Specific Implementation Steps**
  - Break down implementation into clear, verifiable steps
  - Define acceptance criteria for each step
  - Update `detailed-plan.md` with these steps and criteria
  - Only add supporting tasks to `todo.md` if they don't fit in the plans

#### 4. Act Phase

- **Implementation Execution**
  - Follow implementation steps in order
  - Document progress with regular status updates
  - Note any deviations from the plan and reasons
  - Keep code changes focused and aligned with plan

- **Status Documentation**
  - Update status in `high-level-plan.md` first (PRIMARY authority)
  - Then update `detailed-plan.md` status (IMPLEMENTATION authority)
  - Include specific achievements and completion dates
  - Mark off completed steps with clear indicators

### Feature Development Documentation

#### Planning Phase Documentation Template

```markdown
## Current Feature: [Feature Name]

**Status:** Planning

### Overview
[Brief description of the feature]

### Requirements
- [Requirement 1]
- [Requirement 2]
- [Requirement 3]

### Design Approach
[Description of the chosen design approach]

### Implementation Steps
1. [ ] **[Step 1]**
   - Details: [Specific implementation details]
   - Acceptance: [Verification criteria]

2. [ ] **[Step 2]**
   - Details: [Specific implementation details]
   - Acceptance: [Verification criteria]
```

#### Implementation Phase Status Updates

```markdown
## Current Feature: [Feature Name]

**Status:** Implementing
**Last Updated:** [Date]

### Progress
- [x] Step 1 completed on [Date]
  - Notes: [Any relevant implementation notes]
- [ ] Step 2 in progress
  - Challenges: [Any challenges encountered]
  - Solutions: [Applied solutions]
```

#### Completion Phase Documentation

```markdown
## Current Feature: [Feature Name]

**Status:** Complete
**Completion Date:** [Date]

### Achievements
- All implementation steps completed
- [Specific achievement 1]
- [Specific achievement 2]

### Lessons Learned
- [Lesson 1]
- [Lesson 2]

### Next Steps
- Update `high-level-plan.md` to reflect completion
- Begin planning for [Next Feature]
```

## Notes

- Always follow the status tracking hierarchy (high-level-plan.md → detailed-plan.md → todo.md)
- Document decisions and their rationale to preserve context
- Keep all status indicators consistent across memory bank files
- Use the OODA loop as an iterative process, not a one-time sequence
