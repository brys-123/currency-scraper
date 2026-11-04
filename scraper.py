
"""
BANK OF TANZANIA CURRENCY EXCHANGE RATE SCRAPER
================================================
Source:
https://www.bot.go.tz/ExchangeRate/excRates

Features:
- Automatic connection retries
- Extended connection and read timeouts
- English and Swahili column recognition
- Exchange-rate extraction
- Date and numerical cleaning
- Data validation
- Duplicate prevention
- Historical CSV preservation
- GitHub Actions compatibility
"""

import os
import re
import sys
import time
import logging
import unicodedata

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from io import StringIO

import requests
import pandas as pd

from bs4 import BeautifulSoup


# ============================================================
# 1. CONFIGURATION
# ============================================================

SOURCE_URL = "https://www.bot.go.tz/ExchangeRate/excRates"

OUTPUT_FILE = (
    Path(__file__).resolve().parent /
    "BOT_exchange_rate.csv"
)

TIMEZONE = ZoneInfo("Africa/Dar_es_Salaam")

MAX_RETRIES = 4

CONNECT_TIMEOUT = 30
READ_TIMEOUT = 120

RETRY_DELAY = 15

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
    "Connection": "keep-alive",
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
# 2. LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("BOT_CURRENCY_SCRAPER")


# ============================================================
# 3. COLUMN NAME NORMALIZATION
# ============================================================

def normalize_text(text):

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

    standardized = []

    for column in columns:

        normalized = normalize_text(column)

        standardized.append(
            COLUMN_ALIASES.get(
                normalized,
                str(column).strip()
            )
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
    logger.info("Source URL: %s", SOURCE_URL)

    session = requests.Session()
    session.headers.update(HEADERS)

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            logger.info(
                "Connection attempt %s of %s",
                attempt,
                MAX_RETRIES
            )

            response = session.get(
                SOURCE_URL,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT
                )
            )

            response.raise_for_status()

            # Ensure the complete response body is available.
            html = response.text

            if not html or not html.strip():

                raise ValueError(
                    "BOT returned an empty HTML response."
                )

            logger.info(
                "Website response accepted: HTTP %s",
                response.status_code
            )

            logger.info(
                "Downloaded HTML size: %s KB",
                round(len(response.content) / 1024, 2)
            )

            session.close()

            return html

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            ValueError
        ) as error:

            last_error = error

            logger.warning(
                "Connection attempt %s failed: %s",
                attempt,
                error
            )

            if attempt < MAX_RETRIES:

                wait_time = RETRY_DELAY * attempt

                logger.info(
                    "Retrying in %s seconds...",
                    wait_time
                )

                time.sleep(wait_time)

            else:

                logger.error(
                    "All %s connection attempts failed.",
                    MAX_RETRIES
                )

    session.close()

    raise RuntimeError(
        f"Could not download BOT website after "
        f"{MAX_RETRIES} attempts. Last error: {last_error}"
    )


# ============================================================
# 5. EXTRACT EXCHANGE RATE TABLE
# ============================================================

def extract_table(html):

    logger.info("Searching for BOT exchange-rate table...")

    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")

    logger.info(
        "HTML tables discovered: %s",
        len(tables)
    )

    if not tables:

        raise ValueError(
            "No HTML tables found. "
            "The BOT page may have changed or use JavaScript."
        )

    essential_columns = {
        "Currency",
        "Buying",
        "Selling",
        "Mean"
    }

    for table_number, table in enumerate(tables, start=1):

        rows = table.find_all("tr")

        if not rows:
            continue

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

            headers = standardize_columns(
                original_headers
            )

            if not essential_columns.issubset(set(headers)):
                continue

            if "Transaction Date" not in headers:

                logger.warning(
                    "Rate columns found, but transaction date "
                    "was not detected in Table %s.",
                    table_number
                )

                continue

            logger.info(
                "Exchange-rate table identified: Table %s",
                table_number
            )

            logger.info(
                "Detected headings: %s",
                headers
            )

            extracted_rows = []

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

                dataframe = pd.DataFrame(
                    extracted_rows
                )

                logger.info(
                    "Successfully extracted %s records.",
                    len(dataframe)
                )

                return dataframe

    # Fallback using pandas HTML parser.
    logger.warning(
        "Trying pandas HTML table extraction..."
    )

    try:

        pandas_tables = pd.read_html(
            StringIO(html)
        )

        for table in pandas_tables:

            table.columns = standardize_columns(
                table.columns
            )

            if set(REQUIRED_COLUMNS).issubset(
                set(table.columns)
            ):

                logger.info(
                    "Table identified using pandas."
                )

                return table

    except Exception as error:

        logger.warning(
            "Pandas table extraction failed: %s",
            error
        )

    raise ValueError(
        "Could not identify the BOT exchange-rate table. "
        "Check the actual BOT HTML structure and headings."
    )


# ============================================================
# 6. CLEAN NUMERICAL VALUES
# ============================================================

def clean_number(value):

    if pd.isna(value):
        return None

    value = str(value).strip()

    if not value or value.lower() in [
        "nan",
        "none",
        "null",
        "-"
    ]:
        return None

    # Remove thousands separators.
    value = value.replace(",", "")

    # Remove currency symbols and other characters.
    value = re.sub(
        r"[^\d.\-]",
        "",
        value
    )

    try:

        return float(value)

    except (ValueError, TypeError):

        return None


# ============================================================
# 7. CLEAN TRANSACTION DATES
# ============================================================

def clean_dates(series):

    dates = series.astype(str).str.strip()

    parsed = pd.to_datetime(
        dates,
        errors="coerce",
        dayfirst=True
    )

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
# 8. CLEAN AND VALIDATE DATA
# ============================================================

def clean_data(dataframe):

    logger.info(
        "Cleaning extracted exchange-rate data..."
    )

    df = dataframe.copy()

    df.columns = standardize_columns(
        df.columns
    )

    df = df.loc[
        :,
        ~df.columns.duplicated()
    ]

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

    df = df[REQUIRED_COLUMNS].copy()

    df.replace(
        ["", "nan", "None", "NULL", "-"],
        pd.NA,
        inplace=True
    )

    # Currency names.
    df["Currency"] = (
        df["Currency"]
        .astype("string")
        .str.strip()
    )

    # Numerical columns.
    numerical_columns = [
        "Buying",
        "Selling",
        "Mean"
    ]

    for column in numerical_columns:

        df[column] = df[column].apply(
            clean_number
        )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # Transaction dates.
    df["Transaction Date"] = clean_dates(
        df["Transaction Date"]
    )

    original_count = len(df)

    df.dropna(
        subset=REQUIRED_COLUMNS,
        inplace=True
    )

    removed_count = original_count - len(df)

    if removed_count:

        logger.warning(
            "Removed %s incomplete records.",
            removed_count
        )

    # Validate positive exchange rates.
    df = df[
        (df["Buying"] > 0) &
        (df["Selling"] > 0) &
        (df["Mean"] > 0)
    ].copy()

    if df.empty:

        raise ValueError(
            "No valid exchange-rate records remain after cleaning."
        )

    # Tanzania local timestamp.
    scraped_time = datetime.now(
        TIMEZONE
    )

    df["source_url"] = SOURCE_URL

    df["scraped_at"] = scraped_time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Remove duplicates within the current extraction.
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

    df["Transaction Date"] = (
        df["Transaction Date"]
        .dt.strftime("%Y-%m-%d")
    )

    df = df[OUTPUT_COLUMNS]

    df.reset_index(
        drop=True,
        inplace=True
    )

    logger.info(
        "Data cleaning completed successfully."
    )

    logger.info(
        "Valid exchange-rate records: %s",
        len(df)
    )

    return df


# ============================================================
# 9. SAVE HISTORICAL CSV DATA
# ============================================================

def save_data(new_data):

    logger.info("Saving exchange-rate records...")

    if OUTPUT_FILE.exists():

        logger.info(
            "Historical CSV file found."
        )

        try:

            old_data = pd.read_csv(
                OUTPUT_FILE,
                dtype={"Currency": "string"}
            )

            missing_columns = [
                column
                for column in OUTPUT_COLUMNS
                if column not in old_data.columns
            ]

            if missing_columns:

                raise ValueError(
                    f"Historical CSV is missing columns: "
                    f"{missing_columns}"
                )

            logger.info(
                "Existing historical records: %s",
                len(old_data)
            )

            combined = pd.concat(
                [
                    old_data[OUTPUT_COLUMNS],
                    new_data
                ],
                ignore_index=True
            )

        except Exception as error:

            raise RuntimeError(
                f"Could not safely read historical CSV: {error}"
            ) from error

    else:

        logger.info(
            "Creating a new historical CSV file."
        )

        combined = new_data.copy()

    # Remove duplicate records.
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

    # Sort records chronologically.
    combined.sort_values(
        by=[
            "Transaction Date",
            "Currency"
        ],
        inplace=True
    )

    combined.reset_index(
        drop=True,
        inplace=True
    )

    # Save to temporary file first.
    temporary_file = OUTPUT_FILE.with_suffix(".tmp")

    combined.to_csv(
        temporary_file,
        index=False,
        encoding="utf-8"
    )

    # Replace the previous CSV safely.
    os.replace(
        temporary_file,
        OUTPUT_FILE
    )

    logger.info("=" * 65)
    logger.info("DATA SAVED SUCCESSFULLY")
    logger.info("CSV FILE: %s", OUTPUT_FILE.name)
    logger.info("NEW RECORDS: %s", len(new_data))
    logger.info(
        "TOTAL HISTORICAL RECORDS: %s",
        len(combined)
    )
    logger.info("=" * 65)

    return combined


# ============================================================
# 10. EXECUTION SUMMARY
# ============================================================

def display_summary(new_data, final_data):

    logger.info(
        "Currencies extracted: %s",
        new_data["Currency"].nunique()
    )

    logger.info(
        "Latest transaction date: %s",
        new_data["Transaction Date"].max()
    )

    logger.info(
        "Historical dataset size: %s records",
        len(final_data)
    )

    logger.info(
        "Output location: %s",
        OUTPUT_FILE
    )

    print("\nEXCHANGE RATE DATA PREVIEW")

    print(
        new_data.head(10).to_string(
            index=False
        )
    )


# ============================================================
# 11. MAIN PROGRAM
# ============================================================

def main():

    try:

        # Step 1: Download BOT website.
        html = fetch_website()

        # Step 2: Extract exchange-rate table.
        raw_data = extract_table(html)

        # Step 3: Clean and validate.
        cleaned_data = clean_data(raw_data)

        # Step 4: Save historical data.
        final_data = save_data(cleaned_data)

        # Step 5: Display summary.
        display_summary(
            cleaned_data,
            final_data
        )

        logger.info("=" * 65)
        logger.info(
            "BOT CURRENCY SCRAPER COMPLETED SUCCESSFULLY"
        )
        logger.info("=" * 65)

    except Exception:

        logger.exception(
            "BOT CURRENCY SCRAPER FAILED"
        )

        sys.exit(1)


# ============================================================
# 12. START SCRAPER
# ============================================================

if __name__ == "__main__":

    main()
