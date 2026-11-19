"""
test_auth_and_preferences.py - Unit tests for CineStream Authentication and Preferences
"""
import pytest
import uuid
from ml.auth_db import (
    create_user, get_user_by_id, verify_user,
    get_user_preferences, update_user_preferences,
    record_user_rating, get_user_ratings,
    migrate_anonymous_data, delete_user_account
)
from ml.watchlist_db import add_to_watchlist, get_watchlist

def test_user_creation_and_auth():
    test_uname = f"test_{uuid.uuid4().hex[:8]}"
    test_pwd = "SecretPassword123"

    # Create user
    user = create_user(test_uname, test_pwd, display_name="Test Cinephile")
    assert user is not None
    assert user.username == test_uname
    assert user.display_name == "Test Cinephile"

    # Duplicate username should raise ValueError
    with pytest.raises(ValueError):
        create_user(test_uname, "otherpassword")

    # Verify user credentials
    verified = verify_user(test_uname, test_pwd)
    assert verified is not None
    assert verified.id == user.id

    # Wrong password fails
    wrong = verify_user(test_uname, "wrongpassword")
    assert wrong is None

    # Cleanup
    delete_user_account(user.id)

def test_user_preferences():
    test_uname = f"prefs_{uuid.uuid4().hex[:8]}"
    user = create_user(test_uname, "Password123!")

    # Default preferences
    prefs = get_user_preferences(user.id)
    assert prefs["avatar"] == "avatar-1"

    # Update preferences
    new_prefs = {
        "display_name": "Cinema King",
        "avatar": "avatar-3",
        "favorite_genres": ["Action", "Sci-Fi"],
        "preferred_languages": ["en", "kn"],
        "preferred_audio_lang": "kn",
        "favorite_tabs": ["all", "movies"],
        "adult_content": 0
    }
    updated = update_user_preferences(user.id, new_prefs)
    assert updated is True

    # Retrieve and verify
    saved_prefs = get_user_preferences(user.id)
    assert saved_prefs["display_name"] == "Cinema King"
    assert saved_prefs["avatar"] == "avatar-3"
    assert "Action" in saved_prefs["favorite_genres"]
    assert "kn" in saved_prefs["preferred_languages"]

    # Cleanup
    delete_user_account(user.id)

def test_anonymous_migration():
    anon_uid = f"anon_{uuid.uuid4().hex[:8]}"
    user_uname = f"mig_{uuid.uuid4().hex[:8]}"
    user = create_user(user_uname, "Password123!")

    # Add items to anonymous watchlist & ratings
    add_to_watchlist(anon_uid, 550, "movie")
    add_to_watchlist(anon_uid, 680, "movie")
    record_user_rating(anon_uid, 550, 4.5)

    anon_items = get_watchlist(anon_uid)
    assert len(anon_items) == 2

    # Migrate data
    migrated_count = migrate_anonymous_data(anon_uid, user.id)
    assert migrated_count >= 2

    # Verify anonymous items are cleaned up
    assert len(get_watchlist(anon_uid)) == 0

    # Verify user now has the items
    user_items = get_watchlist(user.id)
    assert len(user_items) == 2
    tmdb_ids = {item["tmdb_id"] for item in user_items}
    assert 550 in tmdb_ids
    assert 680 in tmdb_ids

    # Cleanup
    delete_user_account(user.id)
