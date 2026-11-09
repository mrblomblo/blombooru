## Grundläggande taggar

- `tag1 tag2`: Hitta media med båda taggarna
- `-tag1`: Exkludera media med tagg
- `tag*`, `*tag`, `*tag*`: Jokersökning (prefix, suffix eller *delsträng*)
- `?tag`: Fuzzy-sökning (ett eller noll tecken före)
- `"tag with spaces"`: Citerade taggar eller fraser med mellanslag

## Intervall och operatorer

Operatorer: `:`, `..`, `>=`, `>`, `<=`, `<`, `!=`, `-`

- `id:100`: Exakt matchning
- `id:100..200`: Mellan inklusivt
- `id:..100`, `id:100..`: Öppna intervall
- `id:>=100`, `id:>100`, `id:<=100`, `id:<100`, `id:!=100`
- `id:1,2,3`: I lista
- `gentags:13,16,<8,>91`: Flervärdeslistor med jämförelseoperatorer (matchar vilkensomhelst)
- `gentags:6,4 gentags:8,>4`: Kombineras och förenklas automatiskt (`gentags:>=4`)
- `gentags:5,6,<=15`: Överlappande värden rensas automatiskt (`gentags:<=15`)
- `-rating:e`, `-parent:none`: Negera vilken qualifier som helst med ett minustecken

OBS: Intervall och flervärdeslistor kan användas med de flesta metaqualifiers.

## Metaqualifiers

### Relationer och hierarki

- `parent`: Föräldrainläggs-ID (`parent:none` för huvudinlägg, `parent:any` för underinlägg, `parent:100` för exakt matchning)
- `child`: Underinläggs-ID (`child:none` för inga underinlägg, `child:any` för föräldrainlägg, `child:200` för exakt matchning)
- `id`: Internt medie-ID (`id:100`, `id:1..50`)

### Album och pooler

- `album` / `pool`: Album- eller pool-ID / namn (`album:none` för otilldelade, `album:any`, `album:favorites`, `pool:5`)
- `album_tree` / `pool_tree`: Rekursivt album- / poolträd, med namn eller ID (inkluderar alla underalbum) (`album_tree:artbook`, `pool_tree:1`)

### Medieegenskaper

- `width`, `height`: Bilddimensioner i pixlar (`width:>=1920`, `height:<1080`)
- `duration`: Video- / animerad GIF-längd i sekunder (`duration:>30`, `duration:10..60`)
- `filesize`: Filstorlek (b, kb, mb, gb med fuzzy-matchning) (`filesize:>5mb`, `filesize:52mb`)
- `filetype`: Filändelse (png, gif, mp4 osv.) eller medietyp (image, video) (`filetype:png,jpg`, `filetype:video`)
- `filename`: Filnamn med valfri ändelse (`filename:image.png`, `filename:scan_*`, `filename:*.jpg`)

### Metadata och info

- `rating`: safe, questionable, explicit (s, q, e) (`rating:s,q`, `-rating:e`)
- `source`: Käll-URL, domän, http eller none (`source:twitter`, `source:none`, `source:http`)
- `date`, `age`: Uppladdningsdatum (ÅÅÅÅ-MM-DD) eller relativ ålder (s, mi, h, d, w, mo, y) (`date:>=2024-01-01`, `age:<24h`, `age:1w..1mo`)
- `custom_date`, `custom_age`: Anpassat mediedatum (ÅÅÅÅ-MM-DD) eller relativ anpassad ålder (s, mi, h, d, w, mo, y) (`custom_date:>=2024-01-01`, `custom_age:<30d`, `custom_date:2024-01-01..2024-12-31`)
- `md5`: Exakt fil-MD5-hashkontrollsumma (`md5:d34e...`)

### Antal taggar

- `tagcount`: Totalt antal taggar (`tagcount:>20`, `tagcount:0`)
- `gentags`, `arttags`, `chartags`, `copytags`, `metatags`: Specifika kategoriräknare (gentags, arttags, chartags, copytags, metatags)

## Sortering

Använd `order:värde` eller `sort:värde`. Lägg till `_asc` eller `_desc`. De flesta sorteringar har fallande som standard; filename, rating och md5 har stigande som standard.

- `id` / `id_desc`: Nyast först (standard)
- `id_asc`: Äldst först
- `date_desc` / `date_asc`: Uppladdningsdatum
- `custom_date_desc` / `custom_date_asc`: Anpassat mediedatum
- `filesize` / `filesize_asc`: Filstorlek
- `width_desc` / `height_desc` / `mpixels_desc`: Dimensioner och upplösning
- `duration_desc` / `duration_asc`: Längd
- `landscape` / `portrait`: Bildförhållande
- `rating_asc` / `rating_desc`: Innehållsbetygsordning
- `filename_asc` / `filename_desc`: Ursprungligt filnamn i alfabetisk ordning
- `filetype_desc` / `filetype_asc`: Filformat / filändelse
- `md5_asc` / `md5_desc`: MD5-hashsumma
- `tagcount_desc` / `tagcount_asc`: Totalt antal taggar
- `gentags_desc`, `arttags_desc`, `chartags_desc`...: Kategoriräknare för taggar
- `random` / `random:<seed>`: Slumpmässig ordning
- `custom`: Bevara exakt ordning från en id-lista (t.ex. `id:5,2,8 order:custom`)

## Exempelsökningar

- `cat source:none rating:s`: Säkra kattbilder utan källa
- `landscape filetype:mp4 filesize:>5mb duration:>30`: Högkvalitativa landskapsvideor
- `parent:none child:any`: Huvudinlägg som har variantinlägg
- `album_tree:artbook order:id_asc`: Rekursiv albumsökning, äldst först
- `id:1..100 order:id_asc`: Första 100 uppladdningar, äldst först
- `order:random:42 rating:s`: Slumpmässiga säkra bilder med ett reproducerbart frö
- `?girl? *_eyes -dog`: Söker efter en eller flera tjejer med valfri ögonfärg, inga hundar
- `tagcount:>20 arttags:0`: Inlägg med många taggar men ingen artistinfo
