"""Contrato del payload de la API: los 6 campos crudos de un reporte de crimen.

Las validaciones rechazan la entrada antes de llegar al modelo: FastAPI las traduce a un 422.
"""

from datetime import datetime
from typing import Literal, get_args
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

CHICAGO = ZoneInfo("America/Chicago")

# Los 31 valores de "Primary Type" que aparecen en el train del TP-final.
PrimaryType = Literal[
    "ARSON",
    "ASSAULT",
    "BATTERY",
    "BURGLARY",
    "CONCEALED CARRY LICENSE VIOLATION",
    "CRIMINAL DAMAGE",
    "CRIMINAL SEXUAL ASSAULT",
    "CRIMINAL TRESPASS",
    "DECEPTIVE PRACTICE",
    "GAMBLING",
    "HOMICIDE",
    "HUMAN TRAFFICKING",
    "INTERFERENCE WITH PUBLIC OFFICER",
    "INTIMIDATION",
    "KIDNAPPING",
    "LIQUOR LAW VIOLATION",
    "MOTOR VEHICLE THEFT",
    "NARCOTICS",
    "NON-CRIMINAL",
    "OBSCENITY",
    "OFFENSE INVOLVING CHILDREN",
    "OTHER NARCOTIC VIOLATION",
    "OTHER OFFENSE",
    "PROSTITUTION",
    "PUBLIC INDECENCY",
    "PUBLIC PEACE VIOLATION",
    "ROBBERY",
    "SEX OFFENSE",
    "STALKING",
    "THEFT",
    "WEAPONS VIOLATION",
]
PRIMARY_TYPES: tuple[str, ...] = get_args(PrimaryType)

# Ejemplo único del contrato: primera fila real de Crimes_Chicago_2024.csv (TP-final).
# Lo reusan la doc de OpenAPI, el cliente de prueba y los tests, para que no se desincronicen.
EXAMPLE_REPORT: dict[str, object] = {
    "iucr": "1310",
    "primary_type": "CRIMINAL DAMAGE",
    "location_description": "APARTMENT",
    "date": "2024-12-31T23:58:00",
    "latitude": 41.771470188,
    "longitude": -87.59074212,
}


class CrimeReport(BaseModel):
    """Reporte crudo de un crimen, con los campos del dataset de Chicago.

    Un IUCR o un lugar que el modelo no vio en train son válidos: se codifican con frecuencia 0,
    igual que hizo el TP-final con los datos de test.
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [EXAMPLE_REPORT]})

    iucr: str = Field(pattern=r"^[0-9]{3}[0-9A-Z]$")
    primary_type: PrimaryType
    location_description: str | None = None
    date: datetime
    latitude: float = Field(ge=41.60, le=42.05)  # límites de Chicago
    longitude: float = Field(ge=-87.95, le=-87.50)

    @field_validator("iucr", "primary_type", "location_description", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        """Quita espacios y pasa a mayúsculas, como están las categorías en train."""
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("date", mode="after")
    @classmethod
    def to_chicago_time(cls, value: datetime) -> datetime:
        """Sin zona horaria se asume hora de Chicago; con zona, se convierte a esa hora."""
        if value.tzinfo is None:
            return value
        return value.astimezone(CHICAGO).replace(tzinfo=None)


class PredictionOut(BaseModel):
    """Predicción y versión del modelo que la produjo."""

    arrest: int = Field(ge=0, le=1)
    probability: float = Field(ge=0.0, le=1.0)
    model_name: str
    model_version: int


class BatchRequest(BaseModel):
    """Lote de reportes para predecir en una sola llamada."""

    model_config = ConfigDict(extra="forbid")

    reports: list[CrimeReport] = Field(min_length=1, max_length=1000)


class BatchPredictionOut(BaseModel):
    """Predicciones del lote, en el mismo orden que los reportes de entrada."""

    predictions: list[PredictionOut]
