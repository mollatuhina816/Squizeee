"""Shared validation for saved presentation settings and new live sessions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class LiveOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    delivery_mode: Literal['guided', 'self_paced'] = 'self_paced'
    team_mode: bool = False
    streaks: bool = False
    allow_guests: bool = True
