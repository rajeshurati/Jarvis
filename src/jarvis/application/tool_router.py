"""Deterministic router for safe local Jarvis capabilities."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from jarvis.application.identity_service import FaceAuthorizationService
from jarvis.application.planner_service import LocalPlannerService
from jarvis.capabilities.automation import (
    ActionResult,
    DesktopAutomation,
    DesktopInput,
    DesktopInputError,
    ScreenControlError,
    SemanticDesktopControl,
)
from jarvis.capabilities.coding import CodeGenerationError, CodeTools
from jarvis.capabilities.developer import DeveloperCommandError, DeveloperTools
from jarvis.capabilities.documents import DocumentError
from jarvis.capabilities.files import FileManager, FileOperationError, FileSearch
from jarvis.capabilities.identity import IdentityError, SpeakerResult
from jarvis.capabilities.memory import MemoryStore, WorkflowRecord
from jarvis.capabilities.productivity import (
    EmailGateway,
    EmailSummary,
    ProductivityError,
    ProductivityTools,
)
from jarvis.capabilities.research import ResearchError, ResearchTools
from jarvis.capabilities.system import SystemControlError, SystemController
from jarvis.capabilities.vision import ScreenCaptureError


class ScreenUnderstanding(Protocol):
    """Small structural contract used by the router."""

    def describe(self, request: str) -> str:
        """Describe the current screen."""
        ...


class DocumentUnderstanding(Protocol):
    """Local document operations exposed to deterministic voice routing."""

    def summarize(self, query: str) -> str:
        """Summarize one approved local document."""
        ...

    def read_image_text(self, query: str) -> str:
        """Extract text from one approved local image."""
        ...


class ObjectUnderstanding(Protocol):
    """Transient local webcam object recognition."""

    def describe_current(self) -> str:
        """Return a concise description of currently detected objects."""
        ...


class RoomPresence(Protocol):
    """Continuous local room-occupancy coordination."""

    @property
    def enabled(self) -> bool: ...

    def enable(self) -> None: ...
    def disable(self) -> None: ...
    def summary(self) -> str: ...


class SpeakerRecognition(Protocol):
    """Local voiceprint enrollment and recognition."""

    def enroll_current(self, name: str) -> SpeakerResult: ...
    def verify_current(self) -> SpeakerResult: ...
    def delete_profile(self, name: str) -> bool: ...


class WorkflowCoordinator(Protocol):
    """Durable workflow operations consumed by the voice router."""

    def create(self, name: str, commands: list[str]) -> WorkflowRecord: ...
    def list(self) -> list[WorkflowRecord]: ...
    def run(self, workflow_id: int) -> ActionResult: ...
    def cancel(self, workflow_id: int) -> ActionResult: ...
    def confirmation_completed(self) -> ActionResult | None: ...


class JarvisToolRouter:
    """Recognize explicit safe commands before consulting the language model."""

    _screen_phrases = (
        "what is on my screen",
        "what's on my screen",
        "read my screen",
        "summarize my screen",
        "describe my screen",
        "can you see my screen",
        "look at my screen",
    )
    _face_enrollment_terms = (
        "enroll",
        "in roll",
        "roll up",
        "rolling up",
        "register",
        "scan",
        "add",
        "save",
    )

    def __init__(
        self,
        desktop: DesktopAutomation,
        memory: MemoryStore,
        screen: ScreenUnderstanding,
        files: FileSearch,
        identity: FaceAuthorizationService | None = None,
        documents: DocumentUnderstanding | None = None,
        desktop_input: DesktopInput | None = None,
        file_manager: FileManager | None = None,
        workflows: WorkflowCoordinator | None = None,
        semantic_desktop: SemanticDesktopControl | None = None,
        productivity: ProductivityTools | None = None,
        email_gateway: EmailGateway | None = None,
        objects: ObjectUnderstanding | None = None,
        presence: RoomPresence | None = None,
        speaker: SpeakerRecognition | None = None,
        planner: LocalPlannerService | None = None,
        research: ResearchTools | None = None,
        system: SystemController | None = None,
        coding: CodeTools | None = None,
        developer: DeveloperTools | None = None,
        gmail_account: str | None = None,
    ) -> None:
        self._desktop = desktop
        self._memory = memory
        self._screen = screen
        self._files = files
        self._identity = identity
        self._documents = documents
        self._desktop_input = desktop_input
        self._pending_desktop: tuple[str, ...] | None = None
        self._file_manager = file_manager
        self._pending_file: tuple[str, ...] | None = None
        self._workflows = workflows
        self._semantic_desktop = semantic_desktop
        self._productivity = productivity
        self._email_gateway = email_gateway
        self._pending_email: tuple[str, str, str] | None = None
        self._last_email: tuple[str, str] | None = None
        self._recent_emails: list[EmailSummary] = []
        self._last_opened_email_id: str | None = None
        self._objects = objects
        self._presence = presence
        self._speaker = speaker
        self._planner = planner
        self._research = research
        self._system = system
        self._coding = coding
        self._developer = developer
        self._gmail_account = gmail_account
        self._pending_speaker_delete: str | None = None
        self._pending_forget: int | None = None
        self._pending_face_delete: str | None = None

    def try_execute(self, command: str) -> ActionResult | None:
        """Execute recognized read-only or reversible local commands."""
        normalized = re.sub(r"\s+", " ", command.strip()).rstrip(".!?")
        normalized = re.sub(r"^jarvis[\s,:-]+", "", normalized, flags=re.I)
        repeated_parts = [
            part.strip(" .")
            for part in re.split(r"\s*(?:,|;|\.\s+)\s*", normalized)
            if part.strip(" .")
        ]
        if len(repeated_parts) > 1 and len({part.casefold() for part in repeated_parts}) == 1:
            normalized = repeated_parts[0]
        normalized = re.sub(
            r"^(?:(?:can|could|would) you|please|i am asking you(?: to)?|"
            r"i'm asking you(?: to)?)\s+(?=open\b)",
            "",
            normalized,
            flags=re.I,
        )
        if re.match(r"open\b", normalized, re.I):
            normalized = re.sub(r"\bfalse screen\b", "full screen", normalized, flags=re.I)
            normalized = re.sub(
                r"\b(?:force to me|fourth middle|forth middle|fourth meal|forth meal)\b",
                "fourth mail",
                normalized,
                flags=re.I,
            )
        lowered = normalized.casefold()
        if lowered in {
            "what is your name",
            "what's your name",
            "what is your wake name",
            "who are you",
        }:
            return ActionResult(
                "assistant_identity",
                "My name is Jarvis. Say Hey Jarvis whenever you need me.",
            )
        gmail_open = re.fullmatch(
            r"(?:(?:can|could|would) you )?(?:please )?open "
            r"(?:my )?(?:gmail|g mail|email|e mail|d mail|mail|inbox)(?: account)?",
            lowered.replace("-", " "),
        )
        if gmail_open:
            account = quote(self._gmail_account or "", safe="@")
            account_query = f"?authuser={account}" if account else ""
            return ActionResult(
                "open_gmail",
                "Opening your Gmail inbox.",
                f"https://mail.google.com/mail/{account_query}#inbox",
            )
        account = quote(self._gmail_account or "", safe="@")
        account_query = f"?authuser={account}" if account else ""
        if lowered in {
            "go back to inbox",
            "back to inbox",
            "come to inbox",
            "return to inbox",
            "open inbox",
            "show inbox",
            "go to inbox",
        }:
            return ActionResult(
                "open_gmail_inbox",
                "Returning to your Gmail inbox.",
                f"https://mail.google.com/mail/{account_query}#inbox",
            )
        if lowered in {"go back", "back", "previous page", "return to previous page"}:
            return ActionResult(
                "open_gmail_inbox",
                "Returning to your Gmail inbox.",
                f"https://mail.google.com/mail/{account_query}#inbox",
            )
        category = re.fullmatch(
            r"(?:open|go to|show|switch to) (?:the )?"
            r"(primary|promotions|social|updates|forums)(?: (?:folder|category|tab))?",
            lowered,
        )
        if category:
            name = category.group(1)
            fragment = "inbox" if name == "primary" else f"category/{name}"
            return ActionResult(
                "open_gmail_category",
                f"Opening the {name} Gmail category.",
                f"https://mail.google.com/mail/{account_query}#{fragment}",
            )
        if lowered in {
            "open it",
            "show it",
            "preview it",
            "open and show it",
            "review it",
        } and self._last_opened_email_id:
            return ActionResult(
                "open_email",
                "Opening and showing that email.",
                f"https://mail.google.com/mail/{account_query}"
                f"#inbox/{self._last_opened_email_id}",
            )
        scroll = re.search(
            r"(?:can you |please )?scroll (up|down)(?: (?:a )?little(?: bit)?)?",
            lowered,
        )
        if scroll:
            direction = scroll.group(1)
            return ActionResult(
                f"scroll_{direction}",
                f"Scrolling {direction}.",
                desktop_action=f"scroll_{direction}",
            )
        if lowered in {
            "maximize this window",
            "maximize the window",
            "make this full screen",
            "open full screen",
            "full screen",
        }:
            return ActionResult(
                "maximize_window",
                "Maximizing the current window.",
                desktop_action="maximize_window",
            )
        if lowered in {"minimize this window", "minimize the window", "minimize window"}:
            return ActionResult(
                "minimize_window",
                "Minimizing the current window.",
                desktop_action="minimize_window",
            )
        if lowered in {"close this tab", "close the current tab", "close current tab"}:
            return ActionResult(
                "close_tab",
                "Closing the current tab.",
                desktop_action="close_tab",
            )
        if lowered in {
            "is room monitoring active",
            "is the room monitoring active",
            "is my camera monitoring the room",
            "is the camera monitoring the room",
            "is my camera on",
            "is the camera on",
        }:
            enabled = bool(self._presence and self._presence.enabled)
            state = "active, so the camera is on" if enabled else "paused, so the camera is off"
            return ActionResult("presence_status", f"Room monitoring is {state}.")
        developer_commands = {
            "run jarvis tests": "jarvis tests",
            "test jarvis": "jarvis tests",
            "lint jarvis": "jarvis lint",
            "check jarvis types": "jarvis type check",
            "show python version": "python version",
            "show git version": "git version",
            "show docker version": "docker version",
            "show kubectl version": "kubectl version",
            "show terraform version": "terraform version",
        }
        if lowered in developer_commands:
            if self._developer is None:
                return ActionResult(
                    "developer_tools_unavailable", "Developer command tools are unavailable."
                )
            try:
                developer_result = self._developer.run(developer_commands[lowered])
            except DeveloperCommandError as error:
                return ActionResult("developer_command_error", str(error))
            outcome = "passed" if developer_result.succeeded else "failed"
            return ActionResult(
                "developer_command",
                f"{developer_result.name.title()} {outcome}. {developer_result.summary}",
            )
        code_request = re.fullmatch(
            r"(?:generate|write|create) (python|javascript|typescript|java|go|rust|"
            r"c sharp|c#|c plus plus|c\+\+|sql|powershell|bash|terraform|yaml|"
            r"github actions|json) "
            r"code (?:called|named) (.+?) (?:that|to|for) (.+)",
            normalized,
            re.I,
        )
        if code_request:
            if self._coding is None:
                return ActionResult("coding_unavailable", "Local code generation is unavailable.")
            try:
                code_artifact = self._coding.generate(
                    code_request.group(1), code_request.group(2), code_request.group(3)
                )
            except CodeGenerationError as error:
                return ActionResult("code_generation_error", str(error))
            validation = (
                " Syntax validation passed."
                if code_artifact.syntax_valid is True
                else " It was saved without execution."
            )
            return ActionResult(
                "generate_code", f"Created {code_artifact.path.name}.{validation}"
            )
        if lowered == "cancel desktop action":
            self._pending_desktop = None
            return ActionResult("cancel_desktop_action", "Desktop action cancelled.")
        if lowered == "confirm desktop action":
            if self._pending_desktop is None or self._desktop_input is None:
                return ActionResult("confirmation_missing", "No desktop action is pending.")
            pending, self._pending_desktop = self._pending_desktop, None
            try:
                if pending[0] == "click":
                    self._desktop_input.click(int(pending[1]), int(pending[2]))
                elif pending[0] == "type":
                    self._desktop_input.type_text(pending[1])
                elif pending[0] == "press":
                    self._desktop_input.press(pending[1])
                elif pending[0] == "click_text" and self._semantic_desktop is not None:
                    self._semantic_desktop.click_text(pending[1])
                elif pending[0] == "fill_field" and self._semantic_desktop is not None:
                    self._semantic_desktop.fill_field(pending[1], pending[2])
                else:
                    return ActionResult(
                        "desktop_input_unavailable", "Semantic desktop control is unavailable."
                    )
            except (DesktopInputError, ScreenControlError) as error:
                return ActionResult("desktop_input_error", str(error))
            resumed = self._workflows.confirmation_completed() if self._workflows else None
            message = "Desktop action completed."
            if resumed is not None:
                message = f"{message} {resumed.message}"
            return ActionResult("execute_desktop_action", message)

        if lowered == "cancel email action":
            self._pending_email = None
            return ActionResult("cancel_email_action", "Email send cancelled.")
        if lowered == "confirm email action":
            if self._pending_email is None or self._email_gateway is None:
                return ActionResult("confirmation_missing", "No email send is pending.")
            recipient, subject, body = self._pending_email
            self._pending_email = None
            try:
                self._email_gateway.send(recipient, subject, body)
            except ProductivityError as error:
                return ActionResult("email_error", str(error))
            resumed = self._workflows.confirmation_completed() if self._workflows else None
            message = f"Email sent to {recipient}."
            if resumed is not None:
                message = f"{message} {resumed.message}"
            return ActionResult("send_email", message)

        semantic_click = re.fullmatch(
            r"click (?:the )?(?:button|text|label) (.+)", normalized, re.I
        )
        field_fill = re.fullmatch(r"fill (?:the )?(?:field|box) (.+?) with (.+)", normalized, re.I)
        if semantic_click or field_fill:
            if self._desktop_input is None or self._semantic_desktop is None:
                return ActionResult(
                    "desktop_input_unavailable", "Semantic desktop control is unavailable."
                )
            if semantic_click:
                label = semantic_click.group(1).strip()
                self._pending_desktop = ("click_text", label)
                description = f'find and click visible text "{label}"'
            else:
                if field_fill is None:  # pragma: no cover - narrowed above
                    return None
                label, value = field_fill.group(1).strip(), field_fill.group(2)[:500]
                self._pending_desktop = ("fill_field", label, value)
                description = f'fill the visible field "{label}"'
            return ActionResult(
                "confirm_desktop_action",
                f"Ready to {description}. Say confirm desktop action or cancel desktop action.",
            )

        click_match = re.fullmatch(r"click (?:at )?(\d{1,5})[ ,]+(\d{1,5})", lowered)
        type_match = re.fullmatch(r"type (?:the text )?(.+)", normalized, re.I)
        key_match = re.fullmatch(
            r"press (enter|tab|escape|backspace|delete|up|down|left|right|home|end|"
            r"pageup|pagedown|space)",
            lowered,
        )
        if click_match or type_match or key_match:
            if self._desktop_input is None:
                return ActionResult("desktop_input_unavailable", "Desktop input is unavailable.")
            if click_match:
                self._pending_desktop = ("click", click_match.group(1), click_match.group(2))
                description = f"click at {click_match.group(1)}, {click_match.group(2)}"
            elif type_match:
                self._pending_desktop = ("type", type_match.group(1)[:500])
                description = "type into the focused control"
            else:
                if key_match is None:  # pragma: no cover - narrowed above
                    return None
                self._pending_desktop = ("press", key_match.group(1))
                description = f"press {key_match.group(1)}"
            return ActionResult(
                "confirm_desktop_action",
                f"Ready to {description}. Say confirm desktop action or cancel desktop action.",
            )
        if lowered == "cancel file action":
            self._pending_file = None
            return ActionResult("cancel_file_action", "File action cancelled.")
        if lowered == "confirm file action":
            if self._pending_file is None or self._file_manager is None:
                return ActionResult("confirmation_missing", "No file action is pending.")
            pending, self._pending_file = self._pending_file, None
            try:
                if pending[0] == "mkdir":
                    file_result = self._file_manager.create_folder(pending[1], pending[2])
                elif pending[0] == "write":
                    file_result = self._file_manager.create_text_file(
                        pending[1], pending[2], pending[3]
                    )
                elif pending[0] == "copy":
                    file_result = self._file_manager.copy_to(Path(pending[1]), pending[2])
                elif pending[0] == "move":
                    file_result = self._file_manager.move_to(Path(pending[1]), pending[2])
                else:
                    self._file_manager.recycle(Path(pending[1]))
                    return ActionResult("recycle_item", "The item is in the Recycle Bin.")
            except FileOperationError as error:
                return ActionResult("file_operation_error", str(error))
            resumed = self._workflows.confirmation_completed() if self._workflows else None
            message = f"File action completed: {file_result.name}."
            if resumed is not None:
                message = f"{message} {resumed.message}"
            return ActionResult("execute_file_action", message)

        folder_match = re.fullmatch(
            r"create folder (.+) in (desktop|documents|downloads)", normalized, re.I
        )
        text_file_match = re.fullmatch(
            r"create (?:a )?text file (.+) in (desktop|documents|downloads) "
            r"(?:with content|containing) (.+)",
            normalized,
            re.I,
        )
        transfer_match = re.fullmatch(
            r"(copy|move) (?:file|folder|item) (.+) to (desktop|documents|downloads)",
            normalized,
            re.I,
        )
        recycle_match = re.fullmatch(
            r"(?:recycle|delete) (?:file|folder|item) (.+)", normalized, re.I
        )
        if folder_match or text_file_match or transfer_match or recycle_match:
            if self._file_manager is None:
                return ActionResult("file_manager_unavailable", "File management is unavailable.")
            if folder_match:
                self._pending_file = ("mkdir", folder_match.group(2), folder_match.group(1))
                description = f"create folder {folder_match.group(1)}"
            elif text_file_match:
                self._pending_file = (
                    "write",
                    text_file_match.group(2),
                    text_file_match.group(1),
                    text_file_match.group(3)[:10_000],
                )
                description = f"create text file {text_file_match.group(1)}"
            else:
                match = transfer_match or recycle_match
                if match is None:  # pragma: no cover - narrowed above
                    return None
                query = match.group(2) if transfer_match else match.group(1)
                matches = [path for path in self._files.find(query, 2) if path.exists()]
                if not matches:
                    return ActionResult("file_not_found", f"I could not find {query}.")
                if transfer_match:
                    self._pending_file = (
                        transfer_match.group(1).casefold(),
                        str(matches[0]),
                        transfer_match.group(3),
                    )
                    description = f"{transfer_match.group(1)} {matches[0].name}"
                else:
                    self._pending_file = ("recycle", str(matches[0]))
                    description = f"move {matches[0].name} to the Recycle Bin"
            return ActionResult(
                "confirm_file_action",
                f"Ready to {description}. Say confirm file action or cancel file action.",
            )
        workflow_create = re.fullmatch(r"create workflow (.+?) with steps (.+)", normalized, re.I)
        plan_create = re.fullmatch(
            r"(?:make|create|draft) (?:me )?a plan (?:for|to) (.+)", normalized, re.I
        )
        workflow_run = re.fullmatch(r"(?:run|resume) workflow (\d+)", lowered)
        workflow_cancel = re.fullmatch(r"cancel workflow (\d+)", lowered)
        if plan_create:
            if self._planner is None:
                return ActionResult("planner_unavailable", "Local planning is unavailable.")
            try:
                workflow = self._planner.create(plan_create.group(1))
            except ValueError as error:
                return ActionResult("planner_error", str(error))
            return ActionResult(
                "create_plan",
                f"I saved plan {workflow.id}, {workflow.name}, with "
                f"{workflow.total_steps} steps. Say run workflow {workflow.id} when ready.",
            )
        if workflow_create:
            if self._workflows is None:
                return ActionResult("workflow_unavailable", "Workflows are unavailable.")
            commands = re.split(r"\s+then\s+", workflow_create.group(2), flags=re.I)
            try:
                workflow = self._workflows.create(workflow_create.group(1), commands)
            except ValueError as error:
                return ActionResult("workflow_error", str(error))
            return ActionResult(
                "create_workflow",
                f"Workflow {workflow.id}, {workflow.name}, saved with "
                f"{workflow.total_steps} steps.",
            )
        if workflow_run:
            if self._workflows is None:
                return ActionResult("workflow_unavailable", "Workflows are unavailable.")
            return self._workflows.run(int(workflow_run.group(1)))
        if workflow_cancel:
            if self._workflows is None:
                return ActionResult("workflow_unavailable", "Workflows are unavailable.")
            return self._workflows.cancel(int(workflow_cancel.group(1)))
        if lowered in {"show workflows", "list workflows"}:
            if self._workflows is None:
                return ActionResult("workflow_unavailable", "Workflows are unavailable.")
            workflows = self._workflows.list()[:5]
            if not workflows:
                return ActionResult("list_workflows", "You have no saved workflows.")
            summary = "; ".join(f"{item.id}: {item.name}, {item.status}" for item in workflows)
            return ActionResult("list_workflows", f"Workflows: {summary}.")
        if lowered in {
            "what are you doing",
            "what are you doing right now",
            "what is your status",
            "what's your status",
            "what is happening",
            "what's happening",
        }:
            return ActionResult(
                "assistant_status",
                "I am listening for your voice and ready for your next request.",
            )
        if lowered in {"system status", "computer status", "laptop status"}:
            if self._system is None:
                return ActionResult("system_unavailable", "System status is unavailable.")
            try:
                return ActionResult("system_status", self._system.describe())
            except SystemControlError as error:
                return ActionResult("system_error", str(error))
        settings_match = re.fullmatch(
            r"open (sound|microphone|display|network|bluetooth|power|windows update) settings",
            lowered,
        )
        if settings_match:
            if self._system is None:
                return ActionResult("system_unavailable", "System settings are unavailable.")
            try:
                self._system.open_settings(settings_match.group(1))
            except SystemControlError as error:
                return ActionResult("system_error", str(error))
            return ActionResult(
                "open_system_settings", f"Opening {settings_match.group(1)} settings."
            )
        volume_match = re.fullmatch(
            r"(?:turn |set )?(?:the )?volume (up|down)|(?:mute|unmute)(?: the)? sound",
            lowered,
        )
        if volume_match:
            if self._system is None:
                return ActionResult("system_unavailable", "Volume control is unavailable.")
            operation = volume_match.group(1) or "mute"
            try:
                self._system.adjust_volume(operation)
            except SystemControlError as error:
                return ActionResult("system_error", str(error))
            return ActionResult("adjust_volume", f"Volume {operation}.")
        research_match = re.fullmatch(
            r"(?:research|look up|investigate) (.+)", normalized, re.I
        )
        if research_match:
            if self._research is None:
                return ActionResult("research_unavailable", "Web research is unavailable.")
            try:
                report = self._research.research(research_match.group(1))
            except ResearchError as error:
                return ActionResult("research_error", str(error))
            return ActionResult(
                "research",
                f"Research complete using {report.source_count} sources. "
                f"The cited report is saved as {report.path.name}.",
            )
        if lowered in {
            "how complete are you",
            "how complete is jarvis",
            "what percentage are you complete",
            "what percentage is jarvis complete",
        }:
            return ActionResult(
                "capability_status",
                "The local Jarvis build is feature-complete. Account connections and biometric "
                "enrollment remain inactive until you supply credentials or enroll in person.",
            )

        if lowered in {"brief me", "give me my briefing", "morning briefing"}:
            projects = self._memory.list_projects()[:3]
            reminders = self._memory.list_reminders()[:3]
            parts: list[str] = []
            for project in projects:
                tasks = self._memory.list_project_tasks(project.id)
                pending_tasks = [task for task in tasks if task.status != "completed"]
                notes = self._memory.list_project_notes(project.id)
                risks = [note for note in notes if note.kind == "risk" and note.status == "open"]
                parts.append(
                    f"{project.name}: {len(pending_tasks)} open tasks and "
                    f"{len(risks)} open risks"
                )
            if reminders:
                parts.append(f"{len(reminders)} upcoming reminders")
            message = "; ".join(parts) if parts else "No active projects or reminders"
            return ActionResult("briefing", f"Briefing: {message}.")

        email_draft = re.fullmatch(
            r"draft (?:an )?email to (\S+) with subject (.+?) (?:saying|with body) (.+)",
            normalized,
            re.I,
        )
        calendar_event = re.fullmatch(
            r"(?:schedule|create) (?:an )?event (.+?) on (\d{4}-\d{2}-\d{2}) "
            r"at (\d{1,2}:\d{2}) for (\d{1,4}) minutes?",
            normalized,
            re.I,
        )
        document_create = re.fullmatch(
            r"create (?:a )?(report|resume|cover letter|business document|meeting notes|"
            r"architecture document|design document|technical document) "
            r"(?:called|titled) (.+?) with content (.+)",
            normalized,
            re.I,
        )
        presentation_create = re.fullmatch(
            r"create (?:a )?presentation (?:called|titled) (.+?) with content (.+)",
            normalized,
            re.I,
        )
        spreadsheet_create = re.fullmatch(
            r"create (?:a )?spreadsheet (?:called|titled) (.+?) with rows (.+)",
            normalized,
            re.I,
        )
        document_generate = re.fullmatch(
            r"(?:generate|create|write) (?:a )?(report|resume|cover letter|business document|"
            r"meeting notes|architecture document|design document|technical document) "
            r"(?:called|titled) (.+?) (?:about|for|using) (.+)",
            normalized,
            re.I,
        )
        presentation_generate = re.fullmatch(
            r"(?:generate|create) (?:a )?presentation (?:called|titled) (.+?) "
            r"(?:about|for|using) (.+)",
            normalized,
            re.I,
        )
        spreadsheet_generate = re.fullmatch(
            r"(?:generate|create) (?:a )?spreadsheet (?:called|titled) (.+?) "
            r"(?:about|for|tracking) (.+)",
            normalized,
            re.I,
        )
        email_send = re.fullmatch(
            r"send (?:an )?email to (\S+) with subject (.+?) (?:saying|with body) (.+)",
            normalized,
            re.I,
        )
        email_reply = re.fullmatch(
            r"(?:reply|respond)(?: to (?:the |that )?(?:latest|last)? ?email)? "
            r"(?:saying|with body|with message) (.+)",
            normalized,
            re.I,
        )
        email_read = re.fullmatch(
            r"(?:(?:read|show) my latest(?: (\d{1,2}))? emails?|"
            r"(?:please )?(?:check|read|show)(?: me)? my "
            r"(?:gmail|g mail|email|mail|meal|inbox))",
            lowered,
        )
        email_open_ordinal = re.fullmatch(
            r"open (?:(?:the )?(first|second|third|fourth|fifth|\d{1,2}(?:st|nd|rd|th)?) "
            r"(?:email|mail|male)|(?:email|mail|male) (\d{1,2}))",
            lowered,
        )
        noisy_ordinal = re.search(
            r"\bopen (?:(?:the )?)"
            r"(first|second|third|fourth|fifth|\d{1,2}(?:st|nd|rd|th)?) "
            r"(?:email|mail|male|meal)\b",
            lowered,
        )
        if email_open_ordinal is None:
            email_open_ordinal = noisy_ordinal
        email_open_sender = re.fullmatch(
            r"open (?:the )?(?:email|mail) from (.+)", normalized, re.I
        )
        email_open_subject = re.fullmatch(
            r"open (?:the )?(?:email|mail) (?:about|with subject) (.+)", normalized, re.I
        )
        email_open_named = re.fullmatch(
            r"open (?:the )?(?:email|mail) (?:called|named) (.+)", normalized, re.I
        )
        email_open_name_first = re.fullmatch(
            r"open (?:the )?(.+?) (?:email|mail|meal)", normalized, re.I
        )
        email_open_of = re.fullmatch(
            r"open[ ,]*(?:the )?(?:email|mail) (?:of|from) (.+?)(?: name)?",
            normalized,
            re.I,
        )
        if (
            email_open_ordinal
            or email_open_sender
            or email_open_subject
            or email_open_named
            or email_open_name_first
            or email_open_of
        ):
            if self._email_gateway is None:
                return ActionResult(
                    "email_unavailable",
                    "Email access is disabled until Gmail OAuth is connected.",
                )
            selected: EmailSummary | None = None
            visible_query: str | None = None
            if email_open_ordinal:
                ordinal = email_open_ordinal.group(1) or email_open_ordinal.group(2)
                words = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
                position = words.get(ordinal, int(re.sub(r"\D", "", ordinal) or "0"))
                try:
                    messages = self._email_gateway.latest(max(1, position))
                except ProductivityError as error:
                    return ActionResult("email_error", str(error))
                if 1 <= position <= len(messages):
                    selected = messages[position - 1]
            else:
                match = (
                    email_open_sender
                    or email_open_subject
                    or email_open_named
                    or email_open_name_first
                    or email_open_of
                )
                if match is None:  # pragma: no cover - narrowed by outer condition
                    return None
                visible_query = match.group(1)
                visible_query = re.sub(
                    r"\b(?:email|mail|name)\b$", "", visible_query, flags=re.I
                ).strip(" ,")
                if visible_query.casefold() == "open ai":
                    visible_query = "OpenAI"
                if visible_query.casefold() in {
                    "my",
                    "it",
                    "this",
                    "that",
                    "the",
                    "a",
                    "an",
                } or visible_query.casefold().startswith(
                    ("link ", "visible ", "open ", "email ", "mail ")
                ):
                    return ActionResult(
                        "email_clarification",
                        "Please say the sender name, subject words, or a mail number.",
                    )
                query = visible_query.casefold()
                search = getattr(self._email_gateway, "search", None)
                try:
                    if callable(search):
                        searched = search(visible_query, 1)
                        messages = searched
                        if searched:
                            selected = searched[0]
                    else:
                        messages = self._email_gateway.latest(20)
                except ProductivityError as error:
                    return ActionResult("email_error", str(error))
                if selected is None and (
                    email_open_named or email_open_name_first or email_open_of
                ):
                    selected = next(
                        (
                            item
                            for item in messages
                            if query in item.sender.casefold() or query in item.subject.casefold()
                        ),
                        None,
                    )
                elif selected is None:
                    field = "sender" if email_open_sender else "subject"
                    selected = next(
                        (item for item in messages if query in getattr(item, field).casefold()),
                        None,
                    )
            if selected is None:
                if self._semantic_desktop is not None and visible_query is not None:
                    try:
                        self._semantic_desktop.click_text(visible_query)
                    except ScreenControlError:
                        pass
                    else:
                        return ActionResult(
                            "open_visible_email",
                            f"Opening the visible mail matching {visible_query}.",
                            desktop_action="maximize_window",
                        )
                return ActionResult(
                    "email_not_found",
                    "I could not find that email. Say check my mail to hear the numbered list.",
                )
            if not selected.message_id or not re.fullmatch(r"[A-Za-z0-9_-]+", selected.message_id):
                return ActionResult(
                    "email_open_unavailable",
                    "That mail provider cannot open an exact message in Gmail.",
                )
            self._last_email = (selected.sender, selected.subject)
            self._last_opened_email_id = selected.message_id
            account = quote(self._gmail_account or "", safe="@")
            account_query = f"?authuser={account}" if account else ""
            target_url = (
                f"https://mail.google.com/mail/{account_query}#inbox/{selected.message_id}"
            )
            return ActionResult(
                "open_email",
                f"Opening email from {selected.sender}, {selected.subject}.",
                target_url,
            )
        if lowered.startswith("open ") and any(
            token in lowered
            for token in ("mail", "email", " meal", " middle", " me", "made")
        ):
            return ActionResult(
                "email_clarification",
                "I could not identify that mail. Say the sender name, subject words, "
                "or a number such as open the third mail.",
            )
        if email_reply:
            if self._email_gateway is None:
                return ActionResult(
                    "email_unavailable",
                    "Email sending is disabled until a TLS mail account and "
                    "network access are configured.",
                )
            if self._last_email is None:
                return ActionResult(
                    "email_context_missing",
                    "Check your mail first, then say reply saying followed by your message.",
                )
            sender, original_subject = self._last_email
            recipient = parseaddr(sender)[1]
            if not recipient:
                return ActionResult(
                    "email_context_invalid", "The latest sender has no valid reply address."
                )
            subject = (
                original_subject
                if original_subject.casefold().startswith("re:")
                else f"Re: {original_subject}"
            )
            self._pending_email = (recipient, subject[:200], email_reply.group(1)[:20_000])
            return ActionResult(
                "confirm_email_action",
                f"Ready to reply to {recipient}. "
                "Say confirm email action or cancel email action.",
            )
        if email_send:
            if self._email_gateway is None:
                return ActionResult(
                    "email_unavailable",
                    "Email sending is disabled until a TLS mail account and "
                    "network access are configured.",
                )
            self._pending_email = (
                email_send.group(1),
                email_send.group(2)[:200],
                email_send.group(3)[:20_000],
            )
            return ActionResult(
                "confirm_email_action",
                f"Ready to send email to {email_send.group(1)}. "
                "Say confirm email action or cancel email action.",
            )
        if email_read:
            if self._email_gateway is None:
                return ActionResult(
                    "email_unavailable",
                    "Email reading is disabled until a TLS mail account and "
                    "network access are configured.",
                )
            try:
                messages = self._email_gateway.latest(int(email_read.group(1) or 5))
            except ProductivityError as error:
                return ActionResult("email_error", str(error))
            if not messages:
                return ActionResult("read_email", "The configured inbox has no messages.")
            self._recent_emails = messages
            self._last_email = (messages[0].sender, messages[0].subject)
            summary = "; ".join(
                f"{index}. From {item.sender}, {item.subject}"
                for index, item in enumerate(messages, start=1)
            )
            return ActionResult("read_email", f"Latest emails: {summary}.")
        if any((document_generate, presentation_generate, spreadsheet_generate)):
            if self._productivity is None:
                return ActionResult(
                    "productivity_unavailable", "Local productivity tools are unavailable."
                )
            try:
                if document_generate:
                    artifact = self._productivity.generate_document(
                        document_generate.group(1),
                        document_generate.group(2),
                        document_generate.group(3),
                    )
                elif presentation_generate:
                    artifact = self._productivity.generate_presentation(
                        presentation_generate.group(1), presentation_generate.group(2)
                    )
                else:
                    if spreadsheet_generate is None:  # pragma: no cover - narrowed above
                        return None
                    artifact = self._productivity.generate_spreadsheet(
                        spreadsheet_generate.group(1), spreadsheet_generate.group(2)
                    )
            except (ProductivityError, ValueError) as error:
                return ActionResult("productivity_error", str(error))
            return ActionResult(
                "generate_local_artifact",
                f"Generated local {artifact.kind}: {artifact.path.name}.",
            )
        if any(
            (email_draft, calendar_event, document_create, presentation_create, spreadsheet_create)
        ):
            if self._productivity is None:
                return ActionResult(
                    "productivity_unavailable", "Local productivity tools are unavailable."
                )
            try:
                if email_draft:
                    artifact = self._productivity.create_email_draft(
                        email_draft.group(1), email_draft.group(2), email_draft.group(3)
                    )
                elif calendar_event:
                    starts_at = datetime.strptime(
                        f"{calendar_event.group(2)} {calendar_event.group(3)}", "%Y-%m-%d %H:%M"
                    ).astimezone()
                    artifact = self._productivity.create_calendar_event(
                        calendar_event.group(1), starts_at, int(calendar_event.group(4))
                    )
                elif document_create:
                    artifact = self._productivity.create_document(
                        document_create.group(1),
                        document_create.group(2),
                        document_create.group(3),
                    )
                elif presentation_create:
                    artifact = self._productivity.create_presentation(
                        presentation_create.group(1), presentation_create.group(2)
                    )
                else:
                    if spreadsheet_create is None:  # pragma: no cover - narrowed above
                        return None
                    artifact = self._productivity.create_spreadsheet(
                        spreadsheet_create.group(1), spreadsheet_create.group(2)
                    )
            except (ProductivityError, ValueError) as error:
                return ActionResult("productivity_error", str(error))
            return ActionResult(
                "create_local_artifact",
                f"Created local {artifact.kind}: {artifact.path.name}.",
            )
        face_enrollment_intent = (
            ("face" in lowered or lowered in {"enroll me", "register me"})
            and any(term in lowered for term in self._face_enrollment_terms)
            and not any(term in lowered for term in ("don't", "do not", "cancel", "not enroll"))
        )
        if face_enrollment_intent:
            if self._identity is None:
                return ActionResult("identity_unavailable", "Face authorization is unavailable.")
            try:
                result = self._identity.enroll_current("Rajesh")
            except IdentityError:
                return ActionResult(
                    "face_not_visible",
                    "I could not see exactly one face. "
                    "Face the webcam and say enroll my face again.",
                )
            return ActionResult("enroll_face", f"Face authorization is enabled for {result.name}.")

        if lowered in {"recognize me", "verify my face", "am i authorized", "who am i"}:
            if self._identity is None:
                return ActionResult("identity_unavailable", "Face authorization is unavailable.")
            try:
                result = self._identity.verify_current()
            except IdentityError:
                return ActionResult(
                    "face_not_visible", "I could not get a clear face image from the webcam."
                )
            if result.authorized:
                return ActionResult(
                    "verify_face",
                    f"Authorized as {result.name}, similarity {result.similarity:.2f}.",
                )
            return ActionResult("verify_face", "I could not authorize the current face.")

        if lowered in {
            "is anyone in the room",
            "can you see anyone",
            "is someone here",
            "how many people are here",
        }:
            if self._identity is None:
                return ActionResult("identity_unavailable", "Room presence is unavailable.")
            try:
                faces = self._identity.faces_current()
            except IdentityError:
                return ActionResult("presence_error", "I could not inspect the webcam view.")
            if faces == 0:
                return ActionResult("room_presence", "I do not see anyone in the webcam view.")
            return ActionResult(
                "room_presence", f"I see {faces} {'person' if faces == 1 else 'people'}."
            )

        if lowered in {"start room monitoring", "enable room monitoring"}:
            if self._presence is None:
                return ActionResult("presence_unavailable", "Room monitoring is unavailable.")
            self._presence.enable()
            return ActionResult("enable_presence", "Room monitoring is enabled.")

        if lowered in {"stop room monitoring", "disable room monitoring"}:
            if self._presence is None:
                return ActionResult("presence_unavailable", "Room monitoring is unavailable.")
            self._presence.disable()
            return ActionResult("disable_presence", "Room monitoring is paused.")

        if lowered in {"show room activity", "what was the last room event"}:
            if self._presence is None:
                return ActionResult("presence_unavailable", "Room monitoring is unavailable.")
            return ActionResult("presence_summary", self._presence.summary())

        if lowered in {
            "what objects can you see",
            "what is in front of the camera",
            "describe the webcam",
            "look through the camera",
        }:
            if self._objects is None:
                return ActionResult(
                    "objects_unavailable",
                    "Local object recognition needs YOLO weights installed first.",
                )
            try:
                return ActionResult("recognize_objects", self._objects.describe_current())
            except RuntimeError as error:
                return ActionResult("objects_error", str(error))

        delete_face_match = re.fullmatch(r"delete face profile (.+)", normalized, re.I)
        if delete_face_match:
            name = delete_face_match.group(1).strip()
            self._pending_face_delete = name
            return ActionResult(
                "confirm_delete_face",
                f"This removes biometric authorization for {name}. "
                f"Say confirm delete face profile {name}.",
            )

        confirm_face_match = re.fullmatch(r"confirm delete face profile (.+)", normalized, re.I)
        if confirm_face_match:
            profile_name: str = confirm_face_match.group(1).strip()
            if self._identity is None or self._pending_face_delete != profile_name:
                return ActionResult("confirmation_missing", "That deletion is not pending.")
            self._pending_face_delete = None
            deleted = self._identity.delete_profile(profile_name)
            return ActionResult(
                "delete_face", "Face profile deleted." if deleted else "Face profile not found."
            )

        browser_visibility = any(
            phrase in lowered
            for phrase in (
                "what tabs are open",
                "which tabs are open",
                "what browser tabs",
                "what windows are open",
                "what apps are open",
                "look at this page",
            )
        )
        if (
            browser_visibility
            or any(phrase in lowered for phrase in self._screen_phrases)
            or (
                "screen" in lowered
                and any(word in lowered for word in ("see", "read", "look", "describe", "what"))
            )
        ):
            try:
                description = self._screen.describe(normalized)
            except ScreenCaptureError as error:
                return ActionResult("screen_capture_error", str(error))
            return ActionResult("understand_screen", description)

        confirm_match = re.fullmatch(r"confirm forget memory (\d+)", lowered)
        if confirm_match:
            memory_id = int(confirm_match.group(1))
            if self._pending_forget != memory_id:
                return ActionResult("confirmation_missing", "That memory deletion is not pending.")
            self._pending_forget = None
            deleted = self._memory.forget(memory_id)
            message = "Memory deleted." if deleted else "That memory no longer exists."
            return ActionResult("forget_memory", message)

        forget_match = re.fullmatch(r"forget memory (\d+)", lowered)
        if forget_match:
            memory_id = int(forget_match.group(1))
            exists = any(item.id == memory_id for item in self._memory.list_memories())
            if not exists:
                return ActionResult("memory_not_found", "That memory does not exist.")
            self._pending_forget = memory_id
            return ActionResult(
                "confirm_forget_memory",
                f"This will delete memory {memory_id}. Say confirm forget memory {memory_id}.",
            )

        memory_match = re.fullmatch(r"(?:please )?remember (?:that )?(.+)", normalized, re.I)
        if memory_match:
            fact = memory_match.group(1).strip()
            key = f"note-{datetime.now(UTC):%Y%m%d%H%M%S%f}"
            preference = re.fullmatch(r"my (.+?) is (.+)", fact, re.I)
            if preference:
                key, fact = preference.group(1).strip(), preference.group(2).strip()
            item = self._memory.remember("preference", key, fact)
            return ActionResult("remember", f"I will remember that. Memory {item.id}.")

        if lowered in {"what do you remember", "show my memory", "list my memories"}:
            items = self._memory.list_memories()[:10]
            if not items:
                return ActionResult("list_memory", "I do not have any saved memories yet.")
            summary = "; ".join(f"{item.id}: {item.key} is {item.value}" for item in items)
            return ActionResult("list_memory", f"I remember: {summary}.")

        memory_search = re.fullmatch(r"search (?:my )?memor(?:y|ies) for (.+)", normalized, re.I)
        if memory_search:
            try:
                items = self._memory.search_memories(memory_search.group(1), 5)
            except ValueError as error:
                return ActionResult("memory_search_error", str(error))
            if not items:
                return ActionResult("search_memory", "I found no matching local memories.")
            summary = "; ".join(f"{item.key}: {item.value}" for item in items)
            return ActionResult("search_memory", f"Matching memories: {summary}.")

        reminder_match = re.fullmatch(
            r"remind me in (\d+) (second|minute|hour)s?(?: to)? (.+)", normalized, re.I
        )
        timer_match = re.fullmatch(
            r"set (?:a )?timer for (\d+) (second|minute|hour)s?", normalized, re.I
        )
        if reminder_match or timer_match:
            match = reminder_match or timer_match
            if match is None:  # pragma: no cover - narrowed by the condition above
                return None
            amount = int(match.group(1))
            if amount < 1 or amount > 86_400:
                return ActionResult(
                    "invalid_reminder",
                    "Choose a duration between one second and one day.",
                )
            unit = match.group(2).casefold()
            seconds = amount * {"second": 1, "minute": 60, "hour": 3600}[unit]
            title = reminder_match.group(3).strip() if reminder_match else "Timer finished"
            due = datetime.now(UTC) + timedelta(seconds=seconds)
            reminder = self._memory.create_reminder(title, due.isoformat(timespec="seconds"))
            label = f"{amount} {unit}{'' if amount == 1 else 's'}"
            return ActionResult("create_reminder", f"Reminder {reminder.id} set for {label}.")

        clock_reminder = re.fullmatch(
            r"remind me at (\d{1,2})(?::(\d{2}))?\s*(am|pm)(?: to)? (.+)",
            normalized,
            re.I,
        )
        if clock_reminder:
            hour = int(clock_reminder.group(1))
            minute = int(clock_reminder.group(2) or 0)
            if not 1 <= hour <= 12 or minute > 59:
                return ActionResult("invalid_reminder", "That reminder time is not valid.")
            if clock_reminder.group(3).casefold() == "pm" and hour != 12:
                hour += 12
            elif clock_reminder.group(3).casefold() == "am" and hour == 12:
                hour = 0
            local_now = datetime.now().astimezone()
            due_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if due_local <= local_now:
                due_local += timedelta(days=1)
            reminder = self._memory.create_reminder(
                clock_reminder.group(4).strip(),
                due_local.astimezone(UTC).isoformat(timespec="seconds"),
            )
            return ActionResult(
                "create_reminder",
                f"Reminder {reminder.id} set for {due_local:%I:%M %p}.",
            )

        if lowered in {"show reminders", "list reminders", "what are my reminders"}:
            reminders = self._memory.list_reminders()[:5]
            if not reminders:
                return ActionResult("list_reminders", "You have no pending reminders.")
            summary = "; ".join(f"{item.id}: {item.title}" for item in reminders)
            return ActionResult("list_reminders", f"Pending reminders: {summary}.")

        document_match = re.fullmatch(
            r"summarize (?:the )?(?:document|file) (.+)", normalized, re.I
        )
        if document_match:
            if self._documents is None:
                return ActionResult("documents_unavailable", "Document reading is unavailable.")
            try:
                summary = self._documents.summarize(document_match.group(1).strip())
            except DocumentError as error:
                return ActionResult("document_error", str(error))
            return ActionResult("summarize_document", summary)

        ocr_match = re.fullmatch(
            r"(?:read|extract) (?:the )?text (?:from|in) (?:image|picture) (.+)",
            normalized,
            re.I,
        )
        if ocr_match:
            if self._documents is None:
                return ActionResult("ocr_unavailable", "Local OCR is unavailable.")
            try:
                text = self._documents.read_image_text(ocr_match.group(1).strip())
            except DocumentError as error:
                return ActionResult("ocr_error", str(error))
            return ActionResult("read_image_text", text)

        project_match = re.fullmatch(
            r"create project (.+?)(?: with objective (.+))?", normalized, re.I
        )
        if project_match:
            name = project_match.group(1).strip()
            objective = (project_match.group(2) or name).strip()
            project = self._memory.create_project(name, objective)
            return ActionResult("create_project", f"Project {project.name} is now tracked.")

        if lowered in {"show projects", "list projects", "what are my projects"}:
            projects = self._memory.list_projects()
            if not projects:
                return ActionResult("list_projects", "You do not have any tracked projects yet.")
            summary = "; ".join(f"{item.name}: {item.objective}" for item in projects[:10])
            return ActionResult("list_projects", f"Your projects are: {summary}.")

        task_match = re.fullmatch(r"add task (.+) to project (.+)", normalized, re.I)
        if task_match:
            title, project_name = task_match.group(1).strip(), task_match.group(2).strip()
            selected_project = next(
                (
                    item
                    for item in self._memory.list_projects()
                    if item.name.casefold() == project_name.casefold()
                ),
                None,
            )
            if selected_project is None:
                return ActionResult("project_not_found", f"I cannot find project {project_name}.")
            self._memory.add_project_task(selected_project.id, title)
            return ActionResult("add_project_task", f"Added {title} to {selected_project.name}.")

        task_status = re.fullmatch(
            r"(?:mark|set) task (\d+) (?:as )?(pending|in progress|completed|cancelled)",
            lowered,
        )
        if task_status:
            try:
                task = self._memory.update_project_task(
                    int(task_status.group(1)), task_status.group(2).replace(" ", "_")
                )
            except ValueError as error:
                return ActionResult("project_task_error", str(error))
            return ActionResult(
                "update_project_task", f"Task {task.id} is now {task.status.replace('_', ' ')}."
            )

        project_note = re.fullmatch(
            r"add (milestone|risk|dependency) (.+) to project (.+)", normalized, re.I
        )
        if project_note:
            kind, content, project_name = project_note.groups()
            selected_project = next(
                (
                    item
                    for item in self._memory.list_projects()
                    if item.name.casefold() == project_name.casefold()
                ),
                None,
            )
            if selected_project is None:
                return ActionResult("project_not_found", f"I cannot find project {project_name}.")
            note = self._memory.add_project_note(selected_project.id, kind, content)
            return ActionResult(
                "add_project_note", f"Added {note.kind} to {selected_project.name}."
            )

        file_match = re.fullmatch(
            r"(?:find|search for|look for) (?:a |the )?(?:file )?(?:named )?(.+)",
            normalized,
            re.I,
        )
        if file_match:
            query = file_match.group(1).strip()
            matches = self._files.find(query)
            if not matches:
                return ActionResult("search_files", f"I found no files matching {query}.")
            visible = "; ".join(str(path) for path in matches[:5])
            return ActionResult("search_files", f"I found: {visible}.")

        return self._desktop.try_execute(command)
