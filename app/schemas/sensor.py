from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SensorReadingCreate(BaseModel):
    equipment_id: str
    equipment_type: Optional[str] = None
    temperature: float
    vibration: float = Field(ge=0)
    pressure: float = Field(ge=0)
    current: float = Field(ge=0)
    speed: float = Field(ge=0)
    gas: float = Field(default=0.0, ge=0, le=100)   # % CH4 (metan)


class SensorReadingOut(BaseModel):
    id: int
    time: datetime
    equipment_id: str
    equipment_type: Optional[str] = None
    temperature: float
    vibration: float
    pressure: float
    current: float
    speed: float
    gas: Optional[float] = None
    is_anomaly: bool
    anomaly_score: float

    model_config = {"from_attributes": True}


class AnomalyLogOut(BaseModel):
    id: int
    time: datetime
    equipment_id: str
    equipment_type: Optional[str] = None
    anomaly_score: float
    description: Optional[str]
    resolved: bool

    model_config = {"from_attributes": True}
