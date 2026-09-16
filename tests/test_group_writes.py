"""Group members can perform native rename/delete without an invented owner gate."""

import anyio
import pytest

from tests.group_fixture import (
    GROUP,
    GROUPS,
    GroupFixture,
    group_fixture,
    group_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize("staff", [True, False])
def test_member_not_owner_can_rename_without_staff_gate(*, staff: bool) -> None:
    # Given a membership-visible group whose owner is another account.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When a regular member uses the native name-only PATCH.
            result = await invoke(
                session, "update_group", {"group_id": 7, "name": "Renamed"}
            )
            # Then the result preserves membership and unrelated native metadata.
            assert isinstance(result, dict)
            assert result["name"] == "Renamed"
            assert result["owner"] == 99
            assert result["users"] == [{"pk": 2}]

    with group_fixture() as fixture:
        fixture.current["is_staff"] = staff
        fixture.group["owner"] = 99
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", GROUP, None),
        ("PATCH", GROUP, {"name": "Renamed"}),
    ]


def test_member_delete_has_no_post_delete_read() -> None:
    # Given a group visible by membership rather than ownership.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When the native group deletion succeeds.
            result = await invoke(session, "delete_group", {"group_id": 7})
            # Then the bodyless204 result remains successful.
            assert result == {"status": "success", "http_status": 204}

    with group_fixture() as fixture:
        fixture.group["owner"] = 99
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", GROUP, None), ("DELETE", GROUP, {})]


@pytest.mark.parametrize("failure", ["invisible", "identity", "denied"])
def test_group_scope_failure_prevents_mutation(failure: str) -> None:
    # Given a staff caller whose requested group is outside visible membership.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When a scoped delete fails its native read or identity check.
            result = await session.call_tool("delete_group", {"group_id": 7})
            # Then staff status does not become a group-access bypass.
            assert result.is_error

    with group_fixture() as fixture:
        fixture.current["is_staff"] = True
        if failure == "identity":
            fixture.group["pk"] = 999
        else:
            fixture.failures["GET " + GROUP] = 404 if failure == "invisible" else 403
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", GROUP, None)]


@pytest.mark.parametrize("status", [400, 500])
def test_failed_creation_is_not_retried_or_repaired(status: int) -> None:
    # Given duplicate-name or ambiguous native save failure on group creation.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When the single native creation fails.
            result = await session.call_tool(
                "create_group",
                {"name": "Researchers", "acknowledge_native_create_limitations": True},
            )
            # Then failure retains possible effects without automatic repair.
            assert result.is_error
            assert str(status) in result.model_dump_json()
            assert "may" in result.model_dump_json().lower()

    with group_fixture() as fixture:
        fixture.failures["POST " + GROUPS] = status
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1
    assert fixture.requests[-1][0] == "POST"
