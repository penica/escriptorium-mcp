from pathlib import Path

import anyio

from tests.mutation_fixture import Case, api_fixture, exercise


def test_model_upload_when_local_model_is_provided(tmp_path: Path) -> None:
    # Given a local model and an isolated API fixture.
    model = tmp_path / "hand.mlmodel"
    _ = model.write_bytes(b"fixture-kraken-model")
    case = Case(
        "upload_model",
        {"model": {"file_path": str(model), "name": "Parish", "job": 2}},
        "models/",
        multipart=(
            b'name="file"; filename="hand.mlmodel"',
            b"fixture-kraken-model",
            b'name="name"\r\n\r\nParish',
            b'name="job"\r\n\r\nRecognize',
        ),
    )
    with api_fixture() as fixture:
        # When the actual MCP client requests model registration.
        # Then the worker sends the binary and exact model metadata.
        anyio.run(exercise, fixture, case)
