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


<a href="./README.md">English</a> • <a href="./README_RU.md">Русский</a> • <a href="./README_ZH_CN.md">简体中文</a> • **Svenska**

<b>Din Personliga, Egenhostade Booru.</b>

</div>

Blombooru är ett privat, enanvändarorienterat alternativ till publika boorus som Danbooru och Gelbooru. Det är utformat för individer som önskar en kraftfull, användarvänlig och modern lösning för att organisera och tagga sina personliga mediasamlingar. Med fokus på en ren användarupplevelse, robust administration och enkel anpassning ger Blombooru dig fullständig kontroll över ditt bibliotek.

> [!NOTE]
> Lokalisering till svenska: @mrblomblo  
> Senast uppdaterad 3 oktober 2026

**[Visa skärmdumpar](docs/Gallery.md)**

## Innehållsförteckning

- [Innehållsförteckning](#innehållsförteckning)
- [Nyckelfunktioner](#nyckelfunktioner)
  - [Kärnfunktioner](#kärnfunktioner)
  - [AI \& Automatisering](#ai--automatisering)
  - [Säkerhet \& Delning](#säkerhet--delning)
  - [Anpassning \& Teman](#anpassning--teman)
  - [Flexibilitet \& Integration](#flexibilitet--integration)
- [Installation \& Inställning](#installation--inställning)
  - [Docker *(Rekommenderas)*](#docker-rekommenderas)
    - [Driftsättningsalternativ](#driftsättningsalternativ)
    - [Snabbstart (Färdigbyggd avbildning)](#snabbstart-färdigbyggd-avbildning)
    - [Hårdvaruacceleration](#hårdvaruacceleration)
    - [Använda förhandsversioner (Pre-release)](#använda-förhandsversioner-pre-release)
    - [Utvecklarversioner (Lokalt)](#utvecklarversioner-lokalt)
    - [Köra flera instanser](#köra-flera-instanser)
    - [Dela taggar mellan instanser](#dela-taggar-mellan-instanser)
  - [Python](#python)
- [Användarguide](#användarguide)
  - [Logga in](#logga-in)
  - [Adminläge](#adminläge)
  - [Lägga till taggar](#lägga-till-taggar)
    - [1. CSV-import](#1-csv-import)
    - [2. Skapa taggar manuellt](#2-skapa-taggar-manuellt)
  - [Ladda upp media](#ladda-upp-media)
    - [1. Mediafiler](#1-mediafiler)
    - [2. Komprimerade arkiv](#2-komprimerade-arkiv)
    - [3. Skanna filsystemet](#3-skanna-filsystemet)
    - [4. Import via extern URL](#4-import-via-extern-url)
  - [Taggning \& Sökning](#taggning--sökning)
  - [Dela media](#dela-media)
  - [Systemuppdaterare](#systemuppdaterare)
    - [Hur man uppdaterar](#hur-man-uppdaterar)
    - [Ändringar i beroenden](#ändringar-i-beroenden)
  - [Kontoåterställning](#kontoåterställning)
  - [API \& Tredjepartsappar](#api--tredjepartsappar)
    - [Anslutningsdetaljer](#anslutningsdetaljer)
    - [Funktioner som stöds](#funktioner-som-stöds)
    - [Internt API](#internt-api)
- [Teman](#teman)
- [Tekniska detaljer](#tekniska-detaljer)
- [Dokumentation \& Gemenskap](#dokumentation--gemenskap)
- [Ansvarsfriskrivning](#ansvarsfriskrivning)
- [Licens](#licens)

## Nyckelfunktioner

### Kärnfunktioner

- **Taggning i Danbooru-stil:** Ett bekant och kraftfullt taggningssystem med kategorier (artist, character, copyright, etc.), tagg-baserad sökning och exkludering med negativa taggar.

- **Taggalleri & Hantering:** Bläddra, sök och hantera dina taggar i ett dedikerat taggalleri.

- **Enkel import av taggdatabaser:** Importera anpassade tagglistor via en enkel CSV-uppladdning i adminpanelen för att hålla ditt system uppdaterat.

- **Album:** Organisera din media i album, med stöd för underalbum, manuell sortering och automatiskt skapande av albumhierarkier från mappuppladdningar. *Album är Blomboorus motsvarighet till "pools" på andra boorus!*

- **Mediarelationer & Likhet:** Länka relaterad media med förälder-barn-relationer (parent-child), eller upptäck liknande inlägg med hjälp av en konfigurerbar likhetsalgoritm (TF-IDF). Gruppera bildvariationer, flersidiga serier och mer (vilket håller relaterat innehåll lättillgängligt).

- **Markdown-beskrivningar:** Lägg till rika, formaterade beskrivningar till inlägg med fullt Markdown-stöd.

- **Import från externa Boorus:** Importera sömlöst inlägg från Danbooru och andra booru-sidor (som Danbooru, Gelbooru, etc.) genom att helt enkelt klistra in inläggets URL. Taggar, åldersgräns, källa och media hämtas och kartläggs automatiskt.

### AI & Automatisering

- **AI-vänlig:** Visa enkelt medföljande AI-metadata för media genererad med SwarmUI, ComfyUI, A1111, InvokeAI, NovelAI, Fooocus med flera. Du kan även lägga till taggar i taggredigeraren direkt från AI-prompten eller valfritt direkt till mediauppladdaren under import.

- **Automatisk taggning:** Påskynda taggningen med WDv3- eller PixAI Auto Tagger-integrationen, som analyserar bilder och föreslår korrekta taggar med ett enda klick. Stöder valfri Nvidia GPU-acceleration för blixtsnabb batchbearbetning.

- **Sidecar-metadata:** Importerar automatiskt metadata från sidecar-filer, perfekt för dig som använder externa nedladdare som gallery-dl eller imgbrd-grabber.

- **Taggimplikationer:** Definiera relationer mellan taggar. När en måltagg (eller en uppsättning taggar) appliceras på ett mediaobjekt, läggs de implicerade taggarna automatiskt till.

- **Taggalias:** Definiera alias för taggar för att hålla din tagglista ren och organiserad. Att använda ett alias applicerar automatiskt måltaggen istället.

- **Automatiska taggar per mediatyp:** Lägg automatiskt till förkonfigurerade taggar för varje objekt i uppladdningskön baserat på dess mediatyp (bild, GIF eller video).

### Säkerhet & Delning

- **Säkert läge:** När detta är aktiverat måste användare logga in för att interagera med Blombooru. Offentliga rutter såsom delningslänkar och statiska filer förblir offentliga. Perfekt för privata samlingar som du inte vill att någon annan i hushållet ska se!

- **Säker surfning:** Bläddra i din samling utan rädsla för oavsiktliga ändringar. Alla hanteringsåtgärder (uppladdning, redigering, radering) kräver att du är inloggad som administratör.

- **Säker mediadelning:** Generera unika, permanenta länkar för att dela specifik media. Delade objekt presenteras i en avskalad, säker vy med valfri delning av AI-metadata.

- **Blurrade miniatyrbilder:** Gör valfritt explicita miniatyrbilder blurrade i galleri- och mediavyer för säkrare surfning.

- **Hantering av API-nycklar:** Skapa och hantera avgränsade (läs/skriv/admin-nivå) API-nycklar för skript och tredjepartsverktyg.

### Anpassning & Teman

- **Modernt & responsivt gränssnitt:** Byggt med Tailwind CSS för en vacker och konsekvent upplevelse på både datorer och mobila enheter.

- **Mycket anpassningsbara teman:** Skräddarsy utseendet med hjälp av enkla CSS-variabler. Skapa, redigera, importera och exportera anpassade teman direkt i adminpanelen.

- **Många teman att välja mellan:** Blombooru levereras med de fyra färgpaletterna från Catppuccin, Gruvbox (ljus & mörk), Everforest (ljus & mörk), OLED och mer!

- **Anpassningsbara snabbtangenter:** Helt omkonfigurerbara tangentbordsgenvägar med en inbyggd redigerare för snabb navigering.

- **Stöd för flera språk:** Översatt gränssnitt tillgängligt på flera olika språk.

### Flexibilitet & Integration

- **Stöd för SOCKS5/HTTP-proxy:** Konfigurera en SOCKS5- eller HTTP-proxy via adminpanelen för att ladda ner extern media genom den. Perfekt för åtkomst till regionbegränsat innehåll eller av integritetsskäl.

- **Flexibla mediauppladdningar:** Lägg till media via dra-och-släpp, komprimerade arkiv, filsystemsskanningar, import från externa booru- eller direkta media-URL:er, eller batchlistor med URL:er.

- **Skapa taggar direkt (On-The-Fly):** Om en tagg du vill lägga till inte finns ännu, kan du skapa den direkt i valfritt taggfält utan att behöva gå till adminpanelen.

- **Miniatyrbildshantering:** Reparera enkelt trasiga eller saknade miniatyrbilder i adminpanelen. Du kan generera saknade miniatyrer eller helt återskapa alla miniatyrer för stora bibliotek.

- **Säkerhetskopiering & Återställning:** Skapa fullständiga eller partiella säkerhetskopior (databas, mediafiler och taggar) direkt från adminpanelen.

- **Användarvänlig Onboarding:** Enkel installationsprocess för att konfigurera ditt adminkonto, databasanslutning och instansnamn. Du kan även importera en fullständig säkerhetskopia under installationen.

- **Högpresterande cachning:** Valfri Redis-integration ger blixtsnabba svarstider för tunga sökningar, autoslutförande (autocomplete) och Danbooru-kompatibla API-förfrågningar.

- **Delad taggdatabas:** Du kan valfritt dela taggar över flera Blombooru-instanser med hjälp av en centraliserad PostgreSQL-databas dedikerad enbart för taggar.

- **Danbooru v2 API-kompatibilitet:** Anslut till Blombooru med dina favorit-booru-klienter från tredje part (som Grabber, Tachiyomi eller BooruNav) tack vare ett inbyggt kompatibilitetslager.

## Installation & Inställning

Du kan välja att antingen använda Blombooru i en Docker-container *(rekommenderas)* eller köra det direkt med Python.

### Docker *(Rekommenderas)*

Detta är den rekommenderade metoden för att använda Blombooru. Färdigbyggda avbildningar (images) finns tillgängliga på GitHub Container Registry.

| Förkrav | Anteckningar |
|:-------------|:------|
| Docker | Krävs |

#### Driftsättningsalternativ

| Alternativ | Image-tagg | Användningsområde |
|:-------|:----------|:---------|
| **Senaste stabila** | `latest` (standard) | Produktionsanvändning, följer den senaste GitHub-releasen |
| **Senaste stabila (CUDA)** | `latest-cuda` | Produktionsanvändning med CUDA-acceleration |
| **Förhandsversion** | `pre` | Testa kommande versioner, följer den senaste förhandsversionen (pre-release) |
| **Förhandsversion (CUDA)** | `pre-cuda` | Testa kommande versioner med CUDA-acceleration |
| **Låst version** | `1.2.3` / `1.2` / `1` | Låsa till en specifik stabil version |
| **Låst förhandsversion** | `1.2.3-rc.1` | Låsa till en specifik förhandsversion |
| **Utvecklarversion** | Lokal build | För bidragsgivare, ändra källkoden |

#### Snabbstart (Färdigbyggd avbildning)

1. **Ladda ner nödvändiga filer**

    Skapa en mapp för Blombooru (t.ex. `blombooru`), ladda sedan ner filerna `docker-compose.yml` och `example.env` från den [senaste releasen](https://github.com/mrblomblo/blombooru/releases/latest) och placera dem i mappen. (Valfritt: om du planerar att använda GPU-acceleration, ladda även ner hwaccel.yml).

2. **Anpassa miljövariablerna**  
    Skapa en kopia av `example.env` och döp den till `.env`. Öppna sedan den nyskapade filen med din favorittextredigerare och redigera värdena efter `=` på varje rad. Det viktigaste att ändra är exempellösenordet som tilldelats `POSTGRES_PASSWORD`. De andra *kan* förbli som de är, såvida inte till exempel port 8000 redan används av ett annat program.

3. **Första körningen & Onboarding**  
    Starta Docker-containern (se till att du befinner dig i mappen där du placerade `docker-compose.yml`-filen):

    ```bash
    docker compose up -d
    ```

    *Du kan behöva använda `sudo` eller köra kommandot från en terminal med förhöjda rättigheter.*

    Öppna nu din webbläsare och navigera till `http://localhost:<port>` (ersätt `<port>` med porten du angav i `.env`-filen). Du kommer att mötas av introduktionssidan (onboarding). Här kommer du att:
    - Ställa in ditt användarnamn och lösenord för admin.
    - Ange dina anslutningsdetaljer för PostgreSQL. Servern kommer att testa anslutningen innan den fortsätter. Såvida du inte har ändrat `POSTGRES_DB` och/eller `POSTGRES_USER` behöver du bara fylla i lösenordet du angav i `.env`-filen. Ändra inte DB Host.
    - *(Valfritt)* Aktivera och konfigurera Redis för cachning.
    - Anpassa webbplatsens varumärkesnamn (standard är "Blombooru").

    När detta är inskickat kommer servern att skapa databasschemat och ditt adminkonto.

4. **Köra applikationen igen**  
    Efter den första inställningen kan du köra servern med följande kommando (återigen, se till att du är i mappen med `docker-compose.yml`-filen):
    
    ```bash
    docker compose up -d
    ```

    *Du kan behöva använda `sudo` eller köra kommandot från en terminal med förhöjda rättigheter.*

    Alla inställningar sparas i en `settings.json`-fil i mappen `data`, och all uppladdad media sparas i mappen `media/original`. Observera att dessa mappar inte kommer att vara lättillgängliga och skapas inte i Blomboorus rotmapp.

5. **Stänga ner containern**

    ```bash
    docker compose down
    ```

#### Hårdvaruacceleration

Om du har en Nvidia-GPU och vill kraftigt snabba upp WDv3 Auto Taggern kan du använda den CUDA-accelererade Docker-versionen.

> [!IMPORTANT]
> Du måste ha Nvidia Container Toolkit installerat på din dator, och dina GPU-drivrutiner måste vara uppdaterade. Det förutsätts också att du använder en någorlunda modern GPU.

Installering:

1. **Ladda ner hwaccel.yml**  
    Ladda ner filen `hwaccel.yml` från den senaste releasen och placera den i samma mapp som dina `docker-compose.yml`- och `.env`-filer.

2. **Redigera docker-compose.yml**  
    Öppna din `docker-compose.yml`-fil, hitta webbtjänsten och avkommentera (ta bort de tre `#`-tecknen i början av) blocket `extends:`:

    ```yaml
    services:
      web:
        image: ghcr.io/mrblomblo/blombooru:${BLOMBOORU_TAG:-latest}
        extends:
          file: hwaccel.yml
          service: cuda
    ```

3. **Konfigurera miljövariabeln**  
    Se till att taggerenheten i din `.env`-fil är inställd på `auto` (standard) eller `cuda`:

    ```env
    BLOMBOORU_WD_TAGGER_DEVICE=auto # Options: auto, cuda, cpu
    ```

4. **Starta containern**  
    Hämta den nya CUDA-avbildningen och starta containern:

    ```bash
    docker compose up -d
    ```

> [!WARNING]
> Om du använder `latest-cuda`-avbildningen måste du avkommentera `extends:`-blocket i din `docker-compose.yml`. Om du använder CUDA-avbildningen utan att skicka GPU:n till containern kraschar Blombooru när AI-modellen försöker laddas.

Miljövariabeln `BLOMBOORU_WD_TAGGER_DEVICE` styr hur taggaren initieras:

- `auto` (standard): Använder GPU om paketet `onnxruntime-gpu` är installerat, annars CPU.
- `cuda`: Tvingar strikt GPU-användning. Om paketet inte är installerat ger Blombooru ett felmeddelande och vägrar starta.
- `cpu`: Tvingar CPU-användning, även om en GPU är tillgänglig.

#### Använda förhandsversioner (Pre-release)

För att använda den senaste förhandsversionen, ställ in miljövariabeln `BLOMBOORU_TAG`:

```bash
BLOMBOORU_TAG=pre docker compose up -d
```

Eller lägg till `BLOMBOORU_TAG=pre` i din `.env`-fil.

> [!WARNING]
> Förhandsversioner kan innehålla kod som bryter funktionalitet eller buggar. Använd endast för att testa kommande versioner.

#### Utvecklarversioner (Lokalt)

För bidragsgivare eller de som vill bygga från källkoden:

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

Detta använder `docker-compose.dev.yml` som bygger avbildningen (imagen) lokalt från din källkod.

#### Köra flera instanser

Om du behöver köra flera oberoende Blombooru-instanser (till exempel separata bibliotek för olika ändamål eller användare) gör Docker Compose detta okomplicerat. Varje instans kommer att ha sin egen isolerade databas, Redis-cache, medialagring och konfiguration.

**Förkrav:**
- Har slutfört minst en standard Docker-installation (se ovan)
- Grundläggande kännedom om kommandoraden

**Instruktioner:**

1. **Skapa separata kataloger för varje instans**  
    Varje instans bör ligga i sin egen mapp för att hålla allt organiserat och isolerat:

    ```bash
    mkdir -p ~/blombooru-instans1
    mkdir -p ~/blombooru-instans2
    cd ~/blombooru-instans1
    ```

2. **Ställ in filerna för varje instans**  
    Kopiera `docker-compose.yml` och `example.env` till varje katalog:

    ```bash
    # Bara ett exempel, ersätt med den faktiska sökvägen till filerna
    cp ~/blombooru/docker-compose.yml ~/blombooru/example.env ~/blombooru-instans1/
    cp ~/blombooru/docker-compose.yml ~/blombooru/example.env ~/blombooru-instans2/
    ```

3. **Konfigurera unika portar för varje instans**  
    Skapa en `.env`-fil i varje instanskatalog (kopiera från `example.env`) och tilldela **olika portnummer** för att undvika konflikter:

    **Instans 1** (`~/blombooru-instans1/.env`):
    ```env
    APP_PORT=8000
    POSTGRES_PORT=5432
    REDIS_PORT=6379
    POSTGRES_PASSWORD=ditt_säkra_lösenord_här
    # ... andra inställningar
    ```

    **Instans 2** (`~/blombooru-instans2/.env`):
    ```env
    APP_PORT=8001
    POSTGRES_PORT=5433
    REDIS_PORT=6380
    POSTGRES_PASSWORD=ett_annat_säkert_lösenord
    # ... andra inställningar
    ```

> [!IMPORTANT]
> Varje instans **måste** använda unika värden för `APP_PORT`, `POSTGRES_PORT` och `REDIS_PORT`. Att använda samma portar kommer att orsaka konflikter och förhindra att instanserna startar.

> [!NOTE] 
> `POSTGRES_PORT` och `REDIS_PORT` används **endast** för att mappa portar till din värddator, eller ifall en extern PostgreSQL- eller Redis-server använder andra portar. Inuti Docker kommunicerar containrarna alltid med de interna standardportarna (PostgreSQL: `5432`, Redis: `6379`).

4. **Starta varje instans oberoende av varandra**  
    Navigera till varje instanskatalog och starta den med Docker Compose:

    ```bash
    cd ~/blombooru-instans1
    docker compose up --build -d
    ```

    ```bash
    cd ~/blombooru-instans2
    docker compose up --build -d
    ```

    Docker Compose kommer automatiskt att namnge containrar med hjälp av katalognamnet (t.ex. `blombooru-instans1-web-1`, `blombooru-instans2-web-1`), vilket förhindrar namnkonflikter.

5. **Slutför onboarding för varje instans**  
    Varje instans är helt oberoende, så du måste slutföra onboarding-processen separat:
    - Instans 1: `http://localhost:8000`
    - Instans 2: `http://localhost:8001`

**Hantera flera instanser:**

- **Visa körande instanser:**  
    ```bash
    docker ps
    ```

- **Stoppa en specifik instans:**  
    ```bash
    cd ~/blombooru-instans1
    docker compose down
    ```

- **Visa loggar för en specifik instans:**  
    ```bash
    cd ~/blombooru-instans1
    docker compose logs -f
    ```

- **Uppdatera en specifik instans:**  
    Navigera till instanskatalogen och uppdatera via Docker Compose:

    ```bash
    cd ~/blombooru-instans1
    docker compose up -d --pull always
    ```

**Datasisolering:**

Varje instans upprätthåller helt separata:
- **Databaser** – Sparas i Docker-volymer döpta efter instanskatalogen (t.ex. `blombooru-instans1_pgdata`)
- **Mediafiler** – Sparas i separata Docker-volymer (t.ex. `blombooru-instans1_media`)
- **Konfiguration** – Varje instans har sin egen `settings.json` i sin Docker-volym
- **Redis-cache** – Separata Redis-instanser med isolerad data

Detta innebär att du säkert kan radera, uppdatera eller modifiera en instans utan att påverka några andra.

#### Dela taggar mellan instanser

Om du vill att flera Blombooru-instanser ska dela samma taggdatabas (så att taggar som skapas i en instans är tillgängliga i andra), kan du aktivera den valfria funktionen **Delad taggdatabas** genom att ladda ner filen `docker-compose.shared-tags.yml` från den [senaste releasen](https://github.com/mrblomblo/blombooru/releases/latest), placera den i samma katalog som en av dina `docker-compose.yml`-filer och följa dessa steg (alternativt kan du hoppa över steg 1 och 2 och använda en befintlig PostgreSQL-databas om du har en):

1. **Redigera .env-filen för den instans som ska hosta den delade taggdatabasen:**
   - Justera följande rader i instansens `.env`-fil:

   ```env
   SHARED_TAGS_ENABLED=false # Ändra till true för att aktivera den delade taggdatabasen
   SHARED_TAG_DB_USER=postgres
   SHARED_TAG_DB_PASSWORD=supersecretsharedtagdbpassword # Ändra till ett säkert lösenord
   SHARED_TAG_DB=shared_tags
   SHARED_TAG_DB_HOST=shared-tag-db
   SHARED_TAG_DB_PORT=5431 # Ändra till en annan port om nödvändigt
   ```

2. **Starta containern för den delade taggdatabasen:**
   ```bash
   docker compose -f docker-compose.shared-tags.yml up -d
   ```

3. **Konfigurera varje Blombooru-instans:**
   - Gå till **Adminpanel > System** (eller Settings)
   - Aktivera "Shared Tag Database"
   - Ange anslutningsdetaljerna
   - Klicka på "Test Connection" för att verifiera, och spara sedan.

4. **Synkronisera taggar:**
   - Använd knappen "Sync Now" för att manuellt synkronisera taggar mellan instanser
   - Nya taggar delas automatiskt när de skapas

> [!NOTE]
> Lokala taggar har alltid företräde. Om en tagg finns lokalt med en annan kategori än den delade databasen, behålls din lokala kategori.
> **Taggar raderas aldrig från din lokala databas, endast nya taggar importeras.**

### Python

> [!NOTE]
> Python-installationen rekommenderas främst för utvecklingssyften, men kan vara användbar om du kan använda Python venvs men inte Docker.

| Förkrav | Anteckningar |
|:-------------|:------|
| Python 3.10+ | Testad med 3.13.7 & 3.11. Fungerar **inte** med 3.14. |
| PostgreSQL 17 | Krävs |
| Redis 7+ | Valfritt |
| Git | Rekommenderas (alternativt, ladda ner projektet via GitHubs webbplats) |

1. **Klona kodarkivet (repot)**

    ```bash
    git clone https://github.com/mrblomblo/blombooru.git
    cd blombooru
    ```

2. **Skapa en virtuell Python-miljö och installera beroenden**

    ```bash
    python -m venv venv
    source venv/bin/activate  # På Windows, använd `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3. **Skapa en PostgreSQL-databas**  
    Skapa en ny databas och en användare med rättigheter för den databasen. Blombooru kommer att hantera skapandet av nödvändiga tabeller.

4. **Starta en Redis-instans** *(Valfritt)*  
    Om du vill använda högpresterande cachning, se till att en Redis-server (v7+) körs och är tillgänglig. Du kan installera den via ditt operativsystems pakethanterare (t.ex. `apt install redis`, `brew install redis`) eller köra den i en fristående Docker-container.

5. **Första körningen & Onboarding**  
    Starta servern:

    ```bash
    python run.py
    ```

    Öppna nu din webbläsare och navigera till [`http://localhost:8000`](http://localhost:8000). Du kommer att mötas av introduktionssidan. Här kommer du att:
    - Ställa in ditt användarnamn och lösenord för admin.
    - Ange dina anslutningsdetaljer för PostgreSQL. Servern kommer att testa anslutningen innan den fortsätter.
    - *(Valfritt)* Aktivera och konfigurera Redis för högpresterande cachning.
    - Anpassa webbplatsens varumärkesnamn (standard är "Blombooru").

    När detta är inskickat kommer servern att skapa databasschemat och ditt adminkonto.

6. **Köra applikationen igen**  
    Efter den första inställningen kan du köra servern när som helst med samma kommando. Alla inställningar sparas i en `settings.json`-fil i mappen `data`, och all uppladdad media sparas i mappen `media/original`.

## Användarguide

### Logga in

Navigera till webbplatsen och klicka på knappen **Admin Panel** i navigeringsfältet, logga sedan in med uppgifterna du skapade under onboarding. Din inloggningsstatus bevaras med en långlivad cookie för bekvämlighet.

### Adminläge

För att göra några ändringar måste du logga in som admin. Detta skyddar dig från att oavsiktligt radera eller redigera media. När du är inloggad som administratör kan du:

- Ladda upp, redigera eller radera media
- Lägga till, redigera eller ta bort taggar, alias och implikationer
- Organisera och manuellt ordna om album
- Dela media
- Utföra massåtgärder som att mass-tagga, justera medie åldersrating och radera flera objekt från galleriet samtidigt
- Hantera systeminställningar, inklusive instansnamn, teman, säkerhet, säkerhetskopior, inloggningsuppgifter för externa boorus och valfri Redis-cachning

### Lägga till taggar

Du har två sätt att lägga till nya taggar:

#### 1. CSV-import

Använd antingen något liknande [detta skript](https://github.com/DraconicDragon/danbooru-e621-tag-list-processor) från DraconicDragon för att skrapa din egen lista, eller använd den senaste färdigskrapade listan [härifrån](https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru).

> [!IMPORTANT]
> Se till att din CSV-lista följer formatet som specificeras i sektionen "Import Tags from CSV" som visas nedan. För närvarande är endast CSV-listor i "Danbooru"-stil (genererade av skriptet eller funna i de länkade arkiven) fullt kompatibla.

<img width="1920" alt="'Import Tags from CSV' section" src="https://github.com/user-attachments/assets/68be82e9-c734-4967-8c0c-a4a8cab228cf" />

#### 2. Skapa taggar manuellt
  
Mata manuellt in de taggar du vill skapa. Lägg till ett prefix på en tagg, till exempel `meta:`, för att placera den i "meta"-kategorin. De andra tillgängliga tagg-prefixen noteras i sektionen "Add Tags".

*Dubbletter av taggar upptäcks automatiskt och kommer inte att läggas till igen.*

<img width="1920" alt="'Add Tags' section" src="https://github.com/user-attachments/assets/31263bc7-5d18-44bc-b58d-72018f6f8190" />

### Ladda upp media

Du har fyra sätt att lägga till nytt innehåll:

#### 1. Mediafiler

I adminpanelen finns en uppladdningszon där du enkelt kan dra och släppa dina mediafiler. Alternativt kan du klicka på den för att öppna din filutforskare och välja mediafiler.

#### 2. Komprimerade arkiv

Ladda upp ett `.zip`-, `.tar.gz`- eller `.tgz`-arkiv som innehåller din media, så kommer Blombooru att extrahera och bearbeta innehållet.

#### 3. Skanna filsystemet

Flytta dina mediafiler direkt till den konfigurerade lagringskatalogen. Navigera sedan till adminpanelen och klicka på knappen **Scan for Untracked Media**. Servern kommer att skanna katalogen `media/original` (märk väl att det inte är en lättillgänglig katalog), hitta nya filer, generera miniatyrbilder (thumbnails) och lägga till dem i ditt bibliotek.
 
*Dubblettmedia upptäcks automatiskt genom dess hash och kommer inte att importeras på nytt.*

#### 4. Import via extern URL

Klistra in en URL från en booru-sida som stöds (t.ex. de som använder Danbooru- eller Gelbooru-API:et) i importverktyget. Blombooru hämtar metadata (taggar, åldersgräns, källa) och laddar ner den högsta tillgängliga kvalitetsversionen av median, och skapar valfritt automagiskt saknade taggar med rätt kategori (om det finns tillgängligt).

> [!NOTE]
> Vissa boorus kan kräva en API-nyckel eller inloggningsuppgifter för att använda API:et eller för att få tillgång till vissa inlägg. Du kan konfigurera dessa i sektionen Booru Configuration under System-fliken i adminpanelen.

### Taggning & Sökning

- **Autoslutförande (Autocomplete):** När du redigerar ett objekt, börja skriva i taggfältet. En rullbar lista med förslag kommer att visas baserat på befintliga taggar.

- **Taggvisning:** På en mediasida sorteras taggar automatiskt efter kategori (Artist, Character, Copyright, General, Meta) och därefter alfabetiskt inom varje kategori.

- **Söksyntax:** Blombooru stöder en kraftfull Danbooru-kompatibel söksyntax. För en fullständig guide som täcker alla operatorer och kvalifikatorer, se [Söksyntax-guiden](docs/Search%20Syntax%20Guide/syntax_guide-sv.md).

### Dela media

1. Logga in som admin.
2. Navigera till sidan för den media du vill dela.
3. Klicka på knappen **Share** så genereras en unik delnings-URL (`https://localhost:8000/shared/<uuid>`).
4. Alla med denna länk kan visa median i ett förenklat, skrivskyddat gränssnitt. Den delade median kan valfritt inkludera eller exkludera dess medföljande AI-metadata. Delade objekt markeras med en "delad"-ikon i din privata gallerivy.

### Systemuppdaterare

Blombooru inkluderar en inbyggd systemuppdaterare i adminpanelen som gör att du enkelt kan uppdatera din installation till den senaste versionen.

> [!WARNING]
> Säkerhetskopiera alltid din data innan du uppdaterar! Även om uppdateringar är utformade för att vara säkra, kan oväntade problem uppstå, särskilt om du uppdaterar till en ny pre-release eller dev-versionen.

#### Hur man uppdaterar

> [!NOTE]
> Uppdatering via webbgränssnittet stöds endast för direkta Python-installationer. För Docker-instanser uppdaterar du direkt:
> - **Färdigbyggd (GHCR):** `docker compose up -d --pull always`
> - **Lokalt byggd:** `docker compose down && git pull && docker compose -f docker-compose.dev.yml up -d --build`

1. Logga in som admin och navigera till **Adminpanelen**.
2. Välj fliken **System**.
3. Rulla ner till sektionen **System Update**.
4. Klicka på **Check for Updates** för att hämta den senaste versionsinformationen från GitHub.
5. Granska ändringsloggen genom att klicka på **View Changelog** för att se vad som är nytt.
6. Om en uppdatering finns tillgänglig, klicka på **Update to Latest Stable** för att starta uppdateringen.

Uppdateraren hämtar automatiskt den senaste releasetaggen och checkar ut den. Efter uppdateringen, **starta om Blombooru** för att tillämpa ändringarna.

#### Ändringar i beroenden

För direkta Python-installationer installerar uppdateraren automatiskt uppdaterade beroenden om `requirements.txt` har ändrats. Om den automatiska installationen misslyckas kör du manuellt `pip install -r requirements.txt` i din virtuella miljö.

Om konfigurationsfiler (som `docker-compose.yml` eller `example.env`) har ändrats visar uppdateraren ett meddelande med nedladdningslänkar till uppdaterade filer från releasen.

### Kontoåterställning

> [!WARNING]
> Att återställa lösenordet ogiltigförklarar inte befintliga inloggningssessioner (tokens förblir giltiga tills de löper ut, upp till 30 dagar). Om du misstänker att kontot har komprometterats bör du även överväga att rotera din `SECRET_KEY` (sparad i `data/settings.json` eller konfigurerad via `BLOMBOORU_SECRET_KEY`) och starta om instansen, vilket omedelbart ogiltigförklarar alla aktiva sessioner.

Om du har glömt ditt adminlösenord eller behöver ändra administratörens användarnamn kan du använda skriptet `pass_reset.py`.

Minst ett av alternativen `--reset-password`, `--password` eller `--username` måste anges.

**Återställ lösenord interaktivt (rekommenderas):**

Frågar säkert efter lösenord och bekräftelse utan att exponera det i shell-historiken eller processlistan:

```bash
docker compose exec -it web python pass_reset.py --reset-password
```

**Återställ lösenord icke-interaktivt:**

```bash
docker compose exec web python pass_reset.py --password "mynewpassword"
```

**Ändra endast användarnamn:**

```bash
docker compose exec web python pass_reset.py --username "newadmin"
```

**Återställ båda samtidigt:**

```bash
docker compose exec -it web python pass_reset.py --username "newadmin" --reset-password
```

Samma valideringsregler som i webbgränssnittet gäller:

| Fält | Minsta längd | Maxlängd |
|:------|:-----------|:-----------|
| Lösenord | 6 | 50 |
| Användarnamn | 1 | 50 |

> [!NOTE]
> Om du kör Blombooru direkt med Python utelämnar du `docker compose exec web` (eller `docker compose exec -it web`) från kommandona ovan och använder den virtuella miljön för att köra skriptet istället.

### API & Tredjepartsappar

Blombooru implementerar ett **Danbooru v2-kompatibelt API**, vilket gör att du kan använda befintliga tredjeparts-Booru-klienter (som Grabber, Tachiyomi eller BooruNav) för att bläddra i din samling.

#### Anslutningsdetaljer

| Inställning | Värde |
|:--------|:------|
| **Server Type** | Danbooru v2 |
| **URL** | Din server-IP + port (t.ex. `http://192.168.1.10:8000`) eller din domän (t.ex. `https://example.com`) |
| **Authentication** | Stöds via flera metoder (se nedan) |

**Autentiseringsmetoder:**
- **URL-parametrar (Query):** `login` + `api_key`
- **HTTP Basic Auth:** användarnamn + API-nyckel som lösenord
- **Bearer-token:** `Authorization: Bearer <api_key>`

#### Funktioner som stöds

| Funktion | Beskrivning |
|:--------|:------------|
| **Posts** | Full sökförmåga, listning och hämtning av media |
| **Tags** | Tagglistning, sökning, autoslutförande och relaterade taggar |
| **Albums/Pools** | Blombooru-album exponeras som Danbooru "Pools" |
| **Artists** | Blombooru Artist-taggar exponeras som Artists-slutpunkten |

> [!NOTE]
> Skrivoperationer (uppladdning, redigering, etc.) via API:et är skrivskyddade eller simulerade (stubbed) för att förhindra fel i tredjepartsappar. Sociala funktioner såsom röstning, favoriter, kommentarer, forum, DM och wiki-sidor returnerar tomma resultat.

#### Internt API

Blombooru har även ett internt REST-API för administrativa uppgifter, innehållshantering och anpassade automatiseringar. För detaljer om tillgängliga endpoints och autentisering, se den [interna API-dokumentationen](docs/Internal%20API/Introduction.md). Observera att det interna API:et inte har några stabilitetsgarantier och kan ändras mellan versioner, samt att API-dokumentationen endast finns tillgänglig på engelska.

## Teman

Blombooru är designat för att vara enkelt att byta tema på.

- **Temahantering:** Anpassade teman kan skapas, redigeras, exporteras och importeras direkt i adminpanelen utan att behöva starta om servern.

- **CSS-variabler:** Kärnfärgerna styrs av CSS-variabler definierade i varje tema.

## Tekniska detaljer

| Komponent | Teknologi |
|:----------|:-----------|
| **Backend** | FastAPI (Python) |
| **Frontend** | Tailwind CSS (byggs lokalt), Vanilla JavaScript, HTML |
| **Databas** | PostgreSQL 17 |
| **Cachning** | Redis 7+ (Valfritt) |
| **Delade taggar** | Valfri extern PostgreSQL-instans för att dela taggar mellan instanser |
| **Medialagring** | Lokalt filsystem med sökvägar refererade i databasen. Original-metadata bevaras alltid men kan valfritt rensas bort "on-the-fly" i delad media. |
| **Stödda Bildformat** | JPG, PNG, WEBP, GIF, AVIF, JXL, BMP, TIFF, HEIC/HEIF |
| **Stödda Videoformat** | MP4, WEBM, MOV, M4V, MKV, AVI |

## Dokumentation & Gemenskap

- [Söksyntax-guide](docs/Search%20Syntax%20Guide/syntax_guide-sv.md): Fullständig syntaxreferens med exempel.
- [Intern API-dokumentation](docs/Internal%20API/Introduction.md): Endpoints för utvecklare och automatiseringsskript (på engelska).
- [Skärmbildsgalleri](docs/Gallery.md): Visuell översikt av användargränssnittet och funktioner.
- [Ändringslogg](CHANGELOG.md): Sammanfattning av release notes för varje version.
- [Bidra](CONTRIBUTING.md): Riktlinjer för kod- och översättningsbidrag.
- [Säkerhetspolicy](SECURITY.md): Sårbarhetsrapportering och säkerhetsinformation.
- [Tack & Erkännanden](ACKNOWLEDGEMENTS.md): Erkännanden för tredjepartsbibliotek och resurser.

## Ansvarsfriskrivning

Detta är en egenhostad (self-hosted) enanvändarapplikation. Som ensam administratör är du uteslutande ansvarig för allt innehåll du laddar upp, hanterar och delar med denna programvara.

Se till att din användning följer alla tillämpliga lagar, särskilt gällande upphovsrätt och integriteten för alla individer som avbildas eller identifieras i din media.

Utvecklarna och bidragsgivarna till detta projekt tar **inget ansvar** för något olagligt, intrångsgörande eller olämpligt innehåll som hostas av någon användare. Programvaran tillhandahålls "i befintligt skick" (as is) utan garantier. För den fullständiga ansvarsfriskrivningen, vänligen se vår [Disclaimer of Liability](https://github.com/mrblomblo/blombooru/blob/main/DISCLAIMER.md).

## Licens

Detta projekt är licensierat under MIT-licensen. Se filen [LICENSE](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt) för mer information.
