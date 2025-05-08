#!/usr/bin/env python3
"""
Improved Keyword Data Extractor for USA Google Search Results

This script extracts Google Autocomplete suggestions, People Also Ask questions,
and People Also Search For keywords with enhanced data cleaning.
"""

import os
import time
import json
import random
import re
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

# Configure environment-based parameters
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
COUNTRY = os.environ.get("COUNTRY", "us").lower()
WAIT_TIME = int(os.environ.get("WAIT_TIME", "10"))

# Create necessary directories
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
KEYWORDS_FILE = Path("keywords.txt")

class GoogleExtractor:
    """
    Class to handle extraction of Google search data with improved data cleaning
    """
    
    def __init__(self, headless=True, country="us", wait_time=10):
        """Initialize the extractor with browser settings"""
        self.ua = UserAgent()
        self.country = country
        self.wait_time = wait_time
        
        # Setup Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={self.ua.random}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Set language and location for US results
        chrome_options.add_argument("--lang=en-US")
        chrome_options.add_argument("--accept-lang=en-US")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Add geolocation preference for US results
        chrome_options.add_experimental_option("prefs", {
            "intl.accept_languages": "en-US,en",
            "profile.default_content_setting_values.geolocation": 1
        })
        
        # Initialize the browser
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(f"Error setting up ChromeDriverManager: {e}")
            # Fallback to default path
            self.driver = webdriver.Chrome(options=chrome_options)
            
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Configure wait time
        self.wait = WebDriverWait(self.driver, self.wait_time)
    
    def __del__(self):
        """Clean up resources when done"""
        if hasattr(self, 'driver'):
            self.driver.quit()
    
    def get_autocomplete_suggestions(self, keyword):
        """Extract Google autocomplete suggestions for a keyword"""
        suggestions = []
        try:
            # Use US-specific parameters
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&hl=en-US&gl={self.country.upper()}&q={keyword}"
            headers = {"User-Agent": self.ua.random}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                suggestions = data[1] if len(data) > 1 else []
                
            # Fall back to direct browser if API fails
            if not suggestions:
                self.driver.get("https://www.google.com")
                search_box = self.wait.until(EC.presence_of_element_located((By.NAME, "q")))
                search_box.clear()
                search_box.send_keys(keyword)
                time.sleep(1)  # Wait for suggestions to load
                
                suggestion_elements = self.driver.find_elements(By.CSS_SELECTOR, "li.sbct")
                for element in suggestion_elements:
                    suggestion_text = element.text.strip()
                    if suggestion_text and suggestion_text.lower() != keyword.lower():
                        suggestions.append(suggestion_text)
        except Exception as e:
            print(f"Error getting autocomplete suggestions for '{keyword}': {e}")
            
        return suggestions
    
    def clean_text(self, text):
        """Clean text by removing extra whitespace, timestamps, etc."""
        if not text:
            return ""
            
        # Remove timestamps (e.g., "4:22")
        text = re.sub(r'\d+:\d+', '', text)
        
        # Remove pricing info
        text = re.sub(r'\$\d+\.\d+', '', text)
        
        # Remove YouTube and website indicators
        text = re.sub(r'YouTube\s·\s.*|www\..*\.com|https?://.*', '', text)
        
        # Remove dates and views counts
        text = re.sub(r'\d+[KM]?\+?\sviews\s·\s\w+\s\d+.*|\d+\s\w+\sago', '', text)
        
        # Remove special characters and excessive whitespace
        text = re.sub(r'["""\u00b7\\|]', '', text)
        text = ' '.join(text.split())
        
        # Remove curbside/pickup info
        text = re.sub(r'CURBSIDE.*Pick up today', '', text)
        
        # Remove rating/review info
        text = re.sub(r'\d+\.\d+\(\d+[k+]?\)', '', text)
        text = re.sub(r'".*"\s·\s".*"', '', text)
        
        # Remove short fragments less than 3 characters
        if len(text) <= 2:
            return ''
            
        return text.strip()
    
    def get_people_also_ask(self, keyword):
        """Extract 'People Also Ask' questions for a keyword with improved selectors"""
        questions = []
        try:
            # Navigate to Google search with USA parameters
            self.driver.get(f"https://www.google.com/search?q={keyword}&gl={self.country}&hl=en-US")
            
            # Accept cookies if prompt appears
            try:
                cookie_button = self.driver.find_element(By.XPATH, 
                    "//button[contains(., 'Accept all') or contains(., 'I agree') or contains(., 'Accept')]")
                cookie_button.click()
                time.sleep(1)
            except NoSuchElementException:
                pass
            
            # Wait for page to load completely
            time.sleep(2)
            
            # Try multiple selectors for PAA questions
            selectors = [
                "div[jsname='Cpkphb']", 
                "div.related-question-pair", 
                "div.g9WsWb",
                "div.wQiwMc div.JCzEY",  # Updated selector
                "div.wQiwMc div.JlqpRe",  # Another updated selector
                "div.iDjcJe",  # Another potential selector
                "div.related-question-pair div.d8lLbf"  # More specific
            ]
            
            found_questions = False
            for selector in selectors:
                try:
                    # First check if any elements match this selector
                    paa_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if paa_elements:
                        found_questions = True
                        for element in paa_elements:
                            try:
                                question_text = element.text.strip()
                                question_text = self.clean_text(question_text)
                                if question_text and len(question_text) > 5:  # Basic validation
                                    questions.append(question_text)
                            except StaleElementReferenceException:
                                continue
                except Exception as e:
                    print(f"Error with selector {selector}: {e}")
                    continue
            
            # If no questions found yet, try a different approach with BS4
            if not found_questions:
                html_source = self.driver.page_source
                soup = BeautifulSoup(html_source, 'html.parser')
                
                # Look for potential PAA containers
                paa_containers = soup.select('div.ULSxyf, div.wQiwMc, div.JlqpRe')
                for container in paa_containers:
                    question_text = container.get_text().strip()
                    question_text = self.clean_text(question_text)
                    if question_text and len(question_text) > 5:
                        questions.append(question_text)
                
            # Try to click to expand more PAA questions
            if questions:  # If we found any questions
                try:
                    # Find expandable elements
                    expandable = self.driver.find_elements(By.CSS_SELECTOR, 
                        "div.iDjcJe, div.wQiwMc, div.g9WsWb")
                    
                    if expandable and len(expandable) > 0:
                        # Try to click the first one to expand
                        expandable[0].click()
                        time.sleep(2)
                        
                        # Get newly loaded questions
                        for selector in selectors:
                            try:
                                new_paa_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                for element in new_paa_elements:
                                    try:
                                        question_text = element.text.strip()
                                        question_text = self.clean_text(question_text)
                                        if question_text and len(question_text) > 5 and question_text not in questions:
                                            questions.append(question_text)
                                    except StaleElementReferenceException:
                                        continue
                            except Exception:
                                continue
                except Exception as e:
                    print(f"Error expanding PAA for '{keyword}': {e}")
            
            # Remove duplicates
            questions = list(dict.fromkeys(questions))
                
        except Exception as e:
            print(f"Error getting PAA for '{keyword}': {e}")
            
        return questions
    
    def get_people_also_search_for(self, keyword):
        """Extract 'People Also Search For' keywords with improved selectors"""
        related_keywords = []
        
        try:
            # We're already on the search page from PAA extraction
            # Wait to ensure page is fully loaded
            time.sleep(2)
            
            # Try different selectors for "People also search for" section
            selectors = [
                "div.k8XOCe", 
                "a.k8XOCe", 
                "div.s75CSd", 
                "div[data-ved] a:not([class])",
                "div.zVvuGd",
                "div.JjtOHd",
                "a.klitem",  # Updated selector
                "div.AJLUJb > div > a",  # Related searches at bottom
                "div.s6JM6d a",  # Another potential selector
                "a.gL9Hy",  # More specific selector
                "a.s75CSd",  # Another specific selector
                "div.s6JM6d > a"  # Bottom related searches
            ]
            
            found_keywords = False
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        found_keywords = True
                        for element in elements:
                            keyword_text = element.text.strip()
                            cleaned_text = self.clean_text(keyword_text)
                            
                            # Remove common unwanted phrases
                            if any(phrase in cleaned_text.lower() for phrase in 
                                ["more", "view all", "see more", "shop now", "curbside", "view all posts"]):
                                continue
                                
                            if cleaned_text and len(cleaned_text) > 3:
                                related_keywords.append(cleaned_text)
                except Exception:
                    continue
            
            # If no keywords found yet, try direct BS4 approach
            if not found_keywords:
                html_source = self.driver.page_source
                soup = BeautifulSoup(html_source, 'html.parser')
                
                # Try to find related search elements
                related_elements = soup.select('div.AJLUJb a, div.s6JM6d a, a.gL9Hy, a.k8XOCe')
                for element in related_elements:
                    keyword_text = element.get_text().strip()
                    cleaned_text = self.clean_text(keyword_text)
                    if cleaned_text and len(cleaned_text) > 3:
                        related_keywords.append(cleaned_text)
            
            # Also try to find related searches section at the bottom
            try:
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
                
                # Look for related searches with multiple selectors
                bottom_selectors = [
                    "div.card-section a", 
                    "div.s75CSd", 
                    "a.JjtOHd",
                    "div.AJLUJb a",  # Updated selector
                    "div.tF2Cxc a"   # Another potential bottom selector
                ]
                
                for selector in bottom_selectors:
                    try:
                        related_search_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in related_search_elements:
                            keyword_text = element.text.strip()
                            cleaned_text = self.clean_text(keyword_text)
                            
                            if cleaned_text and len(cleaned_text) > 3 and cleaned_text not in related_keywords:
                                related_keywords.append(cleaned_text)
                    except Exception:
                        continue
            except Exception as e:
                print(f"Error getting bottom related searches: {e}")
                
            # Remove duplicates while preserving order
            seen = set()
            related_keywords = [x for x in related_keywords if not (x.lower() in seen or seen.add(x.lower()))]
                        
        except Exception as e:
            print(f"Error getting related searches for '{keyword}': {e}")
            
        return related_keywords

    def extract_data_for_keyword(self, keyword):
        """Extract all data for a single keyword"""
        # First get autocomplete suggestions (separate request)
        autocomplete = self.get_autocomplete_suggestions(keyword)
        
        # Then get PAA and related searches (requires browser navigation)
        paa_questions = self.get_people_also_ask(keyword)
        
        # If PAA is empty, try one more time with a small delay
        if not paa_questions:
            print(f"Retrying PAA for '{keyword}'...")
            time.sleep(2)
            paa_questions = self.get_people_also_ask(keyword)
        
        related_keywords = self.get_people_also_search_for(keyword)
        
        # If related keywords are empty, try one more time
        if not related_keywords:
            print(f"Retrying related searches for '{keyword}'...")
            time.sleep(2)
            related_keywords = self.get_people_also_search_for(keyword)
        
        result = {
            "keyword": keyword,
            "timestamp": datetime.now().isoformat(),
            "autocomplete": autocomplete,
            "people_also_ask": paa_questions,
            "people_also_search_for": related_keywords
        }
        
        # Add small delay for rate limiting
        time.sleep(random.uniform(3.0, 5.0))
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
    
    # Initialize extractor specifically for US results
    extractor = GoogleExtractor(headless=HEADLESS, country=COUNTRY, wait_time=WAIT_TIME)
    
    # Process each keyword and collect results
    all_results = []
    for keyword in tqdm(keywords, desc="Processing keywords"):
        result = extractor.extract_data_for_keyword(keyword)
        
        # Validate results - log warning if no data
        if not result["people_also_ask"] and not result["people_also_search_for"]:
            print(f"WARNING: No PAA or related searches found for '{keyword}'")
        
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
    
    empty_paa_count = sum(1 for r in results if not r["people_also_ask"])
    empty_pasf_count = sum(1 for r in results if not r["people_also_search_for"])
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_keywords_processed": total_keywords,
        "total_autocomplete_suggestions": autocomplete_count,
        "total_people_also_ask_questions": paa_count,
        "total_people_also_search_for": pasf_count,
        "average_autocomplete_per_keyword": round(autocomplete_count / total_keywords, 2),
        "average_paa_per_keyword": round(paa_count / total_keywords, 2),
        "average_pasf_per_keyword": round(pasf_count / total_keywords, 2),
        "keywords_with_empty_paa": empty_paa_count,
        "keywords_with_empty_pasf": empty_pasf_count
    }
    
    summary_file = DATA_DIR / "summary_report.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()