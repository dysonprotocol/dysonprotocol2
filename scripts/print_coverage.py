#!/usr/bin/env python3

import sys
import re
from collections import defaultdict
from pathlib import Path

def parse_coverage_profile(profile_path):
    """Parse Go coverage profile and return list of (file, line, count)"""
    coverage = defaultdict(lambda: defaultdict(int))  # file -> line -> count

    with open(profile_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("mode:"):
                continue
            # Format: filename:start.line,start.col end.line,end.col num_statements count
            try:
                # Split by last two spaces to get count and num_statements
                parts = line.rsplit(' ', 2)
                if len(parts) == 3:
                    key, num_statements, count_str = parts
                else:
                    # Fallback for older format
                    key, count_str = line.rsplit(' ', 1)
                
                filename, positions = key.split(':', 1)
                count = int(count_str)

                # Parse start and end line from positions like "15.70,17.52"
                start_end = positions.split(' ')
                start_pos = start_end[0]
                start_line = int(start_pos.split(',')[0].split('.')[0])
                
                # If there's an end position, parse it too
                if len(start_end) > 1:
                    end_pos = start_end[1]
                    end_line = int(end_pos.split(',')[0].split('.')[0])
                else:
                    end_line = start_line

                # Mark all lines in the range
                for line_num in range(start_line, end_line + 1):
                    coverage[filename][line_num] = max(coverage[filename][line_num], count)
                    
            except Exception as e:
                print(f"Warning: Failed to parse line: {line} -> {e}", file=sys.stderr)

    return coverage

def has_statement(coverage_data, filename, line_num):
    """Check if any block starts on this line (i.e., has a statement)"""
    return line_num in coverage_data.get(filename, {})

def print_line_by_line(coverage_data, output_file=None):
    out = open(output_file, 'w') if output_file else sys.stdout

    total_statements = 0
    total_covered = 0

    for filename in sorted(coverage_data.keys()):
        if not filename.startswith("dysonprotocol.com/"):
            continue
        
        file_path = Path(filename.replace("dysonprotocol.com/", ""))
        if not file_path.exists():
            print(f"File: {filename}", file=out)
            print(f"  [Source file not found]", file=out)
            print(file=out)
            continue

        print(f"File: {filename}", file=out)

        file_coverage = coverage_data[filename]
        statements = 0
        covered = 0

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as src:
            lines = src.readlines()

        for i, line in enumerate(lines, 1):
            line = line.rstrip('\n')
            count = file_coverage.get(i, 0)

            # Count statements: any line with a coverage block starting on it
            if i in file_coverage:
                statements += 1
                if count > 0:
                    covered += 1

            # Determine prefix
            if count > 0:
                prefix = f"{count:4d} "
            elif i in file_coverage:
                prefix = "   - "
            else:
                prefix = "     "  # no statement

            # Only print non-empty lines or lines with coverage info
            if prefix.strip() or line.strip():
                print(f"{prefix} {i:4d}: {line}", file=out)

        # Per-file summary
        coverage_pct = (covered / statements * 100) if statements > 0 else 0.0
        print(f"  Coverage: {coverage_pct:.1f}% ({covered}/{statements} statements)", file=out)
        print(file=out)

        total_statements += statements
        total_covered += covered

    # Overall summary
    if total_statements > 0:
        overall_pct = total_covered / total_statements * 100
        print(f"Overall Coverage: {overall_pct:.1f}% ({total_covered}/{total_statements} statements)", file=out)

    if output_file:
        out.close()
        print(f"Line-by-line coverage written to: {output_file}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 print_coverage.py <coverage.out>", file=sys.stderr)
        sys.exit(1)

    profile_path = sys.argv[1]
    if not Path(profile_path).exists():
        print(f"Error: {profile_path} not found", file=sys.stderr)
        sys.exit(1)

    coverage_data = parse_coverage_profile(profile_path)
    print_line_by_line(coverage_data, output_file="coverage_lines.txt")

if __name__ == "__main__":
    main()