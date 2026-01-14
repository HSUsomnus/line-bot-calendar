import re
import datetime
from datetime import timedelta

# 定義不同類型的活動時長 (小時)
DURATION_MAP = {
    '保單諮詢': 2,
    '專屬諮詢': 1,
    '保單簽約': 1,
    '天耀週轉': 1
}

def parse_schedule_text(text):
    lines = text.split('\n')
    events_to_check = []
    
    default_year = datetime.datetime.now().year
    
    # 抓取年份
    header_match = re.search(r'(\d{2,3})[-\u4e00-\u9fa5]', lines[0])
    if header_match:
        roc_year = int(header_match.group(1))
        default_year = 1911 + roc_year

    for line in lines:
        line = line.strip()
        if not line: continue

        # 模式 1: 跨月活動 (保留舊功能)
        cross_month_match = re.match(r'(\d{1,2})/(\d{1,2})-(\d{1,2})/(\d{1,2})\s+(.*)', line)
        if cross_month_match:
            # ... (保留原本跨月邏輯，省略以節省篇幅，請保留您原本的這段) ...
            m1, d1, m2, d2 = map(int, cross_month_match.groups()[:4])
            content = cross_month_match.group(5)
            y1, y2 = default_year, default_year
            if m1 == 12 and m2 == 1: y2 += 1
            start_dt = datetime.datetime(y1, m1, d1)
            end_dt = datetime.datetime(y2, m2, d2) + timedelta(days=1)
            events_to_check.append({'summary': content, 'start': start_dt, 'end': end_dt, 'all_day': True, 'raw_line': line})
            continue

        # 模式 2: 同月跨日活動 (保留舊功能)
        range_match = re.match(r'(\d{1,2})/(\d{1,2})-(\d{1,2})\s+(.*)', line)
        if range_match:
            # ... (保留原本跨日邏輯) ...
            m, d1, d2 = map(int, range_match.groups()[:3])
            content = range_match.group(4)
            if d2 > d1:
                start_dt = datetime.datetime(default_year, m, d1)
                end_dt = datetime.datetime(default_year, m, d2) + timedelta(days=1)
                events_to_check.append({'summary': content, 'start': start_dt, 'end': end_dt, 'all_day': True, 'raw_line': line})
                continue

        # =================================================
        # 👇 模式 3: 一般/諮詢活動解析 (重點更新)
        # 格式範例：2/1 毓紘保單諮詢(21線上)
        # =================================================
        date_match = re.match(r'(\d{1,2})/(\d{1,2})\s+(.*)', line)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            raw_content = date_match.group(3)
            
            # 嘗試解析括號內的資訊：(時間+類型/方式)
            # 例如：(21線上), (13實體), (13-17財商)
            bracket_match = re.search(r'\((.+)\)', raw_content)
            
            start_dt = None
            end_dt = None
            
            # 預設值
            h_start = 9
            duration = 2 # 預設 2 小時

            if bracket_match:
                inner_text = bracket_match.group(1) # 例如 "21線上" 或 "13-17"
                
                # 判斷是否為 "諮詢/簽約" 特殊格式 (數字後面接文字)
                special_format_match = re.match(r'(\d{1,2})(.+)', inner_text)
                
                # 判斷是否為時間區段 (例如 13-17)
                range_time_match = re.match(r'(\d{1,2})-(\d{1,2})', inner_text)
                
                if range_time_match:
                    h_start = int(range_time_match.group(1))
                    h_end = int(range_time_match.group(2))
                    start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                    end_dt = datetime.datetime(default_year, month, day, h_end, 0, 0)
                
                elif special_format_match:
                    h_start = int(special_format_match.group(1))
                    # 根據活動標題關鍵字決定時長
                    for key, hours in DURATION_MAP.items():
                        if key in raw_content:
                            duration = hours
                            break
                    
                    start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                    end_dt = start_dt + timedelta(hours=duration)
                
                else:
                    # 只有數字的情況 (13)
                    try:
                        h_start = int(inner_text)
                        # 舊有邏輯
                        if '金流正式課' in raw_content or '財富藍圖' in raw_content:
                            start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                            end_dt = start_dt.replace(hour=18, minute=30)
                        else:
                            start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                            end_dt = start_dt + timedelta(hours=2)
                    except:
                        pass
            
            if not start_dt:
                start_dt = datetime.datetime(default_year, month, day, 9, 0, 0)
                end_dt = start_dt + timedelta(hours=2)

            events_to_check.append({
                'summary': raw_content,
                'start': start_dt,
                'end': end_dt,
                'all_day': False,
                'raw_line': line
            })
            
    return events_to_check