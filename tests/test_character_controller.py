"""Exercise actual event sequences and task/notification/idle priorities."""
from PySide6.QtTest import QSignalSpy
from grangerpet.character import CharacterController


def test_task_stays_awake_through_idle_and_failed_source_then_finishes():
    character = CharacterController()
    character.life('sleep')
    assert character.snapshot()['state'] == 'sleeping'
    character.handle_event('agent.task.started')
    character.handle_event('agent.tool.started', {'tool': 'web_read'})
    assert character.snapshot()['state'] == 'reading'
    character.life('sleep')
    character.handle_event('agent.tool.failed', {'tool': 'web_read'})
    assert character.snapshot()['state'] == 'thinking'
    assert character.snapshot()['busy']
    character.handle_event('agent.tool.started', {'tool': 'domain_lookup'})
    assert character.snapshot()['state'] == 'searching'
    character.handle_event('agent.tool.completed')
    assert character.snapshot()['state'] == 'thinking'
    character.handle_event('agent.answer.ready')
    assert character.snapshot()['state'] == 'happy'
    assert not character.snapshot()['busy']
    character.terminal_finished()
    assert character.snapshot()['state'] == 'idle'


def test_notification_preserves_work_priority_and_survives_terminal_animation():
    character = CharacterController()
    character.handle_event('agent.task.started')
    character.handle_event('notification.created')
    assert character.snapshot()['state'] == 'thinking'
    assert character.snapshot()['unread']
    character.handle_event('agent.answer.ready')
    character.terminal_finished()
    assert character.snapshot()['state'] == 'notification'
    character.handle_event('notification.read')
    assert character.snapshot()['state'] == 'idle'
    assert not character.snapshot()['unread']


def test_user_return_wakes_idle_character_without_interrupting_task():
    character = CharacterController()
    character.life('reading')
    assert character.snapshot()['state'] == 'reading'
    character.life('sleep')
    character.handle_event('application.user_returned')
    assert character.snapshot()['state'] == 'listening'
    character.handle_event('agent.task.started')
    character.handle_event('chat.message.received')
    character.handle_event('application.user_returned')
    assert character.snapshot()['state'] == 'thinking'
    character.handle_event('agent.task.cancelled')
    assert not character.snapshot()['busy']
    assert character.snapshot()['state'] == 'idle'


def test_unknown_events_do_not_create_states_or_repeated_timer_updates():
    character = CharacterController()
    changes = QSignalSpy(character.changed)
    assert not character.handle_event('shell.execute', {'command': 'ignored'})
    assert not character.handle_event('coding.arbitrary')
    assert changes.count() == 0
    character.handle_event('chat.message.received')
    character.handle_event('chat.message.received')
    assert changes.count() == 1
    character.life('reading')
    character.life('reading')
    assert changes.count() == 2


def test_coding_seam_advertises_missing_art_without_claiming_laptop_animation():
    character = CharacterController()
    character.handle_event('coding.started')
    assert character.snapshot()['busy']
    assert character.snapshot()['animation'] == 'working'
    assert 'coding' in character.snapshot()['missing_assets']
    character.handle_event('coding.failed')
    assert character.snapshot()['state'] == 'error'
    assert not character.snapshot()['busy']
