# Blombooru

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)
![Docker](https://img.shields.io/badge/docker-ready-blue?style=flat-square&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

**Your Personal, Self-Hosted Media Tagging Tool.**

Blombooru is a single-user, private alternative to image boorus like Danbooru and Gelbooru.  
It is designed for individuals who want a powerful, simple to use, and modern solution for organizing and tagging their personal media collections. With a focus on a clean user experience, robust administration, and easy customization, Blombooru puts you in complete control of your library.

<details>
<summary>View screenshots</summary>

**Homepage**  
<img width="1920" alt="Homepage" src="https://github.com/user-attachments/assets/eaa9b99e-ff64-439f-bb00-e5a37c53db3a" />

**Media-viewer page**
<img width="1920" alt="Media-viewer page" src="https://github.com/user-attachments/assets/c3dcebf7-2cee-475b-b428-54986a27c42c" />

**Shared media page**
<img width="1920" alt="Shared media page" src="https://github.com/user-attachments/assets/6fa43d69-eb44-46a4-85b4-99e85322fbea" />

**Admin panel**
<img width="1920" alt="Admin panel" src="https://github.com/user-attachments/assets/19db7c83-bbcb-48c6-a505-78f03ea6964e" />

</details>

## Table of Contents

- [Key Features](#key-features)
- [Installation & Setup](#installation--setup)
  - [Docker](#docker-recommended)
  - [Python](#python)
- [Usage Guide](#usage-guide)
  - [Logging In](#logging-in)
  - [Admin Mode](#admin-mode)
  - [Adding Tags](#adding-tags)
  - [Uploading Media](#uploading-media)
  - [Tagging & Searching](#tagging--searching)
  - [Sharing Media](#sharing-media)
  - [API & Third-Party Apps](#api--third-party-apps)
- [Theming](#theming)
- [Technical Details](#technical-details)
- [Disclaimer](#disclaimer)
- [License](#license)
## Key Features

- **Danbooru-Style Tagging:** A familiar and powerful tagging system with categories (artist, character, copyright, etc.), tag-based searching, and negative tag exclusion.

- **Easy Tag Database Imports:** You can easily import custom tag lists via a simple CSV upload in the admin panel to keep your system current.

- **Modern & Responsive UI:** Built with Tailwind CSS for a beautiful and consistent experience on both desktop and mobile devices.

- **Secure Mode:** When enabled, users must log in to interact with Blombooru. Public routes such as share links and static files remain public. Perfect for private collections that you don't want anyone else in the house to see!

- **Safe Browsing:** Safely browse your collection without fear of accidental edits. All management actions (uploading, editing, deleting) require you to be logged in as the admin.

- **Highly Customizable Theming:** Tailor the look and feel using simple CSS variables. Drop new `.css` files into the `themes` folder, register the themes in `themes.py`, and restart.

- **Many Themes to Choose From:** By default, Blombooru comes with the four Catppuccin color palettes, gruvbox light & dark, Everforest light & dark, OLED, and more, available as themes!

- **AI-Friendly:** You can easily view accompanying AI metadata for *(almost)* any media generated with SwarmUI, ComfyUI, A1111, and more. You can even append tags to the tag editor from the AI prompt.

- **Automatic Tagging:** Fast-track tagging with the WDv3 Auto Tagger integration, which analyzes images and suggests accurate tags with a single click.

- **Albums:** Organize your media into albums, which can hold both media items and other sub-albums for limitless nesting and organization.

- **Media Relations:** Organize your collection by linking related media using parent-child relationships. Group image variations, multi-page comics, etc., keeping related content easily accessible.

- **Secure Media Sharing:** Generate unique, persistent links to share specific media. Shared items are presented in a stripped-down, secure view with optional sharing of AI metadata.

- **Flexible Media Uploads:** Add media via drag-and-drop, by importing a compressed archive, or by simply placing files in the storage directory and pressing the "Scan for Untracked Media" button.

- **User-Friendly Onboarding:** A simple first-time setup process to configure your admin account, database connection, and branding.

- **Danbooru v2 API Compatibility:** Connect to Blombooru using your favorite third-party Booru clients (like Grabber, Tachiyomi, or BooruNav) thanks to a built-in compatibility layer.

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
> The Python installation is primarily recommended for development purposes, but can be useful if you are able to use Python venvs, but not Docker.

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

Navigate to the site and click the "Admin Panel" button in the navbar and log in using the credentials you created for the admin account during onboarding. Your login status is preserved with a long-lived cookie for convenience.

### Admin Mode

To make any changes, you must log in as the admin. This protects you from accidentally deleting or editing media. While logged in as the admin, you can:

- Upload, edit, or delete media.
- Add or remove tags.
- Share media.
- Perform bulk operations like multi-deleting items from the gallery.

### Adding tags

You have two ways to add new tags:

#### 1. CSV import

Either use something like [this](https://github.com/DraconicDragon/danbooru-e621-tag-list-processor) script by DraconicDragon and scrape your own list together, or use one of the pre-scraped lists either from [here](https://civitai.com/models/950325/danboorue621-autocomplete-tag-lists-incl-aliases-krita-ai-support) or [here](https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru).

> [!Important]
> Ensure your CSV list follows the format specified in the "Import Tags from CSV" section seen below. Currently, only "Danbooru" style CSV lists (generated by the script or found in the linked archives) are fully compatible.

<img width="1920" alt="'Import Tags from CSV' section" src="https://github.com/user-attachments/assets/68be82e9-c734-4967-8c0c-a4a8cab228cf" />

#### 2. Manual tag creation
  
Manually enter the tags you want to create. Prefix a tag with for example "meta:" to put it in the "meta" category. The other available tag prefixes are noted in the "Add Tags" section.  
*Duplicate tags are automatically detected and will not be re-added.*

<img width="1920" alt="'Add Tags' section" src="https://github.com/user-attachments/assets/31263bc7-5d18-44bc-b58d-72018f6f8190" />

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

- Search Syntax: Blombooru supports a powerful Danbooru-compatible search syntax.

#### Basic Tags
- `tag1 tag2`: Find media with both `tag1` AND `tag2`.
- `-tag1`: Exclude media with `tag1`.
- `tag*`: Wildcard search (finds `tag_name`, `tag_stuff`, etc.).
- `?tag`: Find media with one or zero characters before `tag`.

#### Ranges
Most numeric and date qualifiers support range operators:
- `id:100` -> Exact match (x == 100)
- `id:100..200` -> Between inclusive (100 <= x <= 200)
- `id:>=100` -> Greater than or equal (x >= 100)
- `id:>100` -> Greater than (x > 100)
- `id:<=100` -> Less than or equal (x <= 100)
- `id:<100` -> Less than (x < 100)
- `id:1,2,3` -> In list (x is 1, 2, or 3)

#### Meta Qualifiers
| Qualifier | Description | Example(s) |
| :--- | :--- | :--- |
| `id` | Search by internal ID. | `id:100..200`, `id:>500` |
| `width`, `height` | Search by image dimensions (pixels). | `width:>=1920`, `height:1080` |
| `filesize` | Search by file size using `kb`, `mb`, `gb`, `b` units. <br> Supports "fuzzy" matching: `filesize:52MB` finds `52.0MB` to `52.99MB`. | `filesize:1mb..5mb`, `filesize:52MB` |
| `date` | Search by upload date (YYYY-MM-DD). | `date:2024-01-01` |
| `age` | Search by age relative to now (`s`, `mi`, `h`, `d`, `w`, `mo`, `y`). <br> Note: `<` means "newer than" (less age). | `age:<24h` (less than 1 day old) <br> `age:1w..1mo` |
| `rating` | Filter by rating: `s`/`safe`, `q`/`questionable`, `e`/`explicit`. <br> Supports lists. | `rating:s,q`, `-rating:e` |
| `source` | Search source. Use `none` for missing sources, `http` for web URLs. | `source:none`, `source:http`, `source:twitter` |
| `filetype` | Search by file extension. | `filetype:png`, `filetype:gif` |
| `md5` | Search by file hash (exact). | `md5:d34e4c...` |
| `pool`, `album` | Search by album/pool ID or name. `any`/`none` supported. | `album:any`, `pool:favorites`, `pool:5` |
| `parent` | Search by parent ID. `any`/`none` supported. | `parent:none`, `parent:123` |
| `child` | Filter parent posts by children. `any`/`none` supported. | `child:any` (has children), `child:none` |
| `duration` | Search video/gif duration in seconds. | `duration:>60` |

*Note: `duration` may not be set on all GIFs.*

#### Tag Counts
Filter by the number of tags on a post.
- `tagcount`: Total tags
- `gentags`: General tags
- `arttags`: Artist tags
- `chartags`: Character tags
- `copytags`: Copyright tags
- `metatags`: Meta tags

Example: `tagcount:<10` (posts with few tags), `arttags:>=1` (posts with at least 1 artist tag).

#### Sorting
Order results with `order:{value}`. Suffix with `_asc` or `_desc` where applicable (default is usually desc).
| Value | Description |
| :--- | :--- |
| `id` / `id_desc` | Newest uploads first (Default). |
| `id_asc` | Oldest uploads first. |
| `filesize` | Largest files first. |
| `landscape` | Widest aspect ratio first. |
| `portrait` | Tallest aspect ratio first. |
| `md5` | Sort using MD5 hash (deterministic random-like shuffle). |
| `custom` | Sort by the order given in `id:list`. Example: `id:3,1,2 order:custom`. |

### Sharing Media

- Log in as the admin.

- Navigate to the page of the media you wish to share.

- Click the "Share" button and a unique share URL `https://localhost:8000/shared/<uuid>` will be generated.

- Anyone with this link can view the media in a simplified, read-only interface. The shared media can optionally be shared with or without its accompanying AI metadata. Shared items are marked with a "shared" icon in your private gallery view.

### API & Third-Party Apps

Blombooru implements a **Danbooru v2 compatible API**, allowing you to use existing third-party Booru clients (like Grabber, Tachiyomi, or BooruNav) to browse your collection.

**Connection Details:**
- **Server Type:** Danbooru v2
- **URL:** Your server IP + port (e.g., `http://192.168.1.10:8000`) or your domain (e.g., `https://example.com`)
- **Authentication:** Supported via multiple methods:
  - Query parameters: `login` + `api_key`
  - HTTP Basic Auth: username + API key as password
  - Bearer token: `Authorization: Bearer <api_key>`

**Supported Features:**
- **Posts:** Full search capability, listing, and media retrieval.
- **Tags:** Tag listing, search, autocomplete, and related tags.
- **Albums/Pools:** Blombooru Albums are exposed as Danbooru "Pools".
- **Artists:** Blombooru Artist tags are exposed as the Artists endpoint.

*Note: Write operations (uploading, editing, etc.) via the API are read-only or stubbed to prevent errors in third-party apps. Social features such as voting, favoriting, comments, forums, DMs, and wiki pages return empty results.*

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
