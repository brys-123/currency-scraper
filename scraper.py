
"""
BANK OF TANZANIA (BOT) EXCHANGE RATE SCRAPER
------------------------------------------------
Source: https://www.bot.go.tz/ExchangeRate/excRates

Features:
1. Supports English and Swahili column headings.
2. Extracts exchange-rate information from BOT.
3. Cleans dates and numerical values.
4. Validates extracted records.
5. Prevents duplicate records.
6. Preserves historical CSV records.
7. Provides detailed execution logs.
8. Suitable for GitHub Actions automation.
"""

import os
import re
import sys
import logging
import unicodedata
from io import StringIO
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import pandas as pd
from bs4 import BeautifulSoup


# ============================================================
# 1. CONFIGURATION
# ============================================================

SOURCE_URL = "https://www.bot.go.tz/ExchangeRate/excRates"

OUTPUT_FILE = Path(__file__).resolve().parent / "BOT_exchange_rate.csv"

TIMEZONE = ZoneInfo("Africa/Dar_es_Salaam")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,sw;q=0.8",
}

REQUIRED_COLUMNS = [
    "Currency",
    "Buying",
    "Selling",
    "Mean",
    "Transaction Date"
]

OUTPUT_COLUMNS = [
    "Currency",
    "Buying",
    "Selling",
    "Mean",
    "Transaction Date",
    "source_url",
    "scraped_at"
]


# ============================================================
# 2. LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("BOT_SCRAPER")


# ============================================================
# 3. COLUMN NAME NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Normalize text by removing accents, spaces and punctuation.
    """

    text = unicodedata.normalize("NFKD", str(text))

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    text = text.lower().strip()

    return re.sub(r"[^a-z0-9]", "", text)


COLUMN_ALIASES = {

    # Serial number
    "sno": "S/NO",
    "serialno": "S/NO",
    "serialnumber": "S/NO",

    # Currency
    "currency": "Currency",
    "sarafu": "Currency",

    # Buying
    "buying": "Buying",
    "kununua": "Buying",
    "buy": "Buying",

    # Selling
    "selling": "Selling",
    "kuuza": "Selling",
    "sell": "Selling",

    # Mean
    "mean": "Mean",
    "average": "Mean",
    "wastani": "Mean",

    # Transaction date
    "transactiondate": "Transaction Date",
    "date": "Transaction Date",
    "tareheyabiashara": "Transaction Date",
    "tarehe": "Transaction Date",
    "ratedate": "Transaction Date",
    "effectivedate": "Transaction Date",
}


def standardize_columns(columns):
    """
    Convert BOT headings into standardized English headings.
    """

    standardized = []

    for column in columns:

        normalized = normalize_text(column)

        standardized.append(
            COLUMN_ALIASES.get(normalized, str(column).strip())
        )

    return standardized


# ============================================================
# 4. CONNECT TO BANK OF TANZANIA
# ============================================================

def fetch_website():

    logger.info("=" * 65)
    logger.info("BOT CURRENCY SCRAPER STARTED")
    logger.info("=" * 65)

    logger.info("Connecting to Bank of Tanzania...")

    try:

        response = requests.get(
            SOURCE_URL,
            headers=HEADERS,
            timeout=60
        )

        response.raise_for_status()

        logger.info(
            "Website response accepted: HTTP %s",
            response.status_code
        )

        return response.text

    except requests.RequestException as error:

        logger.exception("Unable to connect to BOT website.")

        raise RuntimeError(
            f"BOT website connection failed: {error}"
        ) from error


# ============================================================
# 5. EXTRACT BOT EXCHANGE RATE TABLE
# ============================================================

def extract_table(html):

    logger.info("Searching for BOT exchange-rate table...")

    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")

    if not tables:

        raise ValueError(
            "No HTML tables were found on the BOT website."
        )

    logger.info("HTML tables discovered: %s", len(tables))

    for table_number, table in enumerate(tables, start=1):

        rows = table.find_all("tr")

        if not rows:
            continue

        # Check every row for possible table headings.
        for header_index, header_row in enumerate(rows):

            header_cells = header_row.find_all(
                ["th", "td"],
                recursive=False
            )

            if not header_cells:
                continue

            original_headers = [
                cell.get_text(" ", strip=True)
                for cell in header_cells
            ]

            headers = standardize_columns(original_headers)

            # Identify the essential exchange-rate columns.
            essential = {
                "Currency",
                "Buying",
                "Selling",
                "Mean"
            }

            if not essential.issubset(set(headers)):
                continue

            # Find transaction date column.
            if "Transaction Date" not in headers:

                # Try to find the date heading in nearby rows.
                for nearby_row in rows[
                    max(0, header_index - 1):
                    min(len(rows), header_index + 3)
                ]:

                    nearby_cells = nearby_row.find_all(
                        ["th", "td"],
                        recursive=False
                    )

                    nearby_headers = standardize_columns([
                        cell.get_text(" ", strip=True)
                        for cell in nearby_cells
                    ])

                    if "Transaction Date" in nearby_headers:
                        headers = nearby_headers
                        header_index = rows.index(nearby_row)
                        break

            if not set(REQUIRED_COLUMNS).issubset(set(headers)):
                continue

            logger.info(
                "Exchange-rate table identified: Table %s",
                table_number
            )

            logger.info("Detected columns: %s", headers)

            extracted_rows = []

            # Extract data after the header row.
            for data_row in rows[header_index + 1:]:

                cells = data_row.find_all(
                    ["td", "th"],
                    recursive=False
                )

                values = [
                    cell.get_text(" ", strip=True)
                    for cell in cells
                ]

                if len(values) != len(headers):
                    continue

                # Skip repeated headings.
                normalized_values = set(
                    standardize_columns(values)
                )

                if set(REQUIRED_COLUMNS).issubset(
                    normalized_values
                ):
                    continue

                record = dict(zip(headers, values))

                if not record.get("Currency"):
                    continue

                extracted_rows.append(record)

            if extracted_rows:

                dataframe = pd.DataFrame(extracted_rows)

                logger.info(
                    "Successfully extracted %s records.",
                    len(dataframe)
                )

                return dataframe

    # Fallback: attempt extraction using pandas HTML table parser.
    logger.warning(
        "BeautifulSoup extraction did not identify a suitable table. "
        "Trying pandas HTML parser..."
    )

    try:

        pandas_tables = pd.read_html(StringIO(html))

        for table in pandas_tables:

            table.columns = standardize_columns(table.columns)

            if set(REQUIRED_COLUMNS).issubset(
                set(table.columns)
            ):

                logger.info(
                    "Exchange-rate table identified using pandas."
                )

                return table

    except Exception as error:

        logger.warning(
            "Pandas HTML extraction failed: %s",
            error
        )

    raise ValueError(
        "Could not identify the BOT exchange-rate table. "
        "The website HTML structure or column headings may have changed."
    )


# ============================================================
# 6. CLEAN NUMERICAL VALUES
# ============================================================

def clean_number(value):
    """
    Convert exchange-rate values into numerical format.
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if not value or value.lower() in ["nan", "none", "-"]:
        return None

    # Remove thousands separators and currency symbols.
    value = value.replace(",", "")
    value = re.sub(r"[^\d.\-]", "", value)

    try:
        return float(value)

    except ValueError:
        return None


# ============================================================
# 7. CLEAN TRANSACTION DATES
# ============================================================

def clean_dates(series):

    dates = series.astype(str).str.strip()

    # Try standard date parsing first.
    parsed = pd.to_datetime(
        dates,
        errors="coerce",
        dayfirst=True
    )

    # Try common BOT date formats for any remaining failures.
    formats = [
        "%d-%b-%y",
        "%d-%B-%Y",
        "%d-%b-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d/%m/%y",
    ]

    for date_format in formats:

        missing = parsed.isna()

        if not missing.any():
            break

        parsed.loc[missing] = pd.to_datetime(
            dates.loc[missing],
            format=date_format,
            errors="coerce"
        )

    return parsed


# ============================================================
# 8. VALIDATE AND CLEAN DATA
# ============================================================

def clean_data(dataframe):

    logger.info("Cleaning extracted exchange-rate data...")

    df = dataframe.copy()

    # Standardize column headings.
    df.columns = standardize_columns(df.columns)

    # Remove duplicate column names.
    df = df.loc[:, ~df.columns.duplicated()]

    # Verify required columns.
    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            f"Missing required columns: {missing_columns}. "
            f"Available columns: {df.columns.tolist()}"
        )

    # Keep required fields.
    df = df[REQUIRED_COLUMNS].copy()

    # Remove empty rows.
    df.replace(
        ["", "nan", "None", "NULL", "-"],
        pd.NA,
        inplace=True
    )

    # Clean currency names.
    df["Currency"] = (
        df["Currency"]
        .astype("string")
        .str.strip()
    )

    # Convert numerical columns.
    numerical_columns = [
        "Buying",
        "Selling",
        "Mean"
    ]

    for column in numerical_columns:

        df[column] = df[column].apply(clean_number)

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # Convert transaction dates.
    df["Transaction Date"] = clean_dates(
        df["Transaction Date"]
    )

    # Remove records with missing essential information.
    before = len(df)

    df.dropna(
        subset=REQUIRED_COLUMNS,
        inplace=True
    )

    removed = before - len(df)

    if removed:
        logger.warning(
            "Removed %s incomplete or invalid records.",
            removed
        )

    # Validate exchange rates.
    df = df[
        (df["Buying"] > 0) &
        (df["Selling"] > 0) &
        (df["Mean"] > 0)
    ].copy()

    if df.empty:

        raise ValueError(
            "No valid exchange-rate records remain after cleaning."
        )

    # Add source and extraction timestamp.
    scraped_time = datetime.now(TIMEZONE)

    df["source_url"] = SOURCE_URL

    df["scraped_at"] = scraped_time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Remove duplicate records within the current extraction.
    df.drop_duplicates(
        subset=[
            "Currency",
            "Transaction Date",
            "Buying",
            "Selling",
            "Mean"
        ],
        keep="last",
        inplace=True
    )

    # Standard date format for CSV.
    df["Transaction Date"] = (
        df["Transaction Date"].dt.strftime("%Y-%m-%d")
    )

    # Arrange final columns.
    df = df[OUTPUT_COLUMNS]

    df.reset_index(drop=True, inplace=True)

    logger.info(
        "Data cleaning completed. Valid records: %s",
        len(df)
    )

    return df


# ============================================================
# 9. SAVE DATA TO CSV
# ============================================================

def save_data(new_data):

    logger.info("Saving exchange-rate records...")

    if OUTPUT_FILE.exists():

        try:

            old_data = pd.read_csv(
                OUTPUT_FILE,
                dtype={"Currency": "string"}
            )

            logger.info(
                "Existing historical records: %s",
                len(old_data)
            )

            # Ensure historical data has the expected columns.
            missing = [
                column
                for column in OUTPUT_COLUMNS
                if column not in old_data.columns
            ]

            if missing:

                raise ValueError(
                    "Existing CSV has missing columns: "
                    f"{missing}. Please check the historical file."
                )

            combined = pd.concat(
                [old_data[OUTPUT_COLUMNS], new_data],
                ignore_index=True
            )

        except Exception as error:

            logger.exception(
                "Unable to read existing CSV file."
            )

            raise RuntimeError(
                f"Could not safely update historical CSV: {error}"
            ) from error

    else:

        logger.info("Creating a new historical CSV file.")

        combined = new_data.copy()

    # Prevent duplicate exchange-rate records.
    combined.drop_duplicates(
        subset=[
            "Currency",
            "Transaction Date",
            "Buying",
            "Selling",
            "Mean"
        ],
        keep="last",
        inplace=True
    )

    # Sort historical data.
    combined.sort_values(
        by=["Transaction Date", "Currency"],
        inplace=True
    )

    combined.reset_index(drop=True, inplace=True)

    # Save atomically to avoid corrupting the existing file.
    temporary_file = OUTPUT_FILE.with_suffix(".tmp")

    combined.to_csv(
        temporary_file,
        index=False,
        encoding="utf-8"
    )

    os.replace(
        temporary_file,
        OUTPUT_FILE
    )

    logger.info("=" * 65)
    logger.info("DATA SAVED SUCCESSFULLY")
    logger.info("CSV FILE: %s", OUTPUT_FILE.name)
    logger.info("NEW RECORDS EXTRACTED: %s", len(new_data))
    logger.info("TOTAL HISTORICAL RECORDS: %s", len(combined))
    logger.info("=" * 65)

    return combined


# ============================================================
# 10. MAIN EXECUTION
# ============================================================

def main():

    try:

        # Step 1: Connect to BOT.
        html = fetch_website()

        # Step 2: Extract exchange-rate table.
        raw_data = extract_table(html)

        # Step 3: Clean and validate data.
        cleaned_data = clean_data(raw_data)

        # Step 4: Save historical data.
        final_data = save_data(cleaned_data)

        # Step 5: Display execution summary.
        logger.info("BOT CURRENCY SCRAPER COMPLETED SUCCESSFULLY.")

        logger.info(
            "Currencies extracted: %s",
            cleaned_data["Currency"].nunique()
        )

        logger.info(
            "Latest transaction date: %s",
            cleaned_data["Transaction Date"].max()
        )

        logger.info(
            "Historical dataset size: %s records",
            len(final_data)
        )

        logger.info(
            "Output location: %s",
            OUTPUT_FILE
        )

        print("\nEXCHANGE RATE DATA PREVIEW:")

        print(cleaned_data.head(10).to_string(index=False))

    except Exception:

        logger.exception("BOT CURRENCY SCRAPER FAILED")

        sys.exit(1)


# ============================================================
# 11. START PROGRAM
# ============================================================

if __name__ == "__main__":
    main()
