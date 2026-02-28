# Contributing
Want to help make Blombooru better? Awesome, PRs are welcome (even if I have little experience with PRs and such)!

Before you start, please make sure to read through this document so you know how things work around here.

## Getting Started

### Setting Up for Development

1. **Clone the repository**

    ```bash
    git clone https://github.com/mrblomblo/blombooru.git
    cd blombooru
    ```

2. **Set up your environment**

    I would strongly recommend using a local Python setup for development. It allows changes to apply immediately without having to rebuild a container. Follow the [Python installation instructions](https://github.com/mrblomblo/blombooru#python) in the README to get your dependencies installed.
    
    Once set up, run the server in debug mode:
    ```bash
    # Linux / macOS
    ./venv/bin/python run.py --debug
    
    # Windows (Command Prompt)
    .\venv\Scripts\python.exe run.py --debug
    ```
    
    Docker is the quickest way to get everything running if you only want to use the app, but for development, I would recommend only using it if you are working on something strictly Docker-related:
    ```bash
    cp example.env .env
    # Edit .env with your preferred settings (at least change the passwords)
    docker compose -f docker-compose.dev.yml up --build -d
    ```

3. **Complete the onboarding**

    Open `http://localhost:8000` (or whatever port you configured) and go through the first-time setup.

### Project Structure

Here's a brief overview of how the project is organized:

| Directory | Description |
|:----------|:------------|
| `backend/app/` | FastAPI backend - routes, models, services, and utilities |
| `backend/app/routes/` | API route handlers |
| `backend/app/services/` | Business logic and service layer |
| `backend/app/utils/` | Shared utilities |
| `frontend/templates/` | Jinja2 HTML templates |
| `frontend/static/` | Static assets (CSS, JS, images) |
| `frontend/static/css/themes/` | Theme CSS files |
| `data/` | Runtime data (settings, etc.) - not committed to Git |
| `media/` | Uploaded media, thumbnails for uploaded media, and cached metadata-stripped shared media - not committed to Git |

## Code Contributions

### General Guidelines

- **Keep it focused.** A PR should address one thing. If you're fixing a bug *and* adding a feature, please make separate PRs.
- **Test your changes.** Before submitting, make sure Blombooru still starts up and works as expected. Try to cover the areas your changes touch. For example, if you changed how uploads work, test uploading; if you changed the search, test searching; and so on. Be thorough!
- **Don't break existing functionality.** If your changes modify existing behavior, explain *why* in the PR description.
- **Follow the existing code style.** Look at the surrounding code and match the patterns you see. No need to over-engineer things.

### Backend Changes

The backend is a [FastAPI](https://fastapi.tiangolo.com/) application written in Python. Routes live in `backend/app/routes/`, models in `backend/app/models.py`, and business logic in `backend/app/services/`.

> [!TIP]
> If you're using Docker for development, rebuild the container after making backend changes:
> ```bash
> docker compose -f docker-compose.dev.yml up --build -d
> ```
> If you're running with Python directly, just reload the page. The server will automatically restart as soon as you save your changes.

### Frontend Changes

The frontend uses vanilla JavaScript, Jinja2 templates, and [Tailwind CSS](https://tailwindcss.com/). Stylesheets are built using a local Tailwind setup (see the `tailwind/` directory).

> [!NOTE]
> If you're making changes to Jinja templates or frontend JS that involve Tailwind classes, you may need to rebuild the CSS.
>
> 1. Download the standalone Tailwind CLI (v4.2.1) from [their releases page](https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.2.1) (e.g., `tailwindcss-linux-x64` or `tailwindcss-windows-x64.exe`).
> 2. Move the downloaded executable into the `tailwind/` directory.
> 3. If you're on Linux or macOS, make it executable: `chmod +x <filename>` (e.g. `chmod +x tailwindcss-linux-x64`).
> 4. Run the executable to build the CSS:
>    ```bash
>    cd tailwind
>    
>    # Linux / macOS
>    ./<filename> -i input.css -o ../frontend/static/css/tailwind.css --minify
>    
>    # Windows
>    .\<filename>.exe -i input.css -o ..\frontend\static\css\tailwind.css --minify
>    ```

### Database Migrations

Blombooru uses a simple DIY migration system located in `backend/app/database.py`. If your changes require database schema modifications (like adding a new table column), you should write a migration function (e.g., `migrate_add_your_new_column`) that checks if the column exists and adds it if it doesn't. Then, add your function to the `migrations` list inside `check_and_migrate_schema`.   
Be mindful that existing users will need a way to upgrade without losing data (Don't just remove a column or table without migrating that data first)!

## Themes

Want to add a new color scheme? Here's how.

> [!NOTE]
> When contributing a theme, try to use color palettes that have permissive licenses (like MIT). If the palette comes from an existing project, include a link to the source in your PR. Check existing themes in Blombooru for examples of how licenses are handled, such as the Catppuccin or Gruvbox themes.

### Creating a New Theme

1. **Create a new CSS file** in `frontend/static/css/themes/`. Name it something descriptive and use snake_case (e.g. `tokyo_night.css`).

2. **Use the default theme as a template.** Copy the contents of `default_dark.css` and swap the colors:

    ```css
    :root {
        --primary-color: ;
        --primary-hover: ;
        --background: ;
        --surface: ;
        --surface-hover: ;
        --surface-light: ;
        --surface-light-hover: ;
        --text: ;
        --text-secondary: ;
        --text-tertiary: ;
        --tag-text: ;
        --primary-text: ;
        --border: ;

        --white: ;
        --black: ;
        --green: ;
        --orange: ;
        --red: ;
        --blue: ;

        --tag-artist: ;
        --tag-character: ;
        --tag-copyright: ;
        --tag-general: ;
        --tag-meta: ;
    }
    ```

    > [!IMPORTANT]
    > To keep tag colors consistent across themes, make artist tags red, character tags green, copyright tags purple, general tags blue, and meta tags orange.

3. **Register the theme** in `backend/app/themes.py`. Add a new `self.register_theme(Theme(...))` call inside the `_register_default_themes` method. You'll need to fill in:

    - `id` - A unique identifier in snake_case. This should be an exact match of your CSS filename (without the `.css` extension).
    - `name` - The user-facing display name.
    - `css_path` - Should be `/static/css/themes/<your_filename>.css`.
    - `is_dark` - `True` for dark themes, `False` for light themes.
    - `primary_color` - The hex value of your theme's primary/accent color (same as `--primary-color`).
    - `background_color` - The hex value of your theme's background color (same as `--background`).

4. **Test it!** Select your theme from the theme picker in the Admin Panel and make sure things look right. Check at least the homepage, a media page, and the admin panel.

When creating your PR, please include at least one screenshot. The homepage is a good choice since it showcases many different elements.

### Updating an Existing Theme

Edit the theme's CSS file directly. Do **not** change any theme `id` values in `themes.py`, as that would force users to re-select their theme.

When submitting the PR, explain *why* you made the changes and include before/after screenshots.

If you're modifying the CSS variable structure (adding or removing a variable), update all other themes accordingly (for easier maintenance in the future).

## Reporting Bugs & Requesting Features

Please use the [issue tracker](https://github.com/mrblomblo/blombooru/issues) on GitHub. Blank issue creation is disabled, so please select the most appropriate template for your issue. There are templates for [bug reports](https://github.com/mrblomblo/blombooru/issues/new?template=bug_report.yml), [feature requests](https://github.com/mrblomblo/blombooru/issues/new?template=feature_request.yml), and a general "Other" template if your issue doesn't fit either of those. These templates help keep things organized!

Before opening a new issue, search the existing issues to make sure it hasn't already been reported or requested.

## License

By contributing to Blombooru, you agree that your contributions will be licensed under the [MIT License](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt).
