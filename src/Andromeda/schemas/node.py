from sqlmodel import SQLModel
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from Andromeda.models.node import Node, NodeKey


class NodeCreate(SQLModel):
    pass


class NodePublic(SQLModel):
    id: UUID
    created_at: datetime
