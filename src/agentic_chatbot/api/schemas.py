from __future__ import annotations

from typing import Any

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


class UploadResult(BaseModel):
    name: str
    status: str  # ok | error
    document: DocumentOut | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]
    documents_added: int
    chunks_added: int
