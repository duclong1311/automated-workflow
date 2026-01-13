"""
Jira text formatter - format text thành Jira wiki markup
"""
import re


def format_description_for_jira(text: str) -> str:
    """
    Format description text thành Jira wiki markup để hiển thị đẹp hơn
    
    Jira wiki markup:
    - *bold* cho chữ đậm
    - _italic_ cho chữ nghiêng
    - h1., h2., h3. cho headers
    - * cho bullet level 1
    - ** cho bullet level 2
    - *** cho bullet level 3
    - ---- cho horizontal line
    - {code}...{code} cho code block
    """
    if not text:
        return text
    
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            formatted_lines.append('')
            continue
        
        # Detect và convert bullet points
        # Markdown style bullets: - , * , + 
        # Convert to Jira bullets: *, **, ***
        
        # Count leading spaces to determine level
        leading_spaces = len(line) - len(line.lstrip())
        indent_level = leading_spaces // 2  # 2 spaces = 1 level
        
        # Remove markdown bullet markers
        if re.match(r'^[\*\-\+]\s+', stripped):
            content = re.sub(r'^[\*\-\+]\s+', '', stripped)
            bullet = '*' * max(1, indent_level + 1)  # At least 1 star
            formatted_lines.append(f"{bullet} {content}")
        else:
            # Regular text - check if it looks like a header
            if stripped.startswith('#'):
                # Markdown header
                header_level = len(re.match(r'^#+', stripped).group())
                content = re.sub(r'^#+\s*', '', stripped)
                formatted_lines.append(f"h{header_level}. {content}")
            elif stripped.startswith('[') and stripped.endswith(']'):
                # Looks like a section header
                content = stripped.strip('[]')
                formatted_lines.append(f"*{content}*")
                formatted_lines.append('')  # Add space after header
            else:
                # Regular text
                formatted_lines.append(stripped)
    
    return '\n'.join(formatted_lines)


def format_with_sections(text: str) -> str:
    """
    Format text với sections được phân cách rõ ràng
    Tự động detect sections từ text
    """
    if not text:
        return text
    
    lines = text.split('\n')
    formatted_lines = []
    
    in_code_block = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Empty line
        if not stripped:
            if not in_code_block:
                formatted_lines.append('')
            continue
        
        # Code blocks
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            if in_code_block:
                formatted_lines.append('{code}')
            else:
                formatted_lines.append('{code}')
            continue
        
        if in_code_block:
            formatted_lines.append(line)
            continue
        
        # Headers - những dòng kết thúc bằng ':'
        if stripped.endswith(':') and len(stripped) > 3 and not any(c in stripped for c in ['*', '-', '+']):
            header_text = stripped.rstrip(':')
            formatted_lines.append(f"h3. {header_text}")
            formatted_lines.append('')
            continue
        
        # Bullets
        leading_spaces = len(line) - len(line.lstrip())
        indent_level = leading_spaces // 2
        
        if re.match(r'^[\*\-\+]\s+', stripped):
            content = re.sub(r'^[\*\-\+]\s+', '', stripped)
            bullet = '*' * max(1, indent_level + 1)
            formatted_lines.append(f"{bullet} {content}")
        else:
            # Regular text
            formatted_lines.append(stripped)
    
    return '\n'.join(formatted_lines)


def auto_format_jira_description(text: str) -> str:
    """
    Auto format description với smart detection
    - Detect headers
    - Format bullets
    - Add spacing
    - Format bold/italic
    """
    if not text:
        return text
    
    # First pass: basic formatting
    formatted = format_with_sections(text)
    
    # Enhance: add bold to important terms
    # Pattern: text trong [] hoặc text kết thúc bằng :
    lines = formatted.split('\n')
    enhanced = []
    
    for line in lines:
        # Bold text in [brackets]
        line = re.sub(r'\[([^\]]+)\]', r'*\1*', line)
        
        # Detect URLs and keep them
        # (Jira auto-links URLs, không cần format)
        
        enhanced.append(line)
    
    return '\n'.join(enhanced)
