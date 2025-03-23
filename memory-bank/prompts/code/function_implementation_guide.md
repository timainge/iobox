---
name: "Function Implementation Guide"
situation: "When modifying or creating function implementations, especially those with test dependencies"
tags: ["code", "testing", "implementation", "compatibility"]
created: "2025-03-24"
last_updated: "2025-03-24"
author: "Iobox Team"
version: "1.0"
inputs_required:
  - "Path to function implementation file"
  - "Path to test file (if applicable)"
expected_outputs:
  - "Implementation recommendations"
  - "Compatibility considerations"
---

# Function Implementation Guide

## Context

This guide provides detailed instructions for implementing or modifying functions with a focus on ensuring compatibility with existing tests and dependent functions. It applies the principles from our detailed testing experiences and focuses on maintaining consistent behavior across the codebase.

## Instructions

### Function Analysis Before Implementation

Before modifying any function, thoroughly analyze its test cases to understand:
   - Expected input parameters and their formats 
   - Field name conventions and alternative names (e.g., both 'id' and 'message_id')
   - Output format expectations, including exact spacing, indentation, and ordering
   - Error handling behavior and edge cases

### Dependency Chain Awareness

Map the dependencies between functions and modules to:
   - Identify how changes in one function might affect dependent functions
   - Trace how data flows through the system and where transformations occur
   - Verify that field names and formats are consistently handled across module boundaries
   - Understand test expectations throughout the entire chain

### Graceful Fallback Mechanisms

Implement resilient functions that:
   - Handle missing fields with sensible defaults or deterministic alternatives
   - Support multiple field name conventions for backward compatibility
   - Provide clear error messages when required values cannot be determined
   - Generate deterministic outputs for consistent testing

### Output Format Stability

Pay close attention to output formatting in tests:
   - Ensure exact indentation patterns are preserved if tests expect them
   - Maintain deterministic ordering of fields when serializing data structures
   - Verify output against detailed assertions in tests before submitting
   - Document any formatting requirements in the function docstrings

## Examples

### Function with Field Name Compatibility

```python
def process_email_data(email_data):
    """Process email data with backward compatibility for field names.
    
    Supports both 'id' and 'message_id' field names.
    """
    # Handle both field name conventions
    message_id = email_data.get('message_id', '') or email_data.get('id', '')
    
    # Deterministic fallback for missing ID
    if not message_id and 'subject' in email_data:
        import hashlib
        id_base = email_data.get('subject', '') + email_data.get('date', '')
        message_id = hashlib.md5(id_base.encode()).hexdigest()[:12]
    
    # Clear error for missing required data
    if not message_id:
        raise ValueError("Email data missing required identifier fields")
        
    # Rest of implementation...
```

### Maintaining Output Format Stability

```python
def generate_formatted_output(data):
    """Generate output with precise formatting required by tests.
    
    Note: Tests expect exactly 2-space indentation and specific ordering.
    """
    # Manual formatting to ensure test compatibility
    output = []
    output.append("data:")
    for key in sorted(data.keys()):  # Deterministic ordering
        value = data[key]
        if isinstance(value, list):
            output.append(f"  {key}:")
            for item in value:
                output.append(f"    - {item}")
        else:
            output.append(f"  {key}: {value}")
    
    return "\n".join(output)
```

## Notes

- Always refer to test cases first when implementing or modifying functions
- Document any special handling or compatibility measures in function docstrings
- Consider creating utility functions for common formatting or fallback mechanisms
- When in doubt, prioritize compatibility with existing tests over code elegance
