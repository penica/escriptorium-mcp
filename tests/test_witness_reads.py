"""Owned witness listing and detail retain native shapes and enforce identity."""

import anyio
import pytest
from pydantic import JsonValue

from tests.transcription_fixture import invoke
from tests.witness_fixture import (
    WITNESS,
    WITNESSES,
    WitnessFixture,
    witness_fixture,
    witness_session,
)


def test_owned_witness_pages_and_raw_detail_are_preserved() -> None:
    # Given native paginated witness metadata with unknown fields and query-only next.
    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the full owned catalogue and detail are requested.
            result = await invoke(session, "list_textual_witnesses", {})
            # Then full pagination preserves count/extras and native pk spelling.
            assert result == {
                "count": 2,
                "next": None,
                "future": 0,
                "results": [fixture.witness, {"pk": 8, "owner": "fixture-owner"}],
            }
            assert (
                await invoke(session, "get_textual_witness", {"witness_id": 7})
                == fixture.witness
            )
            fixture.responses[WITNESSES] = []
            assert await invoke(session, "list_textual_witnesses", {}) == []

    with witness_fixture() as fixture:
        fixture.responses[WITNESSES] = {
            "count": 2,
            "next": "?page=2",
            "future": 0,
            "results": [fixture.witness],
        }
        fixture.responses[WITNESSES + "?page=2"] = {
            "next": None,
            "results": [{"pk": 8, "owner": "fixture-owner"}],
        }
        anyio.run(run, fixture)
    assert fixture.requests[:2] == [
        ("GET", WITNESSES, None),
        ("GET", WITNESSES + "?page=2", None),
    ]


@pytest.mark.parametrize("metadata", [{"pk": 8}, {"pk": "7"}, {"pk": True}, {}])
def test_wrong_or_malformed_witness_id_is_rejected(metadata: JsonValue) -> None:
    # Given owned detail returning an unrelated or malformed witness ID.
    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the requested record is read.
            result = await session.call_tool("get_textual_witness", {"witness_id": 7})
            # Then raw metadata cannot override the requested identity.
            assert result.is_error

    with witness_fixture() as fixture:
        fixture.responses[WITNESS] = metadata
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", WITNESS, None)]
