# Sidecar Metadata

> [!NOTE]
> Last updated: `November 19, 2026`

Blombooru can automatically extract tags (with categories), content ratings, source URLs, descriptions, creation dates, and suggested album names from accompanying sidecar files during media import.

---

## Naming, Placement, and Usage

### Naming & Placement

Sidecar files must use the `.xmp` or `.json` extension (case-insensitive) and be placed in the **same directory** as their corresponding media file.

For a media file named `<filename>.<ext>` (for example, `artwork.png`), Blombooru looks for a sidecar matching either of the following patterns, in order of priority:

1. **Full filename with extension:** `<filename>.<ext>.xmp` or `<filename>.<ext>.json` (e.g., `artwork.png.xmp` or `artwork.png.json`)
2. **Filename stem without media extension:** `<filename>.xmp` or `<filename>.json` (e.g., `artwork.xmp` or `artwork.json`)

If both exist in the same folder, the full filename match (`artwork.png.json`) takes precedence over the stem match (`artwork.json`).

### How to Use

Sidecar files are paired automatically across all file-based upload workflows:

- **Direct Upload (File Picker or Drag-and-Drop):** Select or drag your sidecar files into the upload zone together with the media files, or drop an entire folder containing both.
- **Compressed Archives:** Place sidecar files in the same folder within a `.zip`, `.tar.gz`, `.tgz`, or `.tar` archive as their corresponding media files before uploading the archive.
- **Filesystem Scan:** Place sidecar files alongside untracked media files inside `media/original`, then click **Scan for Untracked Media** in the Admin Panel.
- **Internal API:** Pass the sidecar file in the optional `sidecar` form field when staging a file via `POST /api/uploads/sessions/{session_id}/files`.

> [!NOTE]
> By default, metadata parsers are evaluated in the priority order `GalleryDlParser`, `LoliSnatcherParser`, `ExifXmpParser`. If an upload item is not placed inside a subfolder (or folder-to-album mapping is disabled), the first pool or gallery name found in the sidecar is proposed as the item's target album.

### Normalized Values

All sidecar parsers normalize extracted fields into Blombooru's internal types:

| Field | Accepted Sidecar Values | Normalized Result |
|---|---|---|
| **Rating** | `"g"`, `"s"`, `"general"`, `"safe"`, `"sensitive"`, `0`, `1`, `2` | `"safe"` |
| | `"q"`, `"questionable"`, `3` | `"questionable"` |
| | `"e"`, `"explicit"`, `4`, `5` | `"explicit"` |
| **Tag Categories** | `"general"`, `"artist"`, `"character"`, `"copyright"`, `"meta"` | Unrecognized, empty, or `"none"` values fall back to `"general"` |
| **Date** | ISO 8601 (`2024-05-18T10:14:22Z`), `YYYY-MM-DD HH:MM:SS`, EXIF (`YYYY:MM:DD HH:MM:SS`), compact (`YYYYMMDD`, `YYYYMMDDhhmmss`), or Unix epoch seconds / milliseconds | UTC timestamp (must be later than `1970-01-01T00:00:00Z` and not more than 24 hours in the future) |

---

## XML / XMP

XMP sidecar files are handled by `ExifXmpParser`, which supports output from tools such as **imgbrd-grabber**, **ExifTool**, and Adobe XMP editors. If an image file has both an `.xmp` sidecar and embedded EXIF/XMP/PNG metadata, the `.xmp` sidecar takes precedence for every field it defines, while embedded metadata fills in any remaining fields.

### Recognized XML Elements and Attributes

XML tags and attributes are matched case-insensitively by their local name (ignoring namespace prefixes). Values can be stored as `<rdf:Bag>`, `<rdf:Seq>`, or `<rdf:Alt>` lists containing `<rdf:li>` elements, as direct element text, or as attributes on `<rdf:Description>`. The `<x:xmpmeta>` and `<rdf:RDF>` wrapper elements are optional: bare element snippets (including partial snippets with only a single element) are automatically wrapped with standard XMP/RDF namespace declarations (`x`, `rdf`, `dc`, `xmp`, `pdf`, `photoshop`, `xmpMM`) when parsed.

| Target Field | Recognized Local Element / Attribute Names |
|---|---|
| **General Tags** | `subject`, `tags`, `keywords`, `lastkeyw`, `hierarchicalsubject`, `cataloguesets` |
| **Artist Tags** | `creator`, `author`, `artist`, `byline`, `photographer` |
| **Character Tags** | `character`, `characters`, `personinimage`, `persons` |
| **Copyright Tags** | `copyright`, `series` |
| **Rating** | `rating`, `urgency` |
| **Source** | `source`, `url`, `identifier`, `webstatement` |
| **Description** | `description`, `comment`, `usercomment`, `caption`, `imagedescription` |
| **Date** | `createdate`, `datecreated`, `datetimeoriginal`, `earliestdate` |

> [!NOTE]
> When a tag element or attribute contains a single string with multiple tags, it is split using the first matching delimiter in the order: semicolon (`;`), newline (`\n`), comma (`,`), or whitespace. Internal spaces within individual tags are normalized to underscores (`_`). If a tag appears in both a general tag list and a specific category field (such as `dc:creator`), it is assigned the specific category.

Standard XMP and Dublin Core schemas do not define an equivalent field for booru-style meta tags (such as `highres`), and adding a custom field carries a high risk of conflicting with existing real XMP fields (especially since `ExifXmpParser` matches local element and attribute names regardless of namespace). Because of this, `ExifXmpParser` only maps XMP elements and attributes to `general`, `artist`, `character`, and `copyright`. Any meta tags placed in general fields such as `dc:subject` or `pdf:Keywords` are parsed as `general` (unless the tag already exists in Blombooru's database as `meta`, or you reassign its category in the upload queue before committing). If you need explicit `meta` category assignment from sidecar files, use a JSON sidecar instead.

### Example 1: Standard imgbrd-grabber / Dublin Core XMP

Uses standard RDF container elements (`<rdf:Bag>`, `<rdf:Seq>`, `<rdf:Alt>`) for tags, creator, rating, source, description, and creation date:

```xml
<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <dc:subject>
        <rdf:Bag>
          <rdf:li>1girl</rdf:li>
          <rdf:li>night_sky</rdf:li>
          <rdf:li>starry_sky</rdf:li>
        </rdf:Bag>
      </dc:subject>
      <dc:creator>
        <rdf:Seq>
          <rdf:li>example_artist</rdf:li>
        </rdf:Seq>
      </dc:creator>
      <xmp:Rating>0</xmp:Rating>
      <dc:source>https://example.com/posts/12345</dc:source>
      <xmp:CreateDate>2024-05-18T10:14:22Z</xmp:CreateDate>
      <dc:description>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">Illustration of a starry night sky.</rdf:li>
        </rdf:Alt>
      </dc:description>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
```

### Example 2: ExifTool / Grabber XMP with Semicolon-Separated Keywords

Uses `<pdf:Keywords>` with semicolon-delimited multi-word tags alongside `<dc:creator>` and custom category tags. Multi-word tags such as `looking at viewer` are normalized to `looking_at_viewer`, and `example_artist` is upgraded from general to the `artist` category via `<dc:creator>`:

```xml
<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='Image::ExifTool 13.55'>
<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>

 <rdf:Description rdf:about=''
  xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <dc:creator>
   <rdf:Seq>
    <rdf:li>example_artist</rdf:li>
   </rdf:Seq>
  </dc:creator>
  <dc:character>
   <rdf:Bag>
    <rdf:li>hatate_himekaidou</rdf:li>
   </rdf:Bag>
  </dc:character>
  <dc:copyright>
   <rdf:Bag>
    <rdf:li>touhou</rdf:li>
   </rdf:Bag>
  </dc:copyright>
 </rdf:Description>

 <rdf:Description rdf:about=''
  xmlns:pdf='http://ns.adobe.com/pdf/1.3/'>
  <pdf:Keywords>1girl;solo;looking at viewer;example_artist;hatate_himekaidou;touhou</pdf:Keywords>
 </rdf:Description>

</rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>
```

### Example 3: Compact Attribute-Style XMP

Stores metadata directly as attributes on `<rdf:Description>`:

```xml
<x:xmpmeta
  xmlns:x="adobe:ns:meta/"
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:xmp="http://ns.adobe.com/xap/1.0/">
  <rdf:RDF>
    <rdf:Description
      rdf:about=""
      dc:subject="scenery;clouds;sunset"
      dc:creator="example_artist"
      dc:character="original_character"
      dc:copyright="original"
      xmp:Rating="safe"
      dc:source="https://example.com/art/987"
      dc:description="Sunset over the hills."
      xmp:CreateDate="2024-08-12T18:30:00+00:00" />
  </rdf:RDF>
</x:xmpmeta>
```

### Example 4: Minimal Rootless XML Snippet

Omits `<x:xmpmeta>` and `<rdf:RDF>` completely, using direct element text. Any subset of these elements (even a single element on its own) is also valid:

```xml
<dc:subject>1girl blue_hair highres</dc:subject>
<dc:creator>artist_name</dc:creator>
<character>hatsune_miku</character>
<copyright>vocaloid</copyright>
<dc:description>Illustration of Miku singing on stage</dc:description>
<xmp:Rating>general</xmp:Rating>
<dc:source>cool source</dc:source>
<xmp:CreateDate>2026-11-07T01:36:00Z</xmp:CreateDate>
```

---

## JSON

JSON sidecar files are handled by two specialized parsers: `GalleryDlParser` and `LoliSnatcherParser`.

### 1. gallery-dl (`GalleryDlParser`)

`GalleryDlParser` matches any JSON object sidecar that does not contain LoliSnatcher signature keys and includes at least one of the following keys: `category`, `subcategory`, `tags_general`, `tag_string`, `post_url`, `gallery`, or `extractor`.

#### Recognized Fields

| Target Field | Recognized JSON Keys |
|---|---|
| **Categorized Tags** | `tags_general`, `tags_artist`, `tags_character`, `tags_copyright`, `tags_meta` (list of strings or space-separated string; takes precedence over flat tag fields when present) |
| **General / Object Tags** | `tags`, `tag_string`, `keywords` (space-separated string, list of strings, or list of `{"name": "...", "category": "..."}` objects) |
| **Rating** | `rating` |
| **Source** | `source`, `post_url`, `url` (if omitted and `category` or `subcategory` is `"danbooru"` or `"gelbooru"` with an `id`, the post URL is reconstructed automatically) |
| **Description** | `artist_commentary` (object with `original_title`, `translated_title`, `original_description`, `translated_description`, or a string), `description`, `notes`, `commentary`, `caption` |
| **Albums (Pools)** | `pool`, `pools`, `gallery` (string, object with `name` or `title`, or list of strings/objects) |
| **Date** | `date`, `created_at`, `upload_date`, `timestamp`, `datetime` |

> [!NOTE]
> When a sidecar is identified as Danbooru-style (contains an `artist_commentary` object, `tag_string`, or any `tags_<category>` key), DText markup in the description or commentary is automatically converted to Markdown. When `artist_commentary` includes both a translated and original description, the translated text is placed first, separated from the original text by a `---` horizontal rule.

#### Example 1: Danbooru-Style Categorized JSON (Tag Arrays)

Includes per-category tag arrays, a nested `artist_commentary` object with translated and original fields, and a pool object:

```json
{
  "id": 123,
  "category": "danbooru",
  "subcategory": "post",
  "rating": "s",
  "source": "https://example.com/artist/post/123",
  "date": "2024-05-18 10:14:22",
  "tags_artist": ["example_artist"],
  "tags_character": ["example_character"],
  "tags_copyright": ["example_series"],
  "tags_general": ["1girl", "outdoors", "summer"],
  "tags_meta": ["highres"],
  "artist_commentary": {
    "original_title": "Titel",
    "translated_title": "Title",
    "original_description": "Beskrivning",
    "translated_description": "Description"
  },
  "pool": [
    {
      "name": "Summer Collection 2024"
    }
  ],
  "parent_id": 122
}
```

#### Example 2: Danbooru-Style Categorized JSON (Space-Separated Strings)

Uses space-separated strings for `tags_*`, `post_url`, an ISO 8601 `date` with offset, and `artist_commentary` with only original fields and DText markup:

```json
{
  "id": 12345,
  "category": "danbooru",
  "rating": "s",
  "post_url": "https://example.com/posts/12345",
  "tags_artist": "amazing_artist amazing_artist_2",
  "tags_character": "cool_character(banger_series)",
  "tags_copyright": "banger_series",
  "tags_general": "dragon horns scales wings night_sky",
  "tags_meta": "absurdres highres",
  "parent_id": 12344,
  "date": "2001-03-12T13:45:30+00:00",
  "pool": [{ "id": 5120, "name": "Art From Amazing Artist" }],
  "artist_commentary": {
    "original_title": "Sick Dragon Character",
    "original_description": "Drawn for [b]Banger Series[/b].\nColors by [i]Amazing Artist 2[/i]!"
  }
}
```

#### Example 3: Gelbooru / Flat Tag String JSON

Uses a single space-separated `tags` string and `post_url`:

```json
{
  "id": 1234,
  "category": "gelbooru",
  "subcategory": "post",
  "rating": "q",
  "tags": "1girl solo blue_eyes ribbon",
  "post_url": "https://example.com/index.php?page=post&s=view&id=1234",
  "created_at": "2024-06-01T14:20:00Z"
}
```

#### Example 4: Pixiv / Site Extractor JSON (String Tag Array)

Uses `extractor`, a flat `tags` array of strings, a Unix timestamp `date`, and a plain-text `description` (non-Danbooru extractors preserve plain text without DText conversion):

```json
{
  "id": 1234,
  "extractor": "pixiv",
  "subcategory": "artwork",
  "title": "Cool Artwork",
  "tags": ["night_sky", "original", "dragon"],
  "date": 1715300730,
  "description": "A silly dragon."
}
```

#### Example 5: Generic Extractor with Tag Objects

Uses `extractor` (or `category`), a list of tag objects with explicit categories, `caption`, and `gallery`:

```json
{
  "extractor": "custom",
  "url": "https://example.com/gallery/42",
  "rating": "safe",
  "caption": "Concept art for chapter 1.",
  "gallery": "Concept Art Archive",
  "timestamp": 1716027262,
  "tags": [
    { "name": "example_artist", "category": "artist" },
    { "name": "protagonist", "category": "character" },
    { "name": "concept_art", "category": "meta" },
    { "name": "forest", "category": "general" }
  ]
}
```

---

### 2. LoliSnatcher (`LoliSnatcherParser`)

`LoliSnatcherParser` matches JSON object sidecars containing at least one LoliSnatcher signature key: `isSnatched`, `postURL`, `isFavourite`, `sampleURL`, `thumbnailURL`, `fileURL`, `md5String`, `booru`, `tagsList`, or `md5` combined with `post_url`, `file_url`, or `booru_url`.

#### Recognized Fields

| Target Field | Recognized JSON Keys |
|---|---|
| **Tags** | `tags`, `tagsList`, `keywords` (list of objects with `fullString`/`name`/`tag`/`string` and `tagType`/`category`/`type`, list of strings, or space-separated string) |
| **Rating** | `rating` (if omitted or `null` and `postURL` or `post_url` contains `"safebooru"`, defaults to `"safe"`) |
| **Source** | `postURL`, `post_url`, `source`, `sources` (first item if array), `booru_url`, `fileURL`, `file_url`, `sampleURL` |
| **Description** | `artist_commentary` (object or string), `description`, `notes`, `commentary`, `caption` |
| **Albums (Pools)** | `pools`, `pool`, `folder` (string or list of strings) |
| **Date** | `postDate`, `created_at`, `date`, `uploaded_at`, `timestamp` (supports standard timestamps as well as Gelbooru-style date strings such as `"Sun May 18 10:14:22  2024"`) |

#### Example 1: Modern camelCase Format

Matches the standard camelCase JSON output produced by LoliSnatcher:

```json
{
  "postURL": "https://example.com/posts/12345",
  "fileURL": "https://cdn.example.com/original/ab/25/sample_image.jpg",
  "sampleURL": "https://cdn.example.com/sample/ab/25/sample_image.jpg",
  "thumbnailURL": "https://cdn.example.com/180x180/ab/25/sample_image.jpg",
  "tags": [
    { "fullString": "1girl", "updatedAt": 1716027262000, "tagType": "none" },
    { "fullString": "blue_sky", "updatedAt": 1716027262000, "tagType": "general" },
    { "fullString": "example_artist", "updatedAt": 1716027262000, "tagType": "artist" },
    { "fullString": "example_character", "updatedAt": 1716027262000, "tagType": "character" },
    { "fullString": "example_series", "updatedAt": 1716027262000, "tagType": "copyright" },
    { "fullString": "highres", "updatedAt": 1716027262000, "tagType": "meta" }
  ],
  "fileExt": "jpg",
  "isFavourite": false,
  "isSnatched": true,
  "serverId": null,
  "rating": "safe",
  "score": 42,
  "sources": ["https://example.com/original/12345"],
  "md5String": "d41d8cd98f00b204e9800998ecf8427e",
  "postDate": "Sun May 18 10:14:22  2024",
  "postDateFormat": "EEE MMM dd HH:mm:ss  yyyy"
}
```

#### Example 2: Legacy snake_case Format

Uses `booru`, `md5`, `post_url`, `tagsList`, `pools`, and `notes`:

```json
{
  "booru": "danbooru",
  "md5": "d41d8cd98f00b204e9800998ecf8427e",
  "rating": "safe",
  "post_url": "https://example.com/posts/111",
  "created_at": "2024-05-18T10:14:22Z",
  "tagsList": [
    { "name": "example_artist", "category": "artist" },
    { "name": "landscape", "category": "general" }
  ],
  "pools": ["Scenic Illustrations"],
  "notes": "Imported via LoliSnatcher."
}
```
