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

<p align="center"><b>Ditt personliga, egenhostade verktyg för mediataggning.</b></p>

Blombooru är ett privat enanvändaralternativ till bild-boorus som Danbooru och Gelbooru. Det är utformat för individer som vill ha en kraftfull, lättanvänd och modern lösning för att organisera och tagga sina personliga mediasamlingar. Med fokus på en stilren användarupplevelse, robust administration och enkel anpassning ger Blombooru dig full kontroll över ditt bibliotek.

> [!NOTE]
> Lokalisering till svenska: @mrblomblo  
> Senast uppdaterad 25 februari 2026

<details>
<summary>Visa skärmdumpar</summary>

**Startsida**
<img width="1920" alt="Homepage" src="https://github.com/user-attachments/assets/eaa9b99e-ff64-439f-bb00-e5a37c53db3a" />

**Mediavisare**
<img width="1920" alt="Media-viewer page" src="https://github.com/user-attachments/assets/c3dcebf7-2cee-475b-b428-54986a27c42c" />

**Sida för delad media**
<img width="1920" alt="Shared media page" src="https://github.com/user-attachments/assets/6fa43d69-eb44-46a4-85b4-99e85322fbea" />

**Adminpanel**
<img width="1920" alt="Admin panel" src="https://github.com/user-attachments/assets/19db7c83-bbcb-48c6-a505-78f03ea6964e" />

</details>

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
    - [Grundläggande taggar](#grundläggande-taggar)
    - [Intervall (Ranges)](#intervall-ranges)
    - [Meta-kvalifikatorer](#meta-kvalifikatorer)
    - [Taggantal](#taggantal)
    - [Sortering](#sortering)
  - [Dela media](#dela-media)
  - [Systemuppdaterare](#systemuppdaterare)
    - [Hur man uppdaterar](#hur-man-uppdaterar)
    - [Ändringar i beroenden](#ändringar-i-beroenden)
  - [API \& Tredjepartsappar](#api--tredjepartsappar)
    - [Anslutningsdetaljer](#anslutningsdetaljer)
    - [Funktioner som stöds](#funktioner-som-stöds)
- [Teman](#teman)
- [Tekniska detaljer](#tekniska-detaljer)
- [Ansvarsfriskrivning](#ansvarsfriskrivning)
- [Licens](#licens)

## Nyckelfunktioner

### Kärnfunktioner

- **Taggning i Danbooru-stil:** Ett bekant och kraftfullt taggningssystem med kategorier (artist, character, copyright, etc.), tagg-baserad sökning och exkludering med negativa taggar.

- **Enkel import av taggdatabaser:** Importera anpassade tagglistor via en enkel CSV-uppladdning i adminpanelen för att hålla ditt system uppdaterat.

- **Album:** Organisera din media i album, som kan innehålla både mediaobjekt och underalbum för obegränsad nästling och organisering.

- **Mediarelationer:** Länka relaterad media med förälder-barn-relationer (parent-child). Gruppera bildvariationer, flersidiga serier och mer—vilket håller relaterat innehåll lättillgängligt.

- **Import från externa Boorus:** Importera sömlöst inlägg från Danbooru och andra booru-sidor (som Danbooru, Gelbooru, etc.) genom att helt enkelt klistra in inläggets URL. Taggar, åldersgräns, källa och media hämtas och kartläggs automatiskt.

### AI & Automatisering

- **AI-vänlig:** Visa enkelt medföljande AI-metadata för nästan all media genererad med SwarmUI, ComfyUI, A1111 med flera. Du kan till och med lägga till taggar i taggredigeraren direkt från AI-prompten.

- **Automatisk taggning:** Påskynda taggningen med WDv3 Auto Tagger-integrationen, som analyserar bilder och föreslår korrekta taggar med ett enda klick.

### Säkerhet & Delning

- **Säkert läge:** När detta är aktiverat måste användare logga in för att interagera med Blombooru. Offentliga rutter såsom delningslänkar och statiska filer förblir offentliga. Perfekt för privata samlingar som du inte vill att någon annan i hushållet ska se!

- **Säker surfning:** Bläddra i din samling utan rädsla för oavsiktliga ändringar. Alla hanteringsåtgärder (uppladdning, redigering, radering) kräver att du är inloggad som administratör.

- **Säker mediadelning:** Generera unika, permanenta länkar för att dela specifik media. Delade objekt presenteras i en avskalad, säker vy med valfri delning av AI-metadata.

### Anpassning & Teman

- **Modernt & responsivt gränssnitt:** Byggt med Tailwind CSS för en vacker och konsekvent upplevelse på både datorer och mobila enheter.

- **Mycket anpassningsbara teman:** Skräddarsy utseendet med hjälp av enkla CSS-variabler. Släpp in nya `.css`-filer i `themes`-mappen, registrera dem i `themes.py` och starta om.

- **Många teman att välja mellan:** Blombooru levereras med de fyra färgpaletterna från Catppuccin, Gruvbox (ljus & mörk), Everforest (ljus & mörk), OLED och mer!

### Flexibilitet & Integration

- **Flexibla mediauppladdningar:** Lägg till media via dra-och-släpp, genom att importera ett komprimerat arkiv, eller genom att placera filer i lagringsmappen och trycka på "Skanna efter ospårad media".

- **Användarvänlig introduktion (Onboarding):** En enkel installationsprocess för första gången för att konfigurera ditt adminkonto, databasanslutning och varumärkesnamn.

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
| **Förhandsversion** | `pre` | Testa kommande versioner, följer den senaste förhandsversionen (pre-release) |
| **Låst version** | `1.2.3` / `1.2` / `1` | Låsa till en specifik stabil version |
| **Låst förhandsversion** | `1.2.3-rc.1` | Låsa till en specifik förhandsversion |
| **Utvecklarversion** | Lokal build | För bidragsgivare, ändra källkoden |

#### Snabbstart (Färdigbyggd avbildning)

1. **Ladda ner nödvändiga filer**

    Skapa en mapp för Blombooru (t.ex. `blombooru`), ladda sedan ner filerna `docker-compose.yml` och `example.env` från den [senaste releasen](https://github.com/mrblomblo/blombooru/releases/latest) och placera dem i mappen.

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
    Navigera till instanskatalogen och använd den inbyggda uppdateraren via adminpanelen, eller manuellt:

    ```bash
    cd ~/blombooru-instans1
    git pull
    docker compose down && docker compose up --build -d
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
- Lägga till eller ta bort taggar
- Dela media
- Utföra massåtgärder som att radera flera objekt från galleriet samtidigt
- Hantera systeminställningar, inklusive varumärke, säkerhet, inloggningsuppgifter för externa boorus och valfri Redis-cachning

### Lägga till taggar

Du har två sätt att lägga till nya taggar:

#### 1. CSV-import

Använd antingen något i stil med [detta skript](https://github.com/DraconicDragon/danbooru-e621-tag-list-processor) av DraconicDragon för att skrapa din egen lista, eller använd en av de för-skrapade listorna [härifrån](https://civitai.com/models/950325/danboorue621-autocomplete-tag-lists-incl-aliases-krita-ai-support) eller [härifrån](https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru).

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

- **Söksyntax:** Blombooru stöder en kraftfull Danbooru-kompatibel söksyntax.

#### Grundläggande taggar

| Syntax | Beskrivning |
|:-------|:------------|
| `tag1 tag2` | Hitta media med både `tag1` OCH `tag2` |
| `-tag1` | Exkludera media med `tag1` |
| `tag*` | Sökning med jokertecken (hittar `tag_name`, `tag_stuff`, etc.) |
| `?tag` | Hitta media med noll eller ett tecken framför `tag` |

#### Intervall (Ranges)

De flesta numeriska och datum-kvalifikatorer stöder intervalloperatorer:

| Syntax | Beskrivning |
|:-------|:------------|
| `id:100` | Exakt matchning (`x == 100`) |
| `id:100..200` | Mellan, inklusive (`100 <= x <= 200`) |
| `id:>=100` | Större än eller lika med (`x >= 100`) |
| `id:>100` | Större än (`x > 100`) |
| `id:<=100` | Mindre än eller lika med (`x <= 100`) |
| `id:<100` | Mindre än (`x < 100`) |
| `id:1,2,3` | I lista (`x` är 1, 2 eller 3) |

#### Meta-kvalifikatorer

| Kvalifikator | Beskrivning | Exempel |
|:----------|:------------|:-----------|
| `id` | Sök via internt ID | `id:100..200`, `id:>500` |
| `width`, `height` | Sök via bilddimensioner (pixlar) | `width:>=1920`, `height:1080` |
| `filesize` | Sök via filstorlek med enheterna `kb`, `mb`, `gb`, `b`. Stöder "luddig" (fuzzy) matchning: `filesize:52MB` hittar `52.0MB` till `52.99MB`. | `filesize:1mb..5mb`, `filesize:52MB` |
| `date` | Sök på uppladdningsdatum (`ÅÅÅÅ-MM-DD`) | `date:2024-01-01` |
| `age` | Sök på ålder relativt till nu (`s`, `mi`, `h`, `d`, `w`, `mo`, `y`). Obs: `<` betyder "nyare än" (lägre ålder). | `age:<24h` (mindre än 1 dag gammal), `age:1w..1mo` |
| `rating` | Filtrera på åldersgräns: `s`/`safe`, `q`/`questionable`, `e`/`explicit`. Stöder listor. | `rating:s,q`, `-rating:e` |
| `source` | Sök källa. Använd `none` för saknade källor, `http` för webb-URL:er. | `source:none`, `source:http`, `source:twitter` |
| `filetype` | Sök på filändelse | `filetype:png`, `filetype:gif` |
| `md5` | Sök på fil-hash (exakt) | `md5:d34e4c...` |
| `pool`, `album` | Sök via album/pool-ID eller namn. `any`/`none` stöds. | `album:any`, `pool:favorites`, `pool:5` |
| `parent` | Sök på föräldra-ID (parent). `any`/`none` stöds. | `parent:none`, `parent:123` |
| `child` | Filtrera föräldrainlägg på barn (children). `any`/`none` stöds. | `child:any` (har barn), `child:none` |
| `duration` | Sök längd på video/gif i sekunder | `duration:>60` |

> [!NOTE]
> `duration` kanske inte är satt på alla GIF:ar.

#### Taggantal

Filtrera på antalet taggar ett inlägg har:

| Kvalifikator | Beskrivning |
|:----------|:------------|
| `tagcount` | Totalt antal taggar |
| `gentags` | Allmänna taggar (General) |
| `arttags` | Artist-taggar |
| `chartags` | Karaktärstaggar (Character) |
| `copytags` | Upphovsrättstaggar (Copyright) |
| `metatags` | Meta-taggar |

**Exempel:** `tagcount:<10` (inlägg med få taggar), `arttags:>=1` (inlägg med minst 1 artist-tagg)

#### Sortering

Sortera resultat med `order:{värde}`. Lägg till suffixet `_asc` eller `_desc` där det är tillämpligt (standard är oftast fallande/descending).

| Värde | Beskrivning |
|:------|:------------|
| `id` / `id_desc` | Nyaste uppladdningarna först (standard) |
| `id_asc` | Äldsta uppladdningarna först |
| `filesize` | Största filerna först |
| `landscape` | Bredaste bildförhållandet (aspect ratio) först |
| `portrait` | Högsta bildförhållandet först |
| `md5` | Sortera med MD5-hash (deterministisk, slumpmässig blandning) |
| `custom` | Sortera efter ordningen som ges i `id:list`. Exempel: `id:3,1,2 order:custom` |

### Dela media

1. Logga in som admin.
2. Navigera till sidan för den media du vill dela.
3. Klicka på knappen **Share** så genereras en unik delnings-URL (`https://localhost:8000/shared/<uuid>`).
4. Alla med denna länk kan visa median i ett förenklat, skrivskyddat gränssnitt. Den delade median kan valfritt inkludera eller exkludera dess medföljande AI-metadata. Delade objekt markeras med en "delad"-ikon i din privata gallerivy.

### Systemuppdaterare

Blombooru inkluderar en inbyggd systemuppdaterare i adminpanelen som gör att du enkelt kan uppdatera din installation till den senaste versionen.

> [!WARNING]
> Säkerhetskopiera alltid dina data innan du uppdaterar! Även om uppdateringar är utformade för att vara säkra, kan oväntade problem uppstå, särskilt om du uppdaterar till en ny huvudversion eller den senaste utvecklarversionen (dev build).

#### Hur man uppdaterar

1. Logga in som admin och navigera till **Adminpanelen**.
2. Välj fliken **System**.
3. Rulla ner till sektionen **System Update**.
4. Klicka på **Check for Updates** för att hämta den senaste versionsinformationen från GitHub.
5. Granska ändringsloggen genom att klicka på **View Changelog** för att se vad som är nytt.
6. Om uppdateringar finns tillgängliga, klicka på antingen:
   - **Update to Latest Dev** - Uppdaterar till den senaste commiten på `main`-grenen (bleeding edge)
   - **Update to Latest Stable** - Uppdaterar till den senaste taggade releasen (rekommenderas)

Uppdateraren kommer automatiskt att köra `git pull` (eller `git checkout <tag>`) och visa utdata. Efter uppdateringen, **starta om Blombooru** för att tillämpa ändringarna:

- **Docker:** `docker compose down && docker compose up -d`

> [!NOTE]
> Docker-uppdateringar stöds inte för tillfället inifrån webbgränssnittet. När Blombooru körs i Docker visas en varning som ber dig att manuellt köra `git pull` på värddatorn och bygga om containern.

- **Python:** Stoppa servern (Ctrl+C) och kör `python run.py` igen

#### Ändringar i beroenden

Om uppdateringen innehåller ändringar i `requirements.txt` eller `docker-compose.yml` kommer uppdateraren att visa ett meddelande. Du behöver då:

- **Docker:** Köra `docker compose down && docker compose up --build -d` för att bygga om containern.
- **Python:** Stoppa servern (Ctrl+C) och köra `pip install -r requirements.txt` innan du kör `python run.py` igen.

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

## Teman

Blombooru är designat för att vara enkelt att byta tema på.

- **CSS-variabler:** Kärnfärgerna styrs av CSS-variabler definierade i standardtemat/-teman.

- **Anpassade teman:** För att skapa ditt eget tema, skapa helt enkelt en ny `.css`-fil i katalogen `frontend/static/themes/`, kopiera hela innehållet från temat `default_dark.css` och börja anpassa! Registrera det sedan i filen `backend/app/themes.py` för att kunna använda det.

Ditt nya tema kommer automatiskt att dyka upp i rullgardinsmenyn för temaval i adminpanelen.

## Tekniska detaljer

| Komponent | Teknologi |
|:----------|:-----------|
| **Backend** | FastAPI (Python) |
| **Frontend** | Tailwind CSS (byggs lokalt), Vanilla JavaScript, HTML |
| **Databas** | PostgreSQL 17 |
| **Cachning** | Redis 7+ (Valfritt) |
| **Delade taggar** | Valfri extern PostgreSQL-instans för att dela taggar mellan instanser |
| **Medialagring** | Lokalt filsystem med sökvägar refererade i databasen. Original-metadata bevaras alltid men kan valfritt rensas bort "on-the-fly" i delad media. |
| **Format som stöds** | JPG, PNG, WEBP, GIF, MP4, WEBM |

## Ansvarsfriskrivning

Detta är en egenhostad (self-hosted) enanvändarapplikation. Som ensam administratör är du uteslutande ansvarig för allt innehåll du laddar upp, hanterar och delar med denna programvara.

Se till att din användning följer alla tillämpliga lagar, särskilt gällande upphovsrätt och integriteten för alla individer som avbildas eller identifieras i din media.

Utvecklarna och bidragsgivarna till detta projekt tar **inget ansvar** för något olagligt, intrångsgörande eller olämpligt innehåll som hostas av någon användare. Programvaran tillhandahålls "i befintligt skick" (as is) utan garantier. För den fullständiga ansvarsfriskrivningen, vänligen se vår [Disclaimer of Liability](https://github.com/mrblomblo/blombooru/blob/main/DISCLAIMER.md).

## Licens

Detta projekt är licensierat under MIT-licensen. Se filen [LICENSE](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt) för mer information.
