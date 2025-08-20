import pytest

from gyrinx.content.models import ContentBook, ContentPageRef


@pytest.mark.django_db
def test_pageref_books(content_books):
    assert len(list(ContentBook.objects.all())) == 8
    assert len(list(ContentBook.objects.filter(obsolete=False))) == 7


@pytest.mark.django_db
def test_pageref_refs(content_page_refs_full):
    assert len(list(ContentPageRef.objects.all())) == 566
    assert ContentPageRef.objects.filter(title="Agility").count() == 1
    agility = ContentPageRef.objects.get(title="Agility")
    assert agility.book.shortname == "Core"
    assert f"{agility}" == "Core - Skills - p256 - Agility"

    charter_master = ContentPageRef.find(
        title="Ironhead Squat Prospectors Charter Master"
    )

    settlement_raid_outcast = ContentPageRef.objects.get(
        title="Settlement Raid",
        book__shortname="Outcast",
    )
    settlement_raid_core = ContentPageRef.objects.get(
        title="Settlement Raid",
        book__shortname="Core",
    )

    assert list(ContentPageRef.find_similar("Agility")) == [agility]
    assert list(ContentPageRef.find_similar("Charter Master")) == [charter_master]
    assert list(ContentPageRef.find_similar("Settlement Raid")) == [
        settlement_raid_outcast,
        settlement_raid_core,
    ]
