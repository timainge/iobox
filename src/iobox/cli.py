"""
Command-line interface for the iobox application.

This module provides a user-friendly CLI for interacting with iobox functionality.
"""

import os
import sys
import typer
from typing import Optional, List
from pathlib import Path

from iobox.auth import get_gmail_service, check_auth_status
from iobox.email_search import search_emails, get_email_content
from iobox.markdown import convert_email_to_markdown
from iobox.file_manager import save_email_to_markdown, create_output_directory

# Version
__version__ = "0.1.0"

# Create a Typer app
app = typer.Typer(help="Gmail to Markdown converter")


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
    detailed: bool = typer.Option(
        False, "--detailed", "-d", help="Show detailed information for each result"
    ),
):
    """Search for emails matching the specified query."""
    try:
        # Authenticate with Gmail API
        service = get_gmail_service()
        
        # Search for emails
        typer.echo(f"Searching for emails matching: {query}")
        results = search_emails(service, query, max_results)
        
        if not results:
            typer.echo("No emails found matching the query.")
            return
        
        # Display results
        typer.echo(f"\nFound {len(results)} emails:")
        
        for i, email in enumerate(results, 1):
            typer.echo(f"{i}. {email['id']} - {email['snippet'][:50]}...")
            
            if detailed:
                # Get detailed email content
                email_data = get_email_content(service, email["id"])
                typer.echo(f"   Subject: {email_data.get('subject', 'No subject')}")
                typer.echo(f"   From: {email_data.get('from', 'Unknown')}")
                typer.echo(f"   Date: {email_data.get('date', 'Unknown')}")
                typer.echo(f"   Labels: {', '.join(email_data.get('labels', []))}")
                typer.echo("")
        
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@app.command()
def convert(
    message_id: str = typer.Option(
        ..., "--message-id", "-m", help="Gmail message ID to convert"
    ),
    output_dir: str = typer.Option(
        "./output", "--output-dir", "-o", help="Directory to save markdown files to"
    ),
    html_preferred: bool = typer.Option(
        True, "--html-preferred", help="Prefer HTML content if available"
    ),
):
    """Convert a specific email to Markdown format."""
    try:
        # Authenticate with Gmail API
        service = get_gmail_service()
        
        # Create output directory if it doesn't exist
        output_dir = create_output_directory(output_dir)
        
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
        
        typer.echo(f"Successfully converted email to {filepath}")
        
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@app.command()
def batch_convert(
    query: str = typer.Option(
        ..., "--query", "-q", help="Search query using Gmail search syntax"
    ),
    max_results: int = typer.Option(
        10, "--max-results", "-m", help="Maximum number of emails to convert"
    ),
    output_dir: str = typer.Option(
        "./output", "--output-dir", "-o", help="Directory to save markdown files to"
    ),
    html_preferred: bool = typer.Option(
        True, "--html-preferred", help="Prefer HTML content if available"
    ),
):
    """Search for emails and convert them to Markdown format."""
    try:
        # Authenticate with Gmail API
        service = get_gmail_service()
        
        # Create output directory if it doesn't exist
        output_dir = create_output_directory(output_dir)
        
        # Search for emails
        results = search_emails(service, query, max_results)
        
        if not results:
            typer.echo("No emails found matching the query.")
            return
        
        typer.echo(f"Converting {len(results)} emails to Markdown...")
        
        # Convert each email
        converted_count = 0
        for email in results:
            try:
                # Get email content
                email_data = get_email_content(
                    service,
                    email["id"],
                    preferred_content_type="text/html" if html_preferred else "text/plain"
                )
                
                # Convert to markdown
                markdown_content = convert_email_to_markdown(email_data)
                
                # Save to file
                save_email_to_markdown(
                    email_data=email_data,
                    markdown_content=markdown_content,
                    output_dir=output_dir
                )
                
                converted_count += 1
                
            except Exception as e:
                typer.echo(f"Error converting email {email['id']}: {str(e)}", err=True)
        
        typer.echo(f"Successfully converted {converted_count} emails to {output_dir}")
        
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    app()
