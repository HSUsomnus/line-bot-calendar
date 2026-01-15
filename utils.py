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
    
    # 抓取年份 (例如 115)
    header_match = re.search(r'(\d{2,3})[-\u4e00-\u9fa5]', lines[0])
    if header_match:
        roc_year = int(header_match.group(1))
        default_year = 1911 + roc_year

    for line in lines:
        line = line.strip()
        if not line: continue

        # 模式 1: 跨月活動 (例如 1/28-2/1) -> 預設整日
        cross_month_match = re.match(r'(\d{1,2})/(\d{1,2})-(\d{1,2})/(\d{1,2})\s+(.*)', line)
        if cross_month_match:
            m1, d1, m2, d2 = map(int, cross_month_match.groups()[:4])
            content = cross_month_match.group(5)
            y1, y2 = default_year, default_year
            if m1 == 12 and m2 == 1: y2 += 1
            
            start_dt = datetime.datetime(y1, m1, d1)
            end_dt = datetime.datetime(y2, m2, d2) + timedelta(days=1)
            
            events_to_check.append({
                'summary': content,
                'start': start_dt,
                'end': end_dt,
                'all_day': True,
                'raw_line': line
            })
            continue

        # 模式 2: 同月跨日活動 (例如 1/17-18) -> 預設整日
        range_match = re.match(r'(\d{1,2})/(\d{1,2})-(\d{1,2})\s+(.*)', line)
        if range_match:
            m, d1, d2 = map(int, range_match.groups()[:3])
            content = range_match.group(4)
            if d2 > d1:
                start_dt = datetime.datetime(default_year, m, d1)
                end_dt = datetime.datetime(default_year, m, d2) + timedelta(days=1)
                
                events_to_check.append({
                    'summary': content,
                    'start': start_dt,
                    'end': end_dt,
                    'all_day': True,
                    'raw_line': line
                })
                continue

        # 模式 3: 一般/諮詢/上課活動解析
        date_match = re.match(r'(\d{1,2})/(\d{1,2})\s+(.*)', line)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            raw_content = date_match.group(3)
            
            # 嘗試解析括號
            bracket_match = re.search(r'\((.+)\)', raw_content)
            
            start_dt = None
            end_dt = None
            h_start = 9
            duration = 2 

            if bracket_match:
                inner_text = bracket_match.group(1)
                
                # 判斷特殊格式 (數字+文字) 或 (數字-數字)
                special_format_match = re.match(r'(\d{1,2})(.+)', inner_text)
                range_time_match = re.match(r'(\d{1,2})-(\d{1,2})', inner_text)
                
                if range_time_match:
                    h_start = int(range_time_match.group(1))
                    h_end = int(range_time_match.group(2))
                    start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                    end_dt = datetime.datetime(default_year, month, day, h_end, 0, 0)
                
                elif special_format_match:
                    h_start = int(special_format_match.group(1))
                    for key, hours in DURATION_MAP.items():
                        if key in raw_content:
                            duration = hours
                            break
                    start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                    end_dt = start_dt + timedelta(hours=duration)
                
                else:
                    # 純數字的情況
                    try:
                        h_start = int(inner_text)
                        start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                        if '金流正式課' in raw_content or '財富藍圖' in raw_content:
                            end_dt = start_dt.replace(hour=18, minute=30)
                        elif h_start == 13:
                            end_dt = start_dt.replace(hour=17, minute=0)
                        else:
                            end_dt = start_dt + timedelta(hours=2)
                    except:
                        pass
            else:
                # 沒寫時間，但有特定關鍵字
                start_dt = datetime.datetime(default_year, month, day, 9, 0, 0)
                if '金流正式課' in raw_content or '財富藍圖' in raw_content:
                    start_dt = start_dt.replace(hour=9, minute=0)
                    end_dt = start_dt.replace(hour=18, minute=30)
                else:
                    end_dt = start_dt + timedelta(hours=2)

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