"""
CSV Standardization Script

This script processes raw bank CSV files and converts them into a standardized format.
It supports multiple banks and automatically detects the format.

Usage:
    python standardize_csv.py [CSV_FILES...] [OPTIONS]

    # Process all CSVs in data/ directory
    python standardize_csv.py data/*.CSV data/*.csv

    # Process specific files
    python standardize_csv.py data/Chase6559.CSV data/AR_SFCU.csv

Options:
    --output-dir DIR     Directory for individual standardized CSVs (default: data/standardized)
    --merged-output FILE Path for merged output file (default: data/transactions_merged.csv)
    --skip-merged        Don't create merged output file
    --skip-individual    Don't create individual output files

Output:
    - Individual standardized CSVs in output-dir/
    - Merged CSV with all transactions (unless --skip-merged)
"""

import os
import sys
import argparse
from pathlib import Path
import pandas as pd
from bank_adapters import BankDetector


def ensure_directory(path: str) -> None:
    """Create directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)


def standardize_files(
    input_files: list,
    output_dir: str = "data/standardized",
    merged_output: str = "data/transactions_merged.csv",
    skip_merged: bool = False,
    skip_individual: bool = False
) -> None:
    """
    Standardize multiple CSV files.

    Args:
        input_files: List of paths to CSV files to process
        output_dir: Directory to save individual standardized CSVs
        merged_output: Path for merged output file
        skip_merged: If True, don't create merged output
        skip_individual: If True, don't create individual outputs
    """
    # Create output directory
    ensure_directory(output_dir)

    all_transactions = []
    processed_count = 0
    failed_files = []

    print("=" * 80)
    print("CSV STANDARDIZATION")
    print("=" * 80)
    print(f"\nProcessing {len(input_files)} file(s)...\n")

    for file_path in input_files:
        try:
            # Skip if file doesn't exist
            if not os.path.exists(file_path):
                print(f"⚠ Skipping: {file_path} (file not found)")
                continue

            # Skip processed/output files
            filename = os.path.basename(file_path)
            skip_patterns = [
                'category_overrides',
                'transactions_',
                'reclassified_',
                '_standardized'
            ]
            if any(pattern in filename.lower() for pattern in skip_patterns):
                print(f"⊘ Skipping: {filename} (processed/config file)")
                continue

            print(f"Processing: {filename}")

            # Detect and parse
            standardized_df = BankDetector.detect_and_parse(file_path)

            # Save individual file
            if not skip_individual:
                output_filename = f"{Path(filename).stem}_standardized.csv"
                output_path = os.path.join(output_dir, output_filename)
                standardized_df.to_csv(output_path, index=False)
                print(f"  → Saved to: {output_path}")

            # Add to merged list
            all_transactions.append(standardized_df)
            processed_count += 1
            print(f"  ✓ Processed {len(standardized_df)} transactions\n")

        except Exception as e:
            print(f"  ✗ Error: {str(e)}\n")
            failed_files.append((file_path, str(e)))

    # Create merged output
    if not skip_merged and all_transactions:
        print("=" * 80)
        print("MERGING TRANSACTIONS")
        print("=" * 80)

        merged_df = pd.concat(all_transactions, ignore_index=True)

        # Sort by date
        merged_df = merged_df.sort_values('date').reset_index(drop=True)

        # Save merged file
        merged_df.to_csv(merged_output, index=False)

        print(f"\n✓ Merged {len(merged_df)} total transactions")
        print(f"✓ Saved to: {merged_output}\n")

        # Summary statistics
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"\nTotal files processed: {processed_count}/{len(input_files)}")
        print(f"Total transactions: {len(merged_df)}")
        print(f"\nBreakdown by source:")
        source_counts = merged_df['source'].value_counts()
        for source, count in source_counts.items():
            print(f"  {source}: {count} transactions")

        print(f"\nDate range: {merged_df['date'].min()} to {merged_df['date'].max()}")

    # Report failures
    if failed_files:
        print("\n" + "=" * 80)
        print("FAILED FILES")
        print("=" * 80)
        for file_path, error in failed_files:
            print(f"\n✗ {file_path}")
            print(f"  Error: {error}")

    print("\n" + "=" * 80)
    print("COMPLETE")
    print("=" * 80 + "\n")


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Standardize bank CSV files into a common format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all CSVs in data directory
  python standardize_csv.py data/*.CSV data/*.csv

  # Process specific files
  python standardize_csv.py data/Chase6559.CSV data/AR_SFCU.csv

  # Custom output locations
  python standardize_csv.py data/*.CSV --output-dir my_output --merged-output all_transactions.csv
        """
    )

    parser.add_argument(
        'files',
        nargs='+',
        help='CSV files to process'
    )

    parser.add_argument(
        '--output-dir',
        default='data/standardized',
        help='Directory for individual standardized CSVs (default: data/standardized)'
    )

    parser.add_argument(
        '--merged-output',
        default='data/transactions_merged.csv',
        help='Path for merged output file (default: data/transactions_merged.csv)'
    )

    parser.add_argument(
        '--skip-merged',
        action='store_true',
        help="Don't create merged output file"
    )

    parser.add_argument(
        '--skip-individual',
        action='store_true',
        help="Don't create individual output files"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.skip_merged and args.skip_individual:
        print("Error: Cannot skip both merged and individual outputs")
        sys.exit(1)

    # Run standardization
    standardize_files(
        input_files=args.files,
        output_dir=args.output_dir,
        merged_output=args.merged_output,
        skip_merged=args.skip_merged,
        skip_individual=args.skip_individual
    )


if __name__ == "__main__":
    main()
