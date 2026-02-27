# Multi-Account Authentication Guide

This document explains how to configure and use Iobox with multiple Gmail accounts, both via CLI and as a Python library.

## Overview

Iobox supports multiple Gmail accounts through an account profile system. Each account maintains its own OAuth credentials and tokens, allowing you to:

- Switch between accounts without re-authentication
- Process emails from multiple accounts simultaneously
- Maintain separate OAuth applications for different organizations
- Use different accounts for different automation scripts

## Account Profile Structure

Accounts are stored in isolated directories under the credentials folder:

```
credentials/
├── personal/
│   ├── credentials.json    # OAuth client secrets
│   └── token.json         # Access/refresh tokens
├── work/
│   ├── credentials.json
│   └── token.json
├── client1/
│   ├── credentials.json
│   └── token.json
└── accounts.json          # Account registry and metadata
```

## CLI Usage

### Setting Up Accounts

```bash
# Add a new account profile
iobox account add personal --credentials ./personal-gmail-creds.json

# Add work account with custom credentials directory
iobox account add work --credentials ./work-creds.json --creds-dir ./work-oauth

# List all configured accounts
iobox account list

# Show current default account
iobox account current

# Switch default account for subsequent commands
iobox account use work
```

### Using Accounts in Commands

```bash
# Use default account (whatever is currently set)
iobox search -q "from:newsletter@example.com"

# Use specific account for single command
iobox search -q "from:boss@company.com" --account work

# Save emails from specific account
iobox save -q "label:important" --account personal -o ./personal-emails

# Process multiple accounts in sequence
iobox search -q "subject:invoice" --accounts personal,work,client1

# Check authentication status for specific account
iobox auth-status --account work

# Check all accounts
iobox auth-status --all
```

### Account Management

```bash
# Remove account (deletes tokens and credentials)
iobox account remove client1

# Refresh tokens for specific account
iobox account refresh work

# Validate account configuration
iobox account validate personal

# Reset account (force re-authentication)
iobox account reset work
```

## Python Library Usage

### Basic Multi-Account Setup

```python
from iobox.auth import AccountManager, get_gmail_service
from iobox.email_search import search_emails

# Initialize account manager
account_mgr = AccountManager()

# Add accounts programmatically
account_mgr.add_account("personal", "./personal-creds.json")
account_mgr.add_account("work", "./work-creds.json")

# Get service for specific account
personal_service = get_gmail_service(account="personal")
work_service = get_gmail_service(account="work")

# Search emails from different accounts
personal_emails = search_emails(personal_service, "from:newsletter@example.com")
work_emails = search_emails(work_service, "from:boss@company.com")
```

### Advanced Multi-Account Operations

```python
from iobox.auth import AccountManager
from iobox.email_search import search_emails
from iobox.markdown import convert_email_to_markdown
import asyncio

class MultiAccountProcessor:
    def __init__(self):
        self.account_mgr = AccountManager()
    
    def process_all_accounts(self, query, output_base_dir):
        """Process query across all configured accounts"""
        results = {}
        
        for account_name in self.account_mgr.list_accounts():
            try:
                service = get_gmail_service(account=account_name)
                emails = search_emails(service, query)
                
                # Save to account-specific directory
                account_output = f"{output_base_dir}/{account_name}"
                os.makedirs(account_output, exist_ok=True)
                
                for email in emails:
                    # Process and save email
                    markdown_content = convert_email_to_markdown(email)
                    # ... save logic
                
                results[account_name] = len(emails)
                
            except Exception as e:
                print(f"Error processing account {account_name}: {e}")
                results[account_name] = 0
        
        return results
    
    async def async_process_accounts(self, query):
        """Process accounts concurrently"""
        tasks = []
        
        for account_name in self.account_mgr.list_accounts():
            task = self._process_account_async(account_name, query)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return dict(zip(self.account_mgr.list_accounts(), results))
    
    async def _process_account_async(self, account_name, query):
        """Process single account asynchronously"""
        # Implementation for async processing
        pass

# Usage
processor = MultiAccountProcessor()
results = processor.process_all_accounts("label:important", "./output")
print(f"Processed emails per account: {results}")
```

### Context Manager for Account Switching

```python
from iobox.auth import account_context

# Temporarily switch to specific account
with account_context("work"):
    service = get_gmail_service()  # Uses work account
    emails = search_emails(service, "from:boss@company.com")

# Back to default account after context exits
service = get_gmail_service()  # Uses default account
```

## Configuration

### Environment Variables

```bash
# Base credentials directory (default: ./credentials)
export IOBOX_CREDENTIALS_DIR="/path/to/credentials"

# Default account name (default: "default")
export IOBOX_DEFAULT_ACCOUNT="personal"

# Account registry file location
export IOBOX_ACCOUNTS_CONFIG="/path/to/accounts.json"
```

### Account Registry Format

The `accounts.json` file maintains account metadata:

```json
{
  "accounts": {
    "personal": {
      "credentials_path": "credentials/personal/credentials.json",
      "token_path": "credentials/personal/token.json",
      "created_at": "2025-01-15T10:30:00Z",
      "last_used": "2025-01-20T14:22:00Z",
      "email": "user@gmail.com",
      "status": "active"
    },
    "work": {
      "credentials_path": "credentials/work/credentials.json", 
      "token_path": "credentials/work/token.json",
      "created_at": "2025-01-16T09:15:00Z",
      "last_used": "2025-01-20T16:45:00Z",
      "email": "user@company.com",
      "status": "active"
    }
  },
  "default_account": "personal",
  "version": "1.0"
}
```

## Error Handling

### Common Issues and Solutions

```python
from iobox.auth import AccountManager, AccountNotFoundError, AuthenticationError

try:
    service = get_gmail_service(account="nonexistent")
except AccountNotFoundError:
    print("Account not configured. Use 'iobox account add' to set it up.")

try:
    service = get_gmail_service(account="work")
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
    print("Try: iobox account refresh work")

# Check account health before using
account_mgr = AccountManager()
if account_mgr.validate_account("personal"):
    service = get_gmail_service(account="personal")
else:
    print("Account needs reconfiguration")
```

## Migration from Single Account

### Automatic Migration

Existing single-account setups are automatically migrated:

```python
# If you have existing credentials.json and token.json in root
# They will be moved to credentials/default/ automatically
```

### Manual Migration

```bash
# Migrate existing setup to named account
mkdir -p credentials/personal
mv credentials.json credentials/personal/
mv token.json credentials/personal/

# Register the account
iobox account add personal --existing
```

## Security Considerations

- Each account maintains separate OAuth tokens
- Credentials are stored in isolated directories
- Account registry doesn't contain sensitive information
- Use different OAuth applications for different organizations when possible
- Regularly rotate tokens using `iobox account refresh`

## Best Practices

1. **Naming Convention**: Use descriptive account names (`work`, `personal`, `client-acme`)
2. **Organization Separation**: Use separate OAuth apps for different organizations
3. **Token Management**: Regularly refresh tokens and monitor account health
4. **Error Handling**: Always wrap account operations in try-catch blocks
5. **Concurrent Processing**: Use async operations when processing multiple accounts
6. **Logging**: Log account usage for debugging and audit purposes

## Examples

### Automated Newsletter Processing

```python
#!/usr/bin/env python3
"""Process newsletters from multiple accounts"""

from iobox.auth import AccountManager, get_gmail_service
from iobox.email_search import search_emails

def process_newsletters():
    accounts = ["personal", "work", "side-project"]
    newsletter_query = "from:newsletter OR from:digest OR subject:weekly"
    
    for account in accounts:
        try:
            service = get_gmail_service(account=account)
            emails = search_emails(service, newsletter_query, days_back=7)
            
            print(f"Found {len(emails)} newsletters in {account}")
            
            # Process emails...
            
        except Exception as e:
            print(f"Error processing {account}: {e}")

if __name__ == "__main__":
    process_newsletters()
```

### Cross-Account Email Analysis

```bash
#!/bin/bash
# Analyze email patterns across accounts

echo "Searching for important emails across all accounts..."

iobox search -q "label:important OR subject:urgent" \
  --accounts personal,work \
  --days 30 \
  --verbose > important_emails_report.txt

echo "Report saved to important_emails_report.txt"
```