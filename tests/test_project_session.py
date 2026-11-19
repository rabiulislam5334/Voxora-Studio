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


def test_scene_delete_guard_can_block_deletion():
    session = ProjectSession()
    checked = []
    session.add_scene_delete_guard(lambda scene_id: checked.append(scene_id) or False)

    assert session.can_delete_scene("scene-1") is False
    assert checked == ["scene-1"]


def test_scene_delete_guard_exception_fails_closed():
    session = ProjectSession()

    def broken_guard(_scene_id):
        raise RuntimeError("dialog failed")

    session.add_scene_delete_guard(broken_guard)
    assert session.can_delete_scene("scene-1") is False
