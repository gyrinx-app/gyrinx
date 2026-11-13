"""Submit native action scenarios with the identity issued by their current form."""


def post_action(client, url, data=None, **kwargs):
    """Keep one issued identity on a reused payload, including deliberate retries."""
    data = {} if data is None else data
    page = client.get(url, follow=True)
    if page.status_code == 200 and page.context:
        props = page.context.get("action_props")
        if props:
            data.setdefault("command_key", props["values"]["command_key"])
            data.setdefault("revision", props["values"]["revision"])
        elif page.context.get("choice_props"):
            data.setdefault(
                "request_key", page.context["choice_props"]["values"]["request_key"]
            )
    return client.post(url, data, **kwargs)
