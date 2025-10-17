# Blombooru

**Your Personal, Self-Hosted Media Tagging Tool.**

Blombooru is a single-user, private alternative to image boorus like Danbooru and Gelbooru.  
It is designed for individuals who want a powerful, local, simple to use, and modern solution for organizing and tagging their personal media collections. With a focus on a clean user experience, robust administration, and easy customization, Blombooru puts you in complete control of your library.

## Key Features

- **Danbooru-Style Tagging:** A familiar and powerful tagging system with categories (artist, character, copyright, etc.), tag-based searching, and negative tag exclusion.

- **Easy Tag Database Imports:** You can easily import custom tag lists via a simple CSV upload in the admin panel to keep your system current.

- **Modern & Responsive UI:** Built with Tailwind CSS for a beautiful and consistent experience on both desktop and mobile devices.

- **Dedicated Admin Mode:** Safely browse your collection without fear of accidental edits. All management actions (uploading, editing, deleting) require you to be in the explicit "Admin Mode".

- **Highly Customizable Theming:** Tailor the look and feel using simple CSS variables. Drop new `.css` files into the `themes` folder, register the themes in `themes.py`, and restart.

- **Secure Media Sharing:** Generate unique, persistent links to share specific media. Shared items are presented in a stripped-down, secure view with optional sharing of AI metadata.

- **Flexible Media Uploads:** Add media via drag-and-drop, by importing a compressed archive, or by simply placing files in the storage directory and pressing the "Scan for Untracked Media" button.

- **User-Friendly Onboarding:** A simple first-time setup process to configure your admin account, database connection, and branding.

<img width="4388" height="2242" alt="image" src="https://github.com/user-attachments/assets/adfde7fc-9bae-4155-b72d-f00d685f7769" />

*I am logged in as the admin in the above image, hence the checkbox in the top left corner of all media thumbnails*

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

**Prerequisites**  
- Python 3.10+ *(I am using Python 3.13.7)*
- PostgreSQL 17

> [!NOTE]
> The python install  is mostly just recommended for development purposes.

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

### Uploading Media

You have three ways to add new content:

- **Media Files:** In the Admin Panel, there is an upload zone, where you can simply drag & drop your media files into. Alternatively, you can click it and your file explorer will open, allowing you to select media files.

- **Compressed Archives:** Upload a `.zip`, `.tar.gz`, or `.tgz` archive containing your media and Blombooru will extract & process the contents.

- **Filesystem Scan:** Move your media files directly into the configured storage directory. Then, navigate to the Admin Panel and click the "Scan for Untracked Media" button. The server will scan the directory, find new files, generate thumbnails, and add them to your library.

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

- **Custom Themes:** To create your own theme, simply create a new `.css` file in the `frontend/static/themes/` directory, copy the entire contents of the `default_dark.css` theme, and start customizing! To actually use the theme, you need to register it in the `backend/app/themes.py` file.

Your new theme will automatically appear in the theme-picker dropdown in the Admin Panel.

## Technical Details

- **Backend:** FastAPI (Python)
- **Frontend:** Tailwind CSS (locally built), Vanilla JavaScript, and HTML
- **Database:** PostgreSQL 17
- **Media Storage:** Files are stored on the local filesystem, with paths referenced in the database. Original metadata is always preserved.
- **Supported Formats:** JPG, PNG, WEBP, GIF, MP4, and WEBM.

## License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt) file for details.
