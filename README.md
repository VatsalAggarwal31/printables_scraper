# Printables.com Scraper

This Python script is designed to scrape 3D model information and associated files (images, STL/ZIP files) from Printables.com. It supports collecting model URLs, processing their details, converting images to JPG, and organizing the output into a structured folder system based on model tags.

## Features

* **Flexible Operation Modes:**
    * `collect`: Scrape and save a list of model URLs from the main listing page.
    * `process`: Load URLs from a saved file and scrape details for each model.
    * `all`: Perform both collection and processing in a single run.
* **Configurable Limits:** Control the number of URLs collected and models processed.
* **Structured Output:** Organizes downloaded models into folders based on their primary tag, with separate subfolders for images and model files (STL, ZIP, etc.).
* **Image Conversion:** Automatically converts all downloaded images to JPG format.
* **Temporary File Management:** Uses a temporary directory for browser downloads and cleans up after processing each model.
* **Error Handling:** Includes basic error handling for network issues and missing elements.

## Folder Structure

After running the scraper, your `downloaded_models_structured` directory (defined in `config.py`) will have a structure similar to this:

````
downloaded_models_structured/
├── Tag_Category_1/
│   ├── Model_ID_Title_1/
│   │   ├── images/
│   │   │   ├── image_1.jpg
│   │   │   └── image_2.jpg
│   │   ├── files/
│   │   │   ├── model_file_1.stl
│   │   │   └── model_file_2.zip
│   │   └── 12345.json (Model details in JSON format)
│   └── Model_ID_Title_2/
│       └── ...
├── Tag_Category_2/
│   └── ...
├── temp_downloads/ (Temporary directory for browser downloads)
└── printables_model_urls.txt (Saved list of collected URLs)
└── all_printables_models_data.json (Aggregated JSON of all scraped models)
````

## Prerequisites

Before you begin, ensure you have the following installed:

* **Python 3.x:** (Tested with Python 3.8+)
* **pip:** Python package installer (usually comes with Python).
* **Google Chrome or Chromium browser:** The scraper uses Selenium WebDriver to automate Chrome.
* **ChromeDriver:** A WebDriver executable compatible with your Chrome browser version.
    * Download the correct version from [ChromeDriver Downloads](https://chromedriver.chromium.org/downloads).
    * Place the `chromedriver.exe` (or `chromedriver` on Linux/macOS) file in a directory that is in your system's PATH, or directly in your project's root directory.

## Setup

1.  **Clone or Download the Repository:**
    If you're using Git:
    ```bash
    git clone https://github.com/VatsalAggarwal31/Printables_Scarper.git
    ```
    Otherwise, download the `.zip` and extract it.

2.  **Create and Activate a Virtual Environment (Recommended):**
    A virtual environment isolates your project's dependencies.
    ```bash
    python -m venv .venv
    ```
    **Activate the virtual environment:**
    * **Windows (PowerShell):**
        ```powershell
        .venv\Scripts\activate
        ```
    * **Windows (Command Prompt):**
        ```cmd
        .venv\Scripts\activate.bat
        ```
    * **Linux / macOS:**
        ```bash
        source .venv/bin/activate
        ```
    Your command prompt should now show `(.venv)` at the beginning.

3.  **Install Dependencies:**
    With your virtual environment active, install the required Python libraries. First, ensure you have a `requirements.txt` file in your project root with the following content:
    ```
    selenium==4.22.0
    beautifulsoup4==4.12.3
    Pillow==10.4.0
    requests==2.32.3
    ```
    Then run:
    ```bash
    pip install -r requirements.txt
    ```