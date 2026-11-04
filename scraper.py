
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ==========================================================
# 1. CONFIGURATION
# ==========================================================

SOURCE_URL = "https://www.bot.go.tz/ExchangeRate/excRates"
CSV_FILE = Path(__file__).resolve().parent / "BOT_exchange_rate.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

REQUIRED_COLUMNS = [
    "Currency",
    "Buying",
    "Selling",
    "Mean",
    "Transaction Date",
]

NUMERIC_COLUMNS = ["Buying", "Selling", "Mean"]


# ==========================================================
# 2. LOGGING CONFIGURATION
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


# ==========================================================
# 3. CLEAN COLUMN NAMES
# ==========================================================

def clean_column_name(name):

    name = str(name).strip()
    name = re.sub(r"\s+", " ", name)

    # Normalize common variations
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())

    aliases = {
        "sno": "S/NO",
        "serialno": "S/NO",
        "currency": "Currency",
        "buying": "Buying",
        "buyingrate": "Buying",
        "selling": "Selling",
        "sellingrate": "Selling",
        "mean": "Mean",
        "meanrate": "Mean",
        "transactiondate": "Transaction Date",
        "date": "Transaction Date",
        "dateoftransaction": "Transaction Date",
        "ratedate": "Transaction Date",
        "effectivedate": "Transaction Date",
    }

    return aliases.get(normalized, name)


# ==========================================================
# 4. FETCH WEBSITE DATA
# ==========================================================

def fetch_website():

    logger.info("Connecting to Bank of Tanzania...")

    try:
        response = requests.get(
            SOURCE_URL,
            headers=HEADERS,
            timeout=40
        )

        response.raise_for_status()

        logger.info(
            "Website response accepted: HTTP %s",
            response.status_code
        )

        return response.text

    except requests.exceptions.Timeout:
        logger.exception("Website request timed out.")
        raise

    except requests.exceptions.RequestException:
        logger.exception("Unable to connect to Bank of Tanzania.")
        raise


# ==========================================================
# 5. EXTRACT EXCHANGE RATE TABLE
# ==========================================================

def extract_table(html):

    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")

    if not tables:
        raise ValueError("No HTML tables found on BOT website.")

    selected_table = None
    headers = []

    # Find the table containing exchange-rate columns
    for table in tables:

        for tr in table.find_all("tr"):

            cells = tr.find_all(["th", "td"], recursive=False)

            if not cells:
                continue

            candidate_headers = [
                clean_column_name(cell.get_text(" ", strip=True))
                for cell in cells
            ]

            if (
                "Currency" in candidate_headers
                and "Buying" in candidate_headers
                and "Selling" in candidate_headers
            ):
                selected_table = table
                headers = candidate_headers
                break

        if selected_table is not None:
            break

    if selected_table is None:
        raise ValueError(
            "Could not identify the BOT exchange-rate table."
        )

    logger.info("Detected columns: %s", headers)

    if "Transaction Date" not in headers:
        raise ValueError(
            "Transaction Date column is missing. "
            f"Available columns: {headers}. "
            "Check whether BOT has changed its website structure."
        )

    # Extract data rows
    records = []

    for tr in selected_table.find_all("tr"):

        cells = tr.find_all(["th", "td"], recursive=False)

        if not cells:
            continue

        values = [
            cell.get_text(" ", strip=True)
            for cell in cells
        ]

        # Skip header rows
        row_headers = [
            clean_column_name(value)
            for value in values
        ]

        if "Currency" in row_headers and "Buying" in row_headers:
            continue

        if len(values) != len(headers):
            continue

        records.append(values)

    if not records:
        raise ValueError("No exchange-rate records were extracted.")

    df = pd.DataFrame(records, columns=headers)

    # Clean column names again
    df.columns = [clean_column_name(c) for c in df.columns]

    logger.info("Extracted %s raw records.", len(df))

    return df


# ==========================================================
# 6. CLEAN AND VALIDATE DATA
# ==========================================================

def clean_data(df):

    logger.info("Cleaning exchange-rate data...")

    # Remove extra spaces from text
    for column in df.columns:

        if df[column].dtype == "object":
            df[column] = df[column].astype(str).str.strip()

    # Verify required fields
    missing_columns = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}. "
            f"Detected columns: {df.columns.tolist()}"
        )

    # Convert transaction dates
    original_dates = df["Transaction Date"].copy()

    df["Transaction Date"] = pd.to_datetime(
        df["Transaction Date"],
        format="%d-%b-%y",
        errors="coerce"
    )

    # Try general date parsing for other formats
    invalid_dates = df["Transaction Date"].isna()

    if invalid_dates.any():

        fallback_dates = pd.to_datetime(
            original_dates[invalid_dates],
            errors="coerce",
            dayfirst=True
        )

        df.loc[invalid_dates, "Transaction Date"] = fallback_dates

    if df["Transaction Date"].isna().any():

        bad_dates = original_dates[
            df["Transaction Date"].isna()
        ].tolist()

        raise ValueError(
            f"Invalid transaction dates detected: {bad_dates[:10]}"
        )

    # Convert exchange rates into numeric values
    for column in NUMERIC_COLUMNS:

        df[column] = pd.to_numeric(
            df[column]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(" ", "", regex=False),
            errors="coerce"
        )

    # Reject incomplete records
    df["Currency"] = df["Currency"].astype(str).str.strip()

    df.replace(["", "nan", "None"], pd.NA, inplace=True)

    df.dropna(
        subset=REQUIRED_COLUMNS,
        inplace=True
    )

    if df.empty:
        raise ValueError(
            "No valid exchange-rate records remain after cleaning."
        )

    # Validate exchange rates
    for column in NUMERIC_COLUMNS:

        if (df[column] <= 0).any():
            raise ValueError(
                f"Invalid non-positive values found in {column}."
            )

    # Add source information
    df["source_url"] = SOURCE_URL

    df["scraped_at"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Keep a consistent column order
    output_columns = [
        col for col in ["S/NO"] + REQUIRED_COLUMNS
        if col in df.columns
    ]

    output_columns += ["source_url", "scraped_at"]

    df = df[output_columns]

    df.reset_index(drop=True, inplace=True)

    logger.info(
        "Data validation successful: %s valid records.",
        len(df)
    )

    return df


# ==========================================================
# 7. SAVE DATA WITHOUT DUPLICATES
# ==========================================================

def save_data(df):

    logger.info("Saving data to CSV...")

    CSV_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if CSV_FILE.exists():

        existing_df = pd.read_csv(
            CSV_FILE,
            dtype={"Currency": str}
        )

        # Ensure previous records use datetime format
        if not existing_df.empty:

            existing_df["Transaction Date"] = pd.to_datetime(
                existing_df["Transaction Date"],
                errors="coerce"
            )

            df["Transaction Date"] = pd.to_datetime(
                df["Transaction Date"],
                errors="coerce"
            )

            combined_df = pd.concat(
                [existing_df, df],
                ignore_index=True
            )

        else:
            combined_df = df.copy()

    else:
        combined_df = df.copy()

    # Remove duplicate exchange-rate records
    duplicate_keys = [
        "Currency",
        "Transaction Date",
        "Buying",
        "Selling",
        "Mean"
    ]

    before = len(combined_df)

    combined_df.drop_duplicates(
        subset=duplicate_keys,
        keep="last",
        inplace=True
    )

    removed = before - len(combined_df)

    # Save safely
    temp_file = CSV_FILE.with_name(
        CSV_FILE.stem + "_temp.csv"
    )

    combined_df.to_csv(
        temp_file,
        index=False
    )

    os.replace(temp_file, CSV_FILE)

    logger.info("New records received: %s", len(df))
    logger.info("Duplicate records removed: %s", removed)
    logger.info("Total unique records: %s", len(combined_df))
    logger.info("CSV successfully saved: %s", CSV_FILE)

    return len(combined_df)


# ==========================================================
# 8. MAIN EXECUTION
# ==========================================================

def main():

    start_time = datetime.now()

    logger.info("=" * 55)
    logger.info("BOT CURRENCY SCRAPER STARTED")
    logger.info("=" * 55)

    # Fetch
    html = fetch_website()

    # Extract
    raw_data = extract_table(html)

    logger.info("First five raw records:\n%s", raw_data.head())

    # Clean
    cleaned_data = clean_data(raw_data)

    # Save
    total_records = save_data(cleaned_data)

    duration = (
        datetime.now() - start_time
    ).total_seconds()

    logger.info("=" * 55)
    logger.info("SCRAPER COMPLETED SUCCESSFULLY")
    logger.info("Records processed: %s", len(cleaned_data))
    logger.info("Total unique records: %s", total_records)
    logger.info("Execution time: %.2f seconds", duration)
    logger.info("=" * 55)


if __name__ == "__main__":

    try:
        main()

    except Exception:
        logger.exception("BOT CURRENCY SCRAPER FAILED")
        sys.exit(1)
