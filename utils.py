# utils.py - No changes needed to the functions themselves, as they take folder paths as arguments.
#            Only the usage in scraper.py and main.py will change.

import os
import re
import time
import shutil
import requests
from PIL import Image
from selenium.webdriver.common.by import By

# Define a common selector for the cookie banner's main container.
COOKIE_BANNER_CONTAINER_SELECTOR = (By.CLASS_NAME, "cky-consent-bar")


def sanitize_filename(name):
    """Sanitizes a string to be a valid filename/foldername."""
    s = re.sub(r'[^\w\s.-]', '', name).strip()
    s = re.sub(r'\s+', '_', s)
    s = s.strip('_-')
    return s[:100]


def clean_directory(directory_path):
    """Removes all files and subdirectories from the given directory."""
    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
        return

    print(f"  Attempting to clean directory: {directory_path}")
    for item_name in os.listdir(directory_path):
        item_path = os.path.join(directory_path, item_name)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
            print(f"    Successfully cleaned: {item_path}")
        except Exception as e:
            print(f"    Failed to delete {item_path}. Reason: {e}")


def wait_for_download_completion(download_dir, initial_files, timeout=180):
    """
    Waits for a new, completed file to appear in the download directory.
    This version does NOT check for specific names or extensions, only for completion.
    Args:
        download_dir (str): The directory where files are being downloaded (the temp folder).
        initial_files (set): A set of filenames present in the directory before the download started.
        timeout (int): Maximum time in seconds to wait for the download.
    Returns:
        str: The full path to the downloaded (and completed) file in the temp directory if successful, None otherwise.
    """
    timeout_start = time.time()

    print(f"    [VERIFY] Starting general download verification in '{download_dir}'.")
    print(f"    [VERIFY] Initial files: {initial_files}")

    # Common partial download extensions to exclude
    partial_extensions = ('.crdownload', '.part', '.tmp', '.torrent', '.download', '.inprogress')

    while time.time() - timeout_start < timeout:
        current_files = set(os.listdir(download_dir) if os.path.exists(download_dir) else [])

        if len(current_files) > 0:
            print(f"    [VERIFY] Current files in '{download_dir}': {list(current_files)}")

        new_files_raw = list(current_files - initial_files)

        if new_files_raw:
            print(f"    [VERIFY] Potential new files (before partial filter): {new_files_raw}")

        # Filter out partial download files
        new_completed_files = [
            f for f in new_files_raw
            if not f.lower().endswith(partial_extensions)
        ]

        if new_completed_files:
            print(f"    [VERIFY] New completed files (after partial filter): {new_completed_files}")

            # Sort by modification time to prioritize the most recently modified complete file
            candidate_files_with_mtime = []
            for f_name in new_completed_files:
                f_path = os.path.join(download_dir, f_name)
                try:
                    candidate_files_with_mtime.append((f_path, os.path.getmtime(f_path)))
                except OSError:  # File might still be locking/writing, skip for now
                    print(
                        f"    [VERIFY] WARNING: Could not get mtime for '{f_name}'. Skipping candidate for this check.")
                    continue

            if not candidate_files_with_mtime:
                time.sleep(1)
                continue

            # Get the most recently modified complete file
            candidate_files_with_mtime.sort(key=lambda x: x[1], reverse=True)
            downloaded_file_path = candidate_files_with_mtime[0][0]
            print(f"    [VERIFY] Top candidate for completion: '{os.path.basename(downloaded_file_path)}'")

            # Check for file size stability
            stable_size_checks = 0
            last_known_size = -1

            for check_attempt in range(25):  # Check up to 25 times for stability (25 seconds)
                try:
                    current_size = os.path.getsize(downloaded_file_path)

                    if current_size > 0 and current_size == last_known_size:
                        stable_size_checks += 1
                        print(
                            f"    [VERIFY] Size stable check {stable_size_checks}/5 for '{os.path.basename(downloaded_file_path)}' (size: {current_size} bytes)")
                        if stable_size_checks >= 5:  # Require at least 5 consecutive stable readings (5 seconds)
                            print(
                                f"    [VERIFY] SUCCESS: Download complete and stable: '{os.path.basename(downloaded_file_path)}'")
                            return downloaded_file_path
                    elif current_size >= 0:
                        if current_size > 0:
                            stable_size_checks = 1
                        else:
                            stable_size_checks = 0
                        last_known_size = current_size
                        print(
                            f"    [VERIFY] Size changed for '{os.path.basename(downloaded_file_path)}' to {current_size} bytes. Resetting stable checks.")

                except OSError as e:
                    print(
                        f"    [VERIFY] WARNING: Could not get size of '{os.path.basename(downloaded_file_path)}' (Error: {e}). Retrying ({check_attempt + 1}/25)...")
                    stable_size_checks = 0

                time.sleep(1)

            print(
                f"    [VERIFY] Timeout on size stability for '{os.path.basename(downloaded_file_path)}'. Did not reach stable size within checks.")
            return None

        time.sleep(2)
        print(
            f"    [VERVERIFY] Still waiting for any new completed file in '{download_dir}'. Time elapsed: {int(time.time() - timeout_start)}s")

    print(f"  [VERIFY] TIMEOUT: No new completed files found in '{download_dir}' within {timeout} seconds.")
    return None


def download_image(image_url, destination_folder, filename=None, jpg_quality=90):
    """
    Downloads an image from a URL to a specified folder and converts it to JPG if it's not already.
    Args:
        image_url (str): The URL of the image to download.
        destination_folder (str): The path to the folder where the image should be saved.
        filename (str, optional): The desired filename for the downloaded image.
                                  If None, filename is derived from the URL.
        jpg_quality (int): Quality for JPG conversion (0-100).
    Returns:
        str: The full path to the saved JPG image if successful, None otherwise.
    """
    os.makedirs(destination_folder, exist_ok=True)

    # Determine the temporary filename based on original URL
    if filename is None:
        temp_filename = os.path.basename(image_url).split('?')[0]
        if '.' not in temp_filename:
            # Add a likely extension if missing for initial download
            temp_filename += '.tmp_ext'
        temp_filename = sanitize_filename(temp_filename)
    else:
        temp_filename = sanitize_filename(filename)

    # Add a simple mechanism to prevent overwriting if filename already exists (for temp file)
    base_temp, ext_temp = os.path.splitext(temp_filename)
    counter_temp = 1
    initial_file_path = os.path.join(destination_folder, temp_filename)
    while os.path.exists(initial_file_path):
        initial_file_path = f"{base_temp}_{counter_temp}{ext_temp}"
        counter_temp += 1

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }
        response = requests.get(image_url, stream=True, headers=headers, timeout=30)
        response.raise_for_status()

        with open(initial_file_path, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        print(f"    Downloaded image (original format): {os.path.basename(initial_file_path)}")

        # --- Image Conversion Logic ---
        base_name_without_ext = os.path.splitext(os.path.basename(initial_file_path))[0]
        final_jpg_path = os.path.join(destination_folder, f"{base_name_without_ext}.jpg")

        # Ensure the final JPG filename is unique
        jpg_counter = 1
        original_final_jpg_path = final_jpg_path
        while os.path.exists(
                final_jpg_path) and final_jpg_path != initial_file_path:  # Avoid infinite loop if somehow source IS JPG and exists
            final_jpg_path = f"{os.path.splitext(original_final_jpg_path)[0]}_{jpg_counter}.jpg"
            jpg_counter += 1

        if not os.path.splitext(initial_file_path)[1].lower() in ('.jpg', '.jpeg'):
            try:
                img = Image.open(initial_file_path)

                # Convert RGBA to RGB if necessary (for PNGs with transparency)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')

                img.save(final_jpg_path, 'jpeg', quality=jpg_quality)  # Save as JPEG with quality
                print(f"    Converted to JPG: {os.path.basename(final_jpg_path)}")

                # Delete the original downloaded file
                os.remove(initial_file_path)
                print(f"    Removed original file: {os.path.basename(initial_file_path)}")
                return final_jpg_path
            except Exception as convert_e:
                print(
                    f"    Failed to convert {os.path.basename(initial_file_path)} to JPG: {convert_e}. Keeping original file.")
                return initial_file_path  # Return original path if conversion fails
        else:
            print(f"    Image already in JPG format: {os.path.basename(initial_file_path)}")
            # If the initial file *is* a JPG but had a temp_ext, rename it to .jpg if needed.
            # Or if it's a JPG and needs to be unique if the base name already existed
            if not initial_file_path.lower().endswith(('.jpg', '.jpeg')) or os.path.basename(
                    initial_file_path) != os.path.basename(final_jpg_path):
                # Ensure we don't try to rename to itself if already correct and unique
                if not os.path.exists(
                        final_jpg_path) or final_jpg_path == initial_file_path:  # if final_jpg_path doesn't exist, or if it's the same as initial, we can rename
                    try:
                        os.rename(initial_file_path, final_jpg_path)
                        print(
                            f"    Renamed {os.path.basename(initial_file_path)} to {os.path.basename(final_jpg_path)}")
                        return final_jpg_path
                    except OSError as e:
                        print(
                            f"    Error renaming already JPG file {os.path.basename(initial_file_path)} to {os.path.basename(final_jpg_path)}: {e}. Keeping original path.")
                        return initial_file_path
                else:  # final_jpg_path exists and is different from initial, likely due to uniqueness check
                    return initial_file_path  # Can't rename to an existing unique name, just return the path it already has
            return initial_file_path  # Return original path if it's already JPG and no rename needed

    except requests.exceptions.RequestException as e:
        print(f"    Failed to download image from {image_url}: {e}")
        return None
    except Exception as e:
        print(f"    An unexpected error occurred while saving or processing image {image_url}: {e}")
        return None