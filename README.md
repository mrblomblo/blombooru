# Blombooru

**Your Personal, Self-Hosted Media Tagging Tool.**

Blombooru is a single-user, private alternative to image boorus like Danbooru and Gelbooru.  
It is designed for individuals who want a powerful, simple to use, and modern solution for organizing and tagging their personal media collections. With a focus on a clean user experience, robust administration, and easy customization, Blombooru puts you in complete control of your library.

<details>
<summary>View screenshots</summary>

**Homepage**  
<img width="1920" height="1084" alt="Homepage" src="https://github.com/user-attachments/assets/eaa9b99e-ff64-439f-bb00-e5a37c53db3a" />

**Media-viewer page**
<img width="1920" height="1722" alt="Media-viewer page" src="https://github.com/user-attachments/assets/c3dcebf7-2cee-475b-b428-54986a27c42c" />

**Shared media page**
<img width="1920" height="1733" alt="Shared media page" src="https://github.com/user-attachments/assets/6fa43d69-eb44-46a4-85b4-99e85322fbea" />

**Admin panel**
<img width="1920" height="2369" alt="Admin panel" src="https://github.com/user-attachments/assets/19db7c83-bbcb-48c6-a505-78f03ea6964e" />

</details>

## Key Features

- **Danbooru-Style Tagging:** A familiar and powerful tagging system with categories (artist, character, copyright, etc.), tag-based searching, and negative tag exclusion.

- **Easy Tag Database Imports:** You can easily import custom tag lists via a simple CSV upload in the admin panel to keep your system current.

- **Modern & Responsive UI:** Built with Tailwind CSS for a beautiful and consistent experience on both desktop and mobile devices.

- **Dedicated Admin Mode:** Safely browse your collection without fear of accidental edits. All management actions (uploading, editing, deleting) require you to be in the explicit "Admin Mode".

- **Highly Customizable Theming:** Tailor the look and feel using simple CSS variables. Drop new `.css` files into the `themes` folder, register the themes in `themes.py`, and restart.

- **Many Themes to Choose From:** By default, Blombooru comes with the four Catppuccin color palettes, gruvbox light & dark, Everforest light & dark, OLED, and more, available as themes!

- **AI-Friendly:** You can easily view accompanying AI metadata for *(almost)* any media generated with SwarmUI, ComfyUI, A1111, and more. You can even append tags to the tag editor from the AI prompt.

- **Automatic Tagging:** Fast-track tagging with the WDv3 Auto Tagger integration, which analyzes images and suggests accurate tags with a single click.

- **Albums:** Organize your media into albums, which can hold both files and other sub-albums for limitless nesting and organization.

- **Media Relations:** Organize your collection by linking related media using parent-child relationships. Group image variations, multi-page comics, etc., keeping related content easily accessible.

- **Secure Media Sharing:** Generate unique, persistent links to share specific media. Shared items are presented in a stripped-down, secure view with optional sharing of AI metadata.

- **Flexible Media Uploads:** Add media via drag-and-drop, by importing a compressed archive, or by simply placing files in the storage directory and pressing the "Scan for Untracked Media" button.

- **User-Friendly Onboarding:** A simple first-time setup process to configure your admin account, database connection, and branding.

## Installation & Setup

You can choose to either use Blombooru in a docker container *(recommended)* or directly with Python.

**Prerequisites**  
- `git` *(recommended, but you could also just download the project through the GitHub website)*

### Docker *(Recommended)*

**Prerequisites**  
- Docker

This is the recommended method for using Blombooru.

1. **Clone the repository**

    ```bash
    git clone https://github.com/mrblomblo/blombooru.git
    cd blombooru
    ```

2. **Customize the environment variables**  
    Create a copy of the `example.env` file, and name it `.env`. Then open the newly created file with your favorite text editor and edit the values after the "=" on each row. The most important one to change is the example password assigned to `POSTGRES_PASSWORD`. The others *can* stay as they are, unless, for example, port 8000 is already in use by another program.

3. **First-time run & Onboarding**  
    Start the Docker container *(make sure you are in the root Blombooru folder, the one with the `docker-compose.yml` file)*:

    ```bash
    docker compose up --build -d
    ```

    *You may need to use sudo or be in a terminal with elevated privileges to run the above command.*

    Now, open your web browser and navigate to `http://localhost:<port>` *(replace `<port>` with the port you specified in the `.env` file)*. You will be greeted by the onboarding page. Here you will:  
    - Set your Admin Username and Password.
    - Enter your PostgreSQL connection details. The server will test the connection before proceeding. Unless you changed `POSTGRES_DB` and/or `POSTGRES_USER`, you only need to fill in the password that you set in the `.env` file. Do not change the DB Host.
    - Customize the site's Branding Name (defaults to "Blombooru").

    Once submitted, the server will create the database schema and create your admin account.

4. **Running the application again**  
    After the initial setup, you can run the server with the following command, again, make sure you are in the root Blombooru folder:
    
    ```bash
    docker compose up -d
    ```

    *Also again, you may need to use sudo or be in a terminal with elevated privileges to run the above command.*

    All settings are saved to a `settings.json` file in the `data` folder, and all uploaded media is saved to the `media/original` folder. Note that these folders will not be easily accessible, and will not be created in the root Blombooru folder.

If you wish to shut the container down, you should run the following command:

```bash
docker compose down
```

### Python

> [!NOTE]
> The python install  is mostly just recommended for development purposes.

**Prerequisites**  
- Python 3.10+ *(Tested with 3.13.7 & 3.11, does not seem to work with 3.14)*
- PostgreSQL 17

1. **Clone the repository**

    ```bash
    git clone https://github.com/mrblomblo/blombooru.git
    cd blombooru
    ```

2. **Create a Python virtual environment and install dependencies**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3. **Create a PostgreSQL database**  
    Create a new database and a user with permissions for that database. Blombooru will handle creating the necessary tables.

4. **First-time run & Onboarding**  
    Start the server:

    ```bash
    python run.py
    ```

    Now, open your web browser and navigate to [`http://localhost:8000`](http://localhost:8000). You will be greeted by the onboarding page. Here you will:  
    - Set your Admin Username and Password.
    - Enter your PostgreSQL connection details. The server will test the connection before proceeding.
    - Customize the site's Branding Name (defaults to "Blombooru").

    Once submitted, the server will create the database schema and create your admin account.

5. **Running the application again**  
    After the initial setup, you can run the server anytime with the same command. All settings are saved to a `settings.json` file in the `data` folder, and all uploaded media is saved to the `media/original` folder.

## Usage Guide

### Logging In

Navigate to the site and click the "Admin Panel" button in the navbar. Use the credentials you created during onboarding. Your login status is preserved with a long-lived cookie for convenience.

### Admin Mode

By default, you are in "View Mode" after logging in. To make any changes, you must log in as the admin. This protects you from accidentally deleting or editing media. While in Admin Mode, you can:

- Upload, edit, or delete media.
- Add or remove tags.
- Share media.
- Perform bulk operations like multi-deleting items from the gallery.

### Adding tags

You have two ways to add new tags:

#### 1. CSV import

Either use something like [this](https://github.com/DraconicDragon/danbooru-e621-tag-list-processor) script by DraconicDragon and scrape your own list together, or use one of the pre-scraped lists either from [here](https://civitai.com/models/950325/danboorue621-autocomplete-tag-lists-incl-aliases-krita-ai-support) or [here](https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru). Just be sure to use a CSV list that follows the requirements noted in the "Import Tags from CSV" section (it appears only the "Danbooru" CSV lists either generated by the aforementioned script or found in the linked pages for pre-scraped lists are compatible as of now)!

<img width="2269" height="590" alt="'Import Tags from CSV' section" src="https://github.com/user-attachments/assets/68be82e9-c734-4967-8c0c-a4a8cab228cf" />

#### 2. Manual tag creation
  
Manually enter the tags you want to create. Prefix a tag with for example "meta:" to put it in the "meta" category. The other available tag prefixes are noted in the "Add Tags" section.  
*Duplicate tags are automatically detected and will not be re-added.*

<img width="1443" height="424" alt="'Add Tags' section" src="https://github.com/user-attachments/assets/31263bc7-5d18-44bc-b58d-72018f6f8190" />

### Uploading Media

You have three ways to add new content:

#### 1. Media Files

In the Admin Panel, there is an upload zone, where you can simply drag & drop your media files into. Alternatively, you can click it and your file explorer will open, allowing you to select media files.

#### 2. Compressed Archives

Upload a `.zip`, `.tar.gz`, or `.tgz` archive containing your media and Blombooru will extract & process the contents.

#### 3. Filesystem Scan

Move your media files directly into the configured storage directory. Then, navigate to the Admin Panel and click the "Scan for Untracked Media" button. The server will scan the directory, find new files, generate thumbnails, and add them to your library.

*Duplicate media is automatically detected by its hash and will not be re-imported.*

### Tagging & Searching

- Tag Autocomplete: When editing an item, start typing in the tag input field. A scrollable list of suggestions will appear based on existing tags.

- Tag Display: On a media page, tags are automatically sorted by category (Artist, Character, Copyright, General, Meta) and then alphabetically within each category.

- Search Syntax: The search bar supports Danbooru's syntax.
    - `tag1 tag2`: Find media with both `tag1` AND `tag2`.
    - `-excluded_tag`: Exclude media with `excluded_tag`.
    - `*_tag`: Find media with tag(s) that end with `_tag`
    - `?tag`: Find media with tag(s) that have one character before `tag` (including no character before `tag`)
    - Example: `?girl? *_ears long_hair -blue_eyes`

### Sharing Media

- Enter Admin Mode.

- Navigate to the page of the media you wish to share.

- Click the "Share" button and a unique share URL `https://localhost:8000/shared/<uuid>` will be generated.

- Anyone with this link can view the media in a simplified, read-only interface. The shared media can optionally be shared with or without its accompanying AI metadata. Shared items are marked with a "shared" icon in your private gallery view.

## Theming

Blombooru is designed to be easily themeable.

- **CSS Variables:** The core colors are controlled by CSS variables defined in the default theme(s).

- **Custom Themes:** To make your own theme, simply create a new `.css` file in the `frontend/static/themes/` directory, copy the entire contents of the `default_dark.css` theme, and start customizing! To actually use the theme, you need to register it in the `backend/app/themes.py` file.

Your new theme will automatically appear in the theme-picker dropdown in the Admin Panel.

## Technical Details

- **Backend:** FastAPI (Python)
- **Frontend:** Tailwind CSS (locally built), Vanilla JavaScript, and HTML
- **Database:** PostgreSQL 17
- **Media Storage:** Files are stored on the local filesystem, with paths referenced in the database. Original metadata is always preserved, but can optionally be stripped on-the-fly in shared media.
- **Supported Formats:** JPG, PNG, WEBP, GIF, MP4, and WEBM.

## Disclaimer

This is a self-hosted, single-user application. As the sole administrator, you are exclusively responsible for all content you upload, manage, and share using this software.

Ensure your use complies with all applicable laws, especially regarding copyright and the privacy of any individuals depicted or identified in your media.

The developers and contributors of this project assume **no liability** for any illegal, infringing, or inappropriate content hosted by any user. The software is provided "as is" without warranty. For the full disclaimer, please see our [Disclaimer of Liability](https://github.com/mrblomblo/blombooru/blob/main/DISCLAIMER.md).

## License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt) file for details.
