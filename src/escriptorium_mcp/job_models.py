"""Validated processing and training job inputs."""

from typing import Annotated, Final, Literal, Self

from pydantic import Field, FilePath, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier, Name
from escriptorium_mcp.model_models import JobLabel, ModelName

MIN_TRAINING_IMAGES: Final = 2

Parts = Annotated[list[Identifier], Field(min_length=1)]


class Segmentation(Input):
    """Require explicit pages; preserve existing segmentation unless overridden."""

    parts: Parts
    model: Identifier | None = None
    steps: Literal["both", "lines", "masks", "regions"] = "both"
    override: bool = False
    text_direction: Literal[
        "horizontal-lr",
        "horizontal-rl",
        "vertical-lr",
        "vertical-rl",
    ] = "horizontal-lr"


class Recognition(Input):
    """Transcribe selected pages with an existing recognizer and layer."""

    parts: Parts
    model: Identifier
    transcription: Identifier


class Training(Input):
    """Train a new named model or continue an existing one."""

    parts: Parts
    model: Identifier | None = None
    model_name: Name | None = None
    override: bool = False

    @model_validator(mode="after")
    def require_model(self) -> Self:
        """Match the server requirement for a starting model or output name."""
        if self.model is None and self.model_name is None:
            msg = "Supply model or model_name."
            raise ValueError(msg)
        return self


class RecognitionTraining(Training):
    """Recognition training uses a ground-truth transcription layer."""

    transcription: Identifier


class SegmentationTraining(Training):
    """Segmentation training requires at least two distinct page images."""

    @model_validator(mode="after")
    def require_images(self) -> Self:
        """Reject training sets smaller than the API minimum."""
        if len(set(self.parts)) < MIN_TRAINING_IMAGES:
            msg = "Segmentation training requires at least two distinct pages."
            raise ValueError(msg)
        return self


class CancelTask(Input):
    """Cancel a single task report belonging to the specified document."""

    task_report: Identifier


class ModelUpload(Input):
    """Upload a local Kraken model: job 1 segments, job 2 recognizes text."""

    file_path: FilePath
    name: ModelName
    job: Literal[1, 2]


class ModelMetadata(Input):
    """Model registration metadata sent with its binary file."""

    name: ModelName
    job: JobLabel
