from tool_manifest import analytics_routes, manifest_tools


def test_tool_manifest_has_unique_tools_and_functional_assignable_widgets():
    tools = manifest_tools()
    assert len({tool["id"] for tool in tools}) == len(tools)
    assert all(tool.get("widget") for tool in tools if tool["status"] in {"live", "new"})


def test_usage_routes_derive_from_manifest_and_keep_aliases():
    routes = analytics_routes()
    by_path = {path: tool_id for path, tool_id, _ in routes}
    assert by_path["/executive-report"] == "executive_report"
    assert by_path["/file-explorer"] == "file_explorer"
    assert by_path["/tamarac"] == "pipeline_logging"
    assert by_path["/app-usage"] == "admin"
    assert [len(path) for path, _, _ in routes] == sorted(
        (len(path) for path, _, _ in routes), reverse=True
    )
