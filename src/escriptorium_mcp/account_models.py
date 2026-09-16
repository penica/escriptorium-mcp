"""Native account fields and bounded local directory search inputs."""

import re
from typing import Annotated, Self

from pydantic import AfterValidator, Field, StrictBool, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.record_models import Patch


def django_username(value: str) -> str:
    """Match Django's Unicode username syntax without changing stored spelling."""
    if re.fullmatch(r"[\w.@+-]+", value) is None:
        msg = "Username may contain Unicode word characters and . @ + - only."
        raise ValueError(msg)
    return value


Username = Annotated[
    str,
    Field(strict=True, min_length=1, max_length=150),
    AfterValidator(django_username),
]
AccountEmail = Annotated[
    str, Field(strict=True, min_length=1, max_length=255, pattern=r"\S")
]
DisplayName = Annotated[str, Field(strict=True, max_length=150)]
DirectorySearch = Annotated[
    str, Field(strict=True, min_length=1, max_length=512, pattern=r"\S")
]


class UserCreate(Input):
    """Create a native account row; password setup and invitations are separate."""

    username: Username
    email: AccountEmail
    first_name: DisplayName = ""
    last_name: DisplayName = ""
    is_active: StrictBool = True


class UserPatch(Patch):
    """Edit native account fields; empty display names deliberately clear them."""

    username: Username | None = None
    email: AccountEmail | None = None
    first_name: DisplayName | None = None
    last_name: DisplayName | None = None
    is_active: StrictBool | None = None

    @model_validator(mode="after")
    def require_nonnull_changes(self) -> Self:
        """Preserve omitted fields but reject explicit null for every native field."""
        values = {
            "username": self.username,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "is_active": self.is_active,
        }
        if any(values[field] is None for field in self.model_fields_set):
            msg = "Account changes cannot be null; omit fields to preserve them."
            raise ValueError(msg)
        return self
