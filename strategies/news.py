import datetime
import json
import os
import logging

logger = logging.getLogger(__name__)

class NewsFilter:
    def __init__(self):
        self.calendar_path = os.path.join(os.path.dirname(__file__), "..", "data", "news_calendar.json")
        self.news_events = self._load_calendar()

    def _load_calendar(self):
        try:
            if os.path.exists(self.calendar_path):
                with open(self.calendar_path, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Yangiliklar kalendarini yuklashda xatolik: {e}")
            return []

    def check_news_impact(self):
        """
        USD uchun yaqin 1 soat ichida 'Yuqori ta'sirli' (High Impact) yangilik bor-yo'qligini tekshiradi.
        """
        now = datetime.datetime.now()
        
        for event in self.news_events:
            try:
                # Format: "2026-01-29" va "13:30"
                event_time_str = f"{event['date']} {event['time']}"
                event_dt = datetime.datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                
                # Vaqt farqini hisoblash (minutlarda)
                diff = (event_dt - now).total_seconds() / 60
                
                # Agar yangilikka 60 minut qolgan bo'lsa yoki 30 minut o'tgan bo'lsa
                if -30 <= diff <= 60:
                    if event['impact'] == 'High':
                        logger.warning(f"YUQORI TA'SIRLI YANGILIK: {event['title']} ({event_time_str})")
                        return False # Xavfli
            except Exception as e:
                continue
                
        return True # Xavfsiz

    def get_upcoming_news(self, hours=24):
        """
        Keyingi 24 soat ichidagi muhim yangiliklarni qaytaradi.
        """
        now = datetime.datetime.now()
        upcoming = []
        
        for event in self.news_events:
            try:
                event_time_str = f"{event['date']} {event['time']}"
                event_dt = datetime.datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                
                if now < event_dt <= (now + datetime.timedelta(hours=hours)):
                    upcoming.append(event)
            except:
                continue
        return upcoming

    def get_market_session(self):
        """
        Joriy sessiya (London/NY) haqidagi ma'lumotni qaytaradi.
        """
        # UTC+5 (Toshkent vaqti) bo'yicha sessiyalar
        now = datetime.datetime.now().time()
        
        # London: 13:00 - 21:00 (Toshkent)
        london_start = datetime.time(13, 0)
        london_end = datetime.time(21, 0)
        
        # New York: 18:00 - 02:00 (Toshkent)
        ny_start = datetime.time(18, 0)
        ny_end = datetime.time(2, 0)
        
        # NY sessiyasi tun yarmidan o'tganini hisobga olish
        is_ny = False
        if ny_start <= now or now <= ny_end:
            is_ny = True
            
        is_london = london_start <= now <= london_end
        
        if is_london or is_ny:
            return "OPEN"
        return "CLOSED"
