from app.projects.session import ProjectSession


def test_session_exposes_one_existing_project_manager():
    session = ProjectSession()
    assert session.manager is not None
    assert session.manager.current_project.name == "Untitled Project"


def test_project_change_guards_can_block_replacement():
    session = ProjectSession()
    allowed = []
    session.add_change_guard(lambda: allowed.append("checked") or False)

    assert session.can_replace_project() is False
    assert allowed == ["checked"]


def test_all_project_change_guards_must_allow_replacement():
    session = ProjectSession()
    session.add_change_guard(lambda: True)
    session.add_change_guard(lambda: False)

    assert session.can_replace_project() is False


def test_guard_exception_fails_closed():
    session = ProjectSession()

    def broken_guard():
        raise RuntimeError("dialog failed")

    session.add_change_guard(broken_guard)
    assert session.can_replace_project() is False
