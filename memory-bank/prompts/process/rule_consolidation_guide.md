---
name: "Rule Consolidation Cycle Guide"
situation: "When conducting a quarterly review of project rules to improve effectiveness and reduce context bloat"
tags: ["process", "rules", "maintenance", "consolidation", "quarterly"]
created: "2025-03-24"
last_updated: "2025-03-24"
author: "Iobox Team"
version: "1.0"
inputs_required:
  - "rules_usage.log content"
  - "Current .windsurfrules file"
  - "Retrospectives from the last quarter"
expected_outputs:
  - "Analysis of rule effectiveness"
  - "Consolidated rules draft"
  - "Retrospective entry documenting changes"
---

# Rule Consolidation Cycle Guide

## Context

This prompt provides a structured approach for the quarterly review and consolidation of project rules to prevent context dilution and maintain effective guidance. The process helps ensure that rules remain relevant, impactful, and concise.

## Instructions

### Rule Consolidation Cycle

To prevent context dilution and maintain effective guidance:

1. **Quarterly Schedule**: Review rules every three months
2. **Usage Analysis**: Identify which rules were most frequently referenced
   - Review the `rules_usage.log` file for frequency patterns
   - Create a ranked list of rules by usage frequency
   - Identify rules that were rarely or never used

3. **Impact Assessment**: Evaluate which rules had the highest positive impact
   - For each rule usage, assess the outcome value
   - Identify patterns where specific rules consistently led to positive outcomes
   - Note rules that had minimal or negative impact

4. **Consolidation**: Merge similar rules and remove unused ones
   - Identify conceptually similar or overlapping rules
   - Draft merged versions that maintain the essence of each component
   - Consider eliminating rules that are:
     - Never or rarely used
     - Consistently low impact
     - Duplicative of other guidance
     - Better suited to task-specific prompts

5. **Prioritization**: Mark high-impact rules as "core" and situational ones as "supporting"
   - Core rules should be in the main .windsurfrules file
   - Supporting rules can be moved to appropriate prompts
   - Use the @prompt syntax to reference supporting rules

6. **Context Budget**: Keep the total rules file under 20% of available context window
   - Estimate the token count of the current rules file
   - Set a target maximum token count based on context window size
   - Prioritize core rules within this budget
   - Move detailed implementation guidance to prompts

7. **Documentation**: Record all rule changes in `retrospectives.md`
   - Document each change with clear rationale
   - Include metrics from usage and impact analysis
   - Highlight the consolidated structure's benefits

## Implementation Process

1. **Prepare Analysis**
   - Extract and organize data from rules_usage.log
   - Create a spreadsheet or table with:
     - Rule name/section
     - Usage count
     - Positive outcomes count
     - Negative/neutral outcomes count

2. **Draft Changes**
   - Use the @prompt:process/rules_update_guide process
   - Create a .windsurfrules.draft file with proposed changes
   - Clearly mark additions, removals, and changes

3. **User Review**
   - Present analysis and draft to the user
   - Provide clear rationale for each proposed change
   - Incorporate user feedback into the final draft

4. **Implementation**
   - After user approval, update the actual .windsurfrules file
   - Create or update prompt files for detailed guidance
   - Ensure all @prompt references are valid

## Example Analysis

```
Rule Usage Analysis - Q1 2025

| Rule Section         | Usage Count | Positive Outcomes | Neutral/Negative | Action |
|----------------------|-------------|------------------|------------------|--------|
| Function Analysis    | 37          | 32               | 5                | Keep as core |
| Dependency Chain     | 12          | 10               | 2                | Keep as core |
| Fallback Mechanisms  | 8           | 7                | 1                | Move to prompt |
| Output Format        | 5           | 5                | 0                | Move to prompt |
```

## Notes

- Consider the long-term implications of rule changes, not just recent usage
- Balance conciseness with clarity - fewer rules with more examples can be more effective
- Remember that the goal is to improve guidance, not just reduce token count
- Always prioritize rules that have consistently demonstrated high impact
