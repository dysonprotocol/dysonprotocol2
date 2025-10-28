#!/usr/bin/env python3

import sys
import re
from collections import defaultdict
from pathlib import Path
import os

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

def print_file_coverage(filename, file_coverage, file_path, output_dir):
    """Print coverage for a single file to its own output file"""
    # Create output path: $output_dir/x/whaleswap/keeper/genesis.go.txt
    relative_path = filename.replace("dysonprotocol.com/", "")
    output_path = Path(output_dir) / f"{relative_path}.txt"
    
    # Create parent directories
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    statements = 0
    covered = 0
    
    with open(output_path, 'w', encoding='utf-8') as out:
        print(f"File: {filename}", file=out)
        print(f"Source: {file_path}", file=out)
        print(file=out)
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as src:
            lines = src.readlines()

        # Track the most recent coverage count seen to propagate across following lines
        last_display_count = None

        for i, line in enumerate(lines, 1):
            line = line.rstrip('\n')
            # Use None to distinguish between lines that are in any block vs. outside all blocks
            maybe_count = file_coverage.get(i)

            # Update propagation source when this line has a coverage record (covered or not)
            if maybe_count is not None:
                last_display_count = maybe_count

            # Count statements only where the coverage profile has a block entry starting/covering this line
            if maybe_count is not None:
                statements += 1
                if maybe_count > 0:
                    covered += 1

            # Determine displayed prefix: propagate last seen count across subsequent code lines
            # Avoid propagating across empty lines to reduce visual noise
            display_count = last_display_count if (last_display_count is not None and line.strip() != "") else None

            if display_count is not None:
                prefix = f"{display_count:4d} "
            else:
                prefix = "     "  # no statement and no propagated context

            # Only print non-empty lines or lines with coverage info
            if prefix.strip() or line.strip():
                print(f"{prefix} {i:4d}: {line}", file=out)

        # Per-file summary
        print(file=out)
        coverage_pct = (covered / statements * 100) if statements > 0 else 0.0
        print(f"Coverage: {coverage_pct:.1f}% ({covered}/{statements} statements)", file=out)
    
    return statements, covered


def print_line_by_line(coverage_data, output_dir):
    """Generate individual coverage files for each source file"""
    total_statements = 0
    total_covered = 0
    files_processed = 0
    files_not_found = []

    for filename in sorted(coverage_data.keys()):
        if not filename.startswith("dysonprotocol.com/"):
            continue
        
        file_path = Path(filename.replace("dysonprotocol.com/", ""))
        if not file_path.exists():
            files_not_found.append(filename)
            continue

        file_coverage = coverage_data[filename]
        statements, covered = print_file_coverage(filename, file_coverage, file_path, output_dir)
        
        total_statements += statements
        total_covered += covered
        files_processed += 1

    # Write summary file
    summary_path = Path(output_dir) / "coverage_summary.txt"
    with open(summary_path, 'w', encoding='utf-8') as out:
        print(f"Coverage Summary", file=out)
        print(f"================", file=out)
        print(file=out)
        print(f"Files processed: {files_processed}", file=out)
        
        if files_not_found:
            print(f"Files not found: {len(files_not_found)}", file=out)
            for fn in files_not_found:
                print(f"  - {fn}", file=out)
            print(file=out)
        
        if total_statements > 0:
            overall_pct = total_covered / total_statements * 100
            print(f"Overall Coverage: {overall_pct:.1f}% ({total_covered}/{total_statements} statements)", file=out)
        else:
            print(f"No statements found in coverage data", file=out)
    
    print(f"Coverage reports written to: {output_dir}/")
    print(f"  - {files_processed} individual file reports")
    print(f"  - Summary: {summary_path}")
    if total_statements > 0:
        overall_pct = total_covered / total_statements * 100
        print(f"  - Overall: {overall_pct:.1f}% ({total_covered}/{total_statements} statements)")

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python3 print_coverage.py <coverage.out> [output_dir]", file=sys.stderr)
        sys.exit(1)

    profile_path = sys.argv[1]
    if not Path(profile_path).exists():
        print(f"Error: {profile_path} not found", file=sys.stderr)
        sys.exit(1)

    # Default output directory is same as coverage.out location
    if len(sys.argv) == 3:
        output_dir = sys.argv[2]
    else:
        # Use coverage/ subdirectory in current directory
        output_dir = "coverage"
    
    coverage_data = parse_coverage_profile(profile_path)
    print_line_by_line(coverage_data, output_dir)

if __name__ == "__main__":
    main()