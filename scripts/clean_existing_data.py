#!/usr/bin/env python3
"""
Data Cleanup Script for Google Search Results

This script cleans up existing JSON data, particularly focusing on
fixing the "people_also_search_for" section to contain only clean keywords.
"""

import os
import json
import re
from pathlib import Path
from tqdm import tqdm

def clean_text(text):
    """Clean text by removing unwanted elements"""
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
    
    return text.strip()

def is_valid_keyword(text):
    """Check if a piece of text is a valid keyword"""
    # Skip very short text
    if not text or len(text) <= 3:
        return False
        
    # Skip if it's just a number
    if text.replace(".", "").isdigit():
        return False
        
    # Skip common unwanted phrases
    unwanted_phrases = [
        "more products", "see more", "view all", "shop now", "curbside", 
        "pick up today", "amazon.com", "target", "30-day returns", "view all posts"
    ]
    
    if any(phrase in text.lower() for phrase in unwanted_phrases):
        return False
        
    return True

def process_file(file_path):
    """Process a single JSON file"""
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        
        # Clean up "people_also_search_for" data
        if "people_also_search_for" in data:
            cleaned_keywords = []
            
            for item in data["people_also_search_for"]:
                cleaned_item = clean_text(item)
                
                if is_valid_keyword(cleaned_item):
                    cleaned_keywords.append(cleaned_item)
            
            # Remove duplicates while preserving order
            seen = set()
            data["people_also_search_for"] = [
                x for x in cleaned_keywords 
                if not (x.lower() in seen or seen.add(x.lower()))
            ]
        
        # Write the cleaned data back
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
            
        return True
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Main function to process all data files"""
    data_dir = Path("data")
    
    if not data_dir.exists():
        print("Data directory not found. Creating it.")
        data_dir.mkdir(exist_ok=True)
        return
    
    # Get list of JSON files
    json_files = list(data_dir.glob("*.json"))
    
    if not json_files:
        print("No JSON files found in the data directory.")
        return
        
    print(f"Found {len(json_files)} JSON files to process")
    
    # Process each file
    successful = 0
    for file_path in tqdm(json_files, desc="Processing files"):
        if file_path.name == "summary_report.json":
            continue
            
        if process_file(file_path):
            successful += 1
    
    print(f"Successfully processed {successful} of {len(json_files)} files")
    
    # If there's an all_keywords file, also clean that
    all_keywords_files = list(data_dir.glob("all_keywords_*.json"))
    if all_keywords_files:
        print("Processing combined keywords file(s)...")
        for all_file in all_keywords_files:
            try:
                with open(all_file, "r") as f:
                    all_data = json.load(f)
                    
                for item in all_data:
                    if "people_also_search_for" in item:
                        cleaned_keywords = []
                        
                        for keyword in item["people_also_search_for"]:
                            cleaned_item = clean_text(keyword)
                            
                            if is_valid_keyword(cleaned_item):
                                cleaned_keywords.append(cleaned_item)
                        
                        # Remove duplicates while preserving order
                        seen = set()
                        item["people_also_search_for"] = [
                            x for x in cleaned_keywords 
                            if not (x.lower() in seen or seen.add(x.lower()))
                        ]
                
                with open(all_file, "w") as f:
                    json.dump(all_data, f, indent=2)
                    
                print(f"Successfully processed {all_file.name}")
                
            except Exception as e:
                print(f"Error processing {all_file}: {e}")

if __name__ == "__main__":
    main()