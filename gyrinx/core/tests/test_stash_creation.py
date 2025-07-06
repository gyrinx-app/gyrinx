import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import List, ListFighter


@pytest.mark.django_db
def test_new_list_creates_stash_fighter():
    """Test that creating a new list automatically creates a stash fighter"""
    # Create a user
    user = User.objects.create_user(username="testuser", password="testpass")
    
    # Create a house
    house = ContentHouse.objects.create(name="Test House")
    
    # Login
    client = Client()
    client.login(username="testuser", password="testpass")
    
    # Create a new list
    response = client.post(
        reverse("core:lists-new"),
        {
            "name": "Test List",
            "content_house": house.id,
            "public": False,
        },
    )
    
    # Check redirect
    assert response.status_code == 302
    
    # Check list was created
    list_ = List.objects.get(name="Test List")
    assert list_.owner == user
    assert list_.content_house == house
    
    # Check stash fighter was created
    stash_fighter = ListFighter.objects.get(list=list_, content_fighter__is_stash=True)
    assert stash_fighter.name == "Stash"
    assert stash_fighter.content_fighter.is_stash is True
    assert stash_fighter.content_fighter.base_cost == 0
    assert stash_fighter.owner == user


@pytest.mark.django_db
def test_show_stash_adds_stash_fighter():
    """Test that the show_stash view adds a stash fighter to a list that doesn't have one"""
    # Create a user and a list without a stash fighter
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")
    list_ = List.objects.create(name="Test List", content_house=house, owner=user)
    
    # Verify no stash fighter initially
    assert not list_.listfighter_set.filter(content_fighter__is_stash=True).exists()
    
    # Login
    client = Client()
    client.login(username="testuser", password="testpass")
    
    # Call show_stash
    response = client.get(reverse("core:list-show-stash", args=[list_.id]))
    
    # Check redirect
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[list_.id])
    
    # Check stash fighter was created
    stash_fighter = ListFighter.objects.get(list=list_, content_fighter__is_stash=True)
    assert stash_fighter.name == "Stash"
    assert stash_fighter.content_fighter.is_stash is True
    assert stash_fighter.content_fighter.base_cost == 0
    assert stash_fighter.owner == user


@pytest.mark.django_db
def test_show_stash_does_not_duplicate():
    """Test that show_stash doesn't create a duplicate stash fighter"""
    # Create a user and a list with a stash fighter
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")
    list_ = List.objects.create(name="Test List", content_house=house, owner=user)
    
    # Create an existing stash fighter
    from gyrinx.content.models import ContentFighter
    stash_content = ContentFighter.objects.create(
        house=house,
        is_stash=True,
        type="Stash",
        category="STASH",
        base_cost=0,
    )
    ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_content,
        list=list_,
        owner=user,
    )
    
    # Login
    client = Client()
    client.login(username="testuser", password="testpass")
    
    # Call show_stash
    response = client.get(reverse("core:list-show-stash", args=[list_.id]))
    
    # Check redirect
    assert response.status_code == 302
    
    # Check only one stash fighter exists
    stash_count = list_.listfighter_set.filter(content_fighter__is_stash=True).count()
    assert stash_count == 1


@pytest.mark.django_db
def test_show_stash_requires_ownership():
    """Test that show_stash requires the user to own the list"""
    # Create two users
    owner = User.objects.create_user(username="owner", password="testpass")
    other_user = User.objects.create_user(username="other", password="testpass")
    
    # Create a list owned by the first user
    house = ContentHouse.objects.create(name="Test House")
    list_ = List.objects.create(name="Test List", content_house=house, owner=owner)
    
    # Login as the other user
    client = Client()
    client.login(username="other", password="testpass")
    
    # Try to call show_stash
    response = client.get(reverse("core:list-show-stash", args=[list_.id]))
    
    # Should return 404
    assert response.status_code == 404