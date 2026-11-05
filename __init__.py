"""Privacy Pass — Hermes plugin entrypoint.

Registers:

- ``llm_request`` middleware: sanitizes the complete provider-bound request
  (all messages, history, and Responses API input) with session-stable
  aliases. Fail closed: any error returns a blocked request, because Hermes
  middleware itself is fail-open.
- ``transform_llm_output`` hook: restores aliases in user-facing text.
  Display-side failures are fail-open (a shown alias is not a leak).
- ``/privacy`` command: local status and counts only.
"""

from __future__ import annotations


def register(ctx):
    import sys
    from pathlib import Path

    plugin_dir = str(Path(__file__).resolve().parent)
    if plugin_dir not in sys.path:
        # Hermes does not guarantee the plugin directory is importable when
        # register() runs. Make the vendored core (privacy_pass/) and the
        # adapter modules importable. Additive only: nothing outside this
        # plugin directory is added to sys.path.
        sys.path.insert(0, plugin_dir)

    # Sidecar runtime (python_runtime: external): own venv for presidio/
    # spaCy so the shared hermes environment is never modified. One-time
    # bootstrap on first registration.
    import bootstrap

    bootstrap.wire_sys_path()

    from privacy_pass.engine import AdapterState
    from privacy_pass.policy import Policy
    from privacy_pass.storage import SessionStore

    import commands
    import hooks
    import middleware

    # User configuration (plugins.entries.privacy-pass.settings.*; config
    # changes take effect after a plugin reload).
    cfg = {}
    try:
        cfg = dict(ctx.get_config() or {})
    except Exception:
        cfg = {}

    def _terms(key) -> tuple[str, ...]:
        value = cfg.get(key)
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())

    policy = Policy(
        protect_list=_terms("protect_list"),
        skip_list=_terms("skip_list"),
        mode=str(cfg.get("mode") or "personal"),
    )

    # v1 defaults: dates and generalization stay off (policy, not coverage).
    store = SessionStore()
    state = AdapterState(policy, store=store)

    ctx.register_middleware("llm_request", middleware.make_llm_request_handler(state))
    ctx.register_middleware(
        "tool_request", middleware.make_tool_request_handler(state)
    )

    handler = hooks.make_transform_llm_output_handler(state)
    try:  # hold_stream keeps partial (unrestored) chunks from being shown
        ctx.register_hook("transform_llm_output", handler, hold_stream=True)
    except TypeError:
        ctx.register_hook("transform_llm_output", handler)

    # Observer-only: auxiliary side-calls (titling, compression, ...) have no
    # rewrite surface in Hermes; we count them so /privacy can say so.
    ctx.register_hook(
        "pre_auxiliary_call", hooks.make_pre_auxiliary_handler(state)
    )
    ctx.register_hook("pre_tool_call", hooks.make_pre_tool_call_handler(state))
    ctx.register_hook(
        "transform_tool_result", hooks.make_transform_tool_result_handler(state)
    )

    ctx.register_command(
        "privacy",
        commands.make_status_handler(state),
        description="Show Privacy Pass status and counts",
        args_hint="[status]",
    )
