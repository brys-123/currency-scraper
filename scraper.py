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

# Convert Transaction Date
df1["Transaction Date"] = pd.to_datetime(df1["Transaction Date"], format="%d-%b-%y")

cols1 = ['Buying', 'Selling', 'Mean']

# convert the above column into numeric
df1[cols1] = df1[cols1].apply(pd.to_numeric)

df1["source_url"] = "https://www.bot.go.tz/ExchangeRate/excRates"

# Add scrape timestamp
df1["scraped_at"] = datetime.now()

# ====== SIMPLE APPEND ======

csv_file = "BOT_exchange_rate.csv"

if os.path.exists(csv_file):
    # Append without headers
    df1.to_csv(csv_file, mode='a', header=False, index=False)
    print(f"✓ Data appended! Added {len(df1)} rows")
else:
    # First time - create with headers
    df1.to_csv(csv_file, mode='w', header=True, index=False)
    print(f"✓ New file created! Added {len(df1)} rows")

df1
