---
name: "Comprehensive Test Analysis"
situation: "When multiple test failures occur or tests need thorough review"
tags: ["testing", "debugging", "analysis", "compatibility"]
created: "2025-03-24"
last_updated: "2025-03-24"
author: "Iobox Team"
version: "1.0"
inputs_required:
  - "Path to failing test files"
  - "Path to implementation files being tested"
expected_outputs:
  - "Detailed analysis of test expectations"
  - "Implementation recommendations for compatibility"
  - "Dependency chain mapping"
---

# Comprehensive Test Analysis

## Context

This prompt guides the systematic analysis of test failures, particularly when multiple tests are failing or when test expectations aren't immediately clear. It applies the lessons learned from our unit testing framework improvements and focuses on identifying compatibility issues, formatting expectations, and dependency chains.

## Instructions

1. **First, analyze the test file structure:**
   - Identify all assertions and their exact expectations
   - Note any specific formatting requirements (indentation, spacing, order)
   - Map all test fixtures and mock objects to understand the expected environment

2. **Examine implementation files for compatibility:**
   - Check for field name consistency ('id' vs 'message_id', etc.)
   - Identify where data transformations occur
   - Look for hardcoded expectations that might conflict with tests

3. **Map dependency chains:**
   - Create a diagram or list of function dependencies
   - Note where data is transformed between functions
   - Identify potential bottlenecks where inconsistencies might occur

4. **Document specific compatibility issues:**
   - Field naming inconsistencies
   - Formatting expectations
   - Data type assumptions
   - Error handling patterns

5. **Develop implementation recommendations that:**
   - Support multiple field name conventions
   - Include graceful fallback mechanisms
   - Maintain output format stability
   - Provide clear error messages

## Examples

### Good Implementation Pattern

```python
# Handle both 'id' and 'message_id' fields for compatibility
message_id = email_data.get('message_id', '') or email_data.get('id', '')

# Generate deterministic ID if missing but have subject
if not message_id and 'subject' in email_data:
    import hashlib
    id_base = email_data.get('subject', '') + email_data.get('date', str(datetime.now()))
    message_id = hashlib.md5(id_base.encode()).hexdigest()[:12]

# Clear error message when truly missing required data
if not message_id:
    raise ValueError("Email data missing message_id or id and no subject to create one from")
```

## Notes

- Test compatibility often requires more verbose code to handle edge cases
- Consider using explicit formatting functions rather than relying on libraries' default formatting
- Document any special formatting requirements in function docstrings
- When dependencies exist between modules, consider creating interface adapters to standardize data formats
