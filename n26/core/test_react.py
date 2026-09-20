import json

import pytest
from bs4 import BeautifulSoup
from django.template import Context, Template

from n26.core.templatetags import react


def test_island_props_are_inert_json_and_preloads_include_shared_imports(monkeypatch):
    monkeypatch.setattr(
        react,
        "_manifest",
        lambda: {
            "entries/authoring-list.tsx": {
                "file": "assets/list-12345678.js",
                "imports": ["_react"],
            },
            "_react": {"file": "assets/react-12345678.js"},
        },
    )
    value = '</script><img src=x onerror="alert(1)">&'
    result = Template(
        '{% load react %}{% react_island "authoring-list" props %}'
    ).render(Context({"props": {"label": value}}))
    soup = BeautifulSoup(result, "html.parser")
    host = soup.select_one("[data-react-module]")
    assert host.has_attr("x-ignore") and host.has_attr("hx-disable")
    assert soup.find("img") is None
    assert json.loads(soup.find(id=host["data-react-props"]).string) == {"label": value}
    assert [link["href"] for link in soup.select('link[rel="modulepreload"]')] == [
        "/static/n26/react/assets/list-12345678.js",
        "/static/n26/react/assets/react-12345678.js",
    ]


def test_unknown_island_names_fail_before_build_lookup():
    with pytest.raises(ValueError, match="kebab-case"):
        react.react_island("../../file", {})


def test_production_storage_preserves_vite_module_urls(tmp_path):
    """Preloads and relative imports must identify the same React module."""
    from django.core.files.storage import FileSystemStorage
    from whitenoise.storage import CompressedManifestStaticFilesStorage

    source = FileSystemStorage(location=react.BUILD)
    storage = CompressedManifestStaticFilesStorage(location=tmp_path)
    manifest = json.loads((react.BUILD / "manifest.json").read_text())
    files = {chunk["file"] for chunk in manifest.values()}
    paths = {}
    for file in files:
        name = f"n26/react/{file}"
        with source.open(file) as contents:
            storage.save(name, contents)
        paths[name] = (source, file)
    results = list(storage.post_process(paths))
    assert not [
        processed for _, _, processed in results if isinstance(processed, Exception)
    ]
    for file in files:
        original = (tmp_path / "n26/react" / file).read_text()
        assert original == (react.BUILD / file).read_text()
        assert (tmp_path / "n26/react" / f"{file}.gz").exists()
    entry = manifest["entries/authoring-list.tsx"]
    for dependency in entry["imports"]:
        assert (
            manifest[dependency]["file"].split("/")[-1]
            in (react.BUILD / entry["file"]).read_text()
        )
