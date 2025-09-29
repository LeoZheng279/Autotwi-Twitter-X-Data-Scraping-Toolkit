
# Autotwi - Twitter/X 数据采集工具套件 (Twitter/X Data Scraping Toolkit)
> Author: @LeoZheng279
## 简体中文

### 概述

本工具套件是一套基于 Python 和 Selenium 的自动化数据采集程序，专门用于从 Twitter/X 平台抓取公开数据。它由三个独立的脚本组成，分别用于爬取特定关键词的帖子、深入挖掘高价值的转发内容以及批量获取指定用户的个人信息和近期动态。

本套件的**核心优点**包括：

- **模块化设计**：三个脚本各司其职，可以独立运行，也可以组合成一个完整的数据采集与分析工作流。
- **自动化与持久化登录**：首次运行需要手动登录一次，程序会自动保存登录凭证（Cookies）。后续运行时将自动加载凭证，无需重复登录。
- **强大的断点续传**：所有脚本都具备智能的断点续传功能。如果程序中途停止，再次运行时会自动跳过已完成的任务，从上次中断的地方继续，极大地提高了大规模采集的效率和稳定性。
- **人性化反爬策略**：内置随机延迟和错误暂停机制。当遇到平台反爬虫限制时，程序会自动暂停一段时间，模拟人类行为，有效降低被封禁的风险。
- **清晰的数据组织**：所有采集到的数据都以结构化的 JSON 格式保存，并根据任务、用户和日期自动存放在不同的文件夹中，便于后续的数据处理和分析。

---

### 组件说明与使用指南

#### 准备工作

1.  **安装依赖**:
    打开终端或命令行，运行以下命令来安装所有必需的 Python 库。
    ```bash
    pip install selenium beautifulsoup4 pandas
    ```

2.  **安装浏览器驱动**:
    确保您的电脑上安装了 Google Chrome 浏览器和ChromeDriver。

3.  **首次登录与获取Cookies**:
    - 将三份脚本 (`autotwi_V2.0.py`, `trueauto_retweet_V1.2.py`, `user_autotwi.py`) 放在同一个文件夹下。
    - 运行任意一个脚本。程序会检测到缺少 `x_cookies.json` 文件，并自动打开一个 Chrome 浏览器窗口。
    - 在弹出的浏览器中，手动登录您的 Twitter/X 账号。
    - 成功登录到主页后，程序会自动保存您的登录信息到 `x_cookies.json` 文件中，然后浏览器会自动关闭。此步骤只需执行一次。

---

#### 1. `autotwi_V2.0.py` - 关键词帖子采集脚本

此脚本根据您设定的关键词、日期范围和最小互动量（如转推数）来搜索并爬取相关的帖子及其评论和引用。

**使用方法**:

1.  在脚本同目录下，创建一个名为 `tasks.txt` 的文本文件。
2.  按照以下格式在文件中添加采集任务，每行一个任务：
    ```
    # 格式: 搜索关键词,开始日期(YYYY-MM-DD),结束日期(YYYY-MM-DD),保存文件夹名称
    Trump,2024-05-01,2024-05-02,Trump_May_2024
    Biden,2024-05-01,2024-05-02,Biden_May_2024
    ```
3.  运行脚本：
    ```bash
    python autotwi_V2.0.py
    ```
4.  程序会依次执行 `tasks.txt` 中的每个任务。对于每个任务，它会：
    - 创建一个以您指定的“保存文件夹名称”命名的文件夹（例如 `Trump_May_2024`）。
    - 在该文件夹内，首先搜索并保存所有符合条件的帖子链接到 `urls_to_process.json`。
    - 然后，逐一访问这些链接，爬取原帖、帖子的评论（replies）和引用转发（retweets with comment）。
    - 每个原帖及其相关数据都将保存为一个独立的 JSON 文件，存放在任务文件夹中。

---

#### 2. `trueauto_retweet_V1.2.py` - 高价值转发挖掘脚本

此脚本是 `autotwi_2.0.py` 的延伸，用于对第一阶段采集到的数据进行二次挖掘，找出其中传播最广的“爆款”转发，并对这些转发再次进行深入采集。

**使用方法**:

1.  确保您已经使用 `autotwi_2.0.py` 至少完成了一个采集任务，并且生成了对应的任务文件夹。
2.  **重要**: 为了让此脚本能够识别，请将 `autotwi_2.0.py` 生成的任务文件夹重命名，使其以 `stage` 开头（例如，将 `Trump_May_2024` 重命名为 `stage1_Trump`）。
3.  运行脚本：
    ```bash
    python trueauto_retweet_V1.2.py
    ```
4.  程序会自动扫描所有以 `stage` 开头的文件夹，并对每个文件夹执行以下操作：
    - 分析文件夹内所有 JSON 文件，找到每个原帖的“引用转发”中，转发量最高的那一条。
    - 将这些“高价值转发”的链接汇总起来，作为新的采集目标。
    - 自动对这些新目标进行二次采集（包括它们的评论和引用）。
    - 结果将保存在原 `stage` 文件夹下的一个名为 `secondary_output` 的子文件夹中。

---

#### 3. `user_autotwi.py` - 用户信息采集脚本

此脚本用于批量爬取指定用户的个人主页信息（如简介、粉丝数、关注数）以及他们最近发布的帖子。

**使用方法**:

1.  在脚本同目录下，创建一个名为 `users.txt` 的文本文件。
2.  在文件中输入您想爬取的用户的ID（即`@`后面的部分），每行一个：
    ```
    # 请在此文件中输入用户ID，每行一个
    WhiteHouse
    nasa
    google
    ```
3.  运行脚本：
    ```bash
    python user_autotwi.py
    ```
4.  程序会自动创建一个名为 `scraped_users` 的文件夹。
5.  它会逐一访问 `users.txt` 中的每个用户主页，爬取其公开信息和近期帖子，并将每个用户的数据保存为一个独立的 JSON 文件，存放在 `scraped_users` 文件夹中。

<br>

## English

### Overview

This toolkit is an automated data scraping suite built with Python and Selenium, designed specifically for fetching public data from the Twitter/X platform. It consists of three independent scripts for scraping posts based on keywords, deep-diving into high-value retweets, and bulk-fetching profile information and recent activities of specified users.

The **core advantages** of this suite include:

- **Modular Design**: The three scripts have distinct roles. They can be run independently or combined to form a complete data collection and analysis workflow.
- **Automated & Persistent Login**: A manual login is required only on the first run. The program automatically saves your login credentials (cookies) and uses them for subsequent sessions, eliminating the need for repeated logins.
- **Robust Resume Capability**: All scripts feature intelligent resume functionality. If a script is interrupted, it will automatically skip completed tasks and resume from where it left off upon restart, significantly improving the efficiency and stability of large-scale scraping tasks.
- **Human-like Anti-Scraping Strategy**: The suite incorporates random delays and an error-pause mechanism. When it detects potential anti-scraping measures from the platform, it automatically pauses for a set period to mimic human behavior, effectively reducing the risk of being blocked.
- **Clean Data Organization**: All collected data is saved in a structured JSON format and automatically organized into different folders based on tasks, users, and dates, facilitating subsequent data processing and analysis.

---

### Component Descriptions and User Guide

#### Prerequisites

1.  **Install Dependencies**:
    Open your terminal or command prompt and run the following command to install all necessary Python libraries.
    ```bash
    pip install selenium beautifulsoup4 pandas
    ```

2.  **Install Browser Driver**:
    Ensure you have Google Chrome installed. 

3.  **First-time Login & Cookie Generation**:
    - Place the three scripts (`autotwi_V2.0.py`, `trueauto_retweet_V1.2.py`, `user_autotwi.py`) in the same directory.
    - Run any of the scripts. The program will detect that `x_cookies.json` is missing and will automatically open a Chrome browser window.
    - In the opened browser, manually log in to your Twitter/X account.
    - After successfully logging in and reaching the home feed, the program will automatically save your session information into `x_cookies.json`, and the browser will close. This step only needs to be performed once.

---

#### 1. `autotwi_V2.0.py` - Keyword-based Post Scraper

This script searches for and scrapes posts (along with their replies and quotes) based on your specified keywords, date ranges, and minimum engagement metrics (like retweet count).

**How to Use**:

1.  In the same directory as the script, create a text file named `tasks.txt`.
2.  Add scraping tasks to this file using the following format, one task per line:
    ```
    # Format: search_keyword,start_date(YYYY-MM-DD),end_date(YYYY-MM-DD),output_folder_name
    Trump,2024-05-01,2024-05-02,Trump_May_2024
    Biden,2024-05-01,2024-05-02,Biden_May_2024
    ```
3.  Run the script:
    ```bash
    python autotwi_V2.0.py
    ```
4.  The script will execute each task from `tasks.txt` sequentially. For each task, it will:
    - Create a folder with the name you specified (e.g., `Trump_May_2024`).
    - Inside this folder, it first searches for and saves all matching post URLs to `urls_to_process.json`.
    - It then visits each URL to scrape the original post, its replies, and its quote retweets (retweets with comment).
    - The data for each original post and its associated content is saved as a separate JSON file in the task folder.

---

#### 2. `trueauto_retweet_V1.2.py` - High-Value Retweet Miner

This script is an extension of `autotwi_2.0.py`, designed for secondary data mining. It identifies the most widely spread "viral" retweets from the initial collection and performs another deep scrape on them.

**How to Use**:

1.  Ensure you have completed at least one scraping task with `autotwi_2.0.py` and have the corresponding output folder.
2.  **Important**: For this script to recognize the folders, rename the task folders generated by `autotwi_2.0.py` to start with `stage` (e.g., rename `Trump_May_2024` to `stage1_Trump`).
3.  Run the script:
    ```bash
    python trueauto_retweet_V1.2.py
    ```
4.  The script will automatically scan for all folders starting with `stage` and perform the following for each:
    - Analyze all JSON files within the folder to find the quote retweet with the highest retweet count for each original post.
    - Compile a new list of these "high-value retweet" URLs to serve as new scraping targets.
    - Automatically perform a secondary scrape on these new targets (including their replies and quotes).
    - The results will be saved in a subfolder named `secondary_output` inside the original `stage` folder.

---

#### 3. `user_autotwi.py` - User Profile Scraper

This script is used to bulk-scrape the profile information (like bio, follower count, following count) and recent posts of specified users.

**How to Use**:

1.  In the same directory as the script, create a text file named `users.txt`.
2.  Enter the user IDs (the part after `@`) you want to scrape, one per line:
    ```
    # Please enter user IDs in this file, one per line
    WhiteHouse
    nasa
    google
    ```
3.  Run the script:
    ```bash
    python user_autotwi.py
    ```
4.  The script will automatically create a folder named `scraped_users`.
5.  It will then visit the profile page of each user from `users.txt`, scrape their public information and recent posts, and save each user's data as a separate JSON file in the `scraped_users` folder.
