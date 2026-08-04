"""
Near universe scrape of La Jornada articles using the date and the 
topic assigned to each article. 

Author: Eduardo Zago
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.append(str(Path(__file__).resolve().parents[1]))
from project_paths import media_output_path

"""
Function definitions. Importantly, these are made specially for La Jornada. Might not work for other newspapers.
"""

def extract_article_content(url, date, topic):
    """
    Extract the title, summary, main text, authors, date, and topic from a given La Jornada article URL.
    """
    article_data = {
        "url": url,
        "title": None,
        "summary": None,
        "main_text": None,
        "authors": None,
        "date": date.strftime("%Y-%m-%d"),  # Format date as a string
        "topic": topic
    }

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract the title
        title_element = soup.find(class_='cabeza')
        article_data["title"] = title_element.get_text(strip=True) if title_element else None

        # Extract the summary
        summary_element = soup.find(class_='sumarios')
        article_data["summary"] = summary_element.get_text(strip=True) if summary_element else None

        # Extract the main text from <p> tags and remove unwanted footer content
        paragraphs = []
        stop_phrases = ["¿Quiénes somos?", "Contacto", "Publicidad"]
        stop_pattern = re.compile("|".join(stop_phrases))  # Pattern to match any stop phrase

        for p in soup.find_all('p'):
            paragraph_text = p.get_text(strip=True)
            if stop_pattern.search(paragraph_text):  # Stop if any stop phrase is found
                break
            paragraphs.append(paragraph_text)

        article_data["main_text"] = " ".join(paragraphs) if paragraphs else None

        # Extract the authors
        authors = [author.get_text(strip=True) for author in soup.find_all(itemprop='author')]
        article_data["authors"] = ", ".join(authors) if authors else None

        print(f"Successfully extracted article: {url}")

    except requests.exceptions.RequestException as e:
        print(f"Error accessing {url}: {e}")
    
    return article_data

# Define the base URL and topics
base_url = "https://www.jornada.com.mx/{year}/{month:02d}/{day:02d}/{topic}/"
base_url2 = "https://www.jornada.com.mx/{year}/{month:02d}/{day:02d}/"
topics = ["politica", "espectaculos", "estados", "economia", "ultimas", "reportajes", 
          "deportes", "mundo", "ciencia", "opinion", "sociedad", "capital"]

def is_valid_article_url(url, topic):
    """
    Check if the URL follows a general pattern: '.../{topic}/<alphanumeric_code>'.
    """
    pattern = rf"/{topic}/[a-zA-Z0-9]+"  # Topic followed by alphanumeric code
    return re.search(pattern, url) is not None

def find_articles_for_date(date):
    """
    For a given date, retrieve and filter all valid article URLs from La Jornada.
    """
    year, month, day = date.year, date.month, date.day
    articles = []

    for topic in topics:
        url = base_url.format(year=year, month=month, day=day, topic=topic)
        print(f"Base URL: {url}")
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all links and filter them based on the pattern
            for link in soup.find_all("a", href=True):
                url2 = base_url2.format(year=year, month=month, day=day)
                full_url = urljoin(url2, link['href'])
                if "jornada" in full_url and is_valid_article_url(full_url, topic):
                    article_data = extract_article_content(full_url, date, topic)
                    if article_data:  # Only add if extraction was successful
                        articles.append(article_data)

        except requests.exceptions.RequestException as e:
            print(f"Error accessing {url}: {e}")

    return articles

def load_existing_data(file_path):
    """
    Load existing data if file exists and return it with the last date found.
    """
    if os.path.exists(file_path):
        df = pd.read_parquet(file_path)
        last_date = pd.to_datetime(df["date"]).max()
        print(f"Resuming from {last_date.strftime('%Y-%m-%d')}")
        return df, last_date
    else:
        print("No existing file found. Starting from scratch.")
        return pd.DataFrame(), None

def save_data(df, file_path):
    """
    Save the DataFrame to a parquet file.
    """
    df.to_parquet(file_path, compression="gzip")
    print(f"Data saved to '{file_path}'.")

def crawl_articles(start_date, end_date, file_path=None):
    """
    Loop over each day in the specified date range, collecting valid article data.
    Resumes from last saved date if file already exists.
    """
    if file_path is None:
        file_path = parquet_file

    # Load existing data if available
    existing_data, last_date = load_existing_data(file_path)

    # Set starting date based on last saved date, if it exists
    if last_date:
        start_date = last_date + timedelta(days=1)

    all_articles = existing_data

    date = start_date
    while date <= end_date:
        print(f"Checking articles for date: {date.strftime('%Y-%m-%d')}")
        daily_articles = find_articles_for_date(date)
        
        # Append new data to existing data and save
        daily_df = pd.DataFrame(daily_articles)
        all_articles = pd.concat([all_articles, daily_df]).drop_duplicates(subset="url", keep="last")

        # Save after each day
        save_data(all_articles, file_path)

        date += timedelta(days=1)

    return all_articles

"""
User chosen variables. Where to save, which dates to scrape.
If nothing changes that much, the code should be robust for any future date
"""

parquet_file = media_output_path("data", "00-newspaper_data", "crawler", "jornada", "articles.parquet")
start_date = datetime(2009, 1, 1)
end_date = datetime(2024, 10, 30)
crawl_articles(start_date, end_date)
