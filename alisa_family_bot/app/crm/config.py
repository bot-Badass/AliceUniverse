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
