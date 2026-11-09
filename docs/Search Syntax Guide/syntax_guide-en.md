## Basic Tags

- `tag1 tag2`: Find media with both tags
- `-tag1`: Exclude media with tag
- `tag*`, `*tag`, `*tag*`: Wildcard search (prefix, suffix, or *infix*)
- `?tag`: Fuzzy search (one or zero chars before)
- `"tag with spaces"`: Quoted tags or phrases with spaces

## Ranges & Operators

Operators: `:`, `..`, `>=`, `>`, `<=`, `<`, `!=`, `-`

- `id:100`: Exact match
- `id:100..200`: Between inclusive
- `id:..100`, `id:100..`: Open-ended ranges
- `id:>=100`, `id:>100`, `id:<=100`, `id:<100`, `id:!=100`
- `id:1,2,3`: In list
- `gentags:13,16,<8,>91`: Multi-value lists with comparison operators (matches any)
- `gentags:6,4 gentags:8,>4`: Automatically combined and simplified (`gentags:>=4`)
- `gentags:5,6,<=15`: Swallowed values are automatically cleared (`gentags:<=15`)
- `-rating:e`, `-parent:none`: Negate any qualifier with a minus prefix

Note: Ranges and multi-value lists can be used with most meta qualifiers.

## Meta Qualifiers

### Relations & Hierarchy

- `parent`: Parent post ID (`parent:none` for root posts, `parent:any` for child posts, `parent:100` for exact match)
- `child`: Child post ID (`child:none` for no children, `child:any` for parent posts, `child:200` for exact match)
- `id`: Internal media ID (`id:100`, `id:1..50`)

### Albums & Pools

- `album` / `pool`: Album or pool ID / name (`album:none` for unassigned, `album:any`, `album:favorites`, `pool:5`)
- `album_tree` / `pool_tree`: Recursive album / pool tree, using name or ID (includes all descendant sub-albums) (`album_tree:artbook`, `pool_tree:1`)

### Media Properties

- `width`, `height`: Image dimensions in pixels (`width:>=1920`, `height:<1080`)
- `duration`: Video / animated GIF duration in seconds (`duration:>30`, `duration:10..60`)
- `filesize`: File size (b, kb, mb, gb with fuzzy matching) (`filesize:>5mb`, `filesize:52mb`)
- `filetype`: Extension (png, gif, mp4, etc.) or media type (image, video) (`filetype:png,jpg`, `filetype:video`)
- `filename`: Filename with optional extension (`filename:image.png`, `filename:scan_*`, `filename:*.jpg`)

### Metadata & Info

- `rating`: safe, questionable, explicit (s, q, e) (`rating:s,q`, `-rating:e`)
- `source`: Source URL, domain, http, or none (`source:twitter`, `source:none`, `source:http`)
- `date`, `age`: Upload date (YYYY-MM-DD) or relative age (s, mi, h, d, w, mo, y) (`date:>=2024-01-01`, `age:<24h`, `age:1w..1mo`)
- `custom_date`, `custom_age`: Custom media date (YYYY-MM-DD) or relative custom age (s, mi, h, d, w, mo, y) (`custom_date:>=2024-01-01`, `custom_age:<30d`, `custom_date:2024-01-01..2024-12-31`)
- `md5`: Exact file MD5 hash checksum (`md5:d34e...`)

### Tag Counts

- `tagcount`: Total number of tags (`tagcount:>20`, `tagcount:0`)
- `gentags`, `arttags`, `chartags`, `copytags`, `metatags`: Specific category counts

## Sorting

Use `order:value` or `sort:value`. Suffix with `_asc` or `_desc`. Most sorts default to descending; filename, rating, and md5 default to ascending.

- `id` / `id_desc`: Newest first (default)
- `id_asc`: Oldest first
- `date_desc` / `date_asc`: Upload date
- `custom_date_desc` / `custom_date_asc`: Custom media date
- `filesize` / `filesize_asc`: File size
- `width_desc` / `height_desc` / `mpixels_desc`: Dimensions and resolution
- `duration_desc` / `duration_asc`: Duration
- `landscape` / `portrait`: Aspect ratio
- `rating_asc` / `rating_desc`: Content rating order
- `filename_asc` / `filename_desc`: Original filename alphabetically
- `filetype_desc` / `filetype_asc`: File format / extension
- `md5_asc` / `md5_desc`: MD5 hash checksum
- `tagcount_desc` / `tagcount_asc`: Total tag count
- `gentags_desc`, `arttags_desc`, `chartags_desc`...: Category tag counts
- `random` / `random:<seed>`: Randomized order
- `custom`: Preserve exact order from an id list (e.g. `id:5,2,8 order:custom`)

## Example Searches

- `cat source:none rating:s`: Safe cat images without a source
- `landscape filetype:mp4 filesize:>5mb duration:>30`: High-quality landscape videos
- `parent:none child:any`: Root posts that have child variants
- `album_tree:artbook order:id_asc`: Recursive album search, oldest first
- `id:1..100 order:id_asc`: First 100 uploads, oldest first
- `order:random:42 rating:s`: Randomized safe images with a reproducible seed
- `?girl? *_eyes -dog`: Searching for one or more girls with any color eyes, no dogs
- `tagcount:>20 arttags:0`: Posts with many tags but no artist info
