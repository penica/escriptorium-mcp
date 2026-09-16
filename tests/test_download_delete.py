"""Deleting an owned download sends one request and preserves native failures."""

import anyio
import pytest

from tests.download_fixture import DETAIL, FP, download_fixture, download_session


@pytest.mark.parametrize("status", [204, 403, 404, 500])
def test_delete_has_no_retry_or_requery(status: int) -> None:
    with download_fixture() as fixture:
        if status != 204:
            fixture.failures[DETAIL] = status

        async def run() -> None:
            async with download_session(fixture) as session:
                response = await session.call_tool(
                    "delete_download", {"fingerprint": FP}
                )
                assert response.is_error is (status != 204)
                if status != 204:
                    assert str(status) in str(response.content)
                assert "fixture-key" not in str(response.content)

        anyio.run(run)
    assert fixture.requests == [("DELETE", DETAIL)]
