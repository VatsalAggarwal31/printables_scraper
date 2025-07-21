# config.py

import os

BASE_URL = "https://www.printables.com/model"
OUTPUT_BASE_DIRECTORY = r"D:\Projects\Python\Printables_Scraper\downloaded_models_structured" # IMPORTANT: Change this to your desired output directory

# --- New: URL List File ---
URL_LIST_FILE = os.path.join(OUTPUT_BASE_DIRECTORY, "printables_model_urls.txt") # File to save/load URLs

MAX_SCROLL_ATTEMPTS = 20
SCROLL_PAUSE_TIME = 3 # seconds after each scroll

COOKIE_CONSENT_TIMEOUT = 15
CLICK_TIMEOUT = 10 # General timeout for clicking elements like filters or tabs

DOWNLOAD_ALL_TIMEOUT = 240 # seconds for 'Download All' ZIP file
INDIVIDUAL_DOWNLOAD_TIMEOUT = 120 # seconds for individual files

IMAGE_DOWNLOAD_PAUSE_TIME = 0.5 # seconds between image downloads
JPG_CONVERSION_QUALITY = 90 # JPG quality (0-100)

# --- Folder Organization ---
IMAGES_SUBDIR = "images"
FILES_SUBDIR = "files"