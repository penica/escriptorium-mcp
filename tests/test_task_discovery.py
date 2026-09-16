import anyio

from tests.ontology_fixture import OntologyFixture, ontology_session


async def discover_monitoring() -> None:
    async with ontology_session(OntologyFixture("http://127.0.0.1:1/")) as session:
        discovered = await session.list_tools()
        tools = {tool.name: tool for tool in discovered.tools}
        for name in (
            "list_document_tasks",
            "list_task_groups",
            "get_task_group",
            "get_document_job_status",
            "get_import_status",
        ):
            assert name in tools
            annotation = tools[name].annotations
            assert annotation is not None
            assert annotation.read_only_hint
        for name in ("cancel_document_tasks", "cancel_document_import"):
            assert name in tools
            annotation = tools[name].annotations
            assert annotation is not None
            assert annotation.destructive_hint
            assert not annotation.read_only_hint


def test_monitoring_discovery_when_no_credentials_are_needed() -> None:
    # Given a real MCP subprocess with an unreachable API URL.
    # When the client discovers the tool catalogue.
    # Then monitoring and cancellation advertise their correct operation type.
    anyio.run(discover_monitoring)
