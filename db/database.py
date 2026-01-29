from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
import os

Base = declarative_base()

class Config(Base):
    """
    Bot uchun dinamik sozlamalarni saqlaydi.
    Masalan: key="RSI_PERIOD", value="14"
    """
    __tablename__ = 'config'
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)

class SignalLog(Base):
    """
    Bot tomonidan yaratilgan barcha signallarni qayd etadi (log qiladi).
    """
    __tablename__ = 'signals'
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, default="XAU/USD")
    signal_type = Column(String)  # BUY / SELL
    price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    reason = Column(String)
    status = Column(String, default="pending")  # pending (kutilmoqda), published (chiqarildi), rejected (rad etildi)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Subscriber(Base):
    """
    Signallarni qabul qiluvchi foydalanuvchilar yoki kanallarni saqlaydi.
    """
    __tablename__ = 'subscribers'
    chat_id = Column(String, primary_key=True)
    is_active = Column(Boolean, default=True)
    language = Column(String, default='uz') # uz / ru

class Subscription(Base):
    """
    Foydalanuvchilarning to'lov va obuna holatini saqlaydi.
    """
    __tablename__ = 'subscriptions'
    user_id = Column(String, primary_key=True)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime)
    plan_type = Column(String)  # 'weekly', 'monthly' va h.k.
    is_active = Column(Boolean, default=True)

class Database:
    def __init__(self, db_path="sqlite:///bot_data.db"):
        if 'sqlite' in db_path:
            self.engine = create_engine(db_path, echo=False, connect_args={'check_same_thread': False})
        else:
            self.engine = create_engine(db_path, echo=False)
        self.Session = sessionmaker(bind=self.engine)
        self._init_db()
        self._check_schema_updates()

    def _init_db(self):
        Base.metadata.create_all(self.engine)

    def _check_schema_updates(self):
        """
        Mavjud jadvalga yangi ustunlarni qo'shish uchun oddiy migratsiya.
        """
        session = self.Session()
        try:
            # Check if language column exists in subscribers
            try:
                session.execute(text("SELECT language FROM subscribers LIMIT 1"))
            except:
                # Add column if it doesn't exist
                session.execute(text("ALTER TABLE subscribers ADD COLUMN language VARCHAR(10) DEFAULT 'uz'"))
                session.commit()
        except Exception as e:
            # Agar jadval bo'sh bo'lsa yoki boshqa xato bo'lsa
            print(f"Schema update info: {e}")
        finally:
            session.close()

    def get_session(self):
        return self.Session()

    def add_subscriber(self, chat_id):
        session = self.Session()
        try:
            if not session.query(Subscriber).filter_by(chat_id=str(chat_id)).first():
                sub = Subscriber(chat_id=str(chat_id), language='uz')
                session.add(sub)
                session.commit()
        finally:
            session.close()

    def get_subscribers(self):
        session = self.Session()
        try:
            return [ch.chat_id for ch in session.query(Subscriber).filter_by(is_active=True).all()]
        finally:
            session.close()

    def set_user_language(self, chat_id, lang):
        session = self.Session()
        try:
            sub = session.query(Subscriber).filter_by(chat_id=str(chat_id)).first()
            if sub:
                sub.language = lang
                session.commit()
            else:
                self.add_subscriber(chat_id)
                self.set_user_language(chat_id, lang)
        finally:
            session.close()

    def get_user_language(self, chat_id):
        session = self.Session()
        try:
            sub = session.query(Subscriber).filter_by(chat_id=str(chat_id)).first()
            return sub.language if sub else 'uz'
        finally:
            session.close()

    def grant_subscription(self, user_id, days, plan_type='manual'):
        session = self.Session()
        try:
            now = datetime.utcnow()
            end_date = now + timedelta(days=days)
            sub = session.query(Subscription).filter_by(user_id=str(user_id)).first()
            if sub:
                sub.end_date = end_date
                sub.is_active = True
                sub.plan_type = plan_type
            else:
                sub = Subscription(
                    user_id=str(user_id),
                    start_date=now,
                    end_date=end_date,
                    plan_type=plan_type,
                    is_active=True
                )
                session.add(sub)
            session.commit()
            return end_date
        finally:
            session.close()

    def get_subscription(self, user_id):
        session = self.Session()
        try:
            return session.query(Subscription).filter_by(user_id=str(user_id)).first()
        finally:
            session.close()

    def get_expired_subscriptions(self):
        session = self.Session()
        try:
            now = datetime.utcnow()
            return session.query(Subscription).filter(
                Subscription.end_date < now,
                Subscription.is_active == True
            ).all()
        finally:
            session.close()

    def get_expiring_soon_subscriptions(self, hours=24):
        session = self.Session()
        try:
            now = datetime.utcnow()
            warning_time = now + timedelta(hours=hours)
            return session.query(Subscription).filter(
                Subscription.end_date > now,
                Subscription.end_date <= warning_time,
                Subscription.is_active == True
            ).all()
        finally:
            session.close()

    def deactivate_subscription(self, user_id):
        session = self.Session()
        try:
            sub = session.query(Subscription).filter_by(user_id=str(user_id)).first()
            if sub:
                sub.is_active = False
                session.commit()
        finally:
            session.close()

    def set_config(self, key, value):
        session = self.Session()
        try:
            item = session.query(Config).filter_by(key=key).first()
            if item:
                item.value = str(value)
            else:
                item = Config(key=key, value=str(value))
                session.add(item)
            session.commit()
        finally:
            session.close()

    def get_config(self, key, default=None):
        session = self.Session()
        try:
            item = session.query(Config).filter_by(key=key).first()
            return item.value if item else default
        finally:
            session.close()

    def log_signal(self, symbol, signal_type, price, sl, tp, reason):
        session = self.Session()
        try:
            signal = SignalLog(
                symbol=symbol,
                signal_type=signal_type,
                price=price,
                sl=sl,
                tp=tp,
                reason=reason,
                status="pending"
            )
            session.add(signal)
            session.commit()
            return signal.id
        finally:
            session.close()

    def update_signal_status(self, signal_id, status):
        session = self.Session()
        try:
            signal = session.query(SignalLog).filter_by(id=signal_id).first()
            if signal:
                signal.status = status
                session.commit()
        finally:
            session.close()

    def get_signal_by_id(self, signal_id):
        session = self.Session()
        try:
            return session.query(SignalLog).filter_by(id=signal_id).first()
        finally:
            session.close()

    def get_last_signal_info(self, symbol="XAU/USD"):
        """
        Berilgan simbol uchun oxirgi signalning vaqti va turini qaytaradi.
        Bot qayta ishga tushganda dublikatlarni oldini olish uchun ishlatiladi.
        """
        session = self.Session()
        try:
            signal = session.query(SignalLog)\
                            .filter_by(symbol=symbol)\
                            .order_by(SignalLog.timestamp.desc())\
                            .first()
            if signal:
                return {
                    "time": signal.timestamp,
                    "type": signal.signal_type
                }
            return None
        finally:
            session.close()
