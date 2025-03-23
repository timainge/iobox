#!/usr/bin/env python
"""
Iobox - Gmail to Markdown Converter

Main entry point for the application.
"""

import typer
import logging
from pathlib import Path
from datetime import datetime

from iobox.auth import get_gmail_service
from iobox.email_search import search_emails, get_email_content
from iobox.markdown import save_as_markdown
from iobox.file_manager import check_file_exists, ensure_output_directory, list_processed_emails

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create typer app
app = typer.Typer(help="Iobox - Gmail to Markdown Converter")


@app.command()
def convert(
    query: str = typer.Option(..., "--query", "-q", help="Gmail search query"),
    output: Path = typer.Option("output", "--output", "-o", help="Output directory for markdown files"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days back to search for emails"),
    max_results: int = typer.Option(100, "--max", "-m", help="Maximum number of emails to process"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output")
):
    """
    Extract emails from Gmail and save them as markdown files.
    
    Examples:
        python main.py --query "label:inbox subject:(newsletter)" --output ./newsletters --days 30
        python main.py --query "from:example@example.com" --output ./emails --days 10
    """
    # Set logging level based on verbose flag
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info(f"Starting Iobox Gmail to Markdown conversion")
    logger.info(f"Query: {query}")
    logger.info(f"Output directory: {output}")
    logger.info(f"Days back: {days}")
    
    # Ensure output directory exists
    output_str = str(output)
    if not ensure_output_directory(output_str):
        logger.error("Failed to create output directory")
        raise typer.Exit(code=1)
    
    # Get already processed emails to prevent duplicates
    processed_emails = set(list_processed_emails(output_str))
    logger.info(f"Found {len(processed_emails)} already processed emails")
    
    try:
        # Authenticate with Gmail API
        logger.info("Authenticating with Gmail API...")
        service = get_gmail_service()
        
        # Search for emails matching the query
        logger.info(f"Searching for emails matching query: {query}")
        messages = search_emails(service, query, max_results=max_results, days_back=days)
        
        if not messages:
            logger.info("No emails found matching the search criteria")
            return
        
        logger.info(f"Found {len(messages)} emails matching the search criteria")
        
        # Process each email
        processed_count = 0
        skipped_count = 0
        
        for msg in messages:
            msg_id = msg['id']
            
            # Skip already processed emails
            if msg_id in processed_emails:
                logger.debug(f"Skipping already processed email: {msg_id}")
                skipped_count += 1
                continue
            
            # Get email content
            logger.debug(f"Processing email {msg_id}")
            subject, sender, date, content = get_email_content(service, msg_id)
            
            if subject is None:
                logger.warning(f"Failed to retrieve content for email {msg_id}")
                continue
            
            # Save as markdown
            save_as_markdown(subject, sender, date, content, msg_id, output_str)
            processed_count += 1
        
        logger.info(f"Completed processing emails")
        logger.info(f"Processed: {processed_count}, Skipped (already processed): {skipped_count}")
        
    except Exception as e:
        logger.error(f"Error processing emails: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
