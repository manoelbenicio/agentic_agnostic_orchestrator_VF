from __future__ import annotations

from herdmaster.bus.messages import MessageBus, MessageType, new_message
from herdmaster.bus.server import MessageBusServer


def test_task_assigned_enum_alias_matches_task_assign():
    assert MessageType.TASK_ASSIGNED is MessageType.TASK_ASSIGN
    assert MessageType.TASK_ASSIGNED.value == "task_assign"


def test_new_message_accepts_task_assign():
    message = new_message(MessageType.TASK_ASSIGN, "cli", "w4:p2", {"task": "T1"})

    assert message.type is MessageType.TASK_ASSIGN
    assert message.from_agent == "cli"
    assert message.to == "w4:p2"
    assert message.payload == {"task": "T1"}


def test_new_message_accepts_sender_recipient_aliases():
    message = new_message(
        MessageType.TASK_ASSIGNED,
        {"task": "T1"},
        sender="cli",
        recipient="w4:p2",
    )

    assert message.type is MessageType.TASK_ASSIGN
    assert message.from_agent == "cli"
    assert message.to == "w4:p2"
    assert message.payload == {"task": "T1"}


def test_message_bus_alias_points_to_server_class():
    assert MessageBus is MessageBusServer
