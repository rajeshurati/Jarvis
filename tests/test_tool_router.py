"""Safe local capability routing tests."""

from pathlib import Path

from jarvis.adapters.files.local_search import LocalFileSearch
from jarvis.adapters.memory.sqlite_store import SQLiteMemoryStore
from jarvis.application.tool_router import JarvisToolRouter
from jarvis.capabilities.automation import ActionResult
from jarvis.capabilities.coding import CodeArtifact
from jarvis.capabilities.developer import DeveloperCommandResult
from jarvis.capabilities.identity import IdentityError, IdentityResult
from jarvis.capabilities.memory import WorkflowRecord
from jarvis.capabilities.productivity import ArtifactResult, EmailSummary
from jarvis.capabilities.research import ResearchError, ResearchReport
from jarvis.capabilities.system import SystemControlError
from jarvis.capabilities.vision import ScreenCaptureError


class StubPlanner:
    def create(self, goal: str) -> WorkflowRecord:
        return WorkflowRecord(9, f"Plan {goal}", "ready", 0, 2, None)


class StubResearch:
    def research(self, query: str) -> ResearchReport:
        return ResearchReport(query, "Finding [1].", Path("research.md"), 3)


class StubSystem:
    def __init__(self) -> None:
        self.settings: list[str] = []
        self.volume: list[str] = []

    def describe(self) -> str:
        return "Windows test system."

    def open_settings(self, section: str) -> None:
        self.settings.append(section)

    def adjust_volume(self, operation: str) -> None:
        self.volume.append(operation)


class FailingResearch(StubResearch):
    def research(self, query: str) -> ResearchReport:
        raise ResearchError("network disabled")


class FailingSystem(StubSystem):
    def describe(self) -> str:
        raise SystemControlError("status failed")

    def open_settings(self, section: str) -> None:
        raise SystemControlError("settings failed")

    def adjust_volume(self, operation: str) -> None:
        raise SystemControlError("volume failed")


class StubDesktop:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def try_execute(self, command: str) -> ActionResult | None:
        self.commands.append(command)
        if command == "open calculator":
            return ActionResult("open_application", "Opening calculator.")
        if command.startswith("open website https://mail.google.com/"):
            return ActionResult("open_website", "Opening Gmail message.")
        return None


class StubScreen:
    def describe(self, request: str) -> str:
        return f"Visible screen for: {request}"


class FailingScreen:
    def describe(self, request: str) -> str:
        raise ScreenCaptureError("interactive desktop unavailable")


class StubDocuments:
    def summarize(self, query: str) -> str:
        return f"Summary of {query}."

    def read_image_text(self, query: str) -> str:
        return f"OCR from {query}."


class StubDesktopInput:
    def __init__(self) -> None:
        self.actions: list[tuple[object, ...]] = []

    def click(self, x: int, y: int) -> None:
        self.actions.append(("click", x, y))

    def type_text(self, text: str) -> None:
        self.actions.append(("type", text))

    def press(self, key: str) -> None:
        self.actions.append(("press", key))


class StubSemanticDesktop:
    def __init__(self) -> None:
        self.actions: list[tuple[str, ...]] = []

    def click_text(self, label: str) -> None:
        self.actions.append(("click_text", label))

    def fill_field(self, label: str, value: str) -> None:
        self.actions.append(("fill_field", label, value))


class StubProductivity:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.actions: list[tuple[object, ...]] = []

    def create_email_draft(self, recipient: str, subject: str, body: str) -> ArtifactResult:
        self.actions.append(("email", recipient, subject, body))
        return ArtifactResult("email draft", self.root / "draft.eml")

    def create_calendar_event(
        self, title: str, starts_at: object, duration_minutes: int
    ) -> ArtifactResult:
        self.actions.append(("event", title, starts_at, duration_minutes))
        return ArtifactResult("calendar event", self.root / "event.ics")

    def create_document(self, kind: str, title: str, content: str) -> ArtifactResult:
        self.actions.append(("document", kind, title, content))
        return ArtifactResult(kind, self.root / "document.md")

    def create_presentation(self, title: str, content: str) -> ArtifactResult:
        self.actions.append(("presentation", title, content))
        return ArtifactResult("presentation", self.root / "slides.pptx")

    def create_spreadsheet(self, title: str, rows: str) -> ArtifactResult:
        self.actions.append(("spreadsheet", title, rows))
        return ArtifactResult("spreadsheet", self.root / "sheet.xlsx")

    def generate_document(self, kind: str, title: str, brief: str) -> ArtifactResult:
        self.actions.append(("generated_document", kind, title, brief))
        return ArtifactResult(kind, self.root / "generated.docx")

    def generate_presentation(self, title: str, brief: str) -> ArtifactResult:
        self.actions.append(("generated_presentation", title, brief))
        return ArtifactResult("presentation", self.root / "generated.pptx")

    def generate_spreadsheet(self, title: str, brief: str) -> ArtifactResult:
        self.actions.append(("generated_spreadsheet", title, brief))
        return ArtifactResult("spreadsheet", self.root / "generated.xlsx")


class StubCode:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requests: list[tuple[str, str, str]] = []

    def generate(self, language: str, title: str, request: str) -> CodeArtifact:
        self.requests.append((language, title, request))
        return CodeArtifact(self.root / "calculator.py", language, True)


class StubDeveloper:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, name: str) -> DeveloperCommandResult:
        self.commands.append(name)
        return DeveloperCommandResult(name, True, "All checks passed.")


class StubEmailGateway:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.sent.append((recipient, subject, body))

    def latest(self, limit: int) -> list[EmailSummary]:
        return [
            EmailSummary("Manager <manager@example.com>", "Status", "Today", "abc123"),
            EmailSummary("Recruiter <jobs@example.com>", "Interview", "Yesterday", "def456"),
            EmailSummary("Bank <alerts@example.com>", "Statement", "Monday", "ghi789"),
            EmailSummary(
                "Roshan <roshan@example.com>", "RTR Rate Confirmation", "Sunday", "roshan1"
            ),
            EmailSummary("Ankit <ankit@example.com>", "Project update", "Saturday", "ankit1"),
        ][:limit]


class StubIdentity:
    def enroll_current(self, name: str) -> IdentityResult:
        return IdentityResult("enrolled", True, name, 1.0, 1)

    def verify_current(self) -> IdentityResult:
        return IdentityResult("authorized", True, "Rajesh", 0.91, 1)

    def delete_profile(self, name: str) -> bool:
        return name == "Rajesh"

    def faces_current(self) -> int:
        return 1


class FailingIdentity(StubIdentity):
    def enroll_current(self, name: str) -> IdentityResult:
        raise IdentityError("no face")

    def verify_current(self) -> IdentityResult:
        raise IdentityError("camera unavailable")

    def faces_current(self) -> int:
        raise IdentityError("camera unavailable")


class StubObjects:
    def describe_current(self) -> str:
        return "I can see 1 person, 1 laptop."


class StubPresence:
    def __init__(self) -> None:
        self.enabled = True

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def summary(self) -> str:
        return "Latest room state is entered, with 1 faces detected."


def build_router(tmp_path: Path) -> JarvisToolRouter:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    return JarvisToolRouter(StubDesktop(), memory, StubScreen(), LocalFileSearch([tmp_path]))


def test_screen_and_memory_commands(tmp_path: Path) -> None:
    router = build_router(tmp_path)
    screen = router.try_execute("what is on my screen?")
    saved = router.try_execute("remember that my editor is VS Code")
    listed = router.try_execute("what do you remember")

    assert screen and screen.action == "understand_screen"
    assert saved and saved.action == "remember"
    assert listed and "editor is VS Code" in listed.message

    pending = router.try_execute("forget memory 1")
    wrong = router.try_execute("confirm forget memory 2")
    deleted = router.try_execute("confirm forget memory 1")
    missing = router.try_execute("forget memory 1")
    assert pending and pending.action == "confirm_forget_memory"
    assert wrong and wrong.action == "confirmation_missing"
    assert deleted and deleted.action == "forget_memory"
    assert missing and missing.action == "memory_not_found"


def test_screen_capture_failure_is_a_spoken_action_error(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    router = JarvisToolRouter(
        StubDesktop(), memory, FailingScreen(), LocalFileSearch([tmp_path])
    )
    result = router.try_execute("what is on my screen")
    assert result and result.action == "screen_capture_error"


def test_empty_memory_and_project_lifecycle(tmp_path: Path) -> None:
    router = build_router(tmp_path)
    assert "do not have" in router.try_execute("show my memory").message  # type: ignore[union-attr]
    assert "do not have" in router.try_execute("show projects").message  # type: ignore[union-attr]

    created = router.try_execute("create project Jarvis with objective Ship local AI")
    listed = router.try_execute("list projects")
    added = router.try_execute("add task Write tests to project Jarvis")
    milestone = router.try_execute("add milestone First release to project Jarvis")
    completed = router.try_execute("mark task 1 as completed")
    briefing = router.try_execute("brief me")
    missing = router.try_execute("add task Write docs to project Unknown")

    assert created and created.action == "create_project"
    assert listed and "Ship local AI" in listed.message
    assert added and added.action == "add_project_task"
    assert milestone and milestone.action == "add_project_note"
    assert completed and completed.action == "update_project_task"
    assert briefing and briefing.action == "briefing"
    assert missing and missing.action == "project_not_found"


def test_file_search_and_desktop_fallback(tmp_path: Path) -> None:
    (tmp_path / "Quarterly Report.docx").write_text("private", encoding="utf-8")
    router = build_router(tmp_path)

    found = router.try_execute("find file quarterly report")
    absent = router.try_execute("find file missing item")
    desktop = router.try_execute("open calculator")

    assert found and "Quarterly Report.docx" in found.message
    assert absent and "no files" in absent.message
    assert desktop and desktop.action == "open_application"
    assert router.try_execute("unknown command") is None


def test_document_summary_and_image_ocr_commands(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        documents=StubDocuments(),
    )

    summary = router.try_execute("summarize document quarterly report")
    ocr = router.try_execute("read text from image receipt")

    assert summary and summary.action == "summarize_document"
    assert ocr and ocr.action == "read_image_text"


def test_desktop_input_requires_explicit_confirmation(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    desktop_input = StubDesktopInput()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        desktop_input=desktop_input,
    )

    pending = router.try_execute("click at 400, 250")
    assert pending and pending.action == "confirm_desktop_action"
    assert desktop_input.actions == []
    completed = router.try_execute("confirm desktop action")
    assert completed and completed.action == "execute_desktop_action"
    assert desktop_input.actions == [("click", 400, 250)]

    router.try_execute("type hello world")
    router.try_execute("cancel desktop action")
    assert router.try_execute("confirm desktop action").action == "confirmation_missing"  # type: ignore[union-attr]


def test_semantic_desktop_actions_are_resolved_only_after_confirmation(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    desktop_input = StubDesktopInput()
    semantic = StubSemanticDesktop()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        desktop_input=desktop_input,
        semantic_desktop=semantic,
    )

    pending = router.try_execute("click button Record and transcribe")
    assert pending and pending.action == "confirm_desktop_action"
    assert semantic.actions == []
    completed = router.try_execute("confirm desktop action")
    assert completed and completed.action == "execute_desktop_action"
    assert semantic.actions == [("click_text", "Record and transcribe")]

    router.try_execute("fill field Email with rajesh@example.com")
    router.try_execute("confirm desktop action")
    assert semantic.actions[-1] == ("fill_field", "Email", "rajesh@example.com")


def test_local_productivity_commands_create_artifacts(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    productivity = StubProductivity(tmp_path)
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        productivity=productivity,
    )

    draft = router.try_execute(
        "draft email to person@example.com with subject Status saying Work is complete"
    )
    event = router.try_execute("schedule event Review on 2026-08-02 at 14:30 for 45 minutes")
    document = router.try_execute(
        "create report titled Weekly Update with content Everything is on track"
    )
    presentation = router.try_execute(
        "create presentation titled Roadmap with content Goal; Milestone; Next step"
    )
    spreadsheet = router.try_execute(
        "create spreadsheet titled Budget with rows Item,Cost;Model,523"
    )

    assert draft and draft.action == "create_local_artifact"
    assert event and event.action == "create_local_artifact"
    assert document and document.action == "create_local_artifact"
    assert presentation and presentation.action == "create_local_artifact"
    assert spreadsheet and spreadsheet.action == "create_local_artifact"
    assert [action[0] for action in productivity.actions] == [
        "email",
        "event",
        "document",
        "presentation",
        "spreadsheet",
    ]


def test_model_generated_artifacts_and_code_are_routed(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    productivity = StubProductivity(tmp_path)
    coding = StubCode(tmp_path)
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        productivity=productivity,
        coding=coding,
    )

    document = router.try_execute(
        "generate report titled Local AI Review about privacy and latency"
    )
    presentation = router.try_execute(
        "create presentation called Roadmap about Jarvis milestones"
    )
    spreadsheet = router.try_execute(
        "create spreadsheet called Readiness tracking Jarvis components"
    )
    code = router.try_execute(
        "generate Python code called calculator to add two numbers"
    )

    assert document and document.action == "generate_local_artifact"
    assert presentation and presentation.action == "generate_local_artifact"
    assert spreadsheet and spreadsheet.action == "generate_local_artifact"
    assert code and code.action == "generate_code" and "validation passed" in code.message
    assert [item[0] for item in productivity.actions] == [
        "generated_document",
        "generated_presentation",
        "generated_spreadsheet",
    ]
    assert coding.requests == [("Python", "calculator", "add two numbers")]


def test_email_send_is_confirmed_and_read_is_bounded(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    gateway = StubEmailGateway()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        email_gateway=gateway,
    )

    pending = router.try_execute(
        "send email to person@example.com with subject Status saying Work is complete"
    )
    assert pending and pending.action == "confirm_email_action"
    assert gateway.sent == []
    sent = router.try_execute("confirm email action")
    assert sent and sent.action == "send_email"
    assert gateway.sent == [("person@example.com", "Status", "Work is complete")]

    read = router.try_execute("read my latest 3 emails")
    assert read and read.action == "read_email" and "Manager" in read.message

    natural_read = router.try_execute("check my mail")
    assert natural_read and natural_read.action == "read_email"
    reply = router.try_execute("reply saying I will finish it today")
    assert reply and reply.action == "confirm_email_action"
    assert gateway.sent == [("person@example.com", "Status", "Work is complete")]
    router.try_execute("confirm email action")
    assert gateway.sent[-1] == (
        "manager@example.com",
        "Re: Status",
        "I will finish it today",
    )


def test_email_reply_requires_recent_mail_context(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    gateway = StubEmailGateway()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        email_gateway=gateway,
    )

    result = router.try_execute("reply to that email saying Thanks")
    assert result and result.action == "email_context_missing"
    assert gateway.sent == []


def test_opens_one_exact_email_by_number_sender_or_subject(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    desktop = StubDesktop()
    router = JarvisToolRouter(
        desktop,
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        email_gateway=StubEmailGateway(),
        gmail_account="i.rajesh1711@gmail.com",
    )

    inbox = router.try_execute("Can you open my Gmail?")
    repeated_inbox = router.try_execute("Open my email. Open my email.")
    listed = router.try_execute("check my meal")
    second = router.try_execute("open the second email")
    duplicate = router.try_execute("open the second email")
    sender = router.try_execute("open the email from manager")
    subject = router.try_execute("open the email about statement")
    named = router.try_execute("open the Roshan mail, open the Roshan mail")
    arbitrary_name = router.try_execute("open the Ankit mail")
    misheard_ordinal = router.try_execute("I am asking you open the fourth middle")
    noisy_third = router.try_execute(
        "Open the third mail, open the third mail, open the third mail, open the third"
    )
    scroll = router.try_execute("Can you scroll down little bit")
    maximize = router.try_execute("make this full screen")

    assert inbox and inbox.action == "open_gmail"
    assert repeated_inbox and repeated_inbox.action == "open_gmail"
    assert inbox.target_url == (
        "https://mail.google.com/mail/?authuser=i.rajesh1711@gmail.com#inbox"
    )
    assert listed and "1. From Manager" in listed.message and "2. From Recruiter" in listed.message
    assert second and second.action == "open_email" and "Recruiter" in second.message
    assert second.target_url == (
        "https://mail.google.com/mail/?authuser=i.rajesh1711@gmail.com#inbox/def456"
    )
    assert duplicate and duplicate.action == "open_email" and duplicate.target_url
    assert sender and sender.action == "open_email" and "Manager" in sender.message
    assert subject and subject.action == "open_email" and "Statement" in subject.message
    assert named and named.action == "open_email" and "Roshan" in named.message
    assert arbitrary_name and arbitrary_name.action == "open_email"
    assert "Ankit" in arbitrary_name.message
    assert misheard_ordinal and misheard_ordinal.action == "open_email"
    assert "Roshan" in misheard_ordinal.message
    assert noisy_third and noisy_third.action == "open_email"
    assert "Bank" in noisy_third.message
    assert scroll and scroll.desktop_action == "scroll_down"
    assert maximize and maximize.desktop_action == "maximize_window"
    assert not [item for item in desktop.commands if "mail.google.com" in item]


def test_email_is_truthfully_unavailable_without_configuration(tmp_path: Path) -> None:
    router = build_router(tmp_path)
    result = router.try_execute(
        "send email to person@example.com with subject Status saying Hello"
    )
    assert result and result.action == "email_unavailable"


def test_room_presence_and_object_commands(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        identity=StubIdentity(),  # type: ignore[arg-type]
        objects=StubObjects(),
        presence=StubPresence(),
    )

    presence = router.try_execute("is anyone in the room")
    objects = router.try_execute("what objects can you see")

    assert presence and presence.action == "room_presence" and "1 person" in presence.message
    assert objects and objects.action == "recognize_objects" and "laptop" in objects.message

    disabled = router.try_execute("stop room monitoring")
    enabled = router.try_execute("start room monitoring")
    activity = router.try_execute("show room activity")
    assert disabled and disabled.action == "disable_presence"
    assert enabled and enabled.action == "enable_presence"
    assert activity and activity.action == "presence_summary"


def test_object_command_reports_missing_local_model(tmp_path: Path) -> None:
    result = build_router(tmp_path).try_execute("describe the webcam")
    assert result and result.action == "objects_unavailable"


def test_file_creation_requires_confirmation(tmp_path: Path) -> None:
    from jarvis.adapters.files.local_manager import LocalFileManager

    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        file_manager=LocalFileManager({"downloads": tmp_path}),
    )

    pending = router.try_execute("create folder Voice Work in downloads")
    assert pending and pending.action == "confirm_file_action"
    assert not (tmp_path / "Voice Work").exists()
    completed = router.try_execute("confirm file action")
    assert completed and completed.action == "execute_file_action"
    assert (tmp_path / "Voice Work").is_dir()


def test_status_is_truthful_and_deterministic(tmp_path: Path) -> None:
    result = build_router(tmp_path).try_execute("what are you doing right now")
    assert result and result.action == "assistant_status"
    assert "listening" in result.message


def test_identity_and_camera_status_are_deterministic(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    presence = StubPresence()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        presence=presence,
    )

    identity = router.try_execute("what is your wake name")
    camera_on = router.try_execute("is my camera on")
    presence.disable()
    camera_off = router.try_execute("is my camera monitoring the room")

    assert identity and identity.message.startswith("My name is Jarvis")
    assert camera_on and "camera is on" in camera_on.message
    assert camera_off and "camera is off" in camera_off.message


def test_allowlisted_developer_command_is_routed(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    developer = StubDeveloper()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        developer=developer,
    )

    result = router.try_execute("lint Jarvis")

    assert result and result.action == "developer_command"
    assert "passed" in result.message
    assert developer.commands == ["jarvis lint"]


def test_planning_research_and_system_tools_are_routed(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    system = StubSystem()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        planner=StubPlanner(),  # type: ignore[arg-type]
        research=StubResearch(),
        system=system,
    )

    plan = router.try_execute("make a plan to code")
    research = router.try_execute("research local AI")
    status = router.try_execute("system status")
    settings = router.try_execute("open sound settings")
    volume = router.try_execute("volume up")

    assert plan and plan.action == "create_plan"
    assert research and research.action == "research" and "3 sources" in research.message
    assert status and status.action == "system_status"
    assert settings and settings.action == "open_system_settings"
    assert volume and volume.action == "adjust_volume"
    assert system.settings == ["sound"]
    assert system.volume == ["up"]


def test_new_tools_report_unavailable_and_runtime_errors(tmp_path: Path) -> None:
    router = build_router(tmp_path)
    assert router.try_execute("make a plan to code").action == "planner_unavailable"  # type: ignore[union-attr]
    assert router.try_execute("research local AI").action == "research_unavailable"  # type: ignore[union-attr]
    assert router.try_execute("system status").action == "system_unavailable"  # type: ignore[union-attr]
    assert router.try_execute("open sound settings").action == "system_unavailable"  # type: ignore[union-attr]
    assert router.try_execute("volume up").action == "system_unavailable"  # type: ignore[union-attr]

    memory = SQLiteMemoryStore(tmp_path / "errors.db")
    memory.initialize()
    failing = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        research=FailingResearch(),
        system=FailingSystem(),
    )
    assert failing.try_execute("research local AI").action == "research_error"  # type: ignore[union-attr]
    assert failing.try_execute("system status").action == "system_error"  # type: ignore[union-attr]
    assert failing.try_execute("open sound settings").action == "system_error"  # type: ignore[union-attr]
    assert failing.try_execute("mute sound").action == "system_error"  # type: ignore[union-attr]


def test_voice_timers_and_reminders_are_persisted(tmp_path: Path) -> None:
    router = build_router(tmp_path)
    timer = router.try_execute("set a timer for 5 minutes")
    reminder = router.try_execute("remind me in 2 hours to call Mom")
    listed = router.try_execute("show reminders")

    assert timer and timer.action == "create_reminder" and "5 minutes" in timer.message
    assert reminder and reminder.action == "create_reminder"
    assert listed and "call Mom" in listed.message


def test_clock_reminder_and_invalid_duration(tmp_path: Path) -> None:
    router = build_router(tmp_path)
    clock = router.try_execute("remind me at 8 am to start work")
    invalid = router.try_execute("set timer for 99999 hours")

    assert clock and clock.action == "create_reminder" and "08:00 AM" in clock.message
    assert invalid and invalid.action == "invalid_reminder"


def test_face_commands_are_local_and_deletion_is_confirmed(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        StubIdentity(),  # type: ignore[arg-type]
    )

    enrolled = router.try_execute("enroll my face")
    verified = router.try_execute("recognize me")
    pending = router.try_execute("delete face profile Rajesh")
    wrong = router.try_execute("confirm delete face profile Other")
    deleted = router.try_execute("confirm delete face profile Rajesh")

    assert enrolled and enrolled.action == "enroll_face"
    assert verified and "0.91" in verified.message
    assert pending and pending.action == "confirm_delete_face"
    assert wrong and wrong.action == "confirmation_missing"
    assert deleted and deleted.action == "delete_face"


def test_face_enrollment_accepts_whisper_variants_and_reports_camera_failure(
    tmp_path: Path,
) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    router = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        StubIdentity(),  # type: ignore[arg-type]
    )
    for phrase in (
        "roll up your face",
        "in roll my face",
        "register my face",
        "scan my face",
    ):
        result = router.try_execute(phrase)
        assert result and result.action == "enroll_face"

    failing = JarvisToolRouter(
        StubDesktop(),
        memory,
        StubScreen(),
        LocalFileSearch([tmp_path]),
        FailingIdentity(),  # type: ignore[arg-type]
    )
    assert failing.try_execute("enroll my face").action == "face_not_visible"  # type: ignore[union-attr]
    assert failing.try_execute("recognize me").action == "face_not_visible"  # type: ignore[union-attr]


def test_face_commands_report_unavailable_without_identity(tmp_path: Path) -> None:
    router = build_router(tmp_path)
    assert router.try_execute("enroll my face").action == "identity_unavailable"  # type: ignore[union-attr]
    assert router.try_execute("recognize me").action == "identity_unavailable"  # type: ignore[union-attr]
