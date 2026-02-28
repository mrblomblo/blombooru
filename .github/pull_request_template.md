## What does this PR do?
A clear description of what this PR changes or adds.  


## Type of change
Only one of the following should be checked, though it is encouraged to update the documentation if your PR adds a new feature or changes existing behavior. **Basically, check whichever box that is the main focus of your PR.**

- [ ] Bug fix
- [ ] New feature
- [ ] Theme (new or updated)
- [ ] Translation (new or updated)
- [ ] Documentation
- [ ] Other (describe below)

If you checked "Other", please describe the type of change in the blockquote below:  

> <!-- Describe the type of change here -->

## Checklist
> [!IMPORTANT]
> Go through these before submitting. This is mandatory.

- [ ] I have read the [Contributing Guidelines](https://github.com/mrblomblo/blombooru/blob/main/CONTRIBUTING.md).
- [ ] I have tested my changes and confirmed that Blombooru starts up and works as expected.
- [ ] My PR addresses one thing only (e.g., "Fixes #40", "Adds #41", not "Fixes #40 and adds #41").
- [ ] I have not broken any existing functionality (or I have explained why the change was necessary below).

### If this is a theme PR (skip if it isn't):
- [ ] I have included at least one screenshot (preferably of the homepage).
- [ ] Tag colors follow the standard (artist = red, character = green, copyright = purple, general = blue, meta = orange).
- [ ] The color palette has a permissive license, and I have included a link to the source.
- [ ] I have **not** changed any existing theme `id` values in `themes.py`.

### If this is a translation PR (skip if it isn't):
- [ ] I have used `en.json` as the source and translated only the values, not the keys.
- [ ] My locale file contains every key present in `en.json` (no missing or new keys).
- [ ] All placeholders (e.g. `{count}`, `{name}`) are preserved exactly as they appear in the English original.
- [ ] I have registered the locale following the pattern of existing entries (new locales only).
- [ ] I have switched the UI to my locale and confirmed that it looks correct.
- [ ] I have noted my fluency level, as well as if AI or machine translation was used, in the "Additional context" section below.

### If you added strings that will be displayed in the frontend (skip if you didn't):
- [ ] I have added them as keys in `en.json` (console or CLI errors/messages should not be added, those are not displayed in the UI).
- [ ] I have added the **same** keys to *all* other locale files with empty strings as values (e.g., `"new_key": ""`).

### If this involves database schema changes (skip if it doesn't):
- [ ] I have written a migration function in `backend/app/database.py` and added it to the `migrations` list.
- [ ] Existing data is preserved (no columns/tables removed without migrating data first).

## Screenshots
If applicable, add screenshots here. Required for theme PRs and UI changes. For theme updates, include before/after screenshots.  


## Additional context
Any extra information that might be helpful for reviewing this PR. If your changes modify existing behavior, explain why.  

