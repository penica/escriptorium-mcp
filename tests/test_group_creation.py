"""Native group acceptance survives missing ownership and failed verification."""

import anyio
import pytest
from pydantic import JsonValue

from escriptorium_mcp import group_creation
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import call
from tests.group_fixture import (
    CURRENT,
    GROUP,
    GROUPS,
    GroupFixture,
    group_fixture,
    group_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    ("detail", "status", "member", "owner"),
    [
        (
            {"pk": 7, "users": [{"pk": 2}], "owner": 2, "custom": "keep"},
            "verified",
            True,
            True,
        ),
        ({"pk": 7, "users": [], "owner": None}, "incomplete", False, False),
        ({"pk": 7, "users": [{"pk": 2}], "owner": 3}, "incomplete", True, False),
        ({"pk": 7}, "incomplete", None, None),
        ({"pk": 7, "users": []}, "incomplete", False, None),
        ({"pk": 7, "owner": None}, "incomplete", None, False),
    ],
)
def test_group_creation_reports_only_observed_membership(
    detail: JsonValue, status: str, *, member: bool | None, owner: bool | None
) -> None:
    # Given a deployment returning owned, ownerless or incomplete group metadata.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When native creation and its one diagnostic readback complete.
            result = await invoke(
                session,
                "create_group",
                {"name": "Researchers", "acknowledge_native_create_limitations": True},
            )
            # Then acceptance and evidence-based membership/ownership stay separate.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == fixture.created[0]
            verification = result["verification"]
            assert isinstance(verification, dict)
            assert verification["status"] == status
            assert verification["readable"] is True
            assert verification["creator_is_member"] is member
            assert verification["creator_is_owner"] is owner
            assert verification["readback"] == detail

    with group_fixture() as fixture:
        fixture.responses["GET " + GROUP] = detail
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", CURRENT, None),
        ("POST", GROUPS, {"name": "Researchers"}),
        ("GET", GROUP, None),
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "404",
        "403",
        "500",
        "invalid_json",
        "disconnect",
        "identity",
        "invalid_owner",
        "invalid_users",
    ],
)
def test_readback_failure_preserves_accepted_creation(failure: str) -> None:
    # Given the source-like ownerless creation or another unreadable diagnostic result.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When the bounded post-create observation fails.
            result = await invoke(
                session,
                "create_group",
                {"name": "Researchers", "acknowledge_native_create_limitations": True},
            )
            # Then creation remains accepted without invented negative observations.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == fixture.created[0]
            verification = result["verification"]
            assert isinstance(verification, dict)
            assert verification["status"] == "unavailable"
            assert verification["readable"] is None
            assert verification["creator_is_member"] is None
            assert verification["creator_is_owner"] is None
            assert verification["readback"] is None

    with group_fixture() as fixture:
        fixture.created[0] = {"pk": 7, "users": [], "owner": None, "custom": "accepted"}
        if failure in {"404", "403", "500"}:
            fixture.failures["GET " + GROUP] = int(failure)
        if failure == "invalid_json":
            fixture.malformed.add("GET " + GROUP)
        if failure == "disconnect":
            fixture.disconnect.add("GET " + GROUP)
        if failure == "identity":
            fixture.group["pk"] = 999
        if failure == "invalid_owner":
            fixture.group["owner"] = False
        if failure == "invalid_users":
            fixture.group["users"] = None
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", CURRENT, None),
        ("POST", GROUPS, {"name": "Researchers"}),
        ("GET", GROUP, None),
    ]


@pytest.mark.parametrize(
    "created", [{"name": "missing"}, {"pk": "7"}, {"pk": 0}, {"pk": True}, []]
)
def test_invalid_creation_identity_prevents_readback(created: JsonValue) -> None:
    # Given native success without a usable strict group identity.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When accepted metadata cannot identify an owned readback route.
            result = await invoke(
                session,
                "create_group",
                {"name": "Researchers", "acknowledge_native_create_limitations": True},
            )
            # Then raw acceptance survives and no guessed ID is requested.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == created
            verification = result["verification"]
            assert isinstance(verification, dict)
            assert verification["status"] == "unavailable"

    with group_fixture() as fixture:
        fixture.created[0] = created
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", CURRENT, None),
        ("POST", GROUPS, {"name": "Researchers"}),
    ]


def test_malformed_optional_post_fields_do_not_replace_readback_evidence() -> None:
    # Given successful creation with a usable ID but malformed optional POST metadata.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When readable matching detail supplies actual membership and ownership.
            result = await invoke(
                session,
                "create_group",
                {"name": "Researchers", "acknowledge_native_create_limitations": True},
            )
            # Then final verification uses readback and preserves the original response.
            assert isinstance(result, dict)
            assert result["submission"] == fixture.created[0]
            verification = result["verification"]
            assert isinstance(verification, dict)
            assert verification["status"] == "verified"

    with group_fixture() as fixture:
        fixture.created[0] = {"pk": 7, "owner": False, "users": "invalid"}
        anyio.run(run, fixture)
    assert len(fixture.requests) == 3


def test_worker_launch_oserror_after_creation_preserves_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given actual native creation followed by an OS failure launching readback.
    attempts: list[str] = []

    async def readback_launch_fault(request: ApiRequest) -> JsonValue:
        attempts.append(request.method)
        if request.method == "GET":
            message = "Fixture worker launch failed"
            raise OSError(message)
        return await call(request)

    with group_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        monkeypatch.setattr(group_creation, "call", readback_launch_fault)
        # When only the post-acceptance worker launch fails.
        result = anyio.run(group_creation.submit_group, "Researchers")
    # Then acceptance remains and no speculative cleanup or second POST occurs.
    assert isinstance(result, dict)
    assert result["accepted"] is True
    assert result["submission"] == fixture.created[0]
    verification = result["verification"]
    assert isinstance(verification, dict)
    assert verification["status"] == "unavailable"
    assert attempts == ["POST", "GET"]
    assert fixture.requests == [
        ("GET", CURRENT, None),
        ("POST", GROUPS, {"name": "Researchers"}),
    ]
