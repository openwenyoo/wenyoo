#!/usr/bin/env python3
"""
Log Parser for Wenyoo

Parse and extract useful information from wenyoo.log files.

Usage examples:
    # Extract all user inputs from yesterday
    python scripts/parse_log.py --info user_input --date yesterday
    
    # Extract errors from last 7 days, output to file
    python scripts/parse_log.py --info errors --days 7 -o errors_report.txt
    
    # Extract connections and sessions from a specific date range
    python scripts/parse_log.py --info connections,sessions --start 2026-01-15 --end 2026-01-18
    
    # Extract all info types for today
    python scripts/parse_log.py --info all --date today
    
    # Use custom log file
    python scripts/parse_log.py --log ./src/wenyoo.log --info user_input --date yesterday
"""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional, TextIO


# Log line pattern: YYYY-MM-DD HH:MM:SS,mmm - logger.name - LEVEL - message
LOG_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2},\d{3})\s+-\s+([^\s]+)\s+-\s+(INFO|DEBUG|WARNING|ERROR|CRITICAL)\s+-\s+(.*)$'
)

# Info type patterns
INFO_PATTERNS = {
    'user_input': [
        # "Received command from player ...: XXX"
        re.compile(r"Received command from player .*?:\s*(.+)$"),
        # "Processing input 'XXX' for player"
        re.compile(r"Processing input '([^']+)' for player"),
        # "'user_input': 'XXX'" in LLM context
        re.compile(r"'user_input':\s*'([^']+)'"),
        # "Processing interaction for NPC 'X' with input: 'Y'"
        re.compile(r"Processing interaction for NPC '[^']+' with input: '([^']+)'"),
    ],
    'connections': [
        re.compile(r'Player.*connected'),
        re.compile(r'Player.*disconnected'),
        re.compile(r'WebSocket.*connection'),
        re.compile(r'connection\s+(open|closed)'),
    ],
    'sessions': [
        re.compile(r'(creating|joined|cleanup|removed).*session', re.IGNORECASE),
        re.compile(r'Session.*is\s+(empty|now empty|removed)'),
        re.compile(r'is creating session'),
    ],
    'actions': [
        re.compile(r'Executing action'),
        re.compile(r'Available actions identified'),
        re.compile(r'Action.*finished'),
        re.compile(r'tool call', re.IGNORECASE),
        re.compile(r'tool result', re.IGNORECASE),
        re.compile(r'commit_world_event', re.IGNORECASE),
        re.compile(r'roll_dice', re.IGNORECASE),
        re.compile(r'present_form', re.IGNORECASE),
    ],
    'stories': [
        re.compile(r'Successfully loaded.*story'),
        re.compile(r'Loading story from'),
        re.compile(r'Found \d+ valid stories'),
        re.compile(r'selected story'),
        re.compile(r'Created original backup'),
    ],
    'errors': [
        re.compile(r'.*'),  # Match all for ERROR level
    ],
    'llm': [
        re.compile(r'LLM context'),
        re.compile(r'LLM metrics', re.IGNORECASE),
        re.compile(r'Generated response'),
        re.compile(r'Generated text response'),
        re.compile(r'LLM generated'),
        re.compile(r'ollama|dashscope|openai|anthropic|claude', re.IGNORECASE),
        re.compile(r'HTTP Request:\s+POST\s+https://', re.IGNORECASE),
        re.compile(r'Retrying request to /v1/messages', re.IGNORECASE),
    ],
    'players': [
        re.compile(r'Player\s+\w+.*selected'),
        re.compile(r'Assigned character'),
        re.compile(r'Starting game loop for player'),
        re.compile(r'set name to', re.IGNORECASE),
        re.compile(r'Auto-assigned character', re.IGNORECASE),
        re.compile(r'set_player_character', re.IGNORECASE),
    ],
    'movements': [
        re.compile(r'moved player.*to node'),
        re.compile(r'Attempting to move player'),
        re.compile(r'goto_node effect'),
        re.compile(r'state_applied.*visited_nodes', re.IGNORECASE),
        re.compile(r'Successfully moved player', re.IGNORECASE),
    ],
}

INTERNAL_USER_INPUT_PREFIXES = (
    'get_object_actions:',
)


@dataclass
class LogEntry:
    """Parsed log entry, including any continuation lines."""

    timestamp: datetime
    logger: str
    level: str
    message: str
    raw_text: str


def parse_date(date_str: str) -> datetime:
    """Parse a date string into a datetime object."""
    if date_str.lower() == 'today':
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str.lower() == 'yesterday':
        return (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        return datetime.strptime(date_str, '%Y-%m-%d')


def get_date_range(args) -> tuple[datetime, datetime]:
    """Determine the date range from arguments."""
    now = datetime.now()
    
    if args.date:
        start = parse_date(args.date)
        end = start + timedelta(days=1)
    elif args.days:
        start = now - timedelta(days=args.days)
        end = now + timedelta(days=1)
    elif args.start or args.end:
        start = parse_date(args.start) if args.start else datetime.min
        end = parse_date(args.end) + timedelta(days=1) if args.end else now + timedelta(days=1)
    else:
        # Default: all time
        start = datetime.min
        end = datetime.max
    
    return start, end


def iter_log_entries(log_file: Path) -> Iterator[LogEntry]:
    """Yield parsed log entries, preserving multiline continuations."""
    current_entry: Optional[LogEntry] = None
    raw_lines: list[str] = []
    message_lines: list[str] = []

    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
        for raw_line in f:
            parsed = parse_log_line(raw_line)
            if parsed:
                if current_entry is not None:
                    current_entry.message = '\n'.join(message_lines)
                    current_entry.raw_text = ''.join(raw_lines)
                    yield current_entry

                timestamp, logger, level, message = parsed
                current_entry = LogEntry(
                    timestamp=timestamp,
                    logger=logger,
                    level=level,
                    message=message,
                    raw_text=raw_line,
                )
                raw_lines = [raw_line]
                message_lines = [message]
                continue

            if current_entry is None:
                continue

            raw_lines.append(raw_line)
            message_lines.append(raw_line.rstrip('\r\n'))

    if current_entry is not None:
        current_entry.message = '\n'.join(message_lines)
        current_entry.raw_text = ''.join(raw_lines)
        yield current_entry


def matches_info_type(entry: LogEntry, info_type: str) -> Optional[str]:
    """Check if a log line matches the given info type and extract relevant data."""
    # Special handling for errors - only match ERROR level
    if info_type == 'errors':
        if entry.level in {'ERROR', 'CRITICAL'}:
            return entry.message
        return None

    searchable_text = f"{entry.logger} {entry.message}"

    if info_type == 'user_input':
        return extract_user_input(entry.message)

    # For other info types, check patterns
    patterns = INFO_PATTERNS.get(info_type, [])
    for pattern in patterns:
        match = pattern.search(searchable_text)
        if match:
            return entry.message

    return None


def extract_user_input(message: str) -> Optional[str]:
    """Extract user input from a log line."""
    for pattern in INFO_PATTERNS['user_input']:
        match = pattern.search(message)
        if match and match.groups():
            user_input = match.group(1).strip()
            if user_input.startswith(INTERNAL_USER_INPUT_PREFIXES):
                return None
            return user_input
    return None


def parse_log_line(line: str) -> Optional[tuple[datetime, str, str, str]]:
    """Parse a single log line and return (timestamp, logger, level, message)."""
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None
    
    date_str, time_str, logger, level, message = match.groups()
    try:
        timestamp = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M:%S,%f')
    except ValueError:
        return None
    
    return timestamp, logger, level, message


def process_log(
    log_file: Path,
    start_date: datetime,
    end_date: datetime,
    info_types: list[str],
    output: TextIO,
    verbose: bool = False,
    extract_only: bool = False,
):
    """Process the log file and extract matching entries."""
    match_count = 0
    line_count = 0

    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
        for _ in f:
            line_count += 1

    for entry in iter_log_entries(log_file):
        # Check date range
        if entry.timestamp < start_date or entry.timestamp >= end_date:
            continue

        # Check info types
        for info_type in info_types:
            match_result = matches_info_type(entry, info_type)
            if not match_result:
                continue

            if extract_only and info_type == 'user_input':
                user_input = extract_user_input(entry.message)
                if not user_input:
                    break
                output.write(f"[{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {user_input}\n")
            elif verbose:
                output.write(f"[{info_type.upper()}] {entry.raw_text}")
                if not entry.raw_text.endswith('\n'):
                    output.write('\n')
            else:
                output.write(
                    f"{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - "
                    f"{entry.level} - {entry.message}\n"
                )

            match_count += 1
            break  # Only output once per entry

    return match_count, line_count


def list_available_dates(log_file: Path) -> list[str]:
    """List all unique dates in the log file."""
    dates = set()
    for entry in iter_log_entries(log_file):
        dates.add(entry.timestamp.strftime('%Y-%m-%d'))
    return sorted(dates)


def configure_stdio() -> None:
    """Prefer UTF-8 console output when the runtime supports reconfiguration."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            try:
                reconfigure(encoding='utf-8', errors='replace')
            except ValueError:
                # Some redirected streams cannot be reconfigured.
                pass


def main():
    configure_stdio()
    parser = argparse.ArgumentParser(
        description='Parse Wenyoo log files to extract useful information.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available info types:
  user_input   - Player game inputs and NPC interactions
  connections  - Player connection/disconnection events
  sessions     - Game session creation/joining/cleanup
  actions      - Game action execution
  stories      - Story loading events
  errors       - Error messages
  llm          - LLM-related logs (calls, responses)
  players      - Player selection and character assignment
  movements    - Player movement between nodes
  all          - All of the above

Examples:
  # Extract user inputs from yesterday
  python scripts/parse_log.py --info user_input --date yesterday
  
  # Extract errors from last 7 days, save to file
  python scripts/parse_log.py --info errors --days 7 -o errors.txt
  
  # Extract connections and sessions from date range
  python scripts/parse_log.py --info connections,sessions --start 2026-01-15 --end 2026-01-18
  
  # Extract only the input text (not full log lines)
  python scripts/parse_log.py --info user_input --date yesterday --extract-only
  
  # List available dates in log
  python scripts/parse_log.py --list-dates
        """
    )
    
    parser.add_argument(
        '--log', '-l',
        type=Path,
        default=Path(__file__).parent.parent / 'wenyoo.log',
        help='Path to the log file (default: wenyoo.log in project root)'
    )
    
    parser.add_argument(
        '--info', '-i',
        type=str,
        default='all',
        help='Comma-separated list of info types to extract (default: all)'
    )
    
    parser.add_argument(
        '--date', '-d',
        type=str,
        help='Specific date to filter (YYYY-MM-DD, "today", or "yesterday")'
    )
    
    parser.add_argument(
        '--start', '-s',
        type=str,
        help='Start date for range filter (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end', '-e',
        type=str,
        help='End date for range filter (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--days', '-D',
        type=int,
        help='Filter to last N days'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output file path (default: stdout)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Include info type labels and full log lines'
    )
    
    parser.add_argument(
        '--extract-only', '-x',
        action='store_true',
        help='For user_input, extract only the input text (not full log lines)'
    )
    
    parser.add_argument(
        '--list-dates',
        action='store_true',
        help='List all available dates in the log file and exit'
    )
    
    parser.add_argument(
        '--count',
        action='store_true',
        help='Only show count of matches, not the actual content'
    )
    
    args = parser.parse_args()
    
    # Resolve log file path
    if not args.log.is_absolute():
        args.log = Path.cwd() / args.log
    
    if not args.log.exists():
        print(f"Error: Log file not found: {args.log}", file=sys.stderr)
        sys.exit(1)
    
    # Handle --list-dates
    if args.list_dates:
        dates = list_available_dates(args.log)
        print(f"Available dates in {args.log.name}:")
        for date in dates:
            print(f"  {date}")
        print(f"\nTotal: {len(dates)} dates")
        sys.exit(0)
    
    # Parse info types
    info_types = [t.strip().lower() for t in args.info.split(',')]
    if 'all' in info_types:
        info_types = list(INFO_PATTERNS.keys())
    
    # Validate info types
    for t in info_types:
        if t not in INFO_PATTERNS:
            print(f"Error: Unknown info type '{t}'", file=sys.stderr)
            print(f"Available types: {', '.join(INFO_PATTERNS.keys())}", file=sys.stderr)
            sys.exit(1)
    
    # Get date range
    start_date, end_date = get_date_range(args)
    
    # Prepare output
    if args.output:
        output = open(args.output, 'w', encoding='utf-8')
    else:
        output = sys.stdout
    
    try:
        # Print header info to stderr so it doesn't interfere with output
        print(f"Parsing: {args.log}", file=sys.stderr)
        print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", file=sys.stderr)
        print(f"Info types: {', '.join(info_types)}", file=sys.stderr)
        print("-" * 60, file=sys.stderr)
        
        if args.count:
            # Count mode - redirect output to null
            from io import StringIO
            null_output = StringIO()
            match_count, line_count = process_log(
                args.log, start_date, end_date, info_types, null_output, 
                args.verbose, args.extract_only
            )
        else:
            match_count, line_count = process_log(
                args.log, start_date, end_date, info_types, output,
                args.verbose, args.extract_only
            )
        
        print("-" * 60, file=sys.stderr)
        print(f"Processed {line_count:,} lines, found {match_count:,} matches", file=sys.stderr)
        
        if args.output:
            print(f"Output written to: {args.output}", file=sys.stderr)
    
    finally:
        if args.output and output != sys.stdout:
            output.close()


if __name__ == '__main__':
    main()
