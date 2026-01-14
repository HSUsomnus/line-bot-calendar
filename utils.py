# utils.py
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
                'raw_line': line
            })
            
    return events_to_check