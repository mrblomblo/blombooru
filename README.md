<div align="center">

<img width="830" alt="Blombooru Banner" src=".github/images/Blombooru_Banner.webp" />
  
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=fff)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=000)
![FastAPI](https://img.shields.io/badge/FastAPI-009485.svg?style=flat-square&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-%23316192.svg?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-%23DD0031.svg?style=flat-square&logo=redis&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-%2338B2AC.svg?style=flat-square&logo=tailwind-css&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=fff)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/ywpaZh4tHx)


**English** • <a href="./README_RU.md">Русский</a> • <a href="./README_ZH_CN.md">简体中文</a> • <a href="./README_SV.md">Svenska</a>

<b>Your Personal, Self-Hosted Booru.</b>

</div>

Blombooru is a private, single-user alternative to boorus like Danbooru and Gelbooru. It is designed for individuals who want a powerful, easy-to-use, and modern solution for organizing and tagging their personal media collections. With a focus on a clean user experience, robust administration, and easy customization, Blombooru puts you in complete control of your library.

**[View screenshots](docs/Gallery.md)**

## Table of Contents

- [Table of Contents](#table-of-contents)
- [Key Features](#key-features)
  - [Core Functionality](#core-functionality)
  - [AI \& Automation](#ai--automation)
  - [Security \& Sharing](#security--sharing)
  - [Customization \& Theming](#customization--theming)
  - [Flexibility \& Integration](#flexibility--integration)
- [Installation \& Setup](#installation--setup)
  - [Docker *(Recommended)*](#docker-recommended)
    - [Deployment Options](#deployment-options)
    - [Quick Start (Pre-built Image)](#quick-start-pre-built-image)
    - [Hardware Acceleration](#hardware-acceleration)
    - [Using Pre-release Builds](#using-pre-release-builds)
    - [Development Builds (Local)](#development-builds-local)
    - [Running Multiple Instances](#running-multiple-instances)
    - [Sharing Tags Between Instances](#sharing-tags-between-instances)
  - [Python](#python)
- [Usage Guide](#usage-guide)
  - [Logging In](#logging-in)
  - [Admin Mode](#admin-mode)
  - [Adding Tags](#adding-tags)
    - [1. CSV Import](#1-csv-import)
    - [2. Manual Tag Creation](#2-manual-tag-creation)
  - [Uploading Media](#uploading-media)
    - [1. Media Files](#1-media-files)
    - [2. Compressed Archives](#2-compressed-archives)
    - [3. Filesystem Scan](#3-filesystem-scan)
    - [4. External URL Import](#4-external-url-import)
  - [Tagging \& Searching](#tagging--searching)
  - [Sharing Media](#sharing-media)
  - [System Updater](#system-updater)
    - [How to Update](#how-to-update)
    - [Dependency Changes](#dependency-changes)
  - [Account Recovery](#account-recovery)
  - [API \& Third-Party Apps](#api--third-party-apps)
    - [Connection Details](#connection-details)
    - [Supported Features](#supported-features)
    - [Internal API](#internal-api)
- [Theming](#theming)
- [Technical Details](#technical-details)
- [Documentation \& Community](#documentation--community)
- [Disclaimer](#disclaimer)
- [License](#license)

## Key Features

### Core Functionality

- **Danbooru-Style Tagging:** A familiar and powerful tagging system with categories (artist, character, copyright, etc.), tag-based searching, and negative tag exclusion.

- **Tag Gallery & Management:** Browse, search, and manage your tags in a dedicated tag gallery.

- **Easy Tag Database Imports:** Import custom tag lists via a simple CSV upload in the admin panel to keep your system current.

- **Albums:** Organize your media into albums, with support for nested sub-albums, manual sorting, and automatic album hierarchy creation from folder uploads. *Albums are Blombooru's equivalent to "pools" on other boorus!*

- **Media Relations & Similarity:** Link related media using parent-child relationships, or discover similar posts powered by a configurable similarity (TF-IDF) algorithm. Group image variations, multi-page comics, and more (keeping related content easily accessible).

- **Markdown Descriptions:** Add rich, formatted descriptions to posts with full Markdown support.

- **External Booru Import:** Seamlessly import posts from Danbooru and other booru sites (like Danbooru, Gelbooru, etc.) by simply pasting the post URL. Tags, rating, source, and media are all automatically fetched and mapped.

### AI & Automation

- **AI-Friendly:** Easily view accompanying AI metadata for media generated with SwarmUI, ComfyUI, A1111, InvokeAI, NovelAI, Fooocus, and more. You can even append tags to the tag editor directly from the AI prompt or optionally directly to the media uploader during import.

- **Automatic Tagging:** Fast-track tagging with the WDv3 or PixAI Auto Tagger integration, which analyzes images and suggests accurate tags with a single click. Supports optional Nvidia GPU acceleration for lightning-fast batch processing.

- **Sidecar Metadata:** Automatically imports metadata from sidecar files, perfect for those who use external downloaders such as gallery-dl or imgbrd-grabber.

- **Tag Implications:** Define relationships between tags. When a target tag (or set of tags) is applied to a media item, the implied tags are automatically added as well.

- **Tag Aliases:** Define aliases for tags to keep your tag list clean and organized. Using an alias will automatically apply the target tag instead.

- **Automatic Tags by Media Type:** Automatically add pre-configured tags to each upload queue item based on its media type (Image, GIF, or Video).

### Security & Sharing

- **Secure Mode:** When enabled, users must log in to interact with Blombooru. Public routes such as share links and static files remain public. Perfect for private collections that you don't want anyone else in the house to see!

- **Safe Browsing:** Browse your collection without fear of accidental edits. All management actions (uploading, editing, deleting) require you to be logged in as the admin.

- **Secure Media Sharing:** Generate unique, persistent links to share specific media. Shared items are presented in a stripped-down, secure view with optional sharing of AI metadata.

- **Thumbnail Blurring:** Optionally blur explicit thumbnails across gallery and media views for safe browsing.

- **API Key Management:** Generate and manage scoped (read/write/admin-level) API keys for scripts and third-party tools.

### Customization & Theming

- **Modern & Responsive UI:** Built with Tailwind CSS for a beautiful and consistent experience on both desktop and mobile devices.

- **Highly Customizable Theming:** Tailor the look and feel using simple CSS variables. Create, edit, import, and export custom themes directly in the Admin Panel.

- **Many Themes to Choose From:** Blombooru comes with the four Catppuccin color palettes, Gruvbox light & dark, Everforest light & dark, OLED, and more!

- **Customizable Shortcuts:** Fully rebindable keyboard shortcuts with an in-app keybinding editor for quick navigation.

- **Multi-Language Support:** Translated interface available in several languages.

### Flexibility & Integration

- **SOCKS5/HTTP Proxy Support:** Configure a SOCKS5 or HTTP proxy through the Admin Panel to download external media through it. Perfect for accessing region-restricted content or for privacy reasons.

- **Flexible Media Uploads:** Add media via drag-and-drop, compressed archives, filesystem scans, external booru- or direct media URL imports, or batch lists of URLs.

- **On-The-Fly Tag Creation:** If a tag you want to add doesn't exist yet, you can create it on-the-fly directly from any tag input without needing to touch the Admin Panel.

- **Thumbnail Management:** Easily repair broken or missing thumbnails from the Admin Panel. You can generate missing thumbnails or completely re-generate all thumbnails for large libraries.

- **Backup & Restore:** Create full or partial backups (database, media files, and tags) directly from the Admin Panel.

- **User-Friendly Onboarding:** A simple first-time setup process to configure your admin account, database connection, and branding. You can also import a full backup during setup.

- **High-Performance Caching:** Optional Redis integration provides lightning-fast response times for heavy queries, autocompletes, and Danbooru-compatible API requests.

- **Shared Tag Database:** Optionally share tags across multiple Blombooru instances using a centralized PostgreSQL database dedicated to just tags.

- **Danbooru v2 API Compatibility:** Connect to Blombooru using your favorite third-party Booru clients (like Grabber, Tachiyomi, or BooruNav) thanks to a built-in compatibility layer.

## Installation & Setup

You can choose to either use Blombooru in a Docker container *(recommended)* or run it directly with Python.

### Docker *(Recommended)*

This is the recommended method for using Blombooru. Pre-built images are available on GitHub Container Registry.

| Prerequisite | Notes |
|:-------------|:------|
| Docker | Required |

#### Deployment Options

| Option | Image Tag | Use Case |
|:-------|:----------|:---------|
| **Latest Stable** | `latest` (default) | Production use, tracks the latest GitHub release |
| **Latest Stable (CUDA)** | `latest-cuda` | Production use with CUDA acceleration |
| **Pre-release** | `pre` | Testing upcoming versions, tracks the latest GitHub pre-release |
| **Pre-release (CUDA)** | `pre-cuda` | Testing upcoming versions with CUDA acceleration |
| **Pinned Version** | `1.2.3` / `1.2` / `1` | Pinning to a specific stable version |
| **Pinned Pre-release** | `1.2.3-rc.1` | Pinning to a specific pre-release |
| **Development** | Local build | Contributing, modifying source code |

#### Quick Start (Pre-built Image)

1. **Download the required files**

    Create a folder for Blombooru (e.g., `blombooru`), then download the `docker-compose.yml` and `example.env` files from the [latest release](https://github.com/mrblomblo/blombooru/releases/latest) and place them inside it. (Optionally, if you plan to use GPU acceleration, also download hwaccel.yml).

2. **Customize the environment variables**  
    Create a copy of the `example.env` file and name it `.env`. Then open the newly created file with your favorite text editor and edit the values after the `=` on each row. The most important one to change is the example password assigned to `POSTGRES_PASSWORD`. The others *can* stay as they are, unless, for example, port 8000 is already in use by another program.

3. **First-time run & Onboarding**  
    Start the Docker container (make sure you are inside the folder where you placed the `docker-compose.yml` file):

    ```bash
    docker compose up -d
    ```

    *You may need to use `sudo` or run the command from a terminal with elevated privileges.*

    Now, open your web browser and navigate to `http://localhost:<port>` (replace `<port>` with the port you specified in the `.env` file). You will be greeted by the onboarding page. Here you will:
    - Set your Admin Username and Password.
    - Enter your PostgreSQL connection details. The server will test the connection before proceeding. Unless you changed `POSTGRES_DB` and/or `POSTGRES_USER`, you only need to fill in the password you set in the `.env` file. Do not change the DB Host.
    - *(Optional)* Enable and configure Redis for caching.
    - Customize the site's Branding Name (defaults to "Blombooru").

    Once submitted, the server will create the database schema and your admin account.

4. **Running the application again**  
    After the initial setup, you can run the server with the following command (again, make sure you are inside the folder with the `docker-compose.yml` file):
    
    ```bash
    docker compose up -d
    ```

    *You may need to use `sudo` or run the command from a terminal with elevated privileges.*

    All settings are saved to a `settings.json` file in the `data` folder, and all uploaded media is saved to the `media/original` folder. Note that these folders will not be easily accessible and will not be created in the root Blombooru folder.

5. **Shutting down the container**

    ```bash
    docker compose down
    ```

#### Hardware Acceleration

If you have an Nvidia GPU and want to significantly speed up the WDv3 Auto Tagger, you can use the CUDA-accelerated Docker image. 

> [!IMPORTANT]
> You must have the Nvidia Container Toolkit installed on your host machine, and your GPU drivers must be up to date. It is also assumed that you are using a somewhat recent GPU.

Setup:

1. **Download the hwaccel.yml file**  
    Download the `hwaccel.yml` file from the latest release and place it in the same folder as your `docker-compose.yml` and `.env` files.

2. **Edit docker-compose.yml**  
    Open your `docker-compose.yml` file, find the web service, and uncomment (remove the three `#` symbols from the beginning of) the `extends:` block:

    ```yaml
    services:
      web:
        image: ghcr.io/mrblomblo/blombooru:${BLOMBOORU_TAG:-latest}
        extends:
          file: hwaccel.yml
          service: cuda
    ```

3. **Configure the environment variable**  
    In your `.env` file, ensure the tagger device is set to `auto` (default) or `cuda`:

    ```env
    BLOMBOORU_WD_TAGGER_DEVICE=auto # Options: auto, cuda, cpu
    ```

4. **Start the container**  
    Pull the new CUDA image and start the container:

    ```bash
    docker compose up -d
    ```

> [!WARNING]
> If you are using the latest-cuda image, you must uncomment the `extends:` block in your `docker-compose.yml`. If you use the CUDA image but do not pass the GPU to the container, Blombooru will crash when it attempts to load the AI model.

The `BLOMBOORU_WD_TAGGER_DEVICE` environment variable controls how the tagger initializes:

- `auto` (default): Uses the GPU if the `onnxruntime-gpu` package is installed, otherwise uses the CPU.
- `cuda`: Strictly enforces GPU usage. If the package is not installed, Blombooru will throw an error and refuse to start.
- `cpu`: Forces CPU usage, even if a GPU is available.

#### Using Pre-release Builds

To use the latest pre-release version, set the `BLOMBOORU_TAG` environment variable:

```bash
BLOMBOORU_TAG=pre docker compose up -d
```

Or add `BLOMBOORU_TAG=pre` to your `.env` file.

> [!WARNING]
> Pre-release builds may contain breaking changes or bugs. Use for testing upcoming versions only.

#### Development Builds (Local)

For contributors or those who want to build from source:

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

This uses `docker-compose.dev.yml` which builds the image locally from your source code.

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

2. **Setup the files for each instance**  
    Copy the `docker-compose.yml` and `example.env` files into each directory:

    ```bash
    # Only an example, replace with the actual path to the files
    cp ~/blombooru/docker-compose.yml ~/blombooru/example.env ~/blombooru-instance1/
    cp ~/blombooru/docker-compose.yml ~/blombooru/example.env ~/blombooru-instance2/
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
    Navigate to the instance directory and update via Docker Compose:

    ```bash
    cd ~/blombooru-instance1
    docker compose up -d --pull always
    ```

**Data Isolation:**

Each instance maintains completely separate:
- **Databases** – Stored in Docker volumes named after the instance directory (e.g., `blombooru-instance1_pgdata`)
- **Media files** – Stored in separate Docker volumes (e.g., `blombooru-instance1_media`)
- **Configuration** – Each instance has its own `settings.json` in its Docker volume
- **Redis cache** – Separate Redis instances with isolated data

This means you can safely delete, update, or modify one instance without affecting any others.

#### Sharing Tags Between Instances

If you want multiple Blombooru instances to share the same tag database (so tags created in one instance are available in others), you can enable the optional **Shared Tag Database** feature by downloading the `docker-compose.shared-tags.yml` file from the [latest release](https://github.com/mrblomblo/blombooru/releases/latest), placing it in the same directory as one of your `docker-compose.yml` files, and following these steps (alternatively, you can skip steps 1 and 2 and use an existing PostgreSQL database if you have one):

1. **Edit the .env file of the instance that will host the shared tag database:**
   - Adjust the following lines in the instance's `.env` file:

   ```env
   SHARED_TAGS_ENABLED=false # Set to true to enable the shared tag database
   SHARED_TAG_DB_USER=postgres
   SHARED_TAG_DB_PASSWORD=supersecretsharedtagdbpassword # Change this to a secure password
   SHARED_TAG_DB=shared_tags
   SHARED_TAG_DB_HOST=shared-tag-db
   SHARED_TAG_DB_PORT=5431 # Change this to a different port if needed
   ```

2. **Start the shared tag database container:**
   ```bash
   docker compose -f docker-compose.shared-tags.yml up -d
   ```

3. **Configure each Blombooru instance:**
   - Go to **Admin Panel > Settings**
   - Enable "Shared Tag Database"
   - Enter the connection details
   - Click "Test Connection" to verify, then save

4. **Sync tags:**
   - Use the "Sync Now" button to manually sync tags between instances
   - New tags are automatically shared when created

> [!NOTE]
> Local tags always take precedence. If a tag exists locally with a different category than the shared database, your local category is kept.
> **Tags are never deleted from your local database, only new tags are imported.**

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

> [!NOTE]
> If you plan to use an Nvidia GPU for AI tagging, install the CUDA requirements file instead (`requirements-cuda.txt`). You will also need the appropriate Nvidia drivers and CUDA toolkit installed on your host system.

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
- Add, edit, or remove tags, aliases, and implications
- Organize and manually reorder albums
- Share media
- Perform bulk operations like multi-tagging, rating adjustments, and multi-deleting items from the gallery
- Manage system settings, including branding, themes, security, backups, external booru credentials, and optional Redis caching

### Adding Tags

You have two ways to add new tags:

#### 1. CSV Import

Either use something like [this script](https://github.com/DraconicDragon/danbooru-e621-tag-list-processor) by DraconicDragon to scrape your own list, or use the latest pre-scraped list from [here](https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru).

> [!IMPORTANT]
> Ensure your CSV list follows the format specified in the "Import Tags from CSV" section seen below. Currently, only "Danbooru" style CSV lists (generated by the script or found in the linked archives) are fully compatible.

<img width="1920" alt="'Import Tags from CSV' section" src="https://github.com/user-attachments/assets/68be82e9-c734-4967-8c0c-a4a8cab228cf" />

#### 2. Manual Tag Creation
  
Manually enter the tags you want to create. Prefix a tag with, for example, `meta:` to put it in the "meta" category. The other available tag prefixes are noted in the "Add Tags" section.

*Duplicate tags are automatically detected and will not be re-added.*

<img width="1920" alt="'Add Tags' section" src="https://github.com/user-attachments/assets/31263bc7-5d18-44bc-b58d-72018f6f8190" />

### Uploading Media

You have four ways to add new content:

#### 1. Media Files

In the Admin Panel, there is an upload zone where you can simply drag and drop your media files. Alternatively, you can click it to open your file explorer and select media files.

#### 2. Compressed Archives

Upload a `.zip`, `.tar.gz`, or `.tgz` archive containing your media, and Blombooru will extract and process the contents.

#### 3. Filesystem Scan

Move your media files directly into the configured storage directory. Then, navigate to the Admin Panel and click the **Scan for Untracked Media** button. The server will scan the `media/original` dir (notice that it's not an easily accessible directory), find new files, generate thumbnails, and add them to your library.
 
*Duplicate media is automatically detected by its hash and will not be re-imported.*

#### 4. External URL Import

Paste a URL from a supported booru site (e.g., those using the Danbooru or Gelbooru API) into the import tool. Blombooru will fetch the metadata (tags, rating, source) and download the highest-quality version of the media available, optionally automagically creating missing tags with the correct category (if available).

> [!NOTE]
> Some boorus may require an API key or login credentials to use the API or to access certain posts. You can configure these in the Booru Configuration section in the System tab of the Admin Panel.

### Tagging & Searching

- **Tag Autocomplete:** When editing an item, start typing in the tag input field. A scrollable list of suggestions will appear based on existing tags.

- **Tag Display:** On a media page, tags are automatically sorted by category (Artist, Character, Copyright, General, Meta) and then alphabetically within each category.

- **Search Syntax:** Blombooru supports a powerful Danbooru-compatible search syntax. For a complete guide covering all operators and qualifiers, see the [Search Syntax Guide](docs/Search%20Syntax%20Guide/syntax_guide-en.md).

### Sharing Media

1. Log in as the admin.
2. Navigate to the page of the media you wish to share.
3. Click the **Share** button and a unique share URL (`https://localhost:8000/shared/<uuid>`) will be generated.
4. Anyone with this link can view the media in a simplified, read-only interface. The shared media can optionally include or exclude its accompanying AI metadata. Shared items are marked with a "shared" icon in your private gallery view.

### System Updater

Blombooru includes a built-in system updater in the Admin Panel that allows you to easily update your installation to the latest version.

> [!WARNING]
> Always back up your data before updating! While updates are designed to be safe, unexpected issues could occur, especially if you're updating to a pre-release or the dev version.

#### How to Update

> [!NOTE]
> In-app updating is only supported for direct Python installations. For Docker deployments, update directly:
> - **Pre-built image (GHCR):** `docker compose up -d --pull always`
> - **Locally built image:** `docker compose down && git pull && docker compose -f docker-compose.dev.yml up -d --build`

1. Log in as the admin and navigate to the **Admin Panel**.
2. Select the **System** tab.
3. Scroll to the **System Update** section.
4. Click **Check for Updates** to fetch the latest version information from GitHub.
5. Review the changelog by clicking **View Changelog** to see what's new.
6. If an update is available, click **Update to Latest Stable** to begin the update.

The updater will automatically fetch the latest release tag and check it out. After updating, **restart Blombooru** to apply the changes.

#### Dependency Changes

For direct Python installations, the updater automatically installs updated dependencies if `requirements.txt` has changed. If the automatic installation fails, manually run `pip install -r requirements.txt` in your virtual environment.

If configuration files (such as `docker-compose.yml` or `example.env`) have changed, the updater will display a notice with download links to updated release assets.

### Account Recovery

> [!WARNING]
> Resetting the password does not invalidate existing login sessions (tokens remain valid until they expire, up to 30 days). If you suspect the account was compromised, also consider rotating your `SECRET_KEY` (stored in `data/settings.json` or configured via `BLOMBOORU_SECRET_KEY`) and restarting your instance, which will immediately invalidate all active sessions.

If you've forgotten your admin password or need to change the admin username, you can use the `pass_reset.py` script.

At least one of `--reset-password`, `--password`, or `--username` must be provided.

**Reset password interactively (recommended):**

Prompts securely for password input and confirmation without exposing it in shell history or process tables:

```bash
docker compose exec -it web python pass_reset.py --reset-password
```

**Reset password non-interactively:**

```bash
docker compose exec web python pass_reset.py --password "mynewpassword"
```

**Reset username only:**

```bash
docker compose exec web python pass_reset.py --username "newadmin"
```

**Reset both at once:**

```bash
docker compose exec -it web python pass_reset.py --username "newadmin" --reset-password
```

The same validation rules as the web UI apply:

| Field | Min Length | Max Length |
|:------|:-----------|:-----------|
| Password | 6 | 50 |
| Username | 1 | 50 |

> [!NOTE]
> If you are running Blombooru with bare-metal Python, omit `docker compose exec web` (or `docker compose exec -it web`) from the commands above, and use the virtual environment to run the script instead.

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

#### Internal API

Blombooru also provides an internal REST API for administrative tasks, content management, and custom automations. For details on available endpoints and authentication, see the [Internal API Documentation](docs/Internal%20API/Introduction.md). Note that the internal API has no stability guarantees and may change between releases, and that the API docs are only available in English.

## Theming

Blombooru is designed to be easily themeable.

- **Theme Management:** Custom themes can be created, edited, exported, and imported directly in the Admin Panel without restarting the server.

- **CSS Variables:** The core colors are controlled by CSS variables defined in each theme.

## Technical Details

| Component | Technology |
|:----------|:-----------|
| **Backend** | FastAPI (Python) |
| **Frontend** | Tailwind CSS (locally built), Vanilla JavaScript, HTML |
| **Database** | PostgreSQL 17 |
| **Caching** | Redis 7+ (Optional) |
| **Shared Tags** | Optional external PostgreSQL instance for sharing tags between instances |
| **Media Storage** | Local filesystem with paths referenced in the database. Original metadata is always preserved but can optionally be stripped on-the-fly in shared media. |
| **Supported Image Formats** | JPG, PNG, WEBP, GIF, AVIF, JXL, BMP, TIFF, HEIC/HEIF |
| **Supported Video Formats** | MP4, WEBM, MOV, M4V, MKV, AVI |

## Documentation & Community

- [Search Syntax Guide](docs/Search%20Syntax%20Guide/syntax_guide-en.md): Full syntax reference with query examples.
- [Internal API Documentation](docs/Internal%20API/Introduction.md): Endpoints for developers and automation scripts.
- [Screenshots Gallery](docs/Gallery.md): Visual overview of the user interface and features.
- [Changelog](CHANGELOG.md): Summary of the release notes for each version.
- [Contributing](CONTRIBUTING.md): Guidelines for code and translation contributions.
- [Security Policy](SECURITY.md): Vulnerability reporting and security information.
- [Acknowledgements](ACKNOWLEDGEMENTS.md): Credits for third-party libraries and assets.

## Disclaimer

This is a self-hosted, single-user application. As the sole administrator, you are exclusively responsible for all content you upload, manage, and share using this software.

Ensure your use complies with all applicable laws, especially regarding copyright and the privacy of any individuals depicted or identified in your media.

The developers and contributors of this project assume **no liability** for any illegal, infringing, or inappropriate content hosted by any user. The software is provided "as is" without warranty. For the full disclaimer, please see our [Disclaimer of Liability](https://github.com/mrblomblo/blombooru/blob/main/DISCLAIMER.md).

## License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt) file for details.
