# main.py
import os
import re
import json
import time
import shutil
import argparse

from selenium import webdriver
from selenium.common.exceptions import WebDriverException


from scraper import scrape_models, scrape_model_details
from utils import clean_directory, sanitize_filename
from config import (
    BASE_URL, OUTPUT_BASE_DIRECTORY, DOWNLOAD_ALL_TIMEOUT,
    IMAGES_SUBDIR, FILES_SUBDIR, URL_LIST_FILE,
    MAX_SCROLL_ATTEMPTS
)


def save_urls_to_file(urls, filename):
    """Saves a list of URLs to a text file, one URL per line."""
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')
        print(f"Successfully saved {len(urls)} URLs to {filename}")
    except IOError as e:
        print(f"Error saving URLs to file {filename}: {e}")


def load_urls_from_file(filename):
    """Loads a list of URLs from a text file."""
    urls = []
    if not os.path.exists(filename):
        print(f"URL list file not found: {filename}. No URLs loaded.")
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        print(f"Successfully loaded {len(urls)} URLs from {filename}")
        return urls
    except IOError as e:
        print(f"Error loading URLs from file {filename}: {e}")
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Printables.com Scraper")
    parser.add_argument(
        '--mode',
        choices=['collect', 'process', 'all'],
        default='all',
        help="Operation mode: 'collect' (URLs only), 'process' (details from file), 'all' (collect then process). Default: all"
    )
    parser.add_argument(
        '--limit-collection',
        type=int,
        default=0,  # 0 means no limit for collection
        help="Limit the number of URLs to collect in 'collect' or 'all' mode. 0 for no limit."
    )
    parser.add_argument(
        '--limit-processing',
        type=int,
        default=0,  # 0 means no limit for processing
        help="Limit the number of models to process in 'process' or 'all' mode. 0 for no limit."
    )
    args = parser.parse_args()

    # Define temp_download_directory based on config
    temp_download_directory = os.path.join(OUTPUT_BASE_DIRECTORY, "temp_downloads")

    # Ensure OUTPUT_BASE_DIRECTORY and temp_downloads are created
    os.makedirs(OUTPUT_BASE_DIRECTORY, exist_ok=True)
    os.makedirs(temp_download_directory, exist_ok=True)  # Ensure temp_downloads exists before cleaning

    print(f"Initial cleanup of global temporary download directory: {temp_download_directory}")
    clean_directory(temp_download_directory)
    time.sleep(2)

    all_scraped_data_overall = []  # To store all processed model data

    # --- Mode: Collect URLs ---
    if args.mode in ['collect', 'all']:
        print("Starting Printables.com URL Collection...")
        collection_driver_options = webdriver.ChromeOptions()
        # collection_driver_options.add_argument('--headless') # Uncomment for headless browser
        collection_driver_options.add_argument('--disable-gpu')
        collection_driver_options.add_argument('--no-sandbox')
        collection_driver_options.add_argument('--disable-dev-shm-usage')
        collection_driver_options.add_argument("--window-size=1920,1080")

        collection_driver = None
        model_urls = []
        try:
            collection_driver = webdriver.Chrome(options=collection_driver_options)
            # Pass the limit to scrape_models
            model_urls = scrape_models(collection_driver, BASE_URL, limit=args.limit_collection)
            save_urls_to_file(model_urls, URL_LIST_FILE)
        except WebDriverException as e:
            print(
                f"WebDriver error during URL collection: {e}. Ensure ChromeDriver is compatible and in PATH, and browser version matches.")
        except Exception as e:
            print(f"An unexpected error occurred during URL collection: {e}")
        finally:
            if collection_driver:
                collection_driver.quit()
        print(f"\nFinished collecting model URLs. Found {len(model_urls)} unique links.")
        if args.mode == 'collect':
            print("Collection mode finished. Exiting.")
            exit()  # Exit if only collecting

    # --- Mode: Process URLs ---
    model_urls_to_process = []
    if args.mode == 'process':
        model_urls_to_process = load_urls_from_file(URL_LIST_FILE)
    elif args.mode == 'all':
        # If 'all' mode, use the URLs collected in the 'collect' step
        model_urls_to_process = model_urls
        if not model_urls_to_process:  # Fallback if collection failed for some reason
            print("No URLs collected in 'all' mode, attempting to load from file for processing.")
            model_urls_to_process = load_urls_from_file(URL_LIST_FILE)

    if model_urls_to_process:
        print(f"\nStarting to scrape details for {len(model_urls_to_process)} models and download files...")

        # Apply processing limit if specified
        if args.limit_processing > 0:
            model_urls_to_process = model_urls_to_process[:args.limit_processing]
            print(f"Processing limited to the first {len(model_urls_to_process)} models.")

        # Set up WebDriver for scraping individual model details and downloading files
        details_driver_options = webdriver.ChromeOptions()
        prefs = {
            "download.default_directory": temp_download_directory,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safeBrowse.enabled": False
        }
        details_driver_options.add_experimental_option("prefs", prefs)
        details_driver_options.add_experimental_option("detach", True)
        # details_driver_options.add_argument('--headless') # Uncomment for headless browser
        details_driver_options.add_argument('--disable-gpu')
        details_driver_options.add_argument('--no-sandbox')
        details_driver_options.add_argument('--disable-dev-shm-usage')
        details_driver_options.add_argument("--window-size=1920,1080")

        details_driver = None

        try:
            details_driver = webdriver.Chrome(options=details_driver_options)

            for i, url in enumerate(model_urls_to_process):
                print(f"\n======== PROCESSING MODEL {i + 1}/{len(model_urls_to_process)}: {url} ========")

                print(f"  Cleaning up temp download directory '{temp_download_directory}' before processing new model.")
                clean_directory(temp_download_directory)
                time.sleep(2)

                model_id_match = re.search(r'/model/(\d+)', url)
                model_id = model_id_match.group(1) if model_id_match else f"unknown_id_{i}"

                # --- Step 1: Create a temporary model folder for initial details scrape ---
                initial_temp_model_folder_name = f"{model_id}_temp_model_folder"
                initial_temp_model_directory_path = os.path.join(OUTPUT_BASE_DIRECTORY, initial_temp_model_folder_name)
                os.makedirs(initial_temp_model_directory_path, exist_ok=True)

                # Define subdirectories for images and files within this temp model folder
                temp_image_subdir = os.path.join(initial_temp_model_directory_path, IMAGES_SUBDIR)
                temp_files_subdir = os.path.join(initial_temp_model_directory_path, FILES_SUBDIR)
                os.makedirs(temp_image_subdir, exist_ok=True)
                os.makedirs(temp_files_subdir, exist_ok=True)

                print(f"  Created temporary model folder for processing: {initial_temp_model_directory_path}")
                print(f"  Temp images will go to: {temp_image_subdir}")
                print(f"  Temp files will go to: {temp_files_subdir}")
                print(f"  Files will temporarily download to browser's download location: {temp_download_directory}")

                # --- Step 2: Scrape details using temp subdirectories ---
                details = scrape_model_details(
                    details_driver,
                    url,
                    temp_download_directory,
                    temp_image_subdir,  # Images go directly here initially
                    temp_files_subdir  # Files will be moved here from temp_download_directory
                )

                if details:
                    actual_title = details.get('title', f"Model_{model_id}")
                    sanitized_title = sanitize_filename(actual_title)

                    # Determine the first tag for the main category folder
                    first_tag = "No_Tag"  # Default if no tags are found
                    if details.get('tags') and len(details['tags']) > 0:
                        first_tag = sanitize_filename(details['tags'][0])

                    # --- Step 3: Construct the final organized paths ---
                    tag_base_directory = os.path.join(OUTPUT_BASE_DIRECTORY, first_tag)
                    final_model_directory_name = f"{model_id}_{sanitized_title}"
                    final_model_directory_path = os.path.join(tag_base_directory, final_model_directory_name)

                    final_image_destination = os.path.join(final_model_directory_path, IMAGES_SUBDIR)
                    final_files_destination = os.path.join(final_model_directory_path, FILES_SUBDIR)

                    # Create the final destination folders
                    os.makedirs(final_image_destination, exist_ok=True)
                    os.makedirs(final_files_destination, exist_ok=True)

                    print(f"\n  Determined final destination path:")
                    print(f"    Tag Category: {first_tag}")
                    print(f"    Model Folder: {final_model_directory_path}")
                    print(f"    Images will go to: {final_image_destination}")
                    print(f"    Files will go to: {final_files_destination}")

                    # --- Step 4: Move contents from temporary folders to final organized folders ---
                    # Move images
                    if os.path.exists(temp_image_subdir):
                        for item_name in os.listdir(temp_image_subdir):
                            try:
                                shutil.move(os.path.join(temp_image_subdir, item_name), final_image_destination)
                            except shutil.Error as move_e:
                                print(
                                    f"    Warning: Could not move image '{item_name}' to '{final_image_destination}': {move_e}")
                        print(f"  Moved images from temp to {final_image_destination}")

                    # Move files
                    if os.path.exists(temp_files_subdir):
                        for item_name in os.listdir(temp_files_subdir):
                            try:
                                shutil.move(os.path.join(temp_files_subdir, item_name), final_files_destination)
                            except shutil.Error as move_e:
                                print(
                                    f"    Warning: Could not move file '{item_name}' to '{final_files_destination}': {move_e}")
                        print(f"  Moved files from temp to {final_files_destination}")

                    # Update downloaded_filepaths and downloaded_image_filepaths in 'details' dictionary
                    updated_downloaded_filepaths = []
                    for p in details["downloaded_filepaths"]:
                        filename = os.path.basename(p)
                        updated_downloaded_filepaths.append(os.path.join(final_files_destination, filename))
                    details["downloaded_filepaths"] = updated_downloaded_filepaths

                    updated_downloaded_image_filepaths = []
                    for p in details["downloaded_image_filepaths"]:
                        filename = os.path.basename(p)
                        updated_downloaded_image_filepaths.append(os.path.join(final_image_destination, filename))
                    details["downloaded_image_filepaths"] = updated_downloaded_image_filepaths

                    all_scraped_data_overall.append(details)

                    # Save JSON file in the model's main folder (next to images/files folders)
                    json_filename = os.path.join(final_model_directory_path, f"{model_id}.json")
                    with open(json_filename, 'w', encoding='utf-8') as f:
                        json.dump(details, f, indent=4, ensure_ascii=False)
                    print(f"  Details saved to {json_filename}")

                else:
                    print(f"  Failed to scrape details for {url}.")

                # --- Step 5: Clean up temporary model folder ---
                if os.path.exists(initial_temp_model_directory_path):
                    print(f"  Cleaning up temporary model folder: {initial_temp_model_directory_path}")
                    try:
                        shutil.rmtree(initial_temp_model_directory_path)
                        print(f"  Removed temporary model folder.")
                    except OSError as e:
                        print(f"  Could not remove temporary model folder {initial_temp_model_directory_path}: {e}")

                print(f"\n======== FINISHED PROCESSING MODEL {i + 1} ========\n")
                time.sleep(5)

            final_overall_json_path = os.path.join(OUTPUT_BASE_DIRECTORY, "all_printables_models_data.json")
            with open(final_overall_json_path, 'w', encoding='utf-8') as f:
                json.dump(all_scraped_data_overall, f, indent=4, ensure_ascii=False)
            print(f"\nAll aggregated scraped data saved to {final_overall_json_path}")

        except WebDriverException as e:
            print(
                f"WebDriver error in main execution: {e}. Ensure ChromeDriver is compatible and in PATH, and browser version matches.")
        except Exception as e:
            print(f"An unexpected error occurred in main execution: {e}")
        finally:
            if details_driver:
                details_driver.quit()
            print(f"\nFinal cleanup of global temporary download directory: {temp_download_directory}")
            clean_directory(temp_download_directory)

    else:
        print("No model URLs found to scrape details. Exiting.")

    print("\nScraping process complete.")