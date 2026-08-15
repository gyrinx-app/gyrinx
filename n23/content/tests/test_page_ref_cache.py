"""
Cache-key behaviour for ContentPageRef.find_similar.

Page ref titles are free text ("The Path We Follow", "Scout Drone (18\")"), and
using them raw in a cache key made Django emit a CacheKeyWarning on essentially
every request in production.
"""

import warnings

import pytest
from django.core.cache import caches

from n23.content.models import ContentBook, ContentPageRef


@pytest.fixture
def page_ref(db):
    book = ContentBook.objects.create(name="Core Rulebook", shortname="Core")
    return ContentPageRef.objects.create(
        book=book, title="The Path We Follow", page="120", category="Skills"
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    caches["content_page_ref_cache"].clear()
    yield
    caches["content_page_ref_cache"].clear()


@pytest.mark.django_db
def test_titles_with_spaces_do_not_warn(page_ref):
    """The regression: a spacey title used to warn on every lookup."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert list(ContentPageRef.find_similar("The Path We Follow")) == [page_ref]

    cache_warnings = [
        w for w in caught if "CacheKeyWarning" in type(w.message).__name__
    ]
    assert cache_warnings == []


@pytest.mark.django_db
def test_awkward_characters_do_not_warn(page_ref):
    """Titles in production include quotes, brackets and apostrophes."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ContentPageRef.find_similar('Scout Drone (18")')
        ContentPageRef.find_similar("There's Always Another Secret")

    cache_warnings = [
        w for w in caught if "CacheKeyWarning" in type(w.message).__name__
    ]
    assert cache_warnings == []


@pytest.mark.django_db
def test_result_is_cached(page_ref, django_assert_num_queries):
    list(ContentPageRef.find_similar("The Path We Follow"))
    with django_assert_num_queries(0):
        assert list(ContentPageRef.find_similar("The Path We Follow")) == [page_ref]


@pytest.mark.django_db
def test_kwargs_still_separate_the_key(page_ref):
    """
    Hashing must not collapse distinct questions.

    The same title with and without a category filter are two different lookups
    with two different answers.
    """
    assert list(ContentPageRef.find_similar("The Path We Follow")) == [page_ref]
    assert (
        list(ContentPageRef.find_similar("The Path We Follow", category="Nope")) == []
    )
    # And the unfiltered answer is still intact, i.e. the second call did not
    # overwrite the first one's entry.
    assert list(ContentPageRef.find_similar("The Path We Follow")) == [page_ref]


@pytest.mark.django_db
def test_empty_result_is_cached(django_assert_num_queries):
    """Guards the existing sentinel behaviour — a miss must not requery forever."""
    list(ContentPageRef.find_similar("Nothing Matches This"))
    with django_assert_num_queries(0):
        assert list(ContentPageRef.find_similar("Nothing Matches This")) == []
