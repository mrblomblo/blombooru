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

<p align="center"><b>您的个人自托管媒体标注工具。</b></p>

Blombooru 是 Danbooru 和 Gelbooru 等图库站（Booru）的私密、单用户替代方案。它专为那些希望以强大、易用且现代化的方式组织和标注个人媒体收藏的用户而设计。Blombooru 专注于清爽的用户体验、稳健的管理功能和便捷的自定义，让您完全掌控自己的媒体库。

<details>
<summary>查看截图</summary>

**首页**
<img width="1920" alt="Homepage" src="https://github.com/user-attachments/assets/eaa9b99e-ff64-439f-bb00-e5a37c53db3a" />

**媒体查看页**
<img width="1920" alt="Media-viewer page" src="https://github.com/user-attachments/assets/c3dcebf7-2cee-475b-b428-54986a27c42c" />

**媒体共享页**
<img width="1920" alt="Shared media page" src="https://github.com/user-attachments/assets/6fa43d69-eb44-46a4-85b4-99e85322fbea" />

**管理面板**
<img width="1920" alt="Admin panel" src="https://github.com/user-attachments/assets/19db7c83-bbcb-48c6-a505-78f03ea6964e" />

</details>

## 目录

- [目录](#目录)
- [主要功能](#主要功能)
  - [核心功能](#核心功能)
  - [AI 与自动化](#ai-与自动化)
  - [安全与共享](#安全与共享)
  - [自定义与主题](#自定义与主题)
  - [灵活性与集成](#灵活性与集成)
- [安装与设置](#安装与设置)
  - [Docker *(推荐)*](#docker-推荐)
    - [部署选项](#部署选项)
    - [快速入门 (使用预构建镜像)](#快速入门-使用预构建镜像)
    - [使用预发布版本](#使用预发布版本)
    - [开发版本 (本地构建)](#开发版本-本地构建)
    - [运行多个实例](#运行多个实例)
    - [在实例之间共享标签](#在实例之间共享标签)
  - [Python](#python)
- [使用指南](#使用指南)
  - [登录](#登录)
  - [管理员模式](#管理员模式)
  - [添加标签](#添加标签)
    - [1. CSV 导入](#1-csv-导入)
    - [2. 手动创建标签](#2-手动创建标签)
  - [上传媒体](#上传媒体)
    - [1. 媒体文件](#1-媒体文件)
    - [2. 压缩包](#2-压缩包)
    - [3. 文件系统扫描](#3-文件系统扫描)
    - [4. 外部 URL 导入](#4-外部-url-导入)
  - [标注与搜索](#标注与搜索)
    - [基础标签](#基础标签)
    - [范围查询](#范围查询)
    - [元限定符](#元限定符)
    - [标签数量](#标签数量)
    - [排序](#排序)
  - [分享媒体](#分享媒体)
  - [系统更新器](#系统更新器)
    - [如何更新](#如何更新)
    - [依赖项变更](#依赖项变更)
  - [API 与第三方应用](#api-与第三方应用)
    - [连接详情](#连接详情)
    - [支持的功能](#支持的功能)
- [主题定制](#主题定制)
- [技术细节](#技术细节)
- [免责声明](#免责声明)
- [许可证](#许可证)

## 主要功能

### 核心功能

- **Danbooru 风格标注：** 熟悉且强大的标签系统，支持类别（画师、角色、版权等）、基于标签的搜索以及负面标签排除。
- **便捷的标签库导入：** 通过管理面板上传 CSV 文件即可导入自定义标签列表，让您的系统紧跟潮流。
- **相册：** 将媒体整理到相册中，相册可同时容纳媒体项目和其他子相册，实现无限层级的嵌套和组织。
- **媒体关联：** 使用父子关系链接相关媒体。可以将变体图、多页漫画等进行分组，方便随时访问相关内容。
- **外部 Booru 导入：** 只需粘贴作品 URL，即可从 Danbooru、Gelbooru 等站点无缝导入作品。标签、分级、来源和媒体文件都会被自动获取并映射。

### AI 与自动化

- **AI 友好：** 轻松查看由 SwarmUI、ComfyUI、A1111 等生成的媒体所附带的 AI 元数据。您甚至可以直接从 AI 提示词中将标签追加到标签编辑器中。
- **自动标注：** 集成 WDv3 自动**标注**器，一键分析图像并建议准确的标签，从而加速**标注**进程。

### 安全与共享

- **安全模式：** 启用后，用户必须登录才能访问 Blombooru。分享链接和静态文件等公共路由仍保持公开。非常适合不想被家人看到的私人收藏！
- **安全浏览：** 无需担心误删或误改。所有管理操作（上传、编辑、删除）都必须以管理员身份登录后执行。
- **安全媒体共享：** 生成唯一的永久链接以分享特定媒体。共享项以精简且安全的视图呈现，并可选择是否包含 AI 元数据。

### 自定义与主题

- **现代化响应式 UI：** 使用 Tailwind CSS 构建，在桌面和移动设备上都能获得美观一致的体验。
- **高度可定制的主题：** 使用简单的 CSS 变量调整外观。只需将新的 `.css` 文件放入 `themes` 文件夹，在 `themes.py` 中注册并重启即可。
- **多种主题可选：** Blombooru 内置了四种 Catppuccin 色板、Gruvbox（明/暗）、Everforest（明/暗）、OLED 等主题。

### 灵活性与集成

- **灵活的媒体上传：** 通过拖放、导入压缩包或将文件放入存储目录并点击“扫描未追踪媒体”来添加内容。
- **用户友好的新手引导：** 简单的首次设置流程，用于配置管理员账号、数据库连接和品牌名称。
- **高性能缓存：** 可选的 Redis 集成，为重型查询、自动完成和 Danbooru 兼容的 API 请求提供极速响应。
- **共享标签数据库：** 可选功能，通过专用的中心化 PostgreSQL 数据库在多个 Blombooru 实例之间共享标签。
- **Danbooru v2 API 兼容性：** 借助内置的兼容层，您可以使用喜爱的第三方图库客户端（如 Grabber、Tachiyomi 或 BooruNav）连接到 Blombooru。

## 安装与设置

您可以选择在 Docker 容器中使用 Blombooru（推荐）或直接使用 Python 运行。

### Docker *(推荐)*

这是使用 Blombooru 的推荐方法。预构建镜像可在 GitHub Container Registry 获取。

| 前提条件 | 说明 |
|:-------------|:------|
| Docker | 必须安装 |

#### 部署选项

| 选项 | 镜像标签 | 使用场景 |
|:-------|:----------|:---------|
| **最新稳定版** | `latest` (default) | 生产场景使用, 跟踪最新的GitHub稳定版 |
| **预发行版** | `pre` | 测试即将到来的版本，跟踪最新的GitHub预发行版本 |
| **固定稳定版** | `1.2.3` / `1.2` / `1` | 固定到一个特定的稳定版本 |
| **固定预发行版** | `1.2.3-rc.1` | 固定到一个特定的预发行版本 |
| **开发版** | 本地构建 | 贡献，对源码有修改 |

#### 快速入门 (使用预构建镜像)

1. **下载所需文件**
    创建一个文件夹（如 `blombooru`），从[最新发布版本](https://github.com/mrblomblo/blombooru/releases/latest)中下载 `docker-compose.yml` 和 `example.env` 并放入其中。

2. **自定义环境变量**
    将 `example.env` 复制并重命名为 `.env`。然后使用您喜欢的文本编辑器打开新创建的文件，并在每行的“=”之后编辑相应的值。最重要的修改项是 `POSTGRES_PASSWORD` 的密码。其他部分*可以*保持原样，除非，比如说，端口 8000 已被其他程序占用。

3. **首次运行与引导设置**
    在文件夹内运行以下命令启动容器：

    ```bash
    docker compose up -d
    ```

    *你可能需要使用`sudo`或从一个有最高权限的终端运行该命令。*

    在浏览器中访问 `http://localhost:<端口>`（将`<端口`替换为`.env`中指定的应用端口）。你将访问引导页面并执行下面的操作：
    - 设置管理员账号及密码
    - 输入PostgreSQL 连接信息。服务器将在继续操作前先测试连接。除非您更改了 `POSTGRES_DB` 和/或 `POSTGRES_USER` 的值，否则您只需填写在 `.env` 文件中设置的密码。请勿更改数据库主机地址。
    - *(可选)* 开启并配置Redis以进行缓存
    - 自定义站点名称（默认为Blombooru）。

    一旦提交完成，服务器将会创建数据库架构以及您的管理员账户。

4. **再次运行应用**
    在初始设置后，可以通过下面的指令运行服务器（再次重申，确保执行目录为`docker-compose.yml`所在的目录）

    ```bash
    docker compose up -d
    ```

    *你可能需要使用`sudo`或从一个有最高权限的终端运行该命令。*

    所有的设置都被存储在`data`文件夹下的`settings.json`文件中，所有的上传媒体文件都存储在 `media/original` 文件夹下。需要注意的是这些文件夹不易访问，并且不会在“Blombooru”文件夹的根目录下创建。

5. **关闭容器**

    ```bash
    docker compose down
    ```

#### 使用预发布版本

若要使用最新的预发布版，请设置 `BLOMBOORU_TAG` 环境变量：

```bash
BLOMBOORU_TAG=pre docker compose up -d
```

或者在`.env`文件中添加`BLOMBOORU_TAG=pre`。

> [!WARNING]
> 预发布版本可能包含破坏性更改或 Bug。仅建议用于测试即将发布的新功能。

#### 开发版本 (本地构建)
对于贡献者或希望从源码构建的用户：

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

这将通过使用`docker-compose.dev.yml`从本地源码构建镜像。

#### 运行多个实例

如果您需要运行多个独立的 Blombooru 实例（例如，为不同目的或用户准备不同的媒体库），Docker Compose 让这一切变得非常简单。每个实例都将拥有相互隔离的数据库、Redis 缓存、媒体存储和配置。

**前提条件:**

- 已完成至少一次标准 Docker 安装（见上文）
- 熟悉基本的命令行操作

**设置步骤:**

1. **为每个实例创建独立的目录**  
    每个实例应位于其专属的文件夹中（例如 booru_personal 和 booru_work）以保证有序以及数据独立。

    ```bash
    mkdir -p ~/blombooru-instance1
    mkdir -p ~/blombooru-instance2
    cd ~/blombooru-instance1
    ```

2. **为每个实例设定文件**  
    将`docker-compose.yml` and `example.env` 复制到每个文件夹：

    ```bash
    # 仅为举例，请替换为文件实际路径
    cp ~/blombooru/docker-compose.yml ~/blombooru/example.env ~/blombooru-instance1/
    cp ~/blombooru/docker-compose.yml ~/blombooru/example.env ~/blombooru-instance2/
    ```

3. **复制到每个文件夹。**  
    在每个实例的文件夹中创建一个`.env`（拷贝自 from `example.env`）并为他们分配 **不同的端口号**以避免冲突:

    **实例1** (`~/blombooru-instance1/.env`):

    ```env
    APP_PORT=8000
    POSTGRES_PORT=5432
    REDIS_PORT=6379
    POSTGRES_PASSWORD=your_secure_password_here
    # ... other settings
    ```

    **实例2** (`~/blombooru-instance2/.env`):

    ```env
    APP_PORT=8001
    POSTGRES_PORT=5433
    REDIS_PORT=6380
    POSTGRES_PASSWORD=different_secure_password
    # ... other settings
    ```

> [!IMPORTANT]
> 每个实例必须使用唯一的`APP_PORT`、`POSTGRES_PORT` 和 `REDIS_PORT`。使用相同的端口将导致冲突并阻止实例启动。

> [!NOTE] 
> `POSTGRES_PORT` 和 `REDIS_PORT` **仅用于**将端口映射到宿主机，或在外部 PostgreSQL/Redis 服务器使用非标准端口时使用。在 Docker 内部，容器始终使用默认内部端口（PostgreSQL: `5432`, Redis: `6379`）进行通信。

1. **独立启动每个实例**  
    进入每个实例的目录并使用 Docker Compose 启动：

    ```bash
    cd ~/blombooru-instance1
    docker compose up --build -d
    ```

    ```bash
    cd ~/blombooru-instance2
    docker compose up --build -d
    ```

   Docker Compose 会自动使用目录名作为前缀命名容器（例如 `blombooru-instance1-web-1`），从而防止命名冲突。

2. **完成每个实例的新手引导**
    每个实例都是完全独立的，因此您需要分别完成新手引导流程：
    - 实例 1: `http://localhost:8000`
    - 实例 2: `http://localhost:8001`

**管理多个实例:**

- **查看正在运行的实例:**  

    ```bash
    docker ps
    ```

- **停止特定实例:**  

    ```bash
    cd ~/blombooru-instance1
    docker compose down
    ```

- **查看特定实例的日志**  

    ```bash
    cd ~/blombooru-instance1
    docker compose logs -f
    ```

- **更新特定实例:**  
    进入实例目录并通过管理面板使用内置更新器，或手动更新：

    ```bash
    cd ~/blombooru-instance1
    git pull
    docker compose down && docker compose up --build -d
    ```

**数据隔离:**

每个实例都保持完全独立的：

- **数据库** – 存储在以实例目录命名的 Docker 卷中 (例如`blombooru-instance1_pgdata`)
- **媒体文件** –存储在独立的 Docker 卷中 (e.g., `blombooru-instance1_media`)
- **配置** – 每个实例在自己的卷中都有专属的 `settings.json`
- **Redis 缓存** – 带有隔离数据的独立 Redis 实例

这意味着您可以安全地删除、更新或修改其中一个实例，而不会影响其它任何实例。

#### 在实例之间共享标签

如果您希望多个 Blombooru 实例共享同一个标签数据库（这样在一个实例中创建的标签在其它实例中也可用），您可以启用可选的 **S共享标签数据库功能**。请从 [最新发布版本](https://github.com/mrblomblo/blombooru/releases/latest)下载 `docker-compose.shared-tags.yml` f, 将其放入与您的 `docker-compose.yml` 相同的目录中, 并按照以下步骤操作（或者，如果您已有现成的 PostgreSQL 数据库，可以跳过步骤 1 和 2）：

1. **编辑将托管共享标签数据库实例的 .env 文件：**
   - 调整该实例` .env `文件中的以下行：

   ```env
   SHARED_TAGS_ENABLED=false # 设置为 true 以启用共享标签数据库
   SHARED_TAG_DB_USER=postgres
   SHARED_TAG_DB_PASSWORD=supersecretsharedtagdbpassword # 修改为安全密码
   SHARED_TAG_DB=shared_tags
   SHARED_TAG_DB_HOST=shared-tag-db
   SHARED_TAG_DB_PORT=5431 # 如果需要，修改为不同的端口
   ```

2. **启动共享标签数据库容器：**

   ```bash
   docker compose -f docker-compose.shared-tags.yml up -d
   ```

3. **配置每个 Blombooru 实例：**
   - 前往  **管理面板 > 设置**
   - 启用“共享标签数据库”
   - 输入连接详情
   - 点击“测试连接”进行验证，然后保存

4. **同步标签：**
   - 使用“立即同步”按钮在实例之间手动同步标签
   - 新标签在创建时会自动共享

> [!NOTE]
> 本地标签始终优先。如果某个标签在本地已存在且类别与共享数据库不同，则保留您的本地类别。
> **标签永远不会从您的本地数据库中删除，系统只会导入新的标签。**

### Python

> [!NOTE]
> Python 安装主要建议用于开发目的，但如果您能使用 Python 虚拟环境（venv）却无法使用 Docker，它也非常有用。

| 前提条件 | 说明 |
|:-------------|:------|
| Python 3.10+ | 已在 3.13.7 和 3.11 上测试。**不**支持 3.14。 |
| PostgreSQL 17 | 必须 |
| Redis 7+ | 可选 |
| Git | 推荐 (或直接从 GitHub 下载项目) |

1. **克隆仓库**

    ```bash
    git clone https://github.com/mrblomblo/blombooru.git
    cd blombooru
    ```

2. **创建 Python 虚拟环境并安装依赖**

    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows 用户请使用 `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3. **创建 PostgreSQL 数据库**  
    创建一个新数据库及拥有该库权限的用户。Blombooru 会自动处理表结构的创建。

4. **启动 Redis 实例** *(可选)*
    如果您希望使用高性能缓存，请确保 Redis 服务器 (v7+) 正在运行且可访问。您可以通过系统包管理器安装 (e.g., `apt install redis`, `brew install redis`) 或在独立的 Docker 容器中运行。

5. **首次运行与新手引导**  
    启动服务器：

    ```bash
    python run.py
    ```

    在浏览器中访问 `http://localhost:<端口>`（将`<端口`替换为`.env`中指定的应用端口）。你将访问引导页面并执行下面的操作：
    - 设置管理员账号及密码
    - 输入PostgreSQL 连接信息。服务器将在继续操作前先测试连接。除非您更改了 `POSTGRES_DB` 和/或 `POSTGRES_USER` 的值，否则您只需填写在 `.env` 文件中设置的密码。请勿更改数据库主机地址。
    - *(可选)* 开启并配置Redis以进行缓存
    - 自定义站点名称（默认为Blombooru）。

    一旦提交完成，服务器将会创建数据库架构以及您的管理员账户。

6. **再次运行程序**  
    初始设置完成后，您可以随时使用相同的命令运行服务器。所有设置均保存在 `data`文件夹的`settings.json`中，媒体文件保存在`media/original`文件夹。

## 使用指南

### 登录

访问站点并点击导航栏中的 **管理面板 (Admin Panel)** 按钮，然后使用您在初始设置期间创建的凭据登录。为了方便使用，系统会通过长效 Cookie 保留您的登录状态。

### 管理员模式

若要进行任何更改，您必须以管理员身份登录。这可以防止您误删或误改媒体。以管理员身份登录后，您可以：

- 上传、编辑或删除媒体
- 添加或删除标签
- 分享媒体
- 执行批量操作，如从图库中批量删除项目
- 管理系统设置，包括品牌、安全、外部 Booru 凭据以及可选的 Redis 缓存

### 添加标签

有两种方法可以添加新标签：

#### 1. CSV 导入

您可以使用由 DraconicDragon 编写的[此脚本](https://github.com/DraconicDragon/danbooru-e621-tag-list-processor)来爬取自己的列表，或者使用来自 [此处](https://civitai.com/models/950325/danboorue621-autocomplete-tag-lists-incl-aliases-krita-ai-support) 或 [此处](https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru) 的预爬取列表。

> [!IMPORTANT]
> 请确保您的 CSV 列表符合下文“从 CSV 导入标签”部分指定的格式。目前，仅由上述脚本生成或在链接存档中找到的“Danbooru”风格 CSV 列表完全兼容。

<img width="1920" alt="'Import Tags from CSV' section" src="https://github.com/user-attachments/assets/68be82e9-c734-4967-8c0c-a4a8cab228cf" />

#### 2. 手动创建标签
  
手动输入您要创建的标签。您可以为标签添加前缀，例如使用 `meta:` 前缀将其归入“元标签”类别。其它可用的标签前缀在“添加标签”部分有详细说明。

*重复标签会被自动检测，不会被重复添加。*

<img width="1920" alt="'Add Tags' section" src="https://github.com/user-attachments/assets/31263bc7-5d18-44bc-b58d-72018f6f8190" />

### 上传媒体

有四种方法可以添加新内容：

#### 1. 媒体文件

在管理面板中有一个上传区，您可以直接拖放媒体文件。或者，您可以点击它打开文件浏览器来选择媒体文件。

#### 2. 压缩包

上传包含媒体的 `.zip`、`.tar.gz` 或 `.tgz` 压缩包，Blombooru 会自动解压并处理其中的内容。

#### 3. 文件系统扫描

直接将媒体文件移动到配置的存储目录中。然后，前往管理面板并点击 **扫描未追踪媒体 (Scan for Untracked Media)** 按钮。服务器将扫描 `media/original` 目录（请注意，这是一个不容易直接访问的目录），寻找新文件、生成缩略图并将其添加到库中。
  
*重复媒体会通过哈希值自动检测，不会被重复导入。*

#### 4. 外部 URL 导入

将支持的 Booru 站点（例如使用 Danbooru 或 Gelbooru API 的站点）的作品 URL 粘贴到导入工具中。Blombooru 将获取元数据（标签、分级、来源）并下载最高质量的媒体版本，还可选择自动创建缺失的标签并归入正确类别（如果可用）。

> [!NOTE]
> 某些 Booru 可能需要 API 密钥或登录凭据才能使用 API 或访问特定作品。您可以在管理面板“系统”选项卡的“Booru 配置”部分进行配置。

### 标注与搜索

- **标签自动完成：** 在编辑项目时，开始在标签输入框输入。系统会基于现有标签显示一个可滚动的建议列表。

- **标签显示：** 在媒体页面，标签会自动按类别（画师、角色、版权、常规、元标签）排序，类别内部按字母顺序排列。

- **搜索语法：** Blombooru 支持强大的 Danbooru 兼容搜索语法。

#### 基础标签

| 语法 | 说明 |
|:-------|:------------|
| `tag1 tag2` | 查找同时包含 `tag1` 和 `tag2` 的媒体 |
| `-tag1` | 排除包含 `tag1` 的媒体 |
| `tag*` | 通配符搜索（查找 `tag_name`, `tag_stuff` 等） |
| `?tag` | 查找在 `tag` 之前有一个或零个字符的媒体 |

#### 范围查询

大多数数值和日期限定符支持范围运算符：

| 语法 | 说明 |
|:-------|:------------|
| `id:100` | 精确匹配 (`x == 100`) |
| `id:100..200` | 包含两端的闭区间 (`100 <= x <= 200`) |
| `id:>=100` | 大于或等于 (`x >= 100`) |
| `id:>100` | 大于 (`x > 100`) |
| `id:<=100` | 小于或等于 (`x <= 100`) |
| `id:<100` | 小于 (`x < 100`) |
| `id:1,2,3` | 在列表内 (`x` 为 1, 2 或 3) |

#### 元限定符

| 限定符 | 说明 | 示例 |
|:----------|:------------|:-----------|
| `id` | 按内部 ID 搜索 | `id:100..200`, `id:>500` |
| `width`, `height` | 按图像尺寸（像素）搜索 | `width:>=1920`, `height:1080` |
| `filesize` | 使用 `kb`, `mb`, `gb`, `b` 单位按文件大小搜索。支持“模糊”匹配：`filesize:52MB` 会查找 `52.0MB` 到 `52.99MB` 的文件。 | `filesize:1mb..5mb`, `filesize:52MB` |
| `date` | 按上传日期搜索 (`YYYY-MM-DD`) | `date:2024-01-01` |
| `age` | 按相对当前的年龄搜索 (`s`, `mi`, `h`, `d`, `w`, `mo`, `y`)。注意：`<` 表示“比...更新”（年龄更小）。 | `age:<24h` (不足 1 天), `age:1w..1mo` |
| `rating` | 按分级过滤：`s`/`safe` (全年龄), `q`/`questionable` (限制级), `e`/`explicit` (成人级)。支持列表。 | `rating:s,q`, `-rating:e` |
| `source` | 搜索来源。使用 `none` 查找缺失来源的项目，使用 `http` 查找网页 URL。 | `source:none`, `source:http`, `source:twitter` |
| `filetype` | 按文件扩展名搜索 | `filetype:png`, `filetype:gif` |
| `md5` | 按文件哈希搜索（精确匹配） | `md5:d34e4c...` |
| `pool`, `album` | 按相册/收藏池 ID 或名称搜索。支持 `any`/`none`。 | `album:any`, `pool:favorites`, `pool:5` |
| `parent` | 按父项 ID 搜索。支持 `any`/`none`。 | `parent:none`, `parent:123` |
| `child` | 通过子项过滤父项作品。支持 `any`/`none`。 | `child:any` (有子项), `child:none` |
| `duration` | 搜索视频/GIF 的时长（秒） | `duration:>60` |

> [!NOTE]
> 并非所有 GIF 都能检测到 `duration` (时长)。

#### 标签数量

按作品上的标签数量进行过滤：

| 限定符 | 说明 |
|:----------|:------------|
| `tagcount` | 标签总数 |
| `gentags` | 常规标签数 |
| `arttags` | 画师标签数 |
| `chartags` | 角色标签数 |
| `copytags` | 版权标签数 |
| `metatags` | 元标签数 |

**示例：** `tagcount:<10` (标签较少的作品), `arttags:>=1` (至少有一个画师标签的作品)

#### 排序

使用 `order:{属性}` 进行排序。可以添加 `_asc` (升序) 或 `_desc` (降序) 后缀（默认为降序）。

| 属性值 | 说明 |
|:------|:------------|
| `id` / `id_desc` | 最新上传优先 (默认) |
| `id_asc` | 最早上传优先 |
| `filesize` | 文件最大优先 |
| `landscape` | 宽高比最宽优先 |
| `portrait` | 宽高比最高优先 |
| `md5` | 使用 MD5 哈希排序（实现确定的随机洗牌效果） |
| `custom` | 按 `id:list` 中给出的顺序排序。示例：`id:3,1,2 order:custom` |

### 分享媒体

1. 以管理员身份登录。
2. 导航到您想要分享的媒体页面。
3. 点击 **分享 (Share)** 按钮，系统将生成一个唯一的分享 URL (`https://localhost:8000/shared/<uuid>`)。
4. 任何拥有此链接的人都可以通过精简的只读界面查看该媒体。分享的媒体可以根据需要选择包含或排除其附带的 AI 元数据。已分享的项目在您的私有图库视图中会标有“已分享”图标。

### 系统更新器

Blombooru 在管理面板内置了系统更新器，方便您将安装版本轻松更新至最新版。

> [!WARNING]
> 更新前请务必备份数据！虽然更新设计得非常安全，但仍可能发生意外问题，尤其是在更新到新的主版本或最新的开发版 (dev build) 时。

#### 如何更新

1. 以管理员身份登录并前往 **管理面板 (Admin Panel)**。
2. 选择 **系统 (System)** 选项卡。
3. 滚动到 **系统更新 (System Update)** 部分。
4. 点击 **检查更新 (Check for Updates)** 以获取来自 GitHub 的最新版本信息。
5. 点击 **查看更新日志 (View Changelog)** 以查看新内容。
6. 如果有可用更新，点击以下任一按钮：
    - **更新至最新开发版 (Update to Latest Dev)** - 更新到 `main` 分支的最新提交（最前沿版本）
    - **更新至最新稳定版 (Update to Latest Stable)** - 更新到最新的标记发布版本（推荐）

更新器将自动运行 `git pull` (或 `git checkout <tag>`) 并显示输出。更新完成后，**重启 Blombooru** 以应用更改：

- **Docker:** `docker compose down && docker compose up -d`

> [!NOTE]
> 目前暂不支持在 Docker 内部直接更新。在 Docker 中运行时，Blombooru 会显示警告，提示您在宿主机上手动运行 `git pull` 并重新构建容器。

- **Python:** 停止服务器 (Ctrl+C) 并再次运行 `python run.py`

#### 依赖项变更

如果更新包含对 `requirements.txt` 或 `docker-compose.yml` 的更改，更新器会显示通知。您将需要：

- **Docker:** 运行 `docker compose down && docker compose up --build -d` 以重新构建容器
- **Python:** 停止服务器 (Ctrl+C)，在再次运行 `python run.py` 之前运行 `pip install -r requirements.txt`。

### API 与第三方应用

Blombooru 实现了 **Danbooru v2 兼容 API**，允许您使用现有的第三方 Booru 客户端（如 Grabber、Tachiyomi 或 BooruNav）来浏览您的收藏。

#### 连接详情

| 设置项 | 值 |
|:--------|:------|
| **服务器类型** | Danbooru v2 |
| **URL** | 您的服务器 IP + 端口 (例如 `http://192.168.1.10:8000`) 或您的域名 (例如 `https://example.com`) |
| **身份验证** | 支持多种方法（见下文） |

**身份验证方法：**
- **查询参数 (Query parameters):** `login` + `api_key`
- **HTTP 基础认证 (Basic Auth):** 用户名 + API 密钥（作为密码）
- **Bearer 令牌:** `Authorization: Bearer <api_key>`

#### 支持的功能

| 功能 | 说明 |
|:--------|:------------|
| **作品 (Posts)** | 完整的搜索功能、列表展示和媒体获取 |
| **标签 (Tags)** | 标签列表、搜索、自动完成和相关标签 |
| **相册/收藏池 (Albums/Pools)** | Blombooru 相册会作为 Danbooru 的“收藏池 (Pools)”导出 |
| **画师 (Artists)** | Blombooru 画师标签会作为画师 (Artists) 端点导出 |

> [!NOTE]
> 通过 API 进行的写操作（上传、编辑等）目前仅限只读或提供占位接口，以防止第三方应用出错。社交功能（如投票、收藏、评论、论坛、私信和百科页面）将返回空结果。

## 主题定制

Blombooru 设计之初就考虑到了易定制性。

- **CSS 变量：** 核心颜色由默认主题中定义的 CSS 变量控制。

- **自定义主题：** 若要创建自己的主题，只需在 `frontend/static/themes/` 目录中创建一个新的 `.css` 文件，复制 `default_dark.css` 主题的全部内容并开始自定义！然后在 `backend/app/themes.py` 文件中注册它即可使用。

您的新主题将自动出现在管理面板的主题选择下拉菜单中。

## 技术细节

| 组件 | 技术 |
|:----------|:-----------|
| **后端** | FastAPI (Python) |
| **前端** | Tailwind CSS (本地构建), Vanilla JavaScript, HTML |
| **数据库** | PostgreSQL 17 |
| **缓存** | Redis 7+ (可选) |
| **共享标签** | 可选的外部 PostgreSQL 实例，用于在实例之间共享标签 |
| **媒体存储** | 本地文件系统，路径由数据库引用。原始元数据始终保留，但在分享媒体时可以选择动态去除。 |
| **支持格式** | JPG, PNG, WEBP, GIF, MP4, WEBM |

## 免责声明

这是一个自托管的单用户应用程序。作为唯一管理员，您对使用此软件上传、管理和共享的所有内容负有全部责任。

请确保您的使用符合所有适用法律，特别是关于版权和媒体中涉及个人隐私的法律。

本项目开发人员和贡献者对任何用户托管的非法、侵权或不当内容不承担 **任何法律责任**。软件按“原样”提供，不作任何保证。完整免责声明请参阅我们的 [责任免责声明](https://github.com/mrblomblo/blombooru/blob/main/DISCLAIMER.md)。

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt) 文件。