from django.tasks import task


@task
def hello_world(name: str = "World"):
    print(f"Hello, {name}!")
    return f"Greeted {name}"
