#!/usr/bin/env python3
"""
Keyword Data Extractor

This script extracts Google Autocomplete suggestions, People Also Ask questions,
and People Also Search For keywords for a list of target keywords.
"""

import os
import time
import json
import random
import requests
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

# Create necessary directories
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
KEYWORDS_FILE = Path("keywords.txt")

class GoogleExtractor:
    """
    Class to handle extraction of Google search data including:
    - Autocomplete suggestions
    - People Also Ask questions
    - People Also Search For keywords
    """
    
    def __init__(self, headless=True):
        """Initialize the extractor with browser settings"""
        self.ua = UserAgent()
        
        # Setup Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={self.ua.random}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Initialize the browser
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Configure wait time
        self.wait = WebDriverWait(self.driver, 10)
    
    def __del__(self):
        """Clean up resources when done"""
        if hasattr(self, 'driver'):
            self.driver.quit()
    
    def get_autocomplete_suggestions(self, keyword):
        """Extract Google autocomplete suggestions for a keyword"""
        suggestions = []
        try:
            # Use a direct API approach (more reliable than scraping UI)
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&q={keyword}"
            headers = {"User-Agent": self.ua.random}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                suggestions = data[1] if len(data) > 1 else []
        except Exception as e:
            print(f"Error getting autocomplete suggestions for '{keyword}': {e}")
            
        return suggestions
    
    def get_people_also_ask(self, keyword):
        """Extract 'People Also Ask' questions for a keyword"""
        questions = []
        try:
            # Navigate to Google search
            self.driver.get(f"https://www.google.com/search?q={keyword}")
            
            # Accept cookies if prompt appears (common in EU)
            try:
                cookie_button = self.driver.find_element(By.XPATH, 
                    "//button[contains(., 'Accept all') or contains(., 'I agree') or contains(., 'Accept')]")
                cookie_button.click()
                time.sleep(1)
            except NoSuchElementException:
                pass  # No cookie prompt
                
            # Find and extract PAA questions
            paa_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[jsname='Cpkphb']")
            
            # If no elements found, look for alternative selectors
            if not paa_elements:
                paa_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.related-question-pair")
            
            # Extract text from elements
            for element in paa_elements:
                try:
                    question_text = element.text.strip()
                    if question_text and len(question_text) > 5:  # Basic validation
                        questions.append(question_text)
                except StaleElementReferenceException:
                    continue
                    
            # Click on elements to expand more questions (if available)
            if paa_elements and len(paa_elements) > 0:
                try:
                    # Click the first PAA question to load more
                    paa_elements[0].click()
                    time.sleep(2)
                    
                    # Get newly loaded questions
                    paa_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[jsname='Cpkphb']")
                    if not paa_elements:
                        paa_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.related-question-pair")
                    
                    # Extract new questions
                    for element in paa_elements:
                        try:
                            question_text = element.text.strip()
                            if question_text and len(question_text) > 5 and question_text not in questions:
                                questions.append(question_text)
                        except StaleElementReferenceException:
                            continue
                except Exception:
                    pass  # Ignore click errors
                
        except Exception as e:
            print(f"Error getting PAA for '{keyword}': {e}")
            
        return questions
    
    def get_people_also_search_for(self, keyword):
        """Extract 'People Also Search For' keywords"""
        related_keywords = []
        try:
            # We're already on the search page from PAA extraction
            # Look for "People also search for" section
            related_sections = self.driver.find_elements(By.CSS_SELECTOR, 
                "div[jsname='d3PE6e'], div.card-section, div[data-ved]")
            
            for section in related_sections:
                if "people also search" in section.text.lower():
                    # Extract all links in this section
                    links = section.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        link_text = link.text.strip()
                        if link_text and len(link_text) > 2 and link_text not in related_keywords:
                            related_keywords.append(link_text)
            
            # If nothing found, try an alternative approach
            if not related_keywords:
                related_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.AJLUJb > div, a.k8XOCe")
                for element in related_elements:
                    keyword_text = element.text.strip()
                    if keyword_text and len(keyword_text) > 2:
                        related_keywords.append(keyword_text)
                        
        except Exception as e:
            print(f"Error getting related searches for '{keyword}': {e}")
            
        return related_keywords

    def extract_data_for_keyword(self, keyword):
        """Extract all data for a single keyword"""
        result = {
            "keyword": keyword,
            "timestamp": datetime.now().isoformat(),
            "autocomplete": self.get_autocomplete_suggestions(keyword),
            "people_also_ask": self.get_people_also_ask(keyword),
            "people_also_search_for": self.get_people_also_search_for(keyword)
        }
        
        # Add small delay for rate limiting
        time.sleep(random.uniform(1.5, 3.5))
        return result

def main():
    """Main function to process all keywords"""
    # Read keywords from file
    if not KEYWORDS_FILE.exists():
        print(f"Error: Keywords file not found at {KEYWORDS_FILE}")
        return
        
    with open(KEYWORDS_FILE, "r") as f:
        keywords = [line.strip() for line in f if line.strip()]
    
    print(f"Found {len(keywords)} keywords to process")
    
    # Initialize extractor
    extractor = GoogleExtractor(headless=True)
    
    # Process each keyword and collect results
    all_results = []
    for keyword in tqdm(keywords, desc="Processing keywords"):
        result = extractor.extract_data_for_keyword(keyword)
        all_results.append(result)
        
        # Save individual keyword result
        keyword_slug = keyword.lower().replace(" ", "_")[:50]
        keyword_file = DATA_DIR / f"{keyword_slug}.json"
        with open(keyword_file, "w") as f:
            json.dump(result, f, indent=2)
    
    # Save combined results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined_file = DATA_DIR / f"all_keywords_{timestamp}.json"
    with open(combined_file, "w") as f:
        json.dump(all_results, f, indent=2)
    
    # Create a summary report
    create_summary_report(all_results)
    
    print(f"Processing complete. Results saved to {DATA_DIR}")

def create_summary_report(results):
    """Create a summary report with statistics"""
    total_keywords = len(results)
    autocomplete_count = sum(len(r["autocomplete"]) for r in results)
    paa_count = sum(len(r["people_also_ask"]) for r in results)
    pasf_count = sum(len(r["people_also_search_for"]) for r in results)
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_keywords_processed": total_keywords,
        "total_autocomplete_suggestions": autocomplete_count,
        "total_people_also_ask_questions": paa_count,
        "total_people_also_search_for": pasf_count,
        "average_autocomplete_per_keyword": round(autocomplete_count / total_keywords, 2),
        "average_paa_per_keyword": round(paa_count / total_keywords, 2),
        "average_pasf_per_keyword": round(pasf_count / total_keywords, 2)
    }
    
    summary_file = DATA_DIR / "summary_report.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()