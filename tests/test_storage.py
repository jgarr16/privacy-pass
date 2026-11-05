"""Session persistence: restart continuity, isolation, permissions, purge."""

from privacy_pass.engine import AdapterState
from privacy_pass.policy import Policy
from privacy_pass.storage import SessionStore

NAME = "Jane Doe"
OTHER = "John Smith"


def make_store(tmp_path) -> SessionStore:
    return SessionStore(root=tmp_path / "sessions")


def test_restart_continuity(tmp_path):
    store = make_store(tmp_path)
    first = AdapterState(Policy(protect_list=(NAME,)), store=store)
    first.session("s1").sanitize_request(f"{NAME} will attend.")
    alias_before = first.session("s1").sanitize_request(f"{NAME} again.").sanitized_text

    # Fresh process state: same store, same session id.
    second = AdapterState(Policy(protect_list=(NAME,)), store=store)
    alias_after = second.session("s1").sanitize_request(f"{NAME} again.").sanitized_text
    assert alias_before == alias_after
    restored = second.restore("s1", alias_after)
    assert NAME in restored


def test_sessions_isolated_on_disk(tmp_path):
    store = make_store(tmp_path)
    state = AdapterState(Policy(protect_list=(NAME, OTHER)), store=store)
    a = state.session("alice").sanitize_request(f"{NAME} called.")
    b = state.session("bob").sanitize_request(f"{OTHER} called.")
    # Alias text may coincide (<Protected 1> in each); isolation means the
    # mappings never cross between sessions.
    assert state.restore("alice", a.sanitized_text) == f"{NAME} called."
    assert state.restore("bob", b.sanitized_text) == f"{OTHER} called."
    assert "John Smith" not in state.restore("alice", a.sanitized_text)
    assert "Jane Doe" not in state.restore("bob", b.sanitized_text)
    assert len(list(store.root.glob("*.json"))) == 2  # separate files on disk


def test_store_permissions_owner_only(tmp_path):
    import os
    import stat

    store = make_store(tmp_path)
    state = AdapterState(Policy(protect_list=(NAME,)), store=store)
    state.session("s1").sanitize_request(f"{NAME} called.")
    files = list(store.root.glob("*.json"))
    assert len(files) == 1
    assert stat.S_IMODE(os.stat(files[0]).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(store.root).st_mode) == 0o700


def test_snapshot_roundtrip(tmp_path):
    store = make_store(tmp_path)
    state = AdapterState(Policy(protect_list=(NAME,)), store=store)
    engine = state.session("s1")
    result = engine.sanitize_request(f"{NAME} called.")
    snap = engine.snapshot()

    fresh = AdapterState(Policy(protect_list=(NAME,)), store=store)
    new_engine = fresh.session("s2")
    new_engine.load_snapshot(snap)
    assert new_engine.sanitize_request(f"{NAME} again.").sanitized_text == (
        result.sanitized_text.split(" called.")[0] + " again."
    )


def test_purge(tmp_path):
    store = make_store(tmp_path)
    state = AdapterState(Policy(protect_list=(NAME,)), store=store)
    state.session("s1").sanitize_request(f"{NAME} called.")
    assert store.purge(max_age_days=1) == 0  # too recent
    assert store.purge() == 1
    assert store.purge() == 0


def test_corrupt_file_tolerated(tmp_path):
    store = make_store(tmp_path)
    store.root.mkdir(parents=True)
    store.path_for("s1").write_text("not json{", encoding="utf-8")
    state = AdapterState(Policy(protect_list=(NAME,)), store=store)
    result = state.session("s1").sanitize_request(f"{NAME} called.")
    assert "<Protected" in result.sanitized_text  # fresh start, no crash
