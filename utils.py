import re
import datetime
from datetime import timedelta

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

        # =================================================
        # 模式 1: 跨月活動 (例如 1/28-2/1) -> 預設整日
        # =================================================
        # 抓取格式： 月/日-月/日
        cross_month_match = re.match(r'(\d{1,2})/(\d{1,2})-(\d{1,2})/(\d{1,2})\s+(.*)', line)
        if cross_month_match:
            m1 = int(cross_month_match.group(1))
            d1 = int(cross_month_match.group(2))
            m2 = int(cross_month_match.group(3))
            d2 = int(cross_month_match.group(4))
            content = cross_month_match.group(5)

            # 處理跨年 (例如 12/31 - 1/2)
            y1 = default_year
            y2 = default_year
            if m1 == 12 and m2 == 1:
                y2 += 1
            
            start_dt = datetime.datetime(y1, m1, d1)
            # 結束日期：Google 整日活動結束日必須是「活動結束日的隔天」
            end_dt = datetime.datetime(y2, m2, d2) + timedelta(days=1)
            
            events_to_check.append({
                'summary': content,
                'start': start_dt,
                'end': end_dt,
                'all_day': True, # 標記為整日
                'raw_line': line
            })
            continue

        # =================================================
        # 模式 2: 同月跨日活動 (例如 1/17-18) -> 預設整日
        # =================================================
        # 抓取格式： 月/日-日
        range_match = re.match(r'(\d{1,2})/(\d{1,2})-(\d{1,2})\s+(.*)', line)
        if range_match:
            m = int(range_match.group(1))
            d1 = int(range_match.group(2))
            d2 = int(range_match.group(3))
            content = range_match.group(4)
            
            # 簡單防呆：確保日期合理 (d2 > d1)
            if d2 > d1:
                start_dt = datetime.datetime(default_year, m, d1)
                # 結束日期：設為 d2 的隔天
                end_dt = datetime.datetime(default_year, m, d2) + timedelta(days=1)
                
                events_to_check.append({
                    'summary': content,
                    'start': start_dt,
                    'end': end_dt,
                    'all_day': True, # 標記為整日
                    'raw_line': line
                })
                continue

        # =================================================
        # 模式 3: 單日活動 (既有邏輯)
        # =================================================
        date_match = re.match(r'(\d{1,2})/(\d{1,2})\s+(.*)', line)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            content = date_match.group(3)
            
            time_range_match = re.search(r'\((\d{1,2})-(\d{1,2})', content)
            time_single_match = re.search(r'\((\d{1,2})', content)
            
            start_dt = None
            end_dt = None

            if time_range_match:
                h_start = int(time_range_match.group(1))
                h_end = int(time_range_match.group(2))
                start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                end_dt = datetime.datetime(default_year, month, day, h_end, 0, 0)
            elif time_single_match:
                h_start = int(time_single_match.group(1))
                start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                if '金流正式課' in content or '財富藍圖' in content:
                    end_dt = start_dt.replace(hour=18, minute=30)
                elif h_start == 13:
                    end_dt = start_dt.replace(hour=17, minute=0)
                else:
                    end_dt = start_dt + timedelta(hours=2)
            else:
                start_dt = datetime.datetime(default_year, month, day, 9, 0, 0)
                end_dt = start_dt + timedelta(hours=2)

            events_to_check.append({
                'summary': content,
                'start': start_dt,
                'end': end_dt,
                'all_day': False, # 標記為非整日
                'raw_line': line
            })
            
    return events_to_check