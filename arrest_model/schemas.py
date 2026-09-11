"""Contrato del payload de la API: los 6 campos crudos de un reporte de crimen."""

from datetime import datetime

from pydantic import BaseModel, Field


class CrimeReport(BaseModel):
    """Reporte crudo de un crimen, con los campos del dataset de Chicago."""

    iucr: str = Field(examples=["1310"])
    primary_type: str = Field(examples=["CRIMINAL DAMAGE"])
    location_description: str | None = Field(default=None, examples=["APARTMENT"])
    date: datetime = Field(examples=["2024-12-31T23:58:00"])
    latitude: float = Field(examples=[41.771470188])
    longitude: float = Field(examples=[-87.59074212])
