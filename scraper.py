# scraper.py
import os
import re
import shutil
import time
import json
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# Import utilities and configurations
from utils import sanitize_filename, clean_directory, wait_for_download_completion, download_image, \
    COOKIE_BANNER_CONTAINER_SELECTOR
from config import (
    MAX_SCROLL_ATTEMPTS, SCROLL_PAUSE_TIME,
    COOKIE_CONSENT_TIMEOUT, CLICK_TIMEOUT,
    DOWNLOAD_ALL_TIMEOUT, INDIVIDUAL_DOWNLOAD_TIMEOUT,
    IMAGE_DOWNLOAD_PAUSE_TIME, JPG_CONVERSION_QUALITY
)


def scrape_models(driver, base_url, limit=0):
    """
    Scrapes model URLs from the Printables.com listing page using infinite scroll,
    after applying 'Makes' and 'All Time' filters.
    Args:
        driver: The Selenium WebDriver instance.
        base_url (str): The base URL for the models listing page.
        limit (int): Maximum number of unique URLs to collect. 0 means no limit.
    Returns:
        list: A list of unique model URLs.
    """
    driver.get(base_url)

    # --- Handling Cookie Consent (for the initial listing page) ---
    try:
        print("Checking for cookie consent banner on main listing page...")
        accept_cookies_button = WebDriverWait(driver, COOKIE_CONSENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.cky-btn.cky-btn-accept"))
        )
        if accept_cookies_button:
            accept_cookies_button.click()
            print("Accepted cookie consent on main listing page.")
            WebDriverWait(driver, CLICK_TIMEOUT).until(
                EC.invisibility_of_element_located(COOKIE_BANNER_CONTAINER_SELECTOR)
            )
            print("Cookie banner on main listing page is now invisible.")
    except TimeoutException:
        print("No cookie consent banner found on main listing page within the timeout or button not clickable.")
    except Exception as e:
        print(f"An unexpected error occurred while handling cookie consent on main listing page: {e}")

    # --- Filtering by "Makes" ---
    try:
        print("Attempting to click 'Makes' filter...")
        makes_button = WebDriverWait(driver, CLICK_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@class, 't') and contains(@class, 'svelte-l6pc2w') and text()='Makes']"))
        )

        if "active" not in makes_button.get_attribute("class"):
            makes_button.click()
            print("Clicked 'Makes' filter.")
            time.sleep(SCROLL_PAUSE_TIME + 2)  # Give a bit more time for filter to apply
        else:
            print("'Makes' filter is already active.")
    except TimeoutException:
        print("Timeout: 'Makes' filter button not found or not clickable.")
    except Exception as e:
        print(f"Could not find or click 'Makes' filter: {e}")

    # --- Filtering by "Time - All Time" ---
    try:
        print("Attempting to change 'Sort by Time' to 'All Time'...")

        sort_by_time_dropdown = WebDriverWait(driver, CLICK_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH,
                                        "//div[./span[@class='period-label' and text()='In:']]//button[contains(@class, 'f') and contains(@class, 'svelte-ar8eb')]"))
        )
        sort_by_time_dropdown.click()
        print("  Clicked 'Sort by Time' dropdown.")
        time.sleep(1)  # Small pause after clicking dropdown

        all_time_option = WebDriverWait(driver, CLICK_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[contains(@class, 'dropdown-menu')]//button[text()='All time']"))
        )
        all_time_option.click()
        print("  Selected 'All Time' filter.")
        time.sleep(SCROLL_PAUSE_TIME + 2)  # Give a bit more time for filter to apply

    except TimeoutException:
        print("Timeout: Could not find 'Sort by Time' dropdown or 'All Time' option. Check selectors.")
    except Exception as e:
        print(f"Error changing 'Sort by Time' to 'All Time': {e}")

    # --- Infinite Scroll Logic ---
    all_model_links = set()
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0

    print("Starting infinite scroll to collect model links...")

    while True:
        soup_before_scroll = BeautifulSoup(driver.page_source, 'html.parser')
        models_before_scroll = soup_before_scroll.select('a.card-image[href*="/model/"]')
        initial_model_count = len(models_before_scroll)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)

        new_height = driver.execute_script("return document.body.scrollHeight")

        soup_after_scroll = BeautifulSoup(driver.page_source, 'html.parser')
        models_after_scroll = soup_after_scroll.select('a.card-image[href*="/model/"]')
        new_model_count = len(models_after_scroll)

        if new_height == last_height and new_model_count <= initial_model_count:
            scroll_attempts += 1
            print(f"  Scroll height not changed and no new models found ({scroll_attempts}/{MAX_SCROLL_ATTEMPTS}).")
            if scroll_attempts >= MAX_SCROLL_ATTEMPTS:
                print("  Reached max scroll attempts with no new content. Ending scroll.")
                break
        else:
            scroll_attempts = 0
            print(
                f"  Scrolled down, new content loaded. Current height: {new_height}. New models added by scroll: {new_model_count - initial_model_count}")

        last_height = new_height

        for link_element in models_after_scroll:
            href = link_element.get('href')
            if href and href.startswith('/model/'):
                full_link = f"https://www.printables.com{href.split('?')[0]}"
                all_model_links.add(full_link)

        print(f"  Total unique links collected so far: {len(all_model_links)}")

        # New limit check
        if limit > 0 and len(all_model_links) >= limit:
            print(
                f"  Collected {len(all_model_links)} models, which meets or exceeds the collection limit of {limit}. Ending scroll.")
            break

    return list(all_model_links)


def scrape_model_details(driver, model_url, temp_download_dir, final_model_output_image_dir,
                         final_model_output_files_dir):
    """
    Scrapes details for a single model and initiates file downloads, including images.
    Files are downloaded to a temporary directory, verified, and then moved to
    the final_model_output_files_dir.
    Images are downloaded directly to the final_model_output_image_dir.
    Args:
        driver: The Selenium WebDriver instance.
        model_url (str): The URL of the specific model page.
        temp_download_dir (str): Path to the temporary download directory.
        final_model_output_image_dir (str): Path to the model's specific image output directory.
        final_model_output_files_dir (str): Path to the model's specific files output directory.
    Returns:
        dict: A dictionary containing scraped model data, or None if scraping fails.
    """
    driver.get(model_url)

    # --- Handling Cookie Consent (on each specific model page) ---
    try:
        print(f"  Checking for cookie consent banner on model page: {model_url}...")
        time.sleep(1)
        accept_cookies_button_model_page = WebDriverWait(driver, COOKIE_CONSENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.cky-btn.cky-btn-accept"))
        )
        if accept_cookies_button_model_page:
            accept_cookies_button_model_page.click()
            print(f"  Accepted cookie consent on {model_url}.")
            WebDriverWait(driver, CLICK_TIMEOUT).until(
                EC.invisibility_of_element_located(COOKIE_BANNER_CONTAINER_SELECTOR)
            )
            print(f"  Cookie banner on {model_url} is now invisible.")
    except TimeoutException:
        print(f"  No cookie consent banner found on {model_url} within the timeout or already accepted.")
    except Exception as e:
        print(f"  An unexpected error occurred while handling cookie consent on {model_url}: {e}")

    model_data = {
        "title": "N/A",
        "description": "N/A",
        "images": [],
        "grams": "N/A",
        "tags": [],
        "downloaded_filepaths": [],
        "downloaded_image_filepaths": [],
        "url": model_url
    }

    try:
        WebDriverWait(driver, CLICK_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.detail-header h1"))
        )

        # --- Scrape initial details ---
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Model Title
        title_element = soup.select_one("div.model-header h1.svelte-6cpohy")
        model_data["title"] = title_element.text.strip() if title_element else "N/A"
        print(f"  Scraping details for: {model_data['title']}")

        # Model Images (Gallery) - Using original SRC directly
        for img_tag in soup.select(
                'div.image-gallery img[src*="/media/prints/"], div.image-gallery img[src*="/media/stls/"]'):
            src = img_tag.get('src')
            if src:
                model_data["images"].append(src)
                print(f"    Original (and now direct) image SRC: {src}")

        model_data["images"] = list(set(model_data["images"]))
        print(f"  Image URLs found (direct from src): {len(model_data['images'])}")

        # Description (Summary)
        description_element = soup.select_one("div.summary.svelte-jqt6s6")
        model_data["description"] = description_element.text.strip() if description_element else "N/A"

        # Model Grams (GMS)
        grams_element_parent = soup.select_one("div.attr:has(i.fa-scale-balanced)")
        if grams_element_parent:
            grams_value_div = grams_element_parent.select_one("div:last-of-type")
            if grams_value_div:
                grams_text = grams_value_div.get_text(strip=True)
                grams_match = re.search(r'(\d+(\.\d+)?)\s*g', grams_text, re.IGNORECASE)
                if grams_match:
                    model_data["grams"] = float(grams_match.group(1))
        print(f"  Grams: {model_data['grams']}")

        # Tags (Categories and Attributes)
        for breadcrumb_a in soup.select("div.breadcrumbs.svelte-edq10p a"):
            tag_text = breadcrumb_a.text.strip()
            if tag_text and tag_text not in ["3D Models"] and tag_text not in model_data["tags"]:
                model_data["tags"].append(tag_text)

        for attr_a in soup.select("div.attributes.svelte-v07nbv div.attr a"):
            tag_text = attr_a.text.strip()
            if tag_text and tag_text not in model_data["tags"]:
                model_data["tags"].append(tag_text)
        print(f"  Tags: {model_data['tags']}")

        # --- Download Images ---
        print(f"  Attempting to download {len(model_data['images'])} images...")
        downloaded_image_paths = []
        for img_idx, img_url in enumerate(model_data["images"]):
            original_ext = os.path.splitext(os.path.basename(img_url).split('?')[0])[-1]
            if not original_ext:
                match_ext = re.search(r'\.(jpg|jpeg|png|webp)(\?|$)', img_url, re.IGNORECASE)
                if match_ext:
                    original_ext = '.' + match_ext.group(1).lower()
                else:
                    original_ext = '.jpg'

            temp_filename = f"image_{img_idx + 1}{original_ext}"
            downloaded_img_path = download_image(img_url, final_model_output_image_dir, filename=temp_filename,
                                                 jpg_quality=JPG_CONVERSION_QUALITY)

            if downloaded_img_path:
                downloaded_image_paths.append(downloaded_img_path)
            time.sleep(IMAGE_DOWNLOAD_PAUSE_TIME)
        model_data["downloaded_image_filepaths"] = downloaded_image_paths

        # --- Navigate to "Files" Tab and initiate Downloads ---
        try:
            print("  Attempting to click 'Files' tab...")
            files_tab = WebDriverWait(driver, CLICK_TIMEOUT).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[data-testid='model-tab-files']"))
            )
            files_tab.click()
            print("  Clicked 'Files' tab. Waiting for file list to load...")
            time.sleep(SCROLL_PAUSE_TIME)

            initial_files_in_temp_dir = set(os.listdir(temp_download_dir) if os.path.exists(temp_download_dir) else [])
            print(f"  Files in temp dir before download attempt: {initial_files_in_temp_dir}")

            downloaded_a_file_successfully = False

            # --- Attempt to click "Download All" button first ---
            try:
                download_all_button = WebDriverWait(driver, CLICK_TIMEOUT).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='download-all-model']"))
                )
                print("  Found 'Download All model files' button. Clicking it...")
                download_all_button.click()

                downloaded_temp_zip_path = wait_for_download_completion(
                    temp_download_dir,
                    initial_files_in_temp_dir,
                    timeout=DOWNLOAD_ALL_TIMEOUT
                )

                if downloaded_temp_zip_path:
                    # Move to final_model_output_files_dir
                    final_zip_path = os.path.join(final_model_output_files_dir,
                                                  os.path.basename(downloaded_temp_zip_path))
                    print(f"  Moving '{downloaded_temp_zip_path}' to '{final_zip_path}'")
                    try:
                        os.makedirs(os.path.dirname(final_zip_path), exist_ok=True)
                        shutil.move(downloaded_temp_zip_path, final_zip_path)
                        model_data["downloaded_filepaths"].append(final_zip_path)
                        downloaded_a_file_successfully = True
                        print(f"  'Download All' successful and moved: {final_zip_path}")
                    except shutil.Error as move_err:
                        print(
                            f"  Error moving downloaded ZIP: {move_err}. Keeping path to temp: {downloaded_temp_zip_path}")
                        model_data["downloaded_filepaths"].append(downloaded_temp_zip_path)
                        downloaded_a_file_successfully = True
                else:
                    print(f"  'Download All' timed out or failed to verify. Proceeding to individual files if found.")

            except TimeoutException:
                print(
                    "  'Download All model files' button not found within timeout. Proceeding with individual files if any.")

            except Exception as e:
                print(f"  Error with 'Download All' button or verification: {e}. Proceeding to individual files.")

            # --- Fallback to Individual File Downloads ---
            if not downloaded_a_file_successfully:
                file_download_buttons = WebDriverWait(driver, CLICK_TIMEOUT).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "button[data-testid='download-file']"))
                )

                if not file_download_buttons:
                    print("  No individual file download buttons found on 'Files' tab after fallback attempt.")
                else:
                    print(f"  Attempting to download {len(file_download_buttons)} individual files.")

                    for j, file_btn in enumerate(file_download_buttons):
                        initial_files_in_temp_dir_for_individual = set(
                            os.listdir(temp_download_dir) if os.path.exists(temp_download_dir) else [])
                        print(
                            f"    Initial files in temp dir for individual download #{j + 1}: {initial_files_in_temp_dir_for_individual}")

                        try:
                            file_name_element = file_btn.find_element(By.XPATH,
                                                                      "./ancestor::div[contains(@class, 'download-wrapper')]/preceding-sibling::div[contains(@class, 'info')]//h5[contains(@class, 'name-on-desktop')]//div[contains(@class, 'shrink')]")

                            file_name_for_log = file_name_element.text.strip()
                            print(f"    Clicking individual download button for: {file_name_for_log}")

                            file_btn.click()

                            downloaded_temp_file_path = wait_for_download_completion(
                                temp_download_dir,
                                initial_files_in_temp_dir_for_individual,
                                timeout=INDIVIDUAL_DOWNLOAD_TIMEOUT
                            )

                            if downloaded_temp_file_path:
                                # Move to final_model_output_files_dir
                                final_file_path = os.path.join(final_model_output_files_dir,
                                                               os.path.basename(downloaded_temp_file_path))
                                print(f"    Moving '{downloaded_temp_file_path}' to '{final_file_path}'")
                                try:
                                    os.makedirs(os.path.dirname(final_file_path), exist_ok=True)
                                    shutil.move(downloaded_temp_file_path, final_file_path)
                                    model_data["downloaded_filepaths"].append(final_file_path)
                                    downloaded_a_file_successfully = True
                                    print(f"    Downloaded and moved successfully to: {final_file_path}")
                                except shutil.Error as move_err:
                                    print(
                                        f"    Error moving downloaded file: {move_err}. Keeping path to temp: {downloaded_temp_file_path}")
                                    model_data["downloaded_filepaths"].append(downloaded_temp_file_path)
                                    downloaded_a_file_successfully = True
                            else:
                                print(f"    Download of {file_name_for_log} timed out or failed to verify.")
                                partial_extensions = ('.crdownload', '.part', '.tmp', '.torrent', '.download',
                                                      '.inprogress')
                                potential_partial_files = [f for f in os.listdir(temp_download_dir) if
                                                           f.lower().endswith(partial_extensions)]
                                if potential_partial_files:
                                    print(f"    Found partial download files in temp dir: {potential_partial_files}")

                        except StaleElementReferenceException:
                            print(
                                f"    Stale element for an individual download button ({file_name_for_log}). Skipping.")
                        except NoSuchElementException:
                            print(
                                f"    Could not find filename element for individual download button (File #{j + 1}). Skipping.")
                        except Exception as dl_e:
                            print(
                                f"    General error processing individual file download button: {dl_e}. Skipping file.")

            if not downloaded_a_file_successfully:
                print("  No files (ZIP or individual) were successfully downloaded for this model.")


        except TimeoutException:
            print("  'Files' tab or its content not found within timeout. No files downloaded.")
        except Exception as e:
            print(f"  An error occurred while handling 'Files' tab or downloads: {e}")

        return model_data

    except TimeoutException:
        print(f"  Timeout loading model details for {model_url}. Skipping.")
        return None
    except Exception as e:
        print(f"  An unexpected error occurred while scraping details for {model_url}: {e}. Skipping.")
        return None