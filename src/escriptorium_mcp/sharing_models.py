"""One explicit native recipient for each additive sharing grant."""

from typing import Annotated, Literal

from pydantic import Field

from escriptorium_mcp.account_models import Username
from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier


class ShareUser(Input):
    """Share with a known username, even outside the visible user directory."""

    kind: Literal["user"]
    username: Username


class ShareGroup(Input):
    """Share with a group in the caller's native membership scope."""

    kind: Literal["group"]
    group_id: Identifier


ShareTarget = Annotated[ShareUser | ShareGroup, Field(discriminator="kind")]
