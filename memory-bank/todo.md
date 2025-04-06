# Project Todo List

This document captures specific tasks that need to be completed. These tasks are typically more detailed than the high-level milestones for feature details in the high level or detailed plans and should focus on tasks that aren't already covered in the plans.

## How to Use This File

1. **Add specific, actionable tasks** with clear completion criteria
2. **Prioritize tasks** in the appropriate sections below
3. **Update regularly** as tasks are completed or new tasks are identified
4. **Move completed tasks** to the "Completed" section before eventually removing them

## High Priority (Must be done next)

<!-- Tasks that are blocking progress or are critical for the current phase but not detailed in plans -->
- [ ] Research Gmail API attachment endpoints and response formats 
- [ ] Create test fixtures for mock attachment responses
- [ ] Investigate Gmail API query syntax limits for compound queries
- [ ] Document Gmail search operators for label, sender and recipient filtering
- [ ] Test performance of different query approaches with large mailboxes
- [ ] Design attachment storage directory structure with consideration for organization and duplicate handling
- [ ] Research best practices for handling potentially unsafe attachment filenames

## Medium Priority (Should be done soon)

<!-- Tasks that are important but not blocking immediate progress and not detailed in plans -->
- [ ] Create metrics for measuring email processing performance
- [ ] Research caching libraries for Python
- [ ] Design CLI progress indicator format for long-running operations
- [ ] Brainstorm edge cases for complex search queries
- [ ] Explore Gmail API rate limits and throttling considerations
- [ ] Document known Gmail API limitations and workarounds
- [ ] Capture detailed plans from previous features in .chat-logs to support future documentation

## Low Priority (Can wait)

<!-- Tasks that would be nice to have but aren't critical and not detailed in plans -->
- [ ] Create configuration file for user preferences (format, location, schema)
- [ ] Research popular alternative formats besides markdown
- [ ] Design command structure for email stats reporting
- [ ] Explore incremental update approach options
- [ ] Research logging best practices and levels
- [ ] Complete the following prompt stubs with detailed content:
  - [ ] Python Environment Setup (prompts/setup/python_environment_setup.md)
  - [ ] Initial Commit Guide (prompts/setup/initial_commit.md)
  - [ ] Remote Repository Setup (prompts/setup/remote_repository_setup.md)

## Technical Debt (Needs refactoring)

<!-- Code or design issues that should be addressed to improve quality -->
- [ ] Add type hints throughout the codebase
- [ ] Create more modular architecture for extensibility
- [ ] Implement proper exception handling hierarchy
- [ ] Add complete docstrings to all functions and classes
- [ ] Refactor authentication module for better token management

## Future Enhancements (Post v1.0)

<!-- Features or improvements planned for future versions -->
- [ ] Explore options for incremental sync to only process new emails
- [ ] Research options for web interface framework
- [ ] Investigate summarization APIs for potential integration
- [ ] Research ML techniques for email categorization
- [ ] Design approach for scheduled runs and automation

## Documentation Tasks

<!-- Documentation that needs to be created or updated -->
- [ ] Create detailed README with installation and usage instructions
- [ ] Document Google Cloud project setup with screenshots
- [ ] Compile examples of common search queries
- [ ] Create user guide for different use cases
- [ ] Document environment variables and configuration options
- [ ] Add troubleshooting section for common issues

## Completed

<!-- Recently completed tasks - move here before eventually removing -->
- [x] Fix all test failures (March 30, 2025)
- [x] Update Typer code to use modern patterns (remove deprecated is_flag) (April 6, 2025)
- [x] Implement date range enhancements with relative date support (April 6, 2025)
- [x] Set up comprehensive unit testing framework with pytest (March 24, 2025)
- [x] Add integration tests for end-to-end functionality verification (March 24, 2025)
- [x] Implement email search functionality with basic query parameters (March 23, 2025)
- [x] Design and implement email content extraction logic (March 23, 2025)
- [x] Develop markdown conversion with YAML frontmatter (March 23, 2025)
- [x] Create file management module with duplicate prevention (March 23, 2025)
- [x] Implement HTML to Markdown conversion for better formatting (March 23, 2025)
- [x] Enhance CLI interface for direct command-line usage with required query parameter (March 24, 2025)
- [x] Configure default values for output directory and days parameter (March 24, 2025)
- [x] Set up project directory structure (March 23, 2025)
- [x] Create initial core modules (March 23, 2025)
- [x] Implement CLI interface with Typer (March 23, 2025)
- [x] OAuth 2.0 authentication implementation and testing (March 23, 2025)
- [x] Complete project-background.md with project details (March 23, 2025)
- [x] Update high-level-plan.md with project phases and timelines (March 23, 2025)
- [x] Populate todo.md with actionable, prioritized tasks (March 23, 2025)
- [x] Initialize project repository structure (create src, tests directories) (March 23, 2025)
- [x] Copy configuration templates from memory-bank to project root (March 23, 2025)
- [x] Set up Python virtual environment with required dependencies (March 23, 2025)
- [x] Create Google Cloud project and enable Gmail API (March 23, 2025)
- [x] Set up OAuth consent screen and generate credentials (March 23, 2025)
- [x] Create initial README.md with project description and setup instructions (March 23, 2025)
- [x] Implement authentication module for Gmail API access (March 23, 2025)
- [x] Create basic command-line interface structure using Typer (March 23, 2025)
- [x] Organize prompt system with appropriate categories (March 24, 2025)
- [x] Move template files to memory-bank/templates/ directory (March 24, 2025)
- [x] Create process prompts for Rule Consolidation and Rules Update (March 24, 2025)
- [x] Update memory bank documentation to reflect current progress (March 24, 2025)

---
*Review this list at the beginning of each work session to stay focused on priorities.*
