import datetime

class DateTimeProvider:
    @staticmethod
    def now() -> datetime.datetime:
        return datetime.datetime.now()

    @staticmethod
    def date_today_str():
        return datetime.datetime.now().strftime("%Y-%m-%d")