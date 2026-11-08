"""Read the display contract embedded in a real React page response."""

import json

from bs4 import BeautifulSoup


def island_props(response, name):
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, "html.parser")
    host = soup.select_one(f'[data-react-name="{name}"]')
    assert host is not None
    assert not host.select("[data-react-name], [x-data], [hx-target]")
    return json.loads(soup.find(id=host["data-react-props"]).string)


def equip_props(response):
    return island_props(response, "equip")


def equipment_rows(props):
    return [
        row
        for section in props["sections"]
        for category in section["categories"]
        for row in category["entries"]
    ]
