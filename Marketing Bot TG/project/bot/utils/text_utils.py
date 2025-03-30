"""
Utility functions for text processing
"""
import re

def remove_asterisks(text):
    """
    Remove asterisks often used for text formatting in markdown
    """
    # Remove asterisks patterns (*, **, ***)
    cleaned_text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    return cleaned_text

def split_message(text, max_length=4000):
    """
    Split a long message into smaller chunks
    """
    if len(text) <= max_length:
        return [text]

    # Find suitable break points (paragraphs)
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break

        # Try to find a newline character before the max_length
        cutoff = text[:max_length].rfind('\n')
        if cutoff == -1:  # If no newline, try space
            cutoff = text[:max_length].rfind(' ')
        if cutoff == -1:  # If no space, force break
            cutoff = max_length - 1

        parts.append(text[:cutoff + 1])
        text = text[cutoff + 1:]

    return parts

def split_response_into_sections(response):
    """
    Split a response into logical sections based on numbers (1., 2., etc.)
    """
    # Find section headings (numbered points)
    pattern = r'(\d+\.\s+[^\n]+)'
    matches = re.finditer(pattern, response)

    section_positions = []
    for match in matches:
        section_positions.append(match.start())

    # Add end of string position
    section_positions.append(len(response))

    sections = []
    for i in range(len(section_positions) - 1):
        start = section_positions[i]
        end = section_positions[i + 1]
        section_text = response[start:end].strip()
        sections.append(section_text)

    # Check for text before the first section
    if section_positions and section_positions[0] > 0:
        intro = response[:section_positions[0]].strip()
        if intro:
            sections.insert(0, intro)

    return sections

def format_business_plan(text):
    """
    Format business plan text:
    - Remove asterisk formatting
    - Improve section headings and spacing
    - Ensure proper HTML formatting for Telegram
    
    Args:
        text: The business plan text to format
        
    Returns:
        Formatted business plan text
    """
    # Remove markdown asterisks formatting
    text = remove_asterisks(text)
    
    # Replace section numbers with bold formatting (1. -> <b>1.</b>)
    text = re.sub(r'(\d+\.\s+)([^\n]+)', r'<b>\1\2</b>', text)
    
    # Ensure there's blank line after section headers
    text = re.sub(r'(</b>)(\n)(?!\n)', r'\1\n\n', text)
    
    # Remove any existing multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text
