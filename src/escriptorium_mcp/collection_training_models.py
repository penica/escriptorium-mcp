"""Collection training options and the source references read from saved items."""

from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.model_models import ModelName


class CollectionTraining(Input):
    """Training uses saved collection membership, without per-request page filters."""

    model: Identifier | None = None
    model_name: ModelName | None = None
    override: bool = False

    @model_validator(mode="after")
    def require_model(self) -> Self:
        """Require a base model or new name and keep absent options off the wire."""
        if self.model is None and self.model_name is None:
            msg = "Supply model or model_name."
            raise ValueError(msg)
        if ("model" in self.model_fields_set and self.model is None) or (
            "model_name" in self.model_fields_set and self.model_name is None
        ):
            msg = "Omit unused model/model_name options instead of passing null."
            raise ValueError(msg)
        return self


class CollectionTrainingItem(BaseModel):
    """Only source identities are needed; other native item fields remain optional."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    document_id: Identifier
    document_part: Identifier
    transcription_layer: Identifier


class CollectionTrainingItems(BaseModel):
    """The complete native page envelope after the strict paginator has finished."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    results: list[CollectionTrainingItem]
