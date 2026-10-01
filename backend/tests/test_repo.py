from datetime import UTC

from app.db import repo
from app.db.models import Failure, ScopeEvent


def test_recent_turns_order_and_limit(db):
    conv = repo.create_conversation(db)
    for i in range(6):
        repo.add_message(db, conv.id, role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
    assert [m.content for m in repo.recent_turns(db, conv.id, n=10)] == [f"m{i}" for i in range(6)]
    assert [m.content for m in repo.recent_turns(db, conv.id, n=3)] == ["m3", "m4", "m5"]


def test_same_timestamp_still_ordered_by_seq(db):
    conv = repo.create_conversation(db)
    a = repo.add_message(db, conv.id, role="user", content="q")
    b = repo.add_message(db, conv.id, role="assistant", content="a")
    b.created_at = a.created_at  # force a tie (EC DB-03)
    db.commit()
    assert [m.role for m in repo.list_messages(db, conv.id)] == ["user", "assistant"]


def test_claims_round_trip_keeps_null_source(db):
    conv = repo.create_conversation(db)
    msg = repo.add_message(db, conv.id, role="assistant", content="a", claims=[{"text": "x", "source": None}])
    db.expire_all()
    stored = repo.list_messages(db, conv.id)[0]
    assert stored.id == msg.id
    assert stored.claims == [{"text": "x", "source": None}]


def test_timestamps_are_utc_aware(db):
    conv = repo.create_conversation(db)
    db.expire_all()
    loaded = repo.get_conversation(db, conv.id)
    assert loaded.created_at.tzinfo is not None
    assert loaded.created_at.utcoffset() == UTC.utcoffset(None)


def test_updated_at_changes_on_new_message(db):
    conv = repo.create_conversation(db)
    before = conv.updated_at
    repo.add_message(db, conv.id, role="user", content="hi")
    db.expire_all()
    assert repo.get_conversation(db, conv.id).updated_at >= before


def test_failure_and_scope_event_allow_null_foreign_keys(db):
    f = repo.record_failure(db, type="api_error", error_detail="x", raw_output=None, request_context={"a": 1},
                            conversation_id=None)
    e = repo.record_scope_event(db, conversation_id=None, message_id=None, stage="input",
                                category="weight_target", rule_id="IN-WT-01")
    assert db.get(Failure, f.id).conversation_id is None
    assert db.get(ScopeEvent, e.id).message_id is None


def test_count_user_messages(db):
    conv = repo.create_conversation(db)
    repo.add_message(db, conv.id, role="user", content="1")
    repo.add_message(db, conv.id, role="assistant", content="2")
    repo.add_message(db, conv.id, role="user", content="3")
    assert repo.count_user_messages(db, conv.id) == 2
