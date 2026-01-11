"""
Bank-specific CSV adapters for standardizing transaction data.

This module provides a framework for converting bank-specific CSV formats
into a standardized schema that can be used across the finance analysis pipeline.

Standard Schema:
    date: Transaction date (YYYY-MM-DD)
    description: Transaction description
    amount: Transaction amount (negative for debits, positive for credits)
    type: Transaction type (Sale, Return, Payment, Debit, Credit, etc.)
    category: Original bank category
    source: Bank identifier (e.g., "Chase_6559")
    month: Month in YYYY-MM format
    year: Year in YYYY format
"""

from abc import ABC, abstractmethod
from typing import Optional, List
import pandas as pd
from datetime import datetime
import re


class BankAdapter(ABC):
    """Base class for bank-specific CSV adapters."""

    def __init__(self, source_identifier: str):
        """
        Initialize the adapter.

        Args:
            source_identifier: Unique identifier for this data source (e.g., "Chase_6559")
        """
        self.source_identifier = source_identifier

    @abstractmethod
    def can_handle(self, df: pd.DataFrame, file_path: str) -> bool:
        """
        Determine if this adapter can handle the given CSV.

        Args:
            df: DataFrame loaded from CSV
            file_path: Path to the CSV file

        Returns:
            True if this adapter can handle this CSV format
        """
        pass

    @abstractmethod
    def parse(self, file_path: str) -> pd.DataFrame:
        """
        Parse the bank-specific CSV and return standardized DataFrame.

        Args:
            file_path: Path to the CSV file

        Returns:
            DataFrame with standardized schema
        """
        pass

    def _add_derived_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add derived fields (month, year) to the DataFrame.

        Args:
            df: DataFrame with 'date' column

        Returns:
            DataFrame with month and year columns added
        """
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.strftime('%Y-%m')
        df['year'] = df['date'].dt.year
        return df

    def _add_source(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add source identifier to DataFrame.

        Args:
            df: DataFrame to add source to

        Returns:
            DataFrame with source column added
        """
        df['source'] = self.source_identifier
        return df


class ChaseCreditAdapter(BankAdapter):
    """Adapter for Chase credit card CSV exports."""

    def can_handle(self, df: pd.DataFrame, file_path: str) -> bool:
        """Check if CSV has Chase credit card format."""
        expected_columns = {'Transaction Date', 'Post Date', 'Description', 'Category', 'Type', 'Amount', 'Memo'}
        return expected_columns.issubset(set(df.columns))

    def parse(self, file_path: str) -> pd.DataFrame:
        """Parse Chase credit card CSV."""
        df = pd.read_csv(file_path)

        standardized = pd.DataFrame({
            'date': pd.to_datetime(df['Transaction Date']),
            'description': df['Description'],
            'amount': df['Amount'],
            'type': df['Type'],
            'category': df['Category']
        })

        standardized = self._add_source(standardized)
        standardized = self._add_derived_fields(standardized)

        return standardized


class ChaseCheckingAdapter(BankAdapter):
    """Adapter for Chase checking account CSV exports."""

    def can_handle(self, df: pd.DataFrame, file_path: str) -> bool:
        """Check if CSV has Chase checking format."""
        expected_columns = {'Details', 'Posting Date', 'Description', 'Amount', 'Type', 'Balance'}
        return expected_columns.issubset(set(df.columns))

    def parse(self, file_path: str) -> pd.DataFrame:
        """Parse Chase checking CSV."""
        # This CSV has trailing commas that create extra empty columns
        # Need to read with explicit column names to handle this properly
        df = pd.read_csv(file_path)

        # Check if columns are misaligned (happens with trailing commas)
        if 'Posting Date' in df.columns and df['Posting Date'].dtype == 'object':
            # Columns shifted - first value is in wrong column
            # Actual structure: Details(CREDIT/DEBIT), Posting Date, Description, Amount, Type, Balance, Check#, empty
            standardized = pd.DataFrame({
                'date': pd.to_datetime(df['Details']),  # Date is in Details column
                'description': df['Posting Date'].astype(str),  # Description is in Posting Date column
                'amount': pd.to_numeric(df['Description']),  # Amount is in Description column
                'type': df['Amount'],  # Type is in Amount column (CREDIT/DEBIT originally, but ACH_CREDIT etc now)
                'category': 'Checking'  # Generic category for checking transactions
            })
        else:
            # Normal case
            standardized = pd.DataFrame({
                'date': pd.to_datetime(df['Posting Date']),
                'description': df['Description'].astype(str),
                'amount': pd.to_numeric(df['Amount']),
                'type': df['Details'],
                'category': df['Type']
            })

        standardized = self._add_source(standardized)
        standardized = self._add_derived_fields(standardized)

        return standardized


class SFCUAdapter(BankAdapter):
    """Adapter for SFCU (Stanford Federal Credit Union) CSV exports."""

    def can_handle(self, df: pd.DataFrame, file_path: str) -> bool:
        """Check if CSV has SFCU format."""
        expected_columns = {'Account Number', 'Post Date', 'Description', 'Debit', 'Credit', 'Category', 'Status', 'Balance'}
        return expected_columns.issubset(set(df.columns))

    def parse(self, file_path: str) -> pd.DataFrame:
        """Parse SFCU CSV."""
        df = pd.read_csv(file_path)

        # Convert Debit/Credit to single amount column
        # Debit is negative, Credit is positive
        df['amount'] = df['Credit'].fillna(0) - df['Debit'].fillna(0)

        # Infer type from Debit/Credit
        df['type'] = df.apply(
            lambda row: 'Credit' if pd.notna(row['Credit']) and row['Credit'] != 0 else 'Debit',
            axis=1
        )

        standardized = pd.DataFrame({
            'date': pd.to_datetime(df['Post Date']),
            'description': df['Description'],
            'amount': df['amount'],
            'type': df['type'],
            'category': df['Category']
        })

        standardized = self._add_source(standardized)
        standardized = self._add_derived_fields(standardized)

        return standardized


class CitiAdapter(BankAdapter):
    """Adapter for Citi credit card CSV exports."""

    def can_handle(self, df: pd.DataFrame, file_path: str) -> bool:
        """Check if CSV has Citi format by looking at file content."""
        # Citi CSVs have metadata rows at the top, so we need to check the file directly
        try:
            with open(file_path, 'r') as f:
                first_lines = [f.readline() for _ in range(5)]
                # Look for Citi-specific patterns
                content = ''.join(first_lines)
                if 'Card:' in content or 'Time period of report:' in content:
                    return True
        except:
            pass
        return False

    def parse(self, file_path: str) -> pd.DataFrame:
        """Parse Citi CSV, skipping header metadata."""
        # Read file and find where actual data starts
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Find the header row (contains "Date,Description,Debit,Credit")
        header_row = 0
        for i, line in enumerate(lines):
            if 'Date,Description,Debit,Credit' in line:
                header_row = i
                break

        # Read CSV starting from the header row
        df = pd.read_csv(file_path, skiprows=header_row)

        # Convert Debit/Credit to single amount column
        # Debit is negative, Credit is positive
        df['Debit'] = pd.to_numeric(df['Debit'].replace(r'[\$,]', '', regex=True), errors='coerce').fillna(0)
        df['Credit'] = pd.to_numeric(df['Credit'].replace(r'[\$,]', '', regex=True), errors='coerce').fillna(0)
        df['amount'] = df['Credit'] - df['Debit']

        # Infer type from Debit/Credit
        df['type'] = df.apply(
            lambda row: 'Credit' if row['Credit'] != 0 else 'Debit',
            axis=1
        )

        standardized = pd.DataFrame({
            'date': pd.to_datetime(df['Date']),
            'description': df['Description'],
            'amount': df['amount'],
            'type': df['type'],
            'category': df['Category']
        })

        standardized = self._add_source(standardized)
        standardized = self._add_derived_fields(standardized)

        return standardized


class BofAAdapter(BankAdapter):
    """Adapter for Bank of America CSV exports."""

    def can_handle(self, df: pd.DataFrame, file_path: str) -> bool:
        """Check if CSV has BofA format by looking at file content."""
        # BofA CSVs have summary rows at the top
        try:
            with open(file_path, 'r') as f:
                first_lines = [f.readline() for _ in range(10)]
                content = ''.join(first_lines)
                if 'Beginning balance' in content and 'Total credits' in content:
                    return True
        except:
            pass
        return False

    def parse(self, file_path: str) -> pd.DataFrame:
        """Parse BofA CSV, skipping header summary."""
        # Read file and find where actual data starts
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Find the data header row (contains "Date,Description,Amount,Running Bal.")
        header_row = 0
        for i, line in enumerate(lines):
            if 'Date,Description,Amount,Running Bal' in line:
                header_row = i
                break

        # Read CSV starting from the header row
        df = pd.read_csv(file_path, skiprows=header_row)

        # Skip the "Beginning balance" row
        df = df[~df['Description'].str.contains('Beginning balance', na=False)]

        # Clean amount column (remove commas and convert to float)
        df['Amount'] = pd.to_numeric(df['Amount'].replace(r'[\$,]', '', regex=True), errors='coerce')

        # Infer type from amount (positive = credit, negative = debit)
        df['type'] = df['Amount'].apply(lambda x: 'Credit' if x > 0 else 'Debit')

        # Extract category from description if possible, otherwise mark as 'Uncategorized'
        df['category'] = 'Uncategorized'

        standardized = pd.DataFrame({
            'date': pd.to_datetime(df['Date']),
            'description': df['Description'],
            'amount': df['Amount'],
            'type': df['type'],
            'category': df['category']
        })

        standardized = self._add_source(standardized)
        standardized = self._add_derived_fields(standardized)

        return standardized


class BankDetector:
    """Automatically detect which bank adapter to use for a given CSV."""

    @staticmethod
    def detect_and_parse(file_path: str) -> pd.DataFrame:
        """
        Auto-detect bank type and parse CSV.

        Args:
            file_path: Path to CSV file

        Returns:
            Standardized DataFrame

        Raises:
            ValueError: If no adapter can handle this CSV format
        """
        # Extract source identifier from filename
        import os
        filename = os.path.basename(file_path)
        source_id = filename.replace('.csv', '').replace('.CSV', '')

        # Try to read first few rows to check format
        try:
            df_sample = pd.read_csv(file_path, nrows=5)
        except:
            df_sample = pd.DataFrame()

        # Initialize all adapters
        adapters = [
            CitiAdapter(source_id),      # Check Citi first (has metadata)
            BofAAdapter(source_id),       # Check BofA second (has metadata)
            ChaseCreditAdapter(source_id),
            ChaseCheckingAdapter(source_id),
            SFCUAdapter(source_id),
        ]

        # Find matching adapter
        for adapter in adapters:
            if adapter.can_handle(df_sample, file_path):
                print(f"✓ Detected {adapter.__class__.__name__} for {filename}")
                return adapter.parse(file_path)

        raise ValueError(f"Could not detect bank format for {file_path}")
