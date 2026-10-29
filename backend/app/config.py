from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / '.env', extra='ignore')
    oneflow_mode: Literal['demo', 'cloud'] = 'demo'
    oneflow_data_dir: Path = Path(__file__).resolve().parents[1] / 'data'
    google_cloud_project: str = ''
    google_cloud_location: str = 'global'
    vertex_model: str = 'gemini-2.5-flash'
    document_ai_location: str = 'us'
    document_ai_processor_id: str = ''
    frontend_origin: str = 'http://localhost:5173'

    def cloud_missing(self) -> list[str]:
        return [name for name, value in {
            'GOOGLE_CLOUD_PROJECT': self.google_cloud_project,
            'DOCUMENT_AI_PROCESSOR_ID': self.document_ai_processor_id,
        }.items() if not value]


settings = Settings()
