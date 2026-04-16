from warden.mcp_server import SERVER_NAME, SERVER_VERSION, server_metadata


def test_server_metadata_declares_expected_tools() -> None:
    metadata = server_metadata()
    assert metadata["name"] == SERVER_NAME
    assert metadata["version"] == SERVER_VERSION
    names = {tool["name"] for tool in metadata["tools"]}
    assert names == {
        "warden_triage",
        "warden_investigate",
        "warden_code",
        "warden_review",
    }


def test_server_metadata_tools_have_parameters() -> None:
    metadata = server_metadata()
    for tool in metadata["tools"]:
        assert tool["description"], f"{tool['name']} missing description"
        assert isinstance(tool["parameters"], dict)
        assert tool["parameters"], f"{tool['name']} has no parameters"
