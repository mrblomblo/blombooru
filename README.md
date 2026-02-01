<p align="center"><img width="830" alt="Blombooru Banner" src="https://github.com/user-attachments/assets/a13b7b6d-f7e5-4251-a14c-4bf8b069a366" /></p>

<div align="center">
  
  ![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
  ![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)
  ![Redis](https://img.shields.io/badge/Redis-7+-FF4235?style=flat-square&logo=redis&logoColor=white)
  ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-2F6792?style=flat-square&logo=postgresql&logoColor=white)
  ![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)
  ![Docker](https://img.shields.io/badge/Docker-ready-blue?style=flat-square&logo=docker&logoColor=white)
  ![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
  
</div>

<p align="center"><b>Your Personal, Self-Hosted Media Tagging Tool.</b></p>

Blombooru is a private, single-user alternative to image boorus like Danbooru and Gelbooru. It is designed for individuals who want a powerful, easy-to-use, and modern solution for organizing and tagging their personal media collections. With a focus on a clean user experience, robust administration, and easy customization, Blombooru puts you in complete control of your library.

> [!IMPORTANT]
> This project is currently in **heavy development**, and breaking changes may be introduced without prior notice (even if I try my best to limit how much they affect existing users).  
> If you want to use Blombooru after its official release (when breaking changes will be properly documented), please click the **Watch** button to be notified when the first official release is available!

<details>
<summary>View Screenshots</summary>

**Homepage**
<img width="1920" alt="Homepage" src="https://github.com/user-attachments/assets/eaa9b99e-ff64-439f-bb00-e5a37c53db3a" />

**Media Viewer Page**
<img width="1920" alt="Media-viewer page" src="https://github.com/user-attachments/assets/c3dcebf7-2cee-475b-b428-54986a27c42c" />

**Shared Media Page**
<img width="1920" alt="Shared media page" src="https://github.com/user-attachments/assets/6fa43d69-eb44-46a4-85b4-99e85322fbea" />

**Admin Panel**
<img width="1920" alt="Admin panel" src="https://github.com/user-attachments/assets/19db7c83-bbcb-48c6-a505-78f03ea6964e" />

</details>

## Table of Contents

- [Key Features](#key-features)
- [Installation & Setup](#installation--setup)
  - [Docker](#docker-recommended)
    - [Multi-Instance Setup](#running-multiple-instances)
  - [Python](#python)
- [Usage Guide](#usage-guide)
  - [Logging In](#logging-in)
  - [Admin Mode](#admin-mode)
  - [Adding Tags](#adding-tags)
  - [Uploading Media](#uploading-media)
  - [Tagging & Searching](#tagging--searching)
  - [Sharing Media](#sharing-media)
  - [System Updater](#system-updater)
  - [API & Third-Party Apps](#api--third-party-apps)
- [Theming](#theming)
- [Technical Details](#technical-details)
- [Disclaimer](#disclaimer)
- [License](#license)

## Key Features

### Core Functionality

- **Danbooru-Style Tagging:** A familiar and powerful tagging system with categories (artist, character, copyright, etc.), tag-based searching, and negative tag exclusion.

- **Easy Tag Database Imports:** Import custom tag lists via a simple CSV upload in the admin panel to keep your system current.

- **Albums:** Organize your media into albums, which can hold both media items and other sub-albums for limitless nesting and organization.

- **Media Relations:** Link related media using parent-child relationships. Group image variations, multi-page comics, and more—keeping related content easily accessible.

### AI & Automation

- **AI-Friendly:** Easily view accompanying AI metadata for almost any media generated with SwarmUI, ComfyUI, A1111, and more. You can even append tags to the tag editor directly from the AI prompt.

- **Automatic Tagging:** Fast-track tagging with the WDv3 Auto Tagger integration, which analyzes images and suggests accurate tags with a single click.

### Security & Sharing

- **Secure Mode:** When enabled, users must log in to interact with Blombooru. Public routes such as share links and static files remain public. Perfect for private collections that you don't want anyone else in the house to see!

- **Safe Browsing:** Browse your collection without fear of accidental edits. All management actions (uploading, editing, deleting) require you to be logged in as the admin.

- **Secure Media Sharing:** Generate unique, persistent links to share specific media. Shared items are presented in a stripped-down, secure view with optional sharing of AI metadata.

### Customization & Theming

- **Modern & Responsive UI:** Built with Tailwind CSS for a beautiful and consistent experience on both desktop and mobile devices.

- **Highly Customizable Theming:** Tailor the look and feel using simple CSS variables. Drop new `.css` files into the `themes` folder, register them in `themes.py`, and restart.

- **Many Themes to Choose From:** Blombooru comes with the four Catppuccin color palettes, Gruvbox light & dark, Everforest light & dark, OLED, and more!

### Flexibility & Integration

- **Flexible Media Uploads:** Add media via drag-and-drop, by importing a compressed archive, or by placing files in the storage directory and pressing "Scan for Untracked Media."

- **User-Friendly Onboarding:** A simple first-time setup process to configure your admin account, database connection, and branding.

- **High-Performance Caching:** Optional Redis integration provides lightning-fast response times for heavy queries, autocompletes, and Danbooru-compatible API requests.

- **Danbooru v2 API Compatibility:** Connect to Blombooru using your favorite third-party Booru clients (like Grabber, Tachiyomi, or BooruNav) thanks to a built-in compatibility layer.

## Installation & Setup

You can choose to either use Blombooru in a Docker container *(recommended)* or run it directly with Python.

### Docker *(Recommended)*

This is the recommended method for using Blombooru.

| Prerequisite | Notes |
|:-------------|:------|
| Docker | Required |
| Git | Recommended (alternatively, download the project via the GitHub website) |

1. **Clone the repository**

    ```bash
    git clone https://github.com/mrblomblo/blombooru.git
    cd blombooru
    ```

2. **Customize the environment variables**  
    Create a copy of the `example.env` file and name it `.env`. Then open the newly created file with your favorite text editor and edit the values after the `=` on each row. The most important one to change is the example password assigned to `POSTGRES_PASSWORD`. The others *can* stay as they are, unless, for example, port 8000 is already in use by another program.

3. **First-time run & Onboarding**  
    Start the Docker container (make sure you are in the root Blombooru folder, the one with the `docker-compose.yml` file):

    ```bash
    docker compose up --build -d
    ```

    *You may need to use `sudo` or run the command from a terminal with elevated privileges.*

    Now, open your web browser and navigate to `http://localhost:<port>` (replace `<port>` with the port you specified in the `.env` file). You will be greeted by the onboarding page. Here you will:
    - Set your Admin Username and Password.
    - Enter your PostgreSQL connection details. The server will test the connection before proceeding. Unless you changed `POSTGRES_DB` and/or `POSTGRES_USER`, you only need to fill in the password you set in the `.env` file. Do not change the DB Host.
    - *(Optional)* Enable and configure Redis for caching.
    - Customize the site's Branding Name (defaults to "Blombooru").

    Once submitted, the server will create the database schema and your admin account.

4. **Running the application again**  
    After the initial setup, you can run the server with the following command (again, make sure you are in the root Blombooru folder):
    
    ```bash
    docker compose up -d
    ```

    *You may need to use `sudo` or run the command from a terminal with elevated privileges.*

    All settings are saved to a `settings.json` file in the `data` folder, and all uploaded media is saved to the `media/original` folder. Note that these folders will not be easily accessible and will not be created in the root Blombooru folder.

5. **Shutting down the container**

    ```bash
    docker compose down
    ```

#### Running Multiple Instances

If you need to run multiple independent Blombooru instances (for example, separate libraries for different purposes or users), Docker Compose makes this straightforward. Each instance will have its own isolated database, Redis cache, media storage, and configuration.

**Prerequisites:**
- Completed at least one standard Docker installation (see above)
- Basic familiarity with the command line

**Setup Steps:**

1. **Create separate directories for each instance**  
    Each instance should live in its own folder to keep everything organized and isolated:

    ```bash
    mkdir -p ~/blombooru-instance1
    mkdir -p ~/blombooru-instance2
    cd ~/blombooru-instance1
    ```

2. **Clone or copy Blombooru into each directory**  
    You can either clone the repository fresh into each folder:

    ```bash
    git clone https://github.com/mrblomblo/blombooru.git
    ```

    Or copy an existing installation (faster if you've already cloned it once):

    ```bash
    cp -r /path/to/existing/blombooru/* /path/to/other-blombooru-instance/
    ```

3. **Configure unique ports for each instance**  
    Create a `.env` file in each instance directory (copy from `example.env`) and assign **different port numbers** to avoid conflicts:

    **Instance 1** (`~/blombooru-instance1/.env`):
    ```env
    APP_PORT=8000
    POSTGRES_PORT=5432
    REDIS_PORT=6379
    POSTGRES_PASSWORD=your_secure_password_here
    # ... other settings
    ```

    **Instance 2** (`~/blombooru-instance2/.env`):
    ```env
    APP_PORT=8001
    POSTGRES_PORT=5433
    REDIS_PORT=6380
    POSTGRES_PASSWORD=different_secure_password
    # ... other settings
    ```

> [!IMPORTANT]
> Each instance **must** use unique values for `APP_PORT`, `POSTGRES_PORT`, and `REDIS_PORT`. Using the same ports will cause conflicts and prevent instances from starting.

> [!NOTE] 
> `POSTGRES_PORT` and `REDIS_PORT` are **only** used for mapping ports to your host machine, or for if an external PostgreSQL or Redis server is using different ports. Inside Docker, the containers always communicate using the default internal ports (PostgreSQL: `5432`, Redis: `6379`).

4. **Start each instance independently**  
    Navigate to each instance directory and start it with Docker Compose:

    ```bash
    cd ~/blombooru-instance1
    docker compose up --build -d
    ```

    ```bash
    cd ~/blombooru-instance2
    docker compose up --build -d
    ```

    Docker Compose will automatically name containers using the directory name (e.g., `blombooru-instance1-web-1`, `blombooru-instance2-web-1`), preventing naming conflicts.

5. **Complete onboarding for each instance**  
    Each instance is completely independent, so you'll need to complete the onboarding process separately:
    - Instance 1: `http://localhost:8000`
    - Instance 2: `http://localhost:8001`

> [!WARNING]
> During onboarding, the database and Redis port & host fields will be **auto-filled with incorrect values** from your `.env` file. When using Docker, you **must** manually change these to the default internal ports (also noted in the onboarding form):
> - **PostgreSQL Port:** Always use `5432` (not the `POSTGRES_PORT` value from `.env`)
> - **Redis Port:** Always use `6379` (not the `REDIS_PORT` value from `.env`)
> - **DB Host:** Always use `db` (the Docker service name)
> - **Redis Host:** Always use `redis` (the Docker service name)

**Managing Multiple Instances:**

- **View running instances:**  
    ```bash
    docker ps
    ```

- **Stop a specific instance:**  
    ```bash
    cd ~/blombooru-instance1
    docker compose down
    ```

- **View logs for a specific instance:**  
    ```bash
    cd ~/blombooru-instance1
    docker compose logs -f
    ```

- **Update a specific instance:**  
    Navigate to the instance directory and use the built-in updater via the Admin Panel, or manually:
    ```bash
    cd ~/blombooru-instance1
    git pull
    docker compose down && docker compose up --build -d
    ```

**Data Isolation:**

Each instance maintains completely separate:
- **Databases** – Stored in Docker volumes named after the instance directory (e.g., `blombooru-instance1_pgdata`)
- **Media files** – Stored in separate Docker volumes (e.g., `blombooru-instance1_media`)
- **Configuration** – Each instance has its own `settings.json` in its Docker volume
- **Redis cache** – Separate Redis instances with isolated data

This means you can safely delete, update, or modify one instance without affecting any others.

### Python

> [!NOTE]
> The Python installation is primarily recommended for development purposes, but can be useful if you are able to use Python venvs but not Docker.

| Prerequisite | Notes |
|:-------------|:------|
| Python 3.10+ | Tested with 3.13.7 & 3.11. Does **not** work with 3.14. |
| PostgreSQL 17 | Required |
| Redis 7+ | Optional |
| Git | Recommended (alternatively, download the project via the GitHub website) |

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

4. **Start a Redis instance** *(Optional)*  
    If you wish to use high-performance caching, ensure a Redis server (v7+) is running and accessible. You can install it via your OS package manager (e.g., `apt install redis`, `brew install redis`) or run it in a standalone Docker container.

5. **First-time run & Onboarding**  
    Start the server:

    ```bash
    python run.py
    ```

    Now, open your web browser and navigate to [`http://localhost:8000`](http://localhost:8000). You will be greeted by the onboarding page. Here you will:
    - Set your Admin Username and Password.
    - Enter your PostgreSQL connection details. The server will test the connection before proceeding.
    - *(Optional)* Enable and configure Redis for high-performance caching.
    - Customize the site's Branding Name (defaults to "Blombooru").

    Once submitted, the server will create the database schema and your admin account.

6. **Running the application again**  
    After the initial setup, you can run the server anytime with the same command. All settings are saved to a `settings.json` file in the `data` folder, and all uploaded media is saved to the `media/original` folder.

## Usage Guide

### Logging In

Navigate to the site and click the **Admin Panel** button in the navbar, then log in using the credentials you created during onboarding. Your login status is preserved with a long-lived cookie for convenience.

### Admin Mode

To make any changes, you must log in as the admin. This protects you from accidentally deleting or editing media. While logged in as the admin, you can:

- Upload, edit, or delete media
- Add or remove tags
- Share media
- Perform bulk operations like multi-deleting items from the gallery
- Manage system settings, including branding, security, and optional Redis caching

### Adding Tags

You have two ways to add new tags:

#### 1. CSV Import

Either use something like [this script](https://github.com/DraconicDragon/danbooru-e621-tag-list-processor) by DraconicDragon to scrape your own list, or use one of the pre-scraped lists from [here](https://civitai.com/models/950325/danboorue621-autocomplete-tag-lists-incl-aliases-krita-ai-support) or [here](https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru).

> [!IMPORTANT]
> Ensure your CSV list follows the format specified in the "Import Tags from CSV" section seen below. Currently, only "Danbooru" style CSV lists (generated by the script or found in the linked archives) are fully compatible.

<img width="1920" alt="'Import Tags from CSV' section" src="https://github.com/user-attachments/assets/68be82e9-c734-4967-8c0c-a4a8cab228cf" />

#### 2. Manual Tag Creation
  
Manually enter the tags you want to create. Prefix a tag with, for example, `meta:` to put it in the "meta" category. The other available tag prefixes are noted in the "Add Tags" section.

*Duplicate tags are automatically detected and will not be re-added.*

<img width="1920" alt="'Add Tags' section" src="https://github.com/user-attachments/assets/31263bc7-5d18-44bc-b58d-72018f6f8190" />

### Uploading Media

You have three ways to add new content:

#### 1. Media Files

In the Admin Panel, there is an upload zone where you can simply drag and drop your media files. Alternatively, you can click it to open your file explorer and select media files.

#### 2. Compressed Archives

Upload a `.zip`, `.tar.gz`, or `.tgz` archive containing your media, and Blombooru will extract and process the contents.

#### 3. Filesystem Scan

Move your media files directly into the configured storage directory. Then, navigate to the Admin Panel and click the **Scan for Untracked Media** button. The server will scan the directory, find new files, generate thumbnails, and add them to your library.

*Duplicate media is automatically detected by its hash and will not be re-imported.*

### Tagging & Searching

- **Tag Autocomplete:** When editing an item, start typing in the tag input field. A scrollable list of suggestions will appear based on existing tags.

- **Tag Display:** On a media page, tags are automatically sorted by category (Artist, Character, Copyright, General, Meta) and then alphabetically within each category.

- **Search Syntax:** Blombooru supports a powerful Danbooru-compatible search syntax.

#### Basic Tags

| Syntax | Description |
|:-------|:------------|
| `tag1 tag2` | Find media with both `tag1` AND `tag2` |
| `-tag1` | Exclude media with `tag1` |
| `tag*` | Wildcard search (finds `tag_name`, `tag_stuff`, etc.) |
| `?tag` | Find media with one or zero characters before `tag` |

#### Ranges

Most numeric and date qualifiers support range operators:

| Syntax | Description |
|:-------|:------------|
| `id:100` | Exact match (`x == 100`) |
| `id:100..200` | Between inclusive (`100 <= x <= 200`) |
| `id:>=100` | Greater than or equal (`x >= 100`) |
| `id:>100` | Greater than (`x > 100`) |
| `id:<=100` | Less than or equal (`x <= 100`) |
| `id:<100` | Less than (`x < 100`) |
| `id:1,2,3` | In list (`x` is 1, 2, or 3) |

#### Meta Qualifiers

| Qualifier | Description | Example(s) |
|:----------|:------------|:-----------|
| `id` | Search by internal ID | `id:100..200`, `id:>500` |
| `width`, `height` | Search by image dimensions (pixels) | `width:>=1920`, `height:1080` |
| `filesize` | Search by file size using `kb`, `mb`, `gb`, `b` units. Supports "fuzzy" matching: `filesize:52MB` finds `52.0MB` to `52.99MB`. | `filesize:1mb..5mb`, `filesize:52MB` |
| `date` | Search by upload date (`YYYY-MM-DD`) | `date:2024-01-01` |
| `age` | Search by age relative to now (`s`, `mi`, `h`, `d`, `w`, `mo`, `y`). Note: `<` means "newer than" (less age). | `age:<24h` (less than 1 day old), `age:1w..1mo` |
| `rating` | Filter by rating: `s`/`safe`, `q`/`questionable`, `e`/`explicit`. Supports lists. | `rating:s,q`, `-rating:e` |
| `source` | Search source. Use `none` for missing sources, `http` for web URLs. | `source:none`, `source:http`, `source:twitter` |
| `filetype` | Search by file extension | `filetype:png`, `filetype:gif` |
| `md5` | Search by file hash (exact) | `md5:d34e4c...` |
| `pool`, `album` | Search by album/pool ID or name. `any`/`none` supported. | `album:any`, `pool:favorites`, `pool:5` |
| `parent` | Search by parent ID. `any`/`none` supported. | `parent:none`, `parent:123` |
| `child` | Filter parent posts by children. `any`/`none` supported. | `child:any` (has children), `child:none` |
| `duration` | Search video/gif duration in seconds | `duration:>60` |

> [!NOTE]
> `duration` may not be set on all GIFs.

#### Tag Counts

Filter by the number of tags on a post:

| Qualifier | Description |
|:----------|:------------|
| `tagcount` | Total tags |
| `gentags` | General tags |
| `arttags` | Artist tags |
| `chartags` | Character tags |
| `copytags` | Copyright tags |
| `metatags` | Meta tags |

**Example:** `tagcount:<10` (posts with few tags), `arttags:>=1` (posts with at least 1 artist tag)

#### Sorting

Order results with `order:{value}`. Suffix with `_asc` or `_desc` where applicable (default is usually descending).

| Value | Description |
|:------|:------------|
| `id` / `id_desc` | Newest uploads first (default) |
| `id_asc` | Oldest uploads first |
| `filesize` | Largest files first |
| `landscape` | Widest aspect ratio first |
| `portrait` | Tallest aspect ratio first |
| `md5` | Sort using MD5 hash (deterministic random-like shuffle) |
| `custom` | Sort by the order given in `id:list`. Example: `id:3,1,2 order:custom` |

### Sharing Media

1. Log in as the admin.
2. Navigate to the page of the media you wish to share.
3. Click the **Share** button and a unique share URL (`https://localhost:8000/shared/<uuid>`) will be generated.
4. Anyone with this link can view the media in a simplified, read-only interface. The shared media can optionally include or exclude its accompanying AI metadata. Shared items are marked with a "shared" icon in your private gallery view.

### System Updater

Blombooru includes a built-in system updater in the Admin Panel that allows you to easily update your installation to the latest version.

> [!WARNING]
> Always back up your data before updating! While updates are designed to be safe, unexpected issues can occur, especially if you're updating to a new major version or the latest dev build.

#### How to Update

1. Log in as the admin and navigate to the **Admin Panel**.
2. Scroll to the **System Update** section.
3. Click **Check for Updates** to fetch the latest version information from GitHub.
4. Review the changelog by clicking **View Changelog** to see what's new.
5. If updates are available, click either:
   - **Update to Latest Dev** - Updates to the latest commit on the `main` branch (bleeding edge)
   - **Update to Latest Stable** - Updates to the latest tagged release (recommended)

The updater will automatically run `git pull` (or `git checkout <tag>`) and display the output. After updating, **restart Blombooru** to apply the changes:

- **Docker:** `docker compose down && docker compose up -d`
- **Python:** Stop the server (Ctrl+C) and run `python run.py` again

#### Dependency Changes

If the update includes changes to `requirements.txt` or `docker-compose.yml`, the updater will display a notice. You will need to:

- **Docker:** Run `docker compose down && docker compose up --build -d` to rebuild the container
- **Python:** Stop the server (Ctrl+C) and run `pip install -r requirements.txt` before running `python run.py` again.

### API & Third-Party Apps

Blombooru implements a **Danbooru v2 compatible API**, allowing you to use existing third-party Booru clients (like Grabber, Tachiyomi, or BooruNav) to browse your collection.

#### Connection Details

| Setting | Value |
|:--------|:------|
| **Server Type** | Danbooru v2 |
| **URL** | Your server IP + port (e.g., `http://192.168.1.10:8000`) or your domain (e.g., `https://example.com`) |
| **Authentication** | Supported via multiple methods (see below) |

**Authentication Methods:**
- **Query parameters:** `login` + `api_key`
- **HTTP Basic Auth:** username + API key as password
- **Bearer token:** `Authorization: Bearer <api_key>`

#### Supported Features

| Feature | Description |
|:--------|:------------|
| **Posts** | Full search capability, listing, and media retrieval |
| **Tags** | Tag listing, search, autocomplete, and related tags |
| **Albums/Pools** | Blombooru Albums are exposed as Danbooru "Pools" |
| **Artists** | Blombooru Artist tags are exposed as the Artists endpoint |

> [!NOTE]
> Write operations (uploading, editing, etc.) via the API are read-only or stubbed to prevent errors in third-party apps. Social features such as voting, favoriting, comments, forums, DMs, and wiki pages return empty results.

## Theming

Blombooru is designed to be easily themeable.

- **CSS Variables:** The core colors are controlled by CSS variables defined in the default theme(s).

- **Custom Themes:** To create your own theme, simply create a new `.css` file in the `frontend/static/themes/` directory, copy the entire contents of the `default_dark.css` theme, and start customizing! Then register it in the `backend/app/themes.py` file to use it.

Your new theme will automatically appear in the theme-picker dropdown in the Admin Panel.

## Technical Details

| Component | Technology |
|:----------|:-----------|
| **Backend** | FastAPI (Python) |
| **Frontend** | Tailwind CSS (locally built), Vanilla JavaScript, HTML |
| **Database** | PostgreSQL 17 |
| **Caching** | Redis 7+ (Optional) |
| **Media Storage** | Local filesystem with paths referenced in the database. Original metadata is always preserved but can optionally be stripped on-the-fly in shared media. |
| **Supported Formats** | JPG, PNG, WEBP, GIF, MP4, WEBM |

## Disclaimer

This is a self-hosted, single-user application. As the sole administrator, you are exclusively responsible for all content you upload, manage, and share using this software.

Ensure your use complies with all applicable laws, especially regarding copyright and the privacy of any individuals depicted or identified in your media.

The developers and contributors of this project assume **no liability** for any illegal, infringing, or inappropriate content hosted by any user. The software is provided "as is" without warranty. For the full disclaimer, please see our [Disclaimer of Liability](https://github.com/mrblomblo/blombooru/blob/main/DISCLAIMER.md).

## License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt) file for details.
