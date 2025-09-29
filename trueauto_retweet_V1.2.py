# 安装必要的库: pip install selenium beautifulsoup4 pandas
import time
import random
import json
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 全局设置 ---
COOKIES_FILE = 'x_cookies.json'
MAX_WORKERS = 2
HEADLESS_MODE = False
REPLY_RETWEET_LIMIT = 20
ERROR_WAIT_TIME = 183 # 错误发生时的等待时间（秒）

# --- 核心函数 ---

def save_cookies(driver, file_path):
    """保存当前浏览器的Cookies到文件"""
    with open(file_path, 'w') as f:
        json.dump(driver.get_cookies(), f)
    print(f"Cookies have been saved to {file_path}")

def load_cookies(driver, file_path):
    """从文件加载Cookies到浏览器"""
    if os.path.exists(file_path):
        driver.get("https://x.com/")
        with open(file_path, 'r') as f:
            cookies = json.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        return True
    return False

def parse_tweet_article(article_soup):
    """从一个包含单条推文的 'article' HTML片段中解析出所有数据"""
    try:
        time_elements = article_soup.find_all('time')
        if not time_elements: return None
        time_element = time_elements[-1]

        if not time_element.find_parent('a'): return None
        post_link = "https://x.com" + time_element.find_parent('a')['href']
        post_time = time_element['datetime']
        
        user_id = post_link.split('/')[3]
        user_name_div = article_soup.find('div', {'data-testid': 'User-Name'})
        nickname = user_name_div.find_all('span')[0].text if user_name_div else user_id
        
        tweet_text_div = article_soup.find('div', {'data-testid': 'tweetText'})
        if tweet_text_div:
            for img in tweet_text_div.find_all('img', alt=True): img.replace_with(img['alt'])
        content = tweet_text_div.get_text(separator='\n', strip=True) if tweet_text_div else ''
        
        emoji_pattern = re.compile("[" u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF" u"\U0001F680-\U0001F6FF" u"\U0001F1E0-\U0001F1FF" u"\U00002702-\U000027B0" u"\U000024C2-\U0001F251" "]+", flags=re.UNICODE)
        emojis = emoji_pattern.findall(content)
        hashtags = [tag.text for tag in article_soup.find_all('a', href=re.compile(r'/hashtag/'))]
        reply_count_element = article_soup.find('button', {'data-testid': 'reply'}) or article_soup.find('div', {'data-testid': 'reply'})
        retweet_count_element = article_soup.find('button', {'data-testid': 'retweet'}) or article_soup.find('div', {'data-testid': 'retweet'})
        like_count_element = article_soup.find('button', {'data-testid': 'like'}) or article_soup.find('div', {'data-testid': 'like'})

        def parse_metric(element):
            if not element: return 0
            aria_label = element.get('aria-label', '')
            if aria_label:
                match = re.search(r'([\d,]+)', aria_label)
                if match:
                    try: return int(match.group(1).replace(',', ''))
                    except (ValueError, TypeError): pass
            text = element.get_text(strip=True).upper()
            if not text: return 0
            if 'K' in text: return int(float(text.replace('K', '')) * 1000)
            if 'M' in text: return int(float(text.replace('M', '')) * 1000000)
            try: return int(text)
            except (ValueError, TypeError): return 0

        return {"nickname": nickname, "user_id": user_id, "platform": "X", "post_time": post_time, "ip_location": "N/A (Not available on web version)", "hashtags": ", ".join(hashtags), "post_text": content, "emojis": emojis, "reply_count": parse_metric(reply_count_element), "retweet_count": parse_metric(retweet_count_element), "like_count": parse_metric(like_count_element), "post_url": post_link}
    except Exception: return None

def scroll_and_collect(driver, seen_tweets, max_scrolls=1):
    """通过限制滚动次数来快速采集样本"""
    collected_data = []
    scroll_count = 0
    while scroll_count < max_scrolls:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = soup.find_all('article', {'data-testid': 'tweet'})
        new_tweets_found = False
        for article in articles:
            parsed_data = parse_tweet_article(article)
            if parsed_data and parsed_data['post_url'] not in seen_tweets:
                collected_data.append(parsed_data)
                seen_tweets.add(parsed_data['post_url'])
                new_tweets_found = True
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2.0, 3.5))
        new_height = driver.execute_script("return document.body.scrollHeight")
        
        scroll_count += 1
        if new_height == last_height and not new_tweets_found:
            break
            
    return collected_data

def get_chrome_options():
    """配置Chrome浏览器选项以提高速度"""
    options = webdriver.ChromeOptions()
    if HEADLESS_MODE: options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    return options

def perform_initial_login():
    """仅在没有cookies时执行，用于首次手动登录"""
    if os.path.exists(COOKIES_FILE): return
    print("Cookies file not found. A browser will open for you to log in.")
    print("Please log in manually. You have 120 seconds...")
    login_options = get_chrome_options()
    if any('--headless' in arg for arg in login_options.arguments): login_options.arguments.remove('--headless')
    driver = webdriver.Chrome(options=login_options)
    driver.get("https://x.com/login")
    try:
        WebDriverWait(driver, 120).until(EC.url_contains("home"))
        print("Login successful! Saving cookies for future use...")
        save_cookies(driver, COOKIES_FILE)
    except Exception: print("Login timed out or failed.")
    finally: driver.quit()

def process_url(task, secondary_output_path):
    """处理单个URL的完整爬取流程"""
    url = task['url_to_scrape']
    source_filename = task['source_filename']
    
    output_dir = os.path.join(secondary_output_path, source_filename)
    
    thread_id = f"线程-{random.randint(100, 999)}"
    print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 开始处理链接: {url}")
    driver = webdriver.Chrome(options=get_chrome_options())
    try:
        if not load_cookies(driver, COOKIES_FILE):
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 无法加载Cookies，跳过链接 {url}")
            return

        driver.get(url)
        
        wait = WebDriverWait(driver, 20)
        source_tweet = None
        
        try:
            source_article_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet']")))
            
            if random.randint(1, 3) == 1:
                try:
                    like_button = source_article_element.find_element(By.CSS_SELECTOR, "button[data-testid='like']")
                    like_button.click()
                    print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [操作] 模拟点赞成功: {url}")
                    time.sleep(random.uniform(1, 2))
                except Exception:
                    pass

            source_soup = BeautifulSoup(source_article_element.get_attribute('outerHTML'), 'html.parser')
            source_tweet = parse_tweet_article(source_soup)
        except Exception as find_error:
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [警告] 查找源帖子时出错，将暂停 {ERROR_WAIT_TIME // 60} 分钟... Error: {find_error}")
            for i in range(ERROR_WAIT_TIME, 0, -1):
                print(f"\r[{time.strftime('%H:%M:%S')}] {thread_id}: 倒计时: {i:03d} 秒...", end="", flush=True)
                time.sleep(1)
            print(f"\n[{time.strftime('%H:%M:%S')}] {thread_id}: 暂停结束，放弃此链接。")
            return
        
        if not source_tweet:
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [失败] 页面加载后未能找到并解析源帖子 {url}")
            return

        seen_tweets = {source_tweet['post_url']}

        final_replies = scroll_and_collect(driver, seen_tweets, max_scrolls=1)
        quotes_url = url.rstrip('/') + "/quotes"
        all_retweets = []
        try:
            driver.get(quotes_url)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet']")))
            all_retweets = scroll_and_collect(driver, seen_tweets, max_scrolls=1)
        except Exception: pass

        if len(final_replies) > REPLY_RETWEET_LIMIT: sampled_replies = random.sample(final_replies, REPLY_RETWEET_LIMIT)
        else: sampled_replies = final_replies

        if len(all_retweets) > REPLY_RETWEET_LIMIT: sampled_retweets = random.sample(all_retweets, REPLY_RETWEET_LIMIT)
        else: sampled_retweets = all_retweets

        source_tweet['replies'] = sampled_replies
        source_tweet['retweets_with_comment'] = sampled_retweets
        
        post_time_str = source_tweet.get('post_time', str(time.time()))
        filename_time = post_time_str.replace('T', '_').replace(':', '-').split('.')[0]
        tweet_id = url.split('/')[-1]
        output_filename = f"{filename_time}_id_{tweet_id}.json"

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(source_tweet, f, ensure_ascii=False, indent=4)
        print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [成功] {url} 的数据已保存至 {output_path}")

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 处理链接 {url} 时发生严重错误: {e}")
    finally:
        driver.quit()

def find_all_top_retweets(stage_path, secondary_output_path):
    """
    遍历指定stage文件夹的数据文件，找到每个文件中转发量最高的转推，并返回一个任务列表。
    """
    print(f"开始分析 {stage_path} 的第一阶段数据...")
    tasks = []
    
    for filename in os.listdir(stage_path):
        if re.search(r'_id_(\d+).json$', filename):
            file_path = os.path.join(stage_path, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                retweets = data.get('retweets_with_comment', [])
                if not retweets:
                    continue
                    
                top_retweet = max(retweets, key=lambda x: x.get('retweet_count', 0))
                top_url = top_retweet.get('post_url')
                
                if top_url:
                    tasks.append({
                        "source_filename": os.path.splitext(filename)[0],
                        "url_to_scrape": top_url
                    })
            except Exception as e:
                print(f"  [警告] 跳过文件 {file_path}，原因: {e}")
    
    print(f"分析完成！在 {stage_path} 中共找到 {len(tasks)} 个高转发链接需要进行二次采集。")
    return tasks

def main():
    # --- 【新功能】自动化工作流 ---
    # 1. 查找所有以 'stage' 开头的文件夹
    try:
        stage_folders = [d for d in os.listdir('.') if os.path.isdir(d) and d.startswith('stage')]
        stage_folders.sort(key=lambda s: int(re.search(r'\d+', s).group()))
    except Exception:
        print("错误：无法找到或排序stage文件夹。请确保脚本与stage数据文件夹在同一目录下。")
        return

    if not stage_folders:
        print("在当前目录下未找到任何以 'stage' 开头的文件夹。")
        return

    # 2. 对所有任务，只需登录一次
    perform_initial_login()

    # 3. 按顺序执行每个stage的任务
    for stage_folder in stage_folders:
        print(f"\n{'='*50}")
        print(f"开始处理阶段: {stage_folder}")
        print(f"{'='*50}\n")

        secondary_output_path = os.path.join(stage_folder, 'secondary_output')
        tasks_file_path = os.path.join(secondary_output_path, 'secondary_tasks.json')
        os.makedirs(secondary_output_path, exist_ok=True)

        # 4. 断点续传逻辑
        tasks_to_run = []
        if os.path.exists(tasks_file_path):
            print(f"找到阶段 '{stage_folder}' 的任务列表文件，将从中加载链接。")
            with open(tasks_file_path, 'r') as f:
                tasks_to_run = json.load(f)
        else:
            print(f"未找到 '{stage_folder}' 的任务列表文件，将执行新的分析...")
            tasks_to_run = find_all_top_retweets(stage_folder, secondary_output_path)
            if tasks_to_run:
                with open(tasks_file_path, 'w') as f:
                    json.dump(tasks_to_run, f, indent=4)
                print(f"已将 {len(tasks_to_run)} 个待办任务保存至 '{tasks_file_path}'")
        
        if not tasks_to_run:
            print(f"阶段 '{stage_folder}' 未找到任何可供二次采集的链接，跳过此阶段。")
            continue
            
        # 5. 检查已完成的任务
        processed_source_filenames = set(os.listdir(secondary_output_path))
        pending_tasks = [task for task in tasks_to_run if task['source_filename'] not in processed_source_filenames]
        
        if not pending_tasks:
            print(f"阶段 '{stage_folder}' 的所有二次采集任务均已处理完毕！")
            continue

        print(f"\n阶段 '{stage_folder}': 总任务数: {len(tasks_to_run)} | 已完成: {len(tasks_to_run) - len(pending_tasks)} | 待处理: {len(pending_tasks)}")
        print(f"准备就绪，将使用 {MAX_WORKERS} 个并行线程处理剩余的链接...")
        
        # 6. 并行处理阶段
        processed_count = 0
        total_pending = len(pending_tasks)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_url, task, secondary_output_path): task for task in pending_tasks}
            for future in as_completed(futures):
                processed_count += 1
                print(f"\n--- 阶段 '{stage_folder}' 进度: {processed_count}/{total_pending} 个待办链接已处理完毕 ---\n")

    print("\n所有阶段均已处理完毕。")

if __name__ == "__main__":
    main()
