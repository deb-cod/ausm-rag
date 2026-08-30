from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.container import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_db(request: Request) -> Iterator[Session]:
    container: AppContainer = request.app.state.container
    with container.session_factory() as session:
        yield session
