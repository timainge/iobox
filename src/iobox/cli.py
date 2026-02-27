"""
Command-line interface for the iobox application.

This module provides a user-friendly CLI for interacting with iobox functionality.
"""

import os
import sys
import typer
from typing import Optional, List, Dict, Any
from pathlib import Path

from iobox.auth import get_gmail_service, check_auth_status
from iobox.email_search import search_emails, get_email_content, download_attachment
from iobox.markdown import convert_email_to_markdown
from iobox.file_manager import (
    create_output_directory, 
    save_email_to_markdown, 
    save_attachment,
    check_for_duplicates,
    sanitize_filename
)

# Version
__version__ = "0.1.0"

# Create a Typer app
app = typer.Typer(help="Gmail to Markdown converter")

# Add the version option to the main Typer app
version_callback = typer.Option(
    False,
    "--version",
    "-v",
    help="Show version and exit",
    callback=lambda value: typer.echo(f"iobox version {__version__}") or exit(0) if value else None,
)

@app.command()
def version():
    """Display the current version of iobox."""
    typer.echo(f"iobox version {__version__}")


@app.command()
def auth_status():
    """Check the status of Gmail API authentication."""
    status = check_auth_status()
    
    typer.echo("\nAuthentication Status")
    typer.echo("-------------------")
    typer.echo(f"Authenticated: {status['authenticated']}")
    typer.echo(f"Credentials file exists: {status['credentials_file_exists']}")
    typer.echo(f"Credentials path: {status['credentials_path']}")
    typer.echo(f"Token file exists: {status['token_file_exists']}")
    typer.echo(f"Token path: {status['token_path']}")
    
    if status["token_file_exists"] and "expired" in status:
        typer.echo(f"Token expired: {status['expired']}")
        typer.echo(f"Has refresh token: {status['has_refresh_token']}")
    
    if not status["credentials_file_exists"]:
        typer.echo("\nTo set up Google Cloud OAuth 2.0 credentials:")
        typer.echo("1. Go to https://console.cloud.google.com/")
        typer.echo("2. Create a project or select an existing one")
        typer.echo("3. Navigate to APIs & Services > Credentials")
        typer.echo("4. Click 'Create Credentials' > 'OAuth client ID'")
        typer.echo("5. Choose 'Desktop app' as application type")
        typer.echo("6. Download the JSON file and save it as 'credentials.json' in the project root")


@app.command()
def search(
    query: str = typer.Option(
        ..., "--query", "-q", help="Search query using Gmail search syntax"
    ),
    max_results: int = typer.Option(
        10, "--max-results", "-m", help="Maximum number of results to return"
    ),
    days: int = typer.Option(
        7, "--days", "-d", help="Number of days back to search"
    ),
    start_date: str = typer.Option(
        None, "--start-date", "-s", help="Start date in YYYY/MM/DD format (overrides days parameter if provided)"
    ),
    end_date: str = typer.Option(
        None, "--end-date", "-e", help="End date in YYYY/MM/DD format (requires start-date)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information for each result"
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Show debug information about API responses"
    ),
):
    """Search for emails matching the specified query."""
    try:
        # Authenticate with Gmail API
        service = get_gmail_service()
        
        # Search for emails
        typer.echo(f"Searching for emails matching: {query}")
        results = search_emails(
            service, 
            query, 
            max_results, 
            days, 
            start_date, 
            end_date
        )
        
        if not results:
            typer.echo("No emails found matching the query.")
            return
        
        # Display results
        typer.echo(f"\nFound {len(results)} emails:")
        
        # In debug mode, show a sample of available fields from the first email
        if debug and results:
            typer.echo("\nAPI Response Debug Info (first result):")
            typer.echo("Available fields in email object:")
            for key, value in results[0].items():
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                elif isinstance(value, dict):
                    value = f"{type(value)} with keys: {', '.join(value.keys())}"
                elif isinstance(value, list) and len(value) > 5:
                    value = f"List with {len(value)} items: {value[:5]}..."
                typer.echo(f"  - {key}: {value}")
            typer.echo("")
        
        for i, email in enumerate(results, 1):
            # Extract subject from headers
            subject = "No subject"
            sender = "Unknown sender"
            date = "Unknown date"
            
            if 'payload' in email and 'headers' in email['payload']:
                headers = email['payload']['headers']
                for header in headers:
                    if header['name'].lower() == 'subject':
                        subject = header['value']
                    elif header['name'].lower() == 'from':
                        sender = header['value']
                    elif header['name'].lower() == 'date':
                        date = header['value']
            
            # Format the date more nicely if possible
            try:
                from dateutil import parser
                from datetime import datetime
                
                date_obj = parser.parse(date)
                # Use Australian date format as per project guidelines
                date_str = date_obj.strftime("%d/%m/%Y %H:%M")
            except:
                date_str = date
            
            # Extract labels
            labels = email.get('labelIds', [])
            label_str = ', '.join(labels) if labels else "No labels"
            
            # Display basic info
            typer.echo(f"{i}. {subject}")
            typer.echo(f"   ID: {email.get('id', 'No ID')}")
            
            # Show snippet for all results (even if not detailed)
            snippet = email.get('snippet', 'No preview available')
            if snippet:
                # Clean up HTML entities and limit length
                import html
                try:
                    snippet = html.unescape(snippet)
                except:
                    pass
                snippet = snippet[:70] + "..." if len(snippet) > 70 else snippet
                typer.echo(f"   Preview: {snippet}")
            
            # Show basic metadata for all results
            typer.echo(f"   From: {sender}")
            typer.echo(f"   Date: {date_str}")
            
            if verbose:
                # Show labels and other details only in verbose mode
                typer.echo(f"   Labels: {label_str}")
                
                # Get size in KB
                size = email.get('sizeEstimate', 0)
                size_kb = size / 1024
                typer.echo(f"   Size: {size_kb:.1f} KB")
                
                # Add a blank line for readability between detailed results
                typer.echo("")
            else:
                # Add a separator between non-detailed results
                typer.echo("   " + "-" * 40)
        
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@app.command()
def save(
    message_id: str = typer.Option(
        None, "--message-id", "-m", help="ID of a specific email to save"
    ),
    query: str = typer.Option(
        None, "--query", "-q", help="Search query for emails to save (for batch mode)"
    ),
    max_results: int = typer.Option(
        10, "--max", help="Maximum number of emails to save in batch mode"
    ),
    days: int = typer.Option(
        7, "--days", "-d", help="Number of days back to search for emails"
    ),
    start_date: str = typer.Option(
        None, "--start-date", "-s", help="Start date in YYYY/MM/DD format (overrides days parameter if provided)"
    ),
    end_date: str = typer.Option(
        None, "--end-date", "-e", help="End date in YYYY/MM/DD format (requires start-date)"
    ),
    output_dir: str = typer.Option(
        ".", "--output-dir", "-o", help="Directory to save markdown files to"
    ),
    html_preferred: bool = typer.Option(
        True, "--html-preferred", help="Prefer HTML content if available"
    ),
    download_attachments: bool = typer.Option(
        False, "--download-attachments", help="Download email attachments"
    ),
    attachment_types: str = typer.Option(
        None, "--attachment-types", help="Filter attachments by file extension (comma-separated, e.g., 'pdf,docx,xlsx')"
    ),
):
    """
    Save emails as Markdown files.
    
    Supports two modes:
    1. Single mode: Save one specific email (use --message-id)
    2. Batch mode: Save multiple emails matching a query (use --query)
    """
    try:
        # Check parameter validity
        if message_id is None and query is None:
            typer.echo("Error: You must specify either --message-id (-m) or --query (-q)")
            typer.echo("\nFor help, run: iobox save --help")
            raise typer.Exit(code=1)
            
        # Authenticate with Gmail API
        service = get_gmail_service()
        
        # Create output directory if it doesn't exist
        output_dir = create_output_directory(output_dir)
        
        # Parse attachment types if provided
        attachment_filters = []
        if attachment_types:
            attachment_filters = [ext.strip().lower() for ext in attachment_types.split(',')]
            
        # Single email mode
        if message_id is not None:
            # Get email content
            email_data = get_email_content(
                service,
                message_id,
                preferred_content_type="text/html" if html_preferred else "text/plain"
            )
            
            # Convert to markdown
            markdown_content = convert_email_to_markdown(email_data)
            
            # Save to file
            filepath = save_email_to_markdown(
                email_data=email_data,
                markdown_content=markdown_content,
                output_dir=output_dir
            )
            
            typer.echo(f"Successfully saved email to {filepath}")
            
            # Download attachments if requested
            if download_attachments and email_data.get('attachments'):
                download_email_attachments(
                    service=service,
                    email_data=email_data,
                    output_dir=output_dir,
                    attachment_filters=attachment_filters
                )
            
        # Batch mode
        else:
            # Search for emails
            typer.echo(f"Searching for emails matching: {query}")
            results = search_emails(
                service, 
                query, 
                max_results, 
                days,
                start_date,
                end_date
            )
            
            if not results:
                typer.echo("No emails found matching the query.")
                return
                
            total_emails = len(results)
            typer.echo(f"\nFound {total_emails} emails to process.")
            
            # Process each email
            saved_count = 0
            attachment_count = 0
            
            # Check for already processed emails
            message_ids = [result['message_id'] for result in results]
            duplicates = check_for_duplicates(message_ids, output_dir)
            
            for i, email_summary in enumerate(results):
                message_id = email_summary['message_id']
                
                # Skip already processed emails
                if message_id in duplicates:
                    typer.echo(f"Skipping already processed email: {message_id}")
                    continue
                
                typer.echo(f"\nProcessing email {i+1}/{total_emails}: {email_summary.get('subject', 'No Subject')}")
                
                # Get full email content
                email_data = get_email_content(
                    service,
                    message_id,
                    preferred_content_type="text/html" if html_preferred else "text/plain"
                )
                
                # Convert to markdown
                markdown_content = convert_email_to_markdown(email_data)
                
                # Save to file
                filepath = save_email_to_markdown(
                    email_data=email_data,
                    markdown_content=markdown_content,
                    output_dir=output_dir
                )
                
                saved_count += 1
                
                # Download attachments if requested
                if download_attachments and email_data.get('attachments'):
                    email_attachment_count = download_email_attachments(
                        service=service,
                        email_data=email_data,
                        output_dir=output_dir,
                        attachment_filters=attachment_filters
                    )
                    attachment_count += email_attachment_count
            
            # Summary message
            typer.echo(f"\nCompleted processing {total_emails} emails:")
            typer.echo(f"  - {saved_count} emails saved to markdown")
            typer.echo(f"  - {len(duplicates)} emails skipped (already processed)")
            if download_attachments:
                typer.echo(f"  - {attachment_count} attachments downloaded")
                
    except Exception as e:
        typer.echo(f"Error saving emails: {e}")
        raise typer.Exit(code=1)


def download_email_attachments(service, email_data: Dict[str, Any], 
                              output_dir: str, attachment_filters: List[str] = None) -> int:
    """
    Download all attachments for an email.
    
    Args:
        service: Authenticated Gmail API service
        email_data: Email data dictionary
        output_dir: Directory to save attachments to
        attachment_filters: List of file extensions to filter by
        
    Returns:
        int: Number of attachments downloaded
    """
    message_id = email_data.get('message_id', '')
    attachments = email_data.get('attachments', [])
    
    if not attachments:
        typer.echo("  No attachments found")
        return 0
    
    typer.echo(f"  Found {len(attachments)} attachments")
    
    downloaded_count = 0
    for attachment in attachments:
        # Check if this attachment should be filtered
        if attachment_filters:
            filename = attachment.get('filename', '')
            ext = os.path.splitext(filename)[1].lower().lstrip('.')
            if ext and ext not in attachment_filters:
                typer.echo(f"  Skipping attachment (type filter): {filename}")
                continue
        
        attachment_id = attachment.get('id', '')
        filename = attachment.get('filename', '')
        
        if not attachment_id or not filename:
            typer.echo("  Skipping attachment with missing ID or filename")
            continue
        
        try:
            typer.echo(f"  Downloading attachment: {filename}")
            attachment_data = download_attachment(service, message_id, attachment_id)
            
            if attachment_data:
                # Save attachment to disk
                filepath = save_attachment(
                    attachment_data=attachment_data,
                    filename=filename,
                    email_id=message_id,
                    output_dir=output_dir
                )
                
                downloaded_count += 1
                typer.echo(f"  Saved attachment to: {filepath}")
            else:
                typer.echo(f"  Failed to download attachment: {filename}")
        
        except Exception as e:
            typer.echo(f"  Error downloading attachment {filename}: {e}")
            continue
    
    return downloaded_count


@app.callback()
def main(
    ctx: typer.Context,
    version_flag: bool = version_callback,
):
    """
    Iobox - Gmail to Markdown Converter
    
    Use commands to interact with Gmail and convert emails to Markdown.
    """
    pass


def run():
    app()

if __name__ == "__main__":
    run()
