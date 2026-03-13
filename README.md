# AliceUniverse

ТЕХНИЧЕСКОЕ ЗАДАНИЕ
Модуль CRM для холодных звонков (Platinum Auto)
Версия: 1.0 (MVP)
Дата: 13.03.2026
Заказчик: AliceUniverse Family Bot
Исполнитель: [Внешний разработчик]
Статус: На согласовании
1. ОБЩИЕ ПОЛОЖЕНИЯ
1.1 Цель проекта
Разработать изолированный модуль CRM для автоматизации процесса холодных звонков владельцам автомобилей с целью привлечения на платформу Platinum Auto.
1.2 Контекст интеграции
Существующий проект: AliceUniverse/alisa_family_bot
Фреймворк: aiogram 3.x
База данных: PostgreSQL (через SQLAlchemy async)
Архитектура: Модульная, zero-coupling с существующим кодом
1.3 Ключевой принцип
Модуль должен подключаться одной строкой в main.py без модификации существующих файлов проекта (кроме точки входа).
2. ФУНКЦИОНАЛЬНЫЕ ТРЕБОВАНИЯ
2.1 User Stories
Table
ID	Роль	Действие	Цель	Приоритет
US-001	Менеджер	Отправить ссылку Auto.ria боту	Автоматически создать карточку клиента	Must have
US-002	Менеджер	Просмотреть очередь на звонок	Видеть список необработанных лидов	Must have
US-003	Менеджер	Открыть карточку клиента	Видеть полную информацию и инструменты звонка	Must have
US-004	Менеджер	Зафиксировать результат звонка	Обновить статус и поставить напоминание	Must have
US-005	Менеджер	Получить напоминание	Не забыть перезвонить вовремя	Must have
US-006	Менеджер	Вести историю коммуникаций	Видеть контекст предыдущих разговоров	Should have
US-007	Менеджер	Просматривать статистику	Оценивать эффективность работы	Should have
2.2 Воронка продаж (Статусы лида)
plain
Copy
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│  NEW    │───→│ CALLING  │───→│THINKING  │───→│ LISTED  │
│(Новый)  │    │(Звоним)  │    │(Думает)  │    │(Поставил)│
└─────────┘    └────┬─────┘    └────┬─────┘    └─────────┘
                    │               │
                    ↓               ↓
              ┌──────────┐    ┌──────────────┐
              │ REJECTED │    │CALLBACK_SET  │
              │ (Отказ)  │    │(Перезвон назначен)
              └──────────┘    └──────────────┘
                    │               │
                    ↓               ↓
              ┌──────────┐    ┌──────────────┐
              │NO_ANSWER │    │APPOINTMENT_SET│
              │(Нет отв.)│    │(Встреча назначена)
              └──────────┘    └──────────────┘
Описание статусов:
Table
Статус	Код	Описание	Следующий шаг
Новый	new	Только добавлен, не звонили	Начать звонок
В обработке	calling	Сейчас звоним	Выбрать результат
Думает	thinking	Клиент думает, нужен перезвон	Назначить перезвон
Перезвон назначен	callback_scheduled	Конкретная дата/время перезвона	Выполнить перезвон
Встреча назначена	appointment_set	Договорились о встрече/постановке	Подтвердить постановку
Поставлено	listed	Авто успешно поставлено на продажу	Архив
Отказ	rejected	Клиент отказался (с указанием причины)	Архив
Нет ответа	no_answer	Не дозвонились (до 3 попыток)	Повторный звонок
Неверный номер	invalid_phone	Телефон недоступен	Архив
3. АРХИТЕКТУРА МОДУЛЯ
3.1 Структура директорий
plain
Copy
app/crm/                    # Корень модуля (ИЗОЛИРОВАН)
├── __init__.py             # Экспорт crm_router
├── config.py               # Конфигурация модуля
├── constants.py            # Константы, тексты, эмодзи
├── models.py               # SQLAlchemy модели
├── states.py               # FSM состояния
├── router.py               # Главный роутер (точка входа)
│
├── handlers/               # Обработчики сообщений
│   ├── __init__.py
│   ├── add_lead.py         # Добавление авто (парсинг)
│   ├── pipeline.py         # Очередь на прозвон
│   ├── work_card.py        # Рабочая карточка лида
│   ├── reminders.py        # Напоминания
│   ├── search.py           # Поиск по базе
│   └── stats.py            # Статистика
│
├── services/               # Бизнес-логика
│   ├── __init__.py
│   ├── parser.py           # Парсеры Auto.ria/OLX
│   ├── lead_service.py     # CRUD операции
│   ├── reminder_service.py # Управление напоминаниями
│   └── analytics.py        # Агрегация данных
│
├── keyboards/              # UI компоненты
│   ├── __init__.py
│   ├── main.py             # Главное меню
│   ├── pipeline.py         # Клавиатуры очереди
│   ├── card.py             # Клавиатуры карточки
│   └── common.py           # Вспомогательные
│
└── utils/
    └── helpers.py          # Утилиты форматирования
3.2 Точка интеграции
Файл: app/main.py
Изменения: Добавить 2 строки
Python
Copy
# 1. Импорт (в начало файла или в create_dispatcher)
from app.crm import crm_router

# 2. Подключение роутера (внутри create_dispatcher)
dp.include_router(crm_router)
Инициализация БД (в on_startup):
Python
Copy
from app.crm.models import init_crm_tables
await init_crm_tables(engine)  # Создает таблицы crm_*
4. МОДЕЛЬ ДАННЫХ
4.1 Сущность Lead (crm_leads)
Table
Поле	Тип	Описание	Constraints
id	Integer	PK	auto_increment
manager_id	BigInteger	ID менеджера в TG	NOT NULL, INDEX
source	String(20)	Источник: auto_ria, olx, manual	NOT NULL
source_url	Text	URL объявления	NOT NULL, UNIQUE
status	String(30)	Текущий статус	DEFAULT 'new'
priority	Integer	Приоритет 1-5	DEFAULT 3
car_brand	String(50)	Марка авто	NOT NULL
car_model	String(50)	Модель авто	NOT NULL
car_year	Integer	Год выпуска	
car_price	Integer	Цена	INDEX
car_price_currency	String(3)	Валюта	DEFAULT 'USD'
car_mileage	Integer	Пробег, км	
car_location	String(100)	Город	
car_vin	String(20)	VIN-код	
car_photos	JSON	Массив URL фото	DEFAULT []
car_description	Text	Описание из объявления	
owner_name	String(100)	Имя владельца	
owner_phone	String(20)	Телефон	INDEX
owner_phone_hidden	Boolean	Номер был скрыт на сайте	DEFAULT FALSE
call_attempts	Integer	Количество попыток дозвона	DEFAULT 0
last_call_at	DateTime	Время последнего звонка	
success_calls	Integer	Успешных дозвонов	DEFAULT 0
created_at	DateTime	Создание записи	DEFAULT now()
updated_at	DateTime	Обновление	auto_update
archived	Boolean	В архиве	DEFAULT FALSE
4.2 Сущность CallLog (crm_call_logs)
Table
Поле	Тип	Описание
id	Integer	PK
lead_id	Integer	FK → crm_leads.id
manager_id	BigInteger	Кто звонил
result	String(30)	Результат звонка
notes	Text	Заметки менеджера
next_action_type	String(30)	Тип следующего действия
next_action_date	DateTime	Когда нужно действовать
created_at	DateTime	Время записи
4.3 Сущность Reminder (crm_reminders)
Table
Поле	Тип	Описание
id	Integer	PK
lead_id	Integer	FK → crm_leads.id
manager_id	BigInteger	Кому напомнить
remind_at	DateTime	Время напоминания	INDEX
reminder_type	String(30)	callback, appointment, follow_up
message	Text	Текст напоминания
is_completed	Boolean	Выполнено	DEFAULT FALSE
completed_at	DateTime	Когда выполнили
created_at	DateTime	Создание
4.4 SQLAlchemy код
Python
Copy
# app/crm/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Lead(Base):
    __tablename__ = "crm_leads"
    
    id = Column(Integer, primary_key=True)
    manager_id = Column(BigInteger, nullable=False, index=True)
    source = Column(String(20), nullable=False)
    source_url = Column(Text, nullable=False)
    status = Column(String(30), default="new")
    priority = Column(Integer, default=3)
    
    # Car info
    car_brand = Column(String(50), nullable=False)
    car_model = Column(String(50), nullable=False)
    car_year = Column(Integer)
    car_price = Column(Integer)
    car_price_currency = Column(String(3), default="USD")
    car_mileage = Column(Integer)
    car_location = Column(String(100))
    car_vin = Column(String(20))
    car_photos = Column(JSON, default=list)
    car_description = Column(Text)
    
    # Owner info
    owner_name = Column(String(100))
    owner_phone = Column(String(20))
    owner_phone_hidden = Column(Boolean, default=False)
    
    # Stats
    call_attempts = Column(Integer, default=0)
    last_call_at = Column(DateTime)
    success_calls = Column(Integer, default=0)
    
    # Meta
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    archived = Column(Boolean, default=False)
    
    # Relations
    calls = relationship("CallLog", back_populates="lead", order_by="desc(CallLog.created_at)")
    reminders = relationship("Reminder", back_populates="lead", order_by="Reminder.remind_at")

class CallLog(Base):
    __tablename__ = "crm_call_logs"
    
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("crm_leads.id"), nullable=False)
    manager_id = Column(BigInteger, nullable=False)
    result = Column(String(30), nullable=False)
    notes = Column(Text)
    next_action_type = Column(String(30))
    next_action_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    lead = relationship("Lead", back_populates="calls")

class Reminder(Base):
    __tablename__ = "crm_reminders"
    
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("crm_leads.id"), nullable=False)
    manager_id = Column(BigInteger, nullable=False, index=True)
    remind_at = Column(DateTime, nullable=False, index=True)
    reminder_type = Column(String(30), nullable=False)
    message = Column(Text, nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    lead = relationship("Lead", back_populates="reminders")

async def init_crm_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
5. ПАРСИНГ AUTO.RIA
5.1 Требования к парсеру
Целевая ссылка (тестовая):
plain
Copy
https://auto.ria.com/uk/auto_lexus_ct_39224247.html
Извлекаемые данные:
Table
Поле	Селектор/Метод	Fallback
Марка	JSON-LD @type: Vehicle → brand.name	Заголовок h1
Модель	JSON-LD → model	Парсинг заголовка
Год	JSON-LD → vehicleModelDate	Регулярка из заголовка
Цена	div.price_value или JSON-LD	Meta теги
Валюта	Символ рядом с ценой	USD по умолчанию
Пробег	span.argument с "тис. км"	-
Локация	li.item._region или span.region	-
Описание	div.description	div.auto-description_text
Фото	img в галерее, атрибут data-src	src
Имя продавца	div.seller_info_name	h4.seller_name
Телефон	tel:+380... в HTML	Скрыт (phone_hidden=True)
VIN	Регулярка [A-HJ-NPR-Z0-9]{17}	-
5.2 Интерфейс парсера
Python
Copy
# app/crm/services/parser.py

@dataclass
class CarInfo:
    brand: str
    model: str
    year: Optional[int]
    price: int
    currency: str
    mileage: Optional[int]
    location: Optional[str]
    vin: Optional[str]
    photos: List[str]
    description: Optional[str]
    phone: Optional[str]
    seller_name: Optional[str]
    phone_hidden: bool = False

class AutoRiaParser:
    async def parse(self, url: str) -> CarInfo:
        """Возвращает распарсенные данные или raise ParseError"""
        
class ParseError(Exception):
    pass

# Утилита
async def parse_auto_ria(url: str) -> CarInfo:
    async with AutoRiaParser() as parser:
        return await parser.parse(url)
5.3 Особенности реализации
Асинхронность: Использовать aiohttp
Заголовки: Ротация User-Agent, Accept-Language: uk-UA
Таймаут: 10 секунд на запрос
Обработка ошибок:
HTTP != 200 → ParseError("Сайт недоступен")
Нет данных → ParseError("Не удалось распознать объявление")
Телефон: На Auto.ria номер часто скрыт. Если не найден → phone_hidden=True, менеджер вводит вручную.
6. ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРФЕЙС
6.1 Главное меню (Reply Keyboard)
plain
Copy
┌─────────────────────────────────────────┐
│  📋 Очередь на звонок                   │
├─────────────────┬───────────────────────┤
│  ⏰ Напоминания  │  📊 Статистика        │
├─────────────────┼───────────────────────┤
│  🔍 Поиск        │  ⚙️ Настройки         │
└─────────────────┴───────────────────────┘
Команда входа: /crm
6.2 Поток добавления авто (US-001)
Шаг 1: Менеджер отправляет ссылку
Шаг 2: Бот показывает превью:
plain
Copy
🚗 <b>Lexus CT 200h</b> 2014
💰 <b>$12,500</b>
📍 Киев
📏 78,000 км

👤 <b>Александр</b>
📞 <i>Номер скрыт — добавите вручную</i>

<i>Гибрид, идеальное состояние, один владелец...</i>
Клавиатура (Inline):
plain
Copy
[✅ Добавить в очередь]
[✏️ Редактировать данные]
[📞 Добавить номер вручную]
[❌ Отмена]
Шаг 3: При нажатии "Добавить":
Создается запись в БД (status='new')
Бот: ✅ Добавлено в очередь. Приоритет: 3
Предложить: [Следующая ссылка] [В очередь]
6.3 Очередь на прозвон (US-002)
Сортировка: priority DESC, created_at ASC (сначала приоритетные, затем старые)
Формат списка:
plain
Copy
📋 Очередь на звонок (5 авто)

1. 🚗 BMW X5 2019 — $45,000 (Киев) 🔥
2. 🚗 Audi A6 2020 — $38,000 (Одесса)
3. 🚗 Lexus CT 2014 — $12,500 (Киев) ⏰

[▶️ Начать обзвон] [🔍 Фильтр]
При нажатии "Начать": Открывается карточка №1
6.4 Рабочая карточка (US-003)
plain
Copy
┌──────────────────────────────────────────┐
│  🚗 <b>Lexus CT 200h</b> 2014            │
│  💰 $12,500 • 📍 Киев • 📏 78 тыс. км    │
│                                          │
│  👤 Александр                            │
│  📞 +380671234567                        │
│  [📞 Позвонить] [💬 Написать в Telegram] │
│                                          │
│  📝 История:                             │
│  • Сегодня 10:15 — Добавлен в систему    │
│                                          │
│  <b>РЕЗУЛЬТАТ ЗВОНКА:</b>                 │
│  [🤔 Думает] [📅 Договорились на встречу]│
│  [❌ Отказ] [📵 Не отвечает] [⏭️ Дозвон] │
│                                          │
│  [📝 Добавить заметку] [📋 Подробнее]    │
│  [➡️ Следующий] [🏠 В меню]              │
└──────────────────────────────────────────┘
6.5 Обработка результатов (US-004)
Если "🤔 Думает":
plain
Copy
Бот: Когда перезвонить?

[Сегодня вечером] [Завтра]
[Послезавтра] [Через неделю]
[Выбрать дату и время]
При выборе даты:
plain
Copy
Бот: Напишите дату и время (например: "завтра 15:00" или "15.03 11:00")
После установки напоминания:
plain
Copy
✅ Напоминание установлено: 15.03 в 11:00
Добавьте заметку о разговоре (текст или голосовое):
Заметка сохраняется → Предложение следующей карточки
6.6 Напоминания (US-005)
Время: За 5 минут до назначенного времени
Формат уведомления:
plain
Copy
🔔 <b>НАПОМИНАНИЕ</b>

Перезвонить: Александр
🚗 Lexus CT 200h (2014)
💰 $12,500

⏰ Было назначено: 15.03 в 11:00
📝 Ваши заметки: "Ждет зарплату, готов обсудить в пятницу"

[✅ Я позвонил] [⏰ Перенести на...] [❌ Отменить]
При нажатии "Я позвонил": Открывается карточка лида сразу в режиме звонка
7. ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩИМ ПЛАНИРОВЩИКОМ
7.1 Использование scheduler_worker
В существующем проекте есть app/services/scheduler.py с функцией scheduler_worker(bot).
Требование: Интегрировать проверку напоминаний в существующий цикл.
Реализация:
Python
Copy
# app/crm/services/reminder_service.py

async def check_reminders(bot: Bot):
    """Вызывать каждую минуту из scheduler_worker"""
    now = datetime.utcnow()
    reminders = await get_due_reminders(now)  # SELECT * WHERE remind_at <= now AND NOT is_completed
    
    for rem in reminders:
        await send_reminder(bot, rem)
        await mark_reminder_sent(rem.id)  # Или не mark, а ждать подтверждения от менеджера
В app/services/scheduler.py добавить:
Python
Copy
from app.crm.services.reminder_service import check_reminders

async def scheduler_worker(bot: Bot):
    while True:
        await asyncio.sleep(60)  # Каждую минуту
        # ... существующие задачи ...
        await check_reminders(bot)  # ← Добавить
8. ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ
8.1 Зависимости (добавить в requirements.txt)
plain
Copy
beautifulsoup4==4.12.2
lxml==4.9.3
# aiohttp уже есть в проекте
8.2 Конфигурация (app/crm/config.py)
Python
Copy
from pydantic_settings import BaseSettings

class CRMConfig(BaseSettings):
    # Парсинг
    PARSER_TIMEOUT: int = 10
    PARSER_MAX_PHOTOS: int = 5
    
    # Напоминания
    REMINDER_CHECK_INTERVAL: int = 60  # секунд
    REMINDER_DEFAULT_TIME: str = "10:00"  # Если менеджер не указал время
    
    # Очередь
    PIPELINE_PAGE_SIZE: int = 10
    MAX_CALL_ATTEMPTS: int = 3
    
    class Config:
        env_prefix = "CRM_"

crm_config = CRMConfig()
8.3 FSM Состояния (app/crm/states.py)
Python
Copy
from aiogram.fsm.state import State, StatesGroup

class AddLeadStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_phone = State()  # Если скрыт
    confirm_data = State()

class WorkCardStates(StatesGroup):
    in_call = State()
    waiting_result = State()
    thinking_set_date = State()
    appointment_set_date = State()
    adding_notes = State()

class SearchStates(StatesGroup):
    waiting_query = State()
    showing_results = State()
9. КРИТЕРИИ ПРИЕМКИ
9.1 Функциональные тесты
Table
№	Сценарий	Ожидаемый результат
1	Отправить ссылку Auto.ria	Бот показывает превью с корректными данными
2	Нажать "Добавить в очередь"	Запись в БД, статус 'new'
3	Открыть /crm → Очередь	Виден список с добавленным авто
4	Начать звонок → "Думает" → "Завтра 15:00"	Создано напоминание, статус 'thinking'
5	Дождаться времени напоминания	Пришло уведомление с кнопками
6	Нажать "Я позвонил"	Открылась карточка, можно зафиксировать результат
7	3 раза "Не отвечает"	Статус 'no_answer', предложить архивировать
9.2 Интеграционные тесты
[ ] Модуль подключается без ошибок к существующему боту
[ ] Таблицы создаются при старте (если не существуют)
[ ] Не ломает существующий функционал family бота
[ ] Планировщик запускает напоминания без конфликтов
9.3 Нефункциональные требования
Время отклика: < 2 сек на парсинг, < 1 сек на операции БД
Надежность: При ошибке парсера — понятное сообщение, не краш бота
Логирование: Все операции с лидами логировать (уровень INFO)
10. ЭТАПЫ РАЗРАБОТКИ
Этап 1: MVP (3-4 дня)
[ ] Структура модуля, модели БД
[ ] Парсер Auto.ria (базовый)
[ ] Добавление авто по ссылке
[ ] Просмотр очереди (список)
[ ] Базовая карточка с кнопками статусов
[ ] Простые напоминания (через существующий шедулер)
Этап 2: Core (2-3 дня)
[ ] FSM для полноценного диалога в карточке
[ ] История коммуникаций (список звонков)
[ ] Редактирование данных лида
[ ] Поиск по базе
[ ] Обработка "скрытого телефона" (ручной ввод)
Этап 3: Polish (2 дня)
[ ] Статистика и отчеты
[ ] Голосовые заметки (если требуется)
[ ] Причины отказа (категории)
[ ] Приоритеты и сортировка очереди
[ ] Обработка ошибок и edge cases
11. ДОПОЛНИТЕЛЬНЫЕ МАТЕРИАЛЫ
11.1 Примеры сообщений бота
Успешное добавление:
plain
Copy
✅ <b>Добавлено в очередь!</b>

🚗 Lexus CT 200h 2014
📍 Киев • 💰 $12,500
👤 Александр • 📞 +380671234567

Приоритет: ⭐️⭐️⭐️ (3/5)
Позиция в очереди: 3

[📋 Открыть очередь] [➕ Добавить еще]
Статистика (пример):
plain
Copy
📊 <b>Статистика за неделю</b>

📞 Звонков: 45
✅ Успешных дозвонов: 32 (71%)
📅 Встреч назначено: 8
🏆 Поставлено авто: 3
❌ Отказов: 12

Конверсия: 6.6% (3/45)
11.2 Обработка ошибок
Table
Ошибка	Сообщение пользователю
Сайт недоступен	"❌ Не удалось открыть ссылку. Попробуйте позже или добавьте вручную"
Не распознано авто	"❌ Не удалось определить марку/модель. Отправьте данные текстом"
Неверный статус	"⚠️ Ошибка: нельзя перевести из статуса X в Y"
Дубль ссылки	"⚠️ Это авто уже в базе (статус: Думает). Открыть карточку?"
12. КОНТАКТЫ И УТОЧНЕНИЯ
Заказчик: [Ваши контакты]
Тестовая ссылка: https://auto.ria.com/uk/auto_lexus_ct_39224247.html
Доступ к БД: Использовать существующий engine из app/db.py
Вопросы для уточнения:
Нужна ли поддержка OLX в MVP или только Auto.ria?
Сколько менеджеров будет работать? (влияет на мультипользовательность)
Нужны ли голосовые заметки или достаточно текста?
Какие причины отказа предусмотреть? (дорого, уже продал, не доверяет, и т.д.)
Статус документа: ✅ Готов к разработке
Версия для разработчика: Приложить ссылку на репозиторий AliceUniverse/alisa_family_bot
