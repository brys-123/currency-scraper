from bs4 import BeautifulSoup as bs
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import os

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

link = "https://www.bot.go.tz/ExchangeRate/excRates"

try:
    respons = requests.get(link, headers=headers)
    print(respons)
except:
    print("there is a server error")
    exit()

if respons.status_code == 200:
    print("your respons is accepted")
else:
    print("your respons denied")
    exit()

# fetch the html structure 
html = respons.text
html_structure = bs(html, "html.parser")

tables = html_structure.find("table")
table_hed1 = [th.get_text(strip=True) for th in tables.find_all("th")]

table_hed2 = pd.Series(table_hed1)
table_hed3 = list(table_hed2.unique())

# creating the data frame with column headers only
val1 = [tr.get_text(strip=False) for tr in tables.find_all("tr")][1:]

# optain the cleaned rows
cleaned_val = []

for row in val1:
    cell = [cell.strip() for cell in row.split("\n") if cell.strip() != '']
    cleaned_val.append(cell)

cleaned_val = cleaned_val[:-1]

df1 = pd.DataFrame(cleaned_val, columns=table_hed3)
df1.set_index("S/NO", inplace=True)

print(df1)

# add the time stamp column to the data set
df1["Transaction Date"] = pd.to_datetime(df1["Transaction Date"], format="%d-%b-%y")

cols1 = ['Buying', 'Selling', 'Mean']

# convert the above column into numeric
df1[cols1] = df1[cols1].apply(pd.to_numeric)

df1["source_url"] = "https://www.bot.go.tz/ExchangeRate/excRates"

# Add scrape timestamp
df1["scraped_at"] = datetime.now()


csv_file = "BOT_exchange_rate.csv"

# Check if file exists
if os.path.exists(csv_file):
    # Read existing data
    existing_df = pd.read_csv(csv_file, index_col="S/NO")
    existing_df["Transaction Date"] = pd.to_datetime(existing_df["Transaction Date"])
    
    # Combine old and new data
    combined_df = pd.concat([existing_df, df1])
    
    # Remove duplicates (same Currency and Transaction Date)
    combined_df = combined_df.drop_duplicates(
        subset=["Currency", "Transaction Date"], 
        keep="last"  # Keep the latest data
    )
    
    # Sort by date
    combined_df = combined_df.sort_values("Transaction Date", ascending=False)
    
    # Save combined data
    combined_df.to_csv(csv_file)
    print(f"✓ Data updated! Total records: {len(combined_df)}")
    
else:
    # First time - create new file
    df1.to_csv(csv_file)
    print(f"✓ New file created! Total records: {len(df1)}")

df1
