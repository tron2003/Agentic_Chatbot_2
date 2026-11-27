from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from agentic_chatbot.core.settings import get_settings


class Attachment(BaseModel):
    id: str
    name: str


class ChatRequest(BaseModel):
    message: str | None = Field(None, description="User message. Omit when regenerate is true.")
    conversation_id: str | None = Field(
        None,
        validation_alias=AliasChoices("conversation_id", "thread_id"),
        pattern=r"^[A-Za-z0-9_\-:.]{1,100}$",
        description="Existing conversation. Omit to start a new one.",
    )
    regenerate: bool = Field(False, description="Re-answer the latest user message.")
    attachments: list[Attachment] = Field(default_factory=list, max_length=20)
    mode: Literal["auto", "deep_research"] = Field(
        "auto", description="auto lets the router choose; deep_research always writes a researched, cited report."
    )
    project_id: str | None = Field(
        None, pattern=r"^[A-Za-z0-9_\-]{1,64}$",
        description="Start the new conversation in this project. Ignored for existing conversations.",
    )

    @field_validator("message")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        limit = get_settings().max_message_chars
        if len(v) > limit:
            raise ValueError(f"Message is longer than {limit} characters")
        return v

    @model_validator(mode="after")
    def _check(self) -> ChatRequest:
        if self.regenerate:
            if not self.conversation_id:
                raise ValueError("conversation_id is required to regenerate")
        elif not self.message:
            raise ValueError("Message cannot be empty")
        return self


class ApproveRequest(BaseModel):
    """The user's answer to a paused action (the approval card)."""

    conversation_id: str = Field(..., pattern=r"^[A-Za-z0-9_\-:.]{1,100}$")
    message_id: str = Field(..., pattern=r"^[A-Za-z0-9_\-:.]{1,100}$", description="The paused assistant message")
    decisions: dict[str, Literal["approve", "decline"]] = Field(
        ..., description="Tool call ID to approve or decline. Calls left out are declined."
    )
    always_allow: list[str] = Field(
        default_factory=list, max_length=20,
        description="Tool keys (server/tool) to run without asking from now on",
    )


class Source(BaseModel):
    kind: str
    title: str
    url: str | None = None
    page: int | None = None
    snippet: str | None = None
    index: int | None = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ChatResponse(BaseModel):
    conversation_id: str
    title: str | None = None
    message: MessageOut
    # legacy fields for older clients
    response: str
    message_id: str
    timestamp: str


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    last_route: str | None = None  # route of the latest answer (chat | rag | agent), for the home board
    project_id: str | None = None


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Title cannot be empty")
        return v


class DocumentOut(BaseModel):
    id: str
    name: str
    file_type: str
    size_bytes: int
    chunks: int
    created_at: str
    project_id: str | None = None


class ProjectIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    instructions: str = Field("", max_length=8000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Give the project a name")
        return v


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    instructions: str | None = Field(None, max_length=8000)


class ProjectOut(BaseModel):
    id: str
    name: str
    instructions: str = ""
    created_at: str
    updated_at: str
    chat_count: int = 0
    document_count: int = 0


class UploadResult(BaseModel):
    name: str
    status: str  # ok | error
    document: DocumentOut | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]
    documents_added: int
    chunks_added: int


class MemoryOut(BaseModel):
    id: str
    content: str
    category: str = "fact"
    source: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MemoryIn(BaseModel):
    content: str = Field(..., min_length=2, max_length=300)


class MemoryList(BaseModel):
    enabled: bool
    backend: str  # postgres | memory | off
    user_id: str
    items: list[MemoryOut]
