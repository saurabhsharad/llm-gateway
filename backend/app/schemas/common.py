"""Shared schema types used across the API.

Keeping small, cross-cutting types here (rather than duplicating them in every
schema file) avoids repetition and gives us one place to change them.
"""

from enum import Enum


class Role(str, Enum):
    """Valid roles for a chat message.

    LLM chat APIs model a conversation as a list of messages, each with a role:
      - system:    high-level instructions that shape the model's behavior
      - user:      input from the human / calling application
      - assistant: the model's previous responses (for multi-turn context)

    Subclassing `str` means each member IS a string (Role.USER == "user"), so it
    serializes cleanly to/from JSON while still giving us a fixed, validated set
    of allowed values. Any other role in a request is rejected automatically.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Provider(str, Enum):
    """The LLM providers the gateway can route to.

    A fixed enum (rather than free-form strings) means a typo like "googel" is a
    programming error caught immediately, and every part of the code refers to
    the same canonical names. Each value gets a provider adapter in Steps 5–7.
    """

    OPENAI = "openai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
